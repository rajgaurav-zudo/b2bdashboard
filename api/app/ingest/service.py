"""Upload pipeline: identify -> archive -> project, with a changelog on every step.

A file is uploaded to a *source*, not to a dashboard. It is read once, archived
once, and then projected into every dashboard that declares that source -- each
into its own schema, through its own ingest module, producing its own load and
its own changelog. Adding a dashboard does not mean uploading the file again,
and one dashboard's projection failing leaves every other dashboard's load
exactly where it was.

Every load is retained. The current load is a flag, not a deletion, so any past
snapshot stays queryable and a bad export can be rolled back by flipping it.
"""
import hashlib
import io
import json
from pathlib import Path

import polars as pl

from .. import registry
from ..config import settings
from ..db import pool
from ..registry import Dashboard, Dataset, Source
from ..storage import storage
from ..views import invalidate as invalidate_views
from .reader import IngestError, apply_spec, normalize_header, read_table

SYSTEM_COLUMNS = ("load_id", "row_hash")


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


_CONTENT_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}


def _store(source_slug: str, sha: str, filename: str, content: bytes) -> str:
    """Keep the original export. Content-addressed and keyed by source rather
    than by dashboard: the file belongs to the CRM, not to whoever reads it."""
    suffix = Path(filename).suffix.lower() or ".csv"
    key = f"sources/{source_slug}/{sha[:16]}{suffix}"
    return storage().put(key, content, _CONTENT_TYPES.get(suffix, "application/octet-stream"))


def _identify(source: Source, frame: pl.DataFrame) -> None:
    """Refuse a file that is not this source.

    An upload no longer names a dashboard, so nothing downstream is in a
    position to notice that the applications export arrived in the introducers
    slot -- it would simply load 227k rows of the wrong shape. The source's own
    declaration is the check, made before anything is stored.
    """
    if not source.identified_by:
        return
    headers = [normalize_header(c) for c in frame.columns]
    absent = [
        want for want in source.identified_by
        if not any(normalize_header(want) in head for head in headers)
    ]
    if absent:
        others = [
            other.display_name for other in registry.sources()
            if other.slug != source.slug and other.identified_by
            and all(any(normalize_header(w) in h for h in headers) for w in other.identified_by)
        ]
        hint = f" This looks like the {others[0]} export." if others else ""
        raise IngestError(
            f"this is not the {source.display_name} file: no column matching "
            + ", ".join(f"'{a}'" for a in absent) + "." + hint
        )


def _ids(cur, dashboard: Dashboard, dataset_slug: str) -> tuple[int, int]:
    cur.execute("select id from core.dashboards where slug = %s", (dashboard.slug,))
    row = cur.fetchone()
    if row is None:
        raise IngestError(f"dashboard '{dashboard.slug}' is not registered; run migrations")
    dash_id = row["id"]
    cur.execute(
        "select id from core.datasets where dashboard_id = %s and slug = %s",
        (dash_id, dataset_slug),
    )
    row = cur.fetchone()
    if row is None:
        raise IngestError(f"dataset '{dataset_slug}' is not registered")
    return dash_id, row["id"]


def _source_id(cur, slug: str) -> int:
    cur.execute("select id from core.sources where slug = %s", (slug,))
    row = cur.fetchone()
    if row is None:
        raise IngestError(f"source '{slug}' is not registered; restart the API to sync sources.yaml")
    return row["id"]


def _copy_frame(cur, table: str, frame: pl.DataFrame) -> None:
    columns = ", ".join(_q(c) for c in frame.columns)
    buffer = io.BytesIO()
    frame.write_csv(buffer)
    buffer.seek(0)
    with cur.copy(f"copy {table} ({columns}) from stdin with (format csv, header true, null '')") as copy:
        while chunk := buffer.read(1 << 20):
            copy.write(chunk)


