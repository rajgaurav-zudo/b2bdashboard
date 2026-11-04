"""Upload pipeline: identify -> archive -> store -> project.

A file is uploaded to a *source*, not to a dashboard. It is read once, archived
once, written once into the store, and then projected into every dashboard that
declares that source -- each into its own schema, through its own ingest
module, producing its own load. Adding a dashboard does not mean uploading the
file again, and one dashboard's projection failing leaves every other
dashboard's load exactly where it was.

The store (store.<source>) holds the latest upload's rows exactly as uploaded,
replaced on every upload, and store.changelog records what each upload changed
against the one before it. That is the history; the dashboards do not keep one.
Each keeps only the load it is serving, and deletes the one it replaced as the
new one goes current -- unless its manifest says `retain_loads: true`.

Archived files are kept for `settings.archive_days`. Within that window any
past upload can be restored into a dashboard by replaying its file.
"""
import hashlib
import io
import json
import logging
from pathlib import Path

import polars as pl

from .. import registry
from ..config import settings
from ..db import pool
from ..registry import Dashboard, Dataset, Source
from ..storage import StorageError, storage
from ..views import invalidate as invalidate_views
from .reader import Col, IngestError, apply_spec, normalize_header, read_table, resolve_index

log = logging.getLogger(__name__)

SYSTEM_COLUMNS = ("load_id", "row_hash")

# keeps a polars hash inside int8, so it never overflows on the cast
_HASH_MOD = 4_611_686_018_427_387_904


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
    """Make an earlier load the current one again.

    A load whose rows are still in the table (a `retain_loads` dashboard) goes
    back by flipping the current flag. One whose rows were deleted when it was
    replaced is rebuilt from its upload's file, which is possible while the
    file is archived or is the one the store holds. Either way the switch is
    recorded in the changelog so the history still explains why the numbers
    moved.
    """
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select l.id, l.dataset_id, l.dashboard_id, l.row_count, l.is_current,
                      l.purged_at, l.upload_id, u.source_id,
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

    if target["purged_at"] is not None:
        return _restore(dashboard, target, actor)

    with pool.connection() as conn, conn.cursor() as cur:
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
        summary = (f"{dashboard.name} · {target['display_name']}: rolled back to load {load_id} "
                   f"({target['filename']}, {target['row_count']:,} rows)")
        _log_switch(cur, target, load_id, replaced["id"] if replaced else None, summary,
                    {"action": "activate", "actor": actor,
                     "replaced_load": replaced["id"] if replaced else None})
        conn.commit()
    # after the commit: dropping cached views earlier would let a concurrent
    # read repopulate them from the load being replaced
    invalidate_views(dashboard.slug)
    return {"load_id": load_id, "changed": True, "summary": summary,
            "replaced_load": replaced["id"] if replaced else None}


def _restore(dashboard: Dashboard, target: dict, actor: str | None) -> dict:
    """Rebuild a load whose rows are gone, from the file it was made from."""
    result = project_upload(target["upload_id"], dashboard.slug, force=True)
    mine = [p for p in result["projections"] if p["dataset"] == target["dataset"]]
    if not mine or mine[0]["status"] != "ready":
        error = mine[0].get("error") if mine else "this dashboard no longer reads that file"
        raise IngestError(f"could not restore load {target['id']}: {error}")
    new_load = mine[0]["load_id"]
    summary = (f"{dashboard.name} · {target['display_name']}: restored "
               f"{target['filename']} ({mine[0]['rows']:,} rows) as load {new_load}")
    with pool.connection() as conn, conn.cursor() as cur:
        _log_switch(cur, target, new_load, mine[0].get("replaced_load"), summary,
                    {"action": "restore", "actor": actor, "restored_load": target["id"],
                     "from": result.get("read_from")})
        conn.commit()
    return {"load_id": new_load, "changed": True, "summary": summary,
            "replaced_load": mine[0].get("replaced_load")}