def _diff(cur, table: str, keys: list[str], new_load: int, old_load: int, limit: int):
    first = _q(keys[0])
    # plain equality: natural-key columns are part of the primary key, so never null.
    # (IS NOT DISTINCT FROM is not hash/merge-joinable, which FULL OUTER JOIN requires.)
    join = " and ".join(f"n.{_q(k)} = o.{_q(k)}" for k in keys)
    key_expr = " || '|' || ".join(f"coalesce(n.{_q(k)}, o.{_q(k)})" for k in keys)
    body = f"""
        from (select * from {table} where load_id = %(new)s) n
        full outer join (select * from {table} where load_id = %(old)s) o on {join}
        where o.{first} is null or n.{first} is null or n.row_hash is distinct from o.row_hash
    """
    change_type = f"""
        case when o.{first} is null then 'added'
             when n.{first} is null then 'removed'
             else 'changed' end
    """
    params = {"new": new_load, "old": old_load, "lim": limit}

    cur.execute(f"select {change_type} as change_type, count(*) as n {body} group by 1", params)
    counts = {r["change_type"]: r["n"] for r in cur.fetchall()}

    cur.execute(
        f"""
        select {change_type} as change_type,
               {key_expr} as natural_key,
               to_jsonb(o) - 'load_id' - 'row_hash' as before,
               to_jsonb(n) - 'load_id' - 'row_hash' as after
        {body}
        order by 1, 2
        limit %(lim)s
        """,
        params,
    )
    return counts, cur.fetchall()


def _changed_fields(before: dict | None, after: dict | None) -> list[str]:
    if not before or not after:
        return []
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def reconcile_interrupted() -> int:
    """Fail uploads and projections left mid-flight by a crash.

    The pipeline marks its own failures, but a hard kill -- OOM on a large file,
    a container restart -- never reaches the handler, and the row sits at
    'parsing' forever while the UI reports it as still running. Nothing is
    in-flight at startup, so anything unfinished is finished, badly.

    Both levels need it: an upload can die while archiving, and a projection can
    die while copying rows, and they are separate rows now precisely because one
    dashboard's failure is not another's.
    """
    interrupted = "interrupted: the server restarted mid-import"
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """update core.uploads set status = 'failed', finished_at = now(),
                      error = coalesce(error, %s)
               where status in ('pending', 'parsing', 'loading', 'diffing')
               returning id""",
            (interrupted,),
        )
        stranded_uploads = [row["id"] for row in cur.fetchall()]

        cur.execute(
            """update core.projections set status = 'failed', finished_at = now(),
                      error = coalesce(error, %s)
               where status in ('pending', 'loading', 'diffing')
               returning id, load_id""",
            (interrupted,),
        )
        stranded = cur.fetchall()

        # A load row can outlive the projection that was writing it if the kill
        # landed between the two. Never touch a current load: the dashboard is
        # still serving from it.
        orphan_loads = [row["load_id"] for row in stranded if row["load_id"]]
        if stranded_uploads or orphan_loads:
            cur.execute(
                """delete from core.loads
                    where not is_current and (upload_id = any(%s) or id = any(%s))""",
                (stranded_uploads, orphan_loads),
            )
        conn.commit()
    return len(stranded_uploads) + len(stranded)


def activate(dashboard: Dashboard, load_id: int, actor: str | None = None) -> dict:
    """Make an existing load the current one again.

    Every load is kept, so rolling back a bad export is a flag flip rather than a
    re-import: the rows never left. The switch is recorded in the changelog so the
    history still explains why the numbers moved.
    """
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select l.id, l.dataset_id, l.dashboard_id, l.row_count, l.is_current,
                      ds.slug as dataset, ds.display_name, u.filename
                 from core.loads l
                 join core.datasets ds on ds.id = l.dataset_id
                 join core.dashboards d on d.id = l.dashboard_id and d.slug = %s
                 join core.uploads u on u.id = l.upload_id
                where l.id = %s""",
            (dashboard.slug, load_id),
        )
        target = cur.fetchone()
        if target is None:
            raise KeyError(f"{dashboard.slug} has no load {load_id}")
        if target["is_current"]:
            return {"load_id": load_id, "changed": False, "summary": "already the current load"}

        cur.execute(
            """update core.loads set is_current = false, superseded_at = now()
               where dashboard_id = %s and dataset_id = %s and is_current
               returning id""",
            (target["dashboard_id"], target["dataset_id"]),
        )
        replaced = cur.fetchone()
        cur.execute(
            "update core.loads set is_current = true, superseded_at = null where id = %s",
            (load_id,),
        )
        summary = (f"{target['display_name']}: rolled back to load {load_id} "
                   f"({target['filename']}, {target['row_count']:,} rows)")
        cur.execute(
            """insert into core.changelog
                 (dashboard_id, dataset_id, entity, summary, load_id, previous_load_id, details)
               values (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
            (target["dashboard_id"], target["dataset_id"], target["dataset"], summary,
             load_id, replaced["id"] if replaced else None,
             json.dumps({"action": "activate", "actor": actor,
                         "replaced_load": replaced["id"] if replaced else None})),
        )
        conn.commit()
        # after the commit: dropping cached views earlier would let a concurrent
        # read repopulate them from the load being replaced
        invalidate_views(dashboard.slug)
        return {"load_id": load_id, "changed": True, "summary": summary,
                "replaced_load": replaced["id"] if replaced else None}