def _log_switch(cur, target: dict, load_id: int, replaced: int | None,
                summary: str, details: dict) -> None:
    cur.execute(
        """insert into store.changelog
             (source_id, dashboard_id, dataset_id, upload_id, entity, summary,
              load_id, previous_load_id, details)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (target["source_id"], target["dashboard_id"], target["dataset_id"], target["upload_id"],
         target["dataset"], summary, load_id, replaced, json.dumps(details)),
    )


def _analyze(table: str) -> None:
    """Refresh the planner's statistics for a table that just took a load.

    A load swaps every row of the table for rows under a new load_id, and until
    autoanalyze catches up the planner believes the current load has no rows
    and picks nested loops that never finish (Introducer performance hung for
    hours on exactly this). Best effort: the load is committed, so a failure
    here must not be reported as a failed load.
    """
    try:
        with pool.connection() as conn:
            conn.execute(f"analyze {table}")
            conn.commit()
    except Exception:  # noqa: BLE001
        log.exception("analyze %s failed; the planner keeps stale statistics", table)


def _project(dash: Dashboard, ds: Dataset, upload_id: int, frame: pl.DataFrame,
             filename: str, sha: str) -> dict:
    """Read one already-parsed file into one dashboard's tables.

    Everything dashboard-specific happens here and nowhere else: its column
    mappings, its typed frame, its schema, its natural key. The
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
                % _HASH_MOD
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

                summary = f"{ds.display_name}: {prepared.height:,} rows"

                cur.execute(
                    """update core.loads set is_current = false, superseded_at = now()
                       where dashboard_id = %s and dataset_id = %s and is_current""",
                    (dash_id, ds_id),
                )
                cur.execute("update core.loads set is_current = true where id = %s", (load_id,))
                # The replaced load's rows go with it: what changed is in the
                # store's changelog, and an older file comes back by replaying
                # it. Only the load just replaced -- loads left over from before
                # are a cleanup's business, not an upload's.
                if previous_load is not None and not dash.retain_loads:
                    cur.execute(f"delete from {table} where load_id = %s", (previous_load,))
                    cur.execute("update core.loads set purged_at = now() where id = %s",
                                (previous_load,))
                cur.execute(
                    """update core.projections
                          set status = 'ready', load_id = %s, row_count = %s, finished_at = now()
                        where id = %s""",
                    (load_id, prepared.height, projection_id),
                )
            conn.commit()
        _analyze(table)
        invalidate_views(dash.slug)

        return {
            "dashboard": dash.slug,
            "dataset": ds.slug,
            "status": "ready",
            "load_id": load_id,
            "replaced_load": previous_load,
            "rows": prepared.height,
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


def _store_table(source_slug: str) -> str:
    return f"store.{_q(source_slug)}"


def _keyed(source: Source, frame: pl.DataFrame) -> tuple[pl.DataFrame, str | None]:
    """The file as the store keeps it: row number, key, content hash, values.

    The key is the source's `key` column where the file has one, else the row's
    content. A key that repeats is suffixed with its occurrence so it stays
    unique; one that appears once is left alone and can be looked up by hand.
    The values go in as a postgres array literal so the whole frame is one COPY.
    """
    columns = frame.columns
    content = (
        pl.concat_str([pl.col(c).fill_null("\x00") for c in columns], separator="\x1f")
        .hash() % _HASH_MOD
    ).cast(pl.Int64)
    key_column = None
    if source.key:
        idx = resolve_index([normalize_header(c) for c in columns], Col("key", source.key))
        key_column = columns[idx] if idx is not None else None
    element = [
        pl.when(pl.col(c).is_null()).then(pl.lit("NULL"))
        .otherwise(pl.lit('"') + pl.col(c).str.replace_all("\\", "\\\\", literal=True)
                   .str.replace_all('"', '\\"', literal=True) + pl.lit('"'))
        for c in columns
    ]
    # in stages: as one select, polars re-evaluates the 64-column expressions
    # and a 237k-row export takes 15-40s instead of 2s.
    out = frame.select(
        content.alias("row_hash"),
        (pl.col(key_column).str.strip_chars() if key_column else pl.lit(None, pl.Utf8)).alias("_given"),
        (pl.lit("{") + pl.concat_str(element, separator=",") + pl.lit("}")).alias("vals"),
    )
    given = pl.col("_given")
    out = out.with_columns(
        (pl.int_range(pl.len()) + 1).cast(pl.Int32).alias("row_no"),
        pl.when(given.is_not_null() & (given != "")).then(given)
          .otherwise(pl.lit("~") + pl.col("row_hash").cast(pl.Utf8)).alias("_k"),
    )
    out = out.with_columns(
        pl.when(pl.len().over("_k") == 1).then(pl.col("_k"))
        .otherwise(pl.col("_k") + pl.lit("#") + (pl.int_range(pl.len()).over("_k") + 1).cast(pl.Utf8))
        .alias("row_key")
    )
    return out.select("row_no", "row_key", "row_hash", "vals"), key_column


def _changed_fields(before: dict | None, after: dict | None) -> list[str]:
    if not before or not after:
        return []
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def _write_store(source: Source, upload_id: int, frame: pl.DataFrame, filename: str,
                 sha: str, uploaded_by: str | None) -> dict:
    """Replace the source's store table with this file and record what changed.

    One transaction: the store never holds half a file, and the changelog entry
    exists exactly when the rows it describes do. The diff is of the file
    itself, keyed on the source's key column, so it is the same however many
    dashboards read the file and whatever each of them makes of it.
    """
    table = _store_table(source.slug)
    keyed, key_column = _keyed(source, frame)
    limit = settings.changelog_row_limit

    with pool.connection() as conn:
        with conn.cursor() as cur:
            source_id = _source_id(cur, source.slug)
            cur.execute(
                f"""create table if not exists {table} (
                      row_key  text primary key,
                      row_no   integer not null,
                      row_hash bigint not null,
                      vals     text[] not null)"""
            )
            cur.execute("select upload_id, columns from store.snapshots where source_id = %s "
                        "for update", (source_id,))
            previous = cur.fetchone()

            cur.execute(f"create temp table incoming (like {table}) on commit drop")
            _copy_frame(cur, "incoming", keyed)
            cur.execute("analyze incoming")

            if previous is None:
                counts, samples = {"added": frame.height}, []
                summary = f"{source.display_name}: initial upload, {frame.height:,} rows"
            else:
                body = f"""
                    from incoming n full join {table} o on o.row_key = n.row_key
                    where o.row_key is null or n.row_key is null or o.row_hash <> n.row_hash"""
                change_type = """case when o.row_key is null then 'added'
                                      when n.row_key is null then 'removed'
                                      else 'changed' end"""
                cur.execute(f"select {change_type} as change_type, count(*) as n {body} group by 1")
                counts = {r["change_type"]: r["n"] for r in cur.fetchall()}
                cur.execute(
                    f"""select {change_type} as change_type,
                               coalesce(n.row_key, o.row_key) as natural_key,
                               jsonb_object(%(old)s::text[], o.vals) as before,
                               jsonb_object(%(new)s::text[], n.vals) as after
                        {body}
                        order by 1, 2 limit %(lim)s""",
                    {"old": previous["columns"], "new": frame.columns, "lim": limit},
                )
                samples = cur.fetchall()
                summary = (f"{source.display_name}: "
                           f"+{counts.get('added', 0):,} added · {counts.get('changed', 0):,} changed"
                           f" · -{counts.get('removed', 0):,} removed ({frame.height:,} rows)")

            cur.execute(f"truncate {table}")
            cur.execute(f"insert into {table} (row_key, row_no, row_hash, vals) "
                        "select row_key, row_no, row_hash, vals from incoming")
            cur.execute(
                """insert into store.snapshots (source_id, upload_id, columns, key_column, row_count)
                   values (%s, %s, %s, %s, %s)
                   on conflict (source_id) do update
                     set upload_id = excluded.upload_id, columns = excluded.columns,
                         key_column = excluded.key_column, row_count = excluded.row_count,
                         loaded_at = now()""",
                (source_id, upload_id, frame.columns, key_column, frame.height),
            )

            unchanged = frame.height - counts.get("added", 0) - counts.get("changed", 0)
            cur.execute(
                """insert into store.changelog
                     (source_id, upload_id, previous_upload_id, entity, rows_added, rows_removed,
                      rows_changed, rows_unchanged, rows_sampled, summary, details)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) returning id""",
                (source_id, upload_id, previous["upload_id"] if previous else None, source.slug,
                 counts.get("added", 0), counts.get("removed", 0), counts.get("changed", 0),
                 max(unchanged, 0), len(samples), summary,
                 json.dumps({"sha256": sha, "filename": filename, "actor": uploaded_by,
                             "key_column": key_column,
                             "row_limit_hit": len(samples) >= limit})),
            )
            changelog_id = cur.fetchone()["id"]
            if samples:
                with cur.copy(
                    "copy store.changelog_rows (changelog_id, change_type, natural_key, changed_fields, before, after)"
                    " from stdin"
                ) as copy:
                    for row in samples:
                        copy.write_row((
                            changelog_id, row["change_type"], row["natural_key"],
                            _changed_fields(row["before"], row["after"]),
                            json.dumps(row["before"]) if row["before"] else None,
                            json.dumps(row["after"]) if row["after"] else None,
                        ))
        conn.commit()
    _analyze(table)
    return {"rows": frame.height, "added": counts.get("added", 0),
            "removed": counts.get("removed", 0), "changed": counts.get("changed", 0),
            "summary": summary, "changelog_id": changelog_id}


def _from_store(source_slug: str, upload_id: int) -> pl.DataFrame | None:
    """The file back out of the store, if the store still holds this upload.

    The same all-strings frame read_table() gives, so a dashboard rebuilt from
    here is the one it would have been from the file.
    """
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select sn.columns from store.snapshots sn
                 join core.sources s on s.id = sn.source_id
                where s.slug = %s and sn.upload_id = %s""",
            (source_slug, upload_id),
        )
        snap = cur.fetchone()
        if snap is None:
            return None
        cur.execute(f"select vals from {_store_table(source_slug)} order by row_no")
        rows = [r["vals"] for r in cur.fetchall()]
    return pl.DataFrame(rows, schema={c: pl.Utf8 for c in snap["columns"]}, orient="row")


def purge_archive(days: int | None = None) -> int:
    """Delete archived files older than `days`; keep their upload records.

    Never the newest file of a source (the weekly summary reads it) or the one
    the store holds. A file shared by an upload that is being kept stays too:
    keys are content-addressed, so two uploads of the same bytes share one.
    """
    days = settings.archive_days if days is None else days
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """with keep as (
                 select distinct on (source_id) id from core.uploads
                  where status = 'ready' and stored_path is not null
                  order by source_id, started_at desc
               ), expired as (
                 select id, stored_path from core.uploads
                  where stored_path is not null
                    and started_at < now() - make_interval(days => %s)
                    and id not in (select id from keep)
                    and id not in (select upload_id from store.snapshots)
               )
               select e.id, e.stored_path,
                      exists (select 1 from core.uploads k
                               where k.stored_path = e.stored_path
                                 and k.id not in (select id from expired)) as shared
                 from expired e""",
            (days,),
        )
        expired = cur.fetchall()
        for row in expired:
            if not row["shared"]:
                storage().delete(row["stored_path"])
            cur.execute("update core.uploads set stored_path = null where id = %s", (row["id"],))
        conn.commit()
    return len(expired)


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

    The file is read once, archived once and written to the store once,
    regardless of how many dashboards read it. Re-uploading a file already held
    is not an error: it is how a dashboard added later gets fed, so the dedupe
    is per dashboard rather than per file.
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
                """select u.id, u.stored_path,
                          exists (select 1 from store.snapshots sn
                                   where sn.source_id = u.source_id and sn.upload_id = u.id) as in_store
                     from core.uploads u
                    where u.source_id = %s and u.sha256 = %s and u.status = 'ready'
                    order by u.id desc limit 1""",
                (source_id, sha),
            )
            existing = cur.fetchone()
        conn.commit()

    store = None
    if existing:
        # Already archived under a content-addressed key: the bytes are the same
        # bytes. Reuse the row rather than writing a second copy of 114MB --
        # unless the archive has since expired, in which case this is the file.
        upload_id, reused = existing["id"], True
        if not existing["stored_path"]:
            stored = _store(source_slug, sha, filename, content)
            with pool.connection() as conn:
                conn.execute("update core.uploads set stored_path = %s where id = %s",
                             (stored, upload_id))
                conn.commit()
        if not existing["in_store"]:
            store = _write_store(source, upload_id, frame, filename, sha, uploaded_by)
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
            store = _write_store(source, upload_id, frame, filename, sha, uploaded_by)
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
    try:
        purge_archive()
    except Exception:  # noqa: BLE001
        log.exception("purging the archive failed; expired files stay until the next upload")
    return {
        "upload_id": upload_id,
        "source": source_slug,
        "status": "ready",
        "rows": frame.height,
        "reused_archive": reused,
        "store": store,
        "projections": projections,
        "changed": any(p["status"] == "ready" for p in projections),
    }


def project_upload(upload_id: int, dashboard_slug: str | None = None,
                   force: bool = False) -> dict:
    """Rebuild a dashboard's tables from a file already uploaded.

    A dashboard added today reads the export that arrived last week without
    anyone finding the file again, and a fixed ingest.py is re-applied to the
    same bytes rather than to a re-export that has since moved on. The file
    comes from the archive while it is kept, and from the store when the store
    still holds that upload -- so the latest upload of a source can always be
    replayed, archive or not.
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

    frame, read_from = None, None
    if upload["stored_path"]:
        try:
            content = storage().get(upload["stored_path"])
        except StorageError:
            content = None
        if content is not None:
            if hashlib.sha256(content).hexdigest() != upload["sha256"]:
                raise IngestError(
                    f"the archived file for upload {upload_id} does not match the sha recorded for it"
                )
            frame, read_from = read_table(upload["filename"], content), "archive"
    if frame is None:
        frame, read_from = _from_store(upload["source"], upload_id), "store"
    if frame is None:
        raise IngestError(
            f"{upload['filename']} is older than {settings.archive_days} days, so its file is no "
            "longer kept and it cannot be restored. Upload the export again instead."
        )
    projections = _fan_out(upload["source"], upload_id, frame, upload["filename"],
                           upload["sha256"], only=dashboard_slug, force=force)
    return {"upload_id": upload_id, "source": upload["source"], "read_from": read_from,
            "rows": frame.height, "projections": projections}