def _project(dash: Dashboard, ds: Dataset, upload_id: int, frame: pl.DataFrame,
             filename: str, sha: str) -> dict:
    """Read one already-parsed file into one dashboard's tables.

    Everything dashboard-specific happens here and nowhere else: its column
    mappings, its typed frame, its schema, its natural key, its changelog. The
    caller hands over a frame and never learns what was done with it, which is
    what keeps two dashboards reading the same file independent of each other.

    Runs in its own transaction. A failure marks this projection failed and
    leaves every other dashboard's load untouched.
    """
    module = dash.module
    table = f"{_q(dash.db_schema)}.{_q(ds.table_name)}"
    load_id = None

    with pool.connection() as conn:
        with conn.cursor() as cur:
            dash_id, ds_id = _ids(cur, dash, ds.slug)
            cur.execute(
                """insert into core.projections (upload_id, dashboard_id, dataset_id, status)
                   values (%s, %s, %s, 'loading')
                   on conflict (upload_id, dataset_id) do update
                     set status = 'loading', error = null, load_id = null,
                         started_at = now(), finished_at = null
                   returning id""",
                (upload_id, dash_id, ds_id),
            )
            projection_id = cur.fetchone()["id"]
        conn.commit()

    try:
        resolution = apply_spec(frame, module.COLUMNS[ds.slug])
        if resolution.missing:
            hint = module.wrong_file_hint(ds.slug, list(frame.columns)) \
                if hasattr(module, "wrong_file_hint") else ""
            raise IngestError(
                "missing required column(s): " + ", ".join(resolution.missing)
                + (f". {hint}" if hint else "")
            )
        prepared: pl.DataFrame = module.finalize(ds.slug, resolution.frame)
        # A file with rows that produces a table with none is a broken mapping,
        # not an empty week. Committing it would mark the projection ready, swap
        # the current flag onto an empty load, and take a working dashboard dark
        # -- with the only symptom a 409 from a view that cannot say why. Fail
        # here instead: the previous load stays current and the reason is on the
        # projection row.
        if prepared.height == 0 and frame.height > 0:
            raise IngestError(
                f"every one of the {frame.height:,} rows was dropped by this "
                f"dashboard's ingest rules, so the load would be empty. The "
                f"previous load is left current. Check the file's column formats "
                f"against {dash.slug}/context.md."
            )
        # Optional, dashboard-owned: counts that only exist before rows are collapsed.
        load_stats = module.stats(ds.slug, resolution.frame, prepared) \
            if hasattr(module, "stats") else {}
        prepared = prepared.with_columns(
            (
                pl.concat_str(
                    [pl.col(c).cast(pl.Utf8).fill_null("\x00") for c in prepared.columns],
                    separator="\x1f",
                ).hash()
                % 4_611_686_018_427_387_904          # keep it inside int8, no overflow on cast
            )
            .cast(pl.Int64)
            .alias("row_hash")
        )

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """insert into core.loads (dashboard_id, dataset_id, upload_id, row_count, stats)
                       values (%s, %s, %s, %s, %s::jsonb) returning id""",
                    (dash_id, ds_id, upload_id, prepared.height, json.dumps(load_stats)),
                )
                load_id = cur.fetchone()["id"]
                _copy_frame(cur, table, prepared.with_columns(pl.lit(load_id).alias("load_id")))

                cur.execute(
                    """select id from core.loads
                       where dashboard_id = %s and dataset_id = %s and is_current""",
                    (dash_id, ds_id),
                )
                current = cur.fetchone()
                previous_load = current["id"] if current else None

                cur.execute("update core.projections set status = 'diffing' where id = %s",
                            (projection_id,))
                if previous_load is None:
                    counts, samples = {"added": prepared.height}, []
                    summary = f"{ds.display_name}: initial load, {prepared.height:,} rows"
                else:
                    counts, samples = _diff(cur, table, ds.natural_key, load_id,
                                            previous_load, settings.changelog_row_limit)
                    bits = [f"+{counts.get('added', 0):,} added",
                            f"{counts.get('changed', 0):,} changed",
                            f"-{counts.get('removed', 0):,} removed"]
                    summary = f"{ds.display_name}: " + " · ".join(bits) + f" ({prepared.height:,} rows)"

                unchanged = prepared.height - counts.get("added", 0) - counts.get("changed", 0)
                cur.execute(
                    """insert into core.changelog
                       (dashboard_id, dataset_id, upload_id, load_id, previous_load_id, entity,
                        rows_added, rows_removed, rows_changed, rows_unchanged, rows_sampled, summary, details)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) returning id""",
                    (dash_id, ds_id, upload_id, load_id, previous_load, ds.slug,
                     counts.get("added", 0), counts.get("removed", 0), counts.get("changed", 0),
                     max(unchanged, 0), len(samples), summary,
                     json.dumps({"sha256": sha, "filename": filename,
                                 "columns_resolved": resolution.mapping,
                                 "row_limit_hit": len(samples) >= settings.changelog_row_limit})),
                )
                changelog_id = cur.fetchone()["id"]

                if samples:
                    with cur.copy(
                        "copy core.changelog_rows (changelog_id, change_type, natural_key, changed_fields, before, after)"
                        " from stdin"
                    ) as copy:
                        for row in samples:
                            copy.write_row((
                                changelog_id, row["change_type"], row["natural_key"],
                                _changed_fields(row["before"], row["after"]),
                                json.dumps(row["before"]) if row["before"] else None,
                                json.dumps(row["after"]) if row["after"] else None,
                            ))

                # swap: previous load stays queryable, it simply stops being current
                cur.execute(
                    """update core.loads set is_current = false, superseded_at = now()
                       where dashboard_id = %s and dataset_id = %s and is_current""",
                    (dash_id, ds_id),
                )
                cur.execute("update core.loads set is_current = true where id = %s", (load_id,))
                cur.execute(
                    """update core.projections
                          set status = 'ready', load_id = %s, row_count = %s, finished_at = now()
                        where id = %s""",
                    (load_id, prepared.height, projection_id),
                )
            conn.commit()
        invalidate_views(dash.slug)

        return {
            "dashboard": dash.slug,
            "dataset": ds.slug,
            "status": "ready",
            "load_id": load_id,
            "rows": prepared.height,
            "added": counts.get("added", 0),
            "removed": counts.get("removed", 0),
            "changed_rows": counts.get("changed", 0),
            "summary": summary,
            "columns_resolved": resolution.mapping,
        }

    except Exception as exc:  # noqa: BLE001
        # Recording the failure must not be able to fail. A dashboard whose
        # migrations have not run has no table to clean up, and letting that
        # second error escape would abandon the projection row at 'loading' and
        # take down the other dashboards' projections with it.
        _abandon(table, load_id, projection_id, str(exc)[:2000])
        return {"dashboard": dash.slug, "dataset": ds.slug, "status": "failed",
                "error": str(exc)[:2000]}


def _abandon(table: str, load_id: int | None, projection_id: int, error: str) -> None:
    """Roll a failed projection back to nothing, and say why on its row."""
    if load_id is not None:
        for statement, params in ((f"delete from {table} where load_id = %s", (load_id,)),
                                  ("delete from core.loads where id = %s", (load_id,))):
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(statement, params)
                    conn.commit()
            except Exception:  # noqa: BLE001, S110
                pass          # the rows are unreachable either way: no load is current
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """update core.projections set status = 'failed', error = %s, finished_at = now()
                        where id = %s""",
                    (error, projection_id),
                )
            conn.commit()
    except Exception:  # noqa: BLE001, S110
        pass              # reconcile_interrupted() will finish it at the next boot


def _fan_out(source_slug: str, upload_id: int, frame: pl.DataFrame, filename: str,
             sha: str, only: str | None = None, force: bool = False) -> list[dict]:
    """Project one file into every dashboard that reads this source.

    Dashboards that already hold this exact file are skipped, so re-uploading it
    after adding a dashboard feeds the new one without disturbing the others.
    `force` re-runs anyway, which is how a fixed ingest.py is applied to a file
    that is already in.

    Each projection is separate and none of them raises: one dashboard's bad
    mapping must not cost the others their load. The failures come back in the
    result and are on core.projections.
    """
    results = []
    for dash, ds in registry.consumers(source_slug):
        if only and dash.slug != only:
            continue
        if not force:
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """select p.id, p.load_id from core.projections p
                         join core.datasets d on d.id = p.dataset_id
                        where p.upload_id = %s and d.dashboard_id =
                              (select id from core.dashboards where slug = %s)
                          and d.slug = %s and p.status = 'ready'""",
                    (upload_id, dash.slug, ds.slug),
                )
                done = cur.fetchone()
            if done:
                results.append({"dashboard": dash.slug, "dataset": ds.slug,
                                "status": "duplicate", "load_id": done["load_id"],
                                "summary": f"{ds.display_name}: already loaded from this file"})
                continue
        try:
            results.append(_project(dash, ds, upload_id, frame, filename, sha))
        except Exception as exc:  # noqa: BLE001
            # _project handles its own failures; this is the belt to that
            # braces. Whatever happens to one dashboard, the next one still runs.
            results.append({"dashboard": dash.slug, "dataset": ds.slug,
                            "status": "failed", "error": str(exc)[:2000]})
    return results


def ingest_source(source_slug: str, filename: str, content: bytes,
                  uploaded_by: str | None = None) -> dict:
    """Take one file for one source and give it to every dashboard that wants it.

    The file is read once and archived once regardless of how many dashboards
    read it. Re-uploading a file already held is not an error: it is how a
    dashboard added later gets fed, so the dedupe is per dashboard rather than
    per file.
    """
    source = registry.source(source_slug)
    sha = hashlib.sha256(content).hexdigest()

    # Parse before storing anything: a file that is not this source should leave
    # no upload row, no archived object and no trace but the 422.
    frame = read_table(filename, content)
    _identify(source, frame)

    with pool.connection() as conn:
        with conn.cursor() as cur:
            source_id = _source_id(cur, source_slug)
            cur.execute(
                """select id, stored_path from core.uploads
                    where source_id = %s and sha256 = %s and status = 'ready'
                    order by id desc limit 1""",
                (source_id, sha),
            )
            existing = cur.fetchone()
        conn.commit()

    if existing:
        # Already archived under a content-addressed key: the bytes are the same
        # bytes. Reuse the row rather than writing a second copy of 114MB.
        upload_id, reused = existing["id"], True
    else:
        reused = False
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """insert into core.uploads
                       (source_id, filename, byte_size, sha256, status, row_count, uploaded_by)
                       values (%s, %s, %s, %s, 'parsing', %s, %s) returning id""",
                    (source_id, filename, len(content), sha, frame.height, uploaded_by),
                )
                upload_id = cur.fetchone()["id"]
            conn.commit()
        try:
            stored = _store(source_slug, sha, filename, content)
        except Exception as exc:  # noqa: BLE001
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """update core.uploads set status = 'failed', error = %s, finished_at = now()
                            where id = %s""",
                        (str(exc)[:2000], upload_id),
                    )
                conn.commit()
            raise
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """update core.uploads set stored_path = %s, status = 'ready', finished_at = now()
                        where id = %s""",
                    (stored, upload_id),
                )
            conn.commit()

    projections = _fan_out(source_slug, upload_id, frame, filename, sha)
    return {
        "upload_id": upload_id,
        "source": source_slug,
        "status": "ready",
        "rows": frame.height,
        "reused_archive": reused,
        "projections": projections,
        "changed": any(p["status"] == "ready" for p in projections),
    }


def project_upload(upload_id: int, dashboard_slug: str | None = None,
                   force: bool = False) -> dict:
    """Rebuild a dashboard's tables from a file already uploaded.

    This is what makes the archive worth keeping. A dashboard added today reads
    the export that arrived last week without anyone finding the file again, and
    a fixed ingest.py is re-applied to the same bytes rather than to a
    re-export that has since moved on.
    """
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select u.id, u.filename, u.sha256, u.stored_path, s.slug as source
                 from core.uploads u join core.sources s on s.id = u.source_id
                where u.id = %s""",
            (upload_id,),
        )
        upload = cur.fetchone()
    if upload is None:
        raise KeyError(f"no upload {upload_id}")
    if not upload["stored_path"]:
        raise IngestError(f"upload {upload_id} was never archived, so it cannot be replayed")

    content = storage().get(upload["stored_path"])
    if hashlib.sha256(content).hexdigest() != upload["sha256"]:
        raise IngestError(
            f"the archived file for upload {upload_id} does not match the sha recorded for it"
        )
    frame = read_table(upload["filename"], content)
    projections = _fan_out(upload["source"], upload_id, frame, upload["filename"],
                           upload["sha256"], only=dashboard_slug, force=force)
    return {"upload_id": upload_id, "source": upload["source"],
            "rows": frame.height, "projections": projections}
