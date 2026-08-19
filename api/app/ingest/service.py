"""Upload pipeline: parse -> stage -> diff -> swap, with a changelog on every step.

Every load is retained. The current load is a flag, not a deletion, so any past
snapshot stays queryable and a bad export can be rolled back by flipping it.
"""
import hashlib
import io
import json
from pathlib import Path

import polars as pl

from ..config import settings
from ..db import pool
from ..registry import Dashboard
from .reader import IngestError, apply_spec, read_table

SYSTEM_COLUMNS = ("load_id", "row_hash")


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _store(dashboard: Dashboard, dataset_slug: str, sha: str, filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix or ".csv"
    directory = Path(settings.upload_dir) / dashboard.slug / dataset_slug
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{sha[:16]}{suffix}"
    if not path.exists():
        path.write_bytes(content)
    return str(path)


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


def activate(dashboard: Dashboard, load_id: int) -> dict:
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
             json.dumps({"action": "activate", "replaced_load": replaced["id"] if replaced else None})),
        )
        conn.commit()
        return {"load_id": load_id, "changed": True, "summary": summary,
                "replaced_load": replaced["id"] if replaced else None}


def ingest(dashboard: Dashboard, dataset_slug: str, filename: str, content: bytes,
           uploaded_by: str | None = None) -> dict:
    dataset = dashboard.dataset(dataset_slug)
    module = dashboard.module
    table = f"{_q(dashboard.db_schema)}.{_q(dataset.table_name)}"
    sha = hashlib.sha256(content).hexdigest()

    with pool.connection() as conn:
        with conn.cursor() as cur:
            dash_id, ds_id = _ids(cur, dashboard, dataset_slug)

            # An identical file is a no-op, but it is still recorded.
            cur.execute(
                """select id from core.uploads
                   where dashboard_id = %s and dataset_id = %s and sha256 = %s and status = 'ready'
                   order by id desc limit 1""",
                (dash_id, ds_id, sha),
            )
            if (previous := cur.fetchone()) is not None:
                cur.execute(
                    """insert into core.uploads
                       (dashboard_id, dataset_id, filename, byte_size, sha256, status, uploaded_by, finished_at)
                       values (%s, %s, %s, %s, %s, 'duplicate', %s, now()) returning id""",
                    (dash_id, ds_id, filename, len(content), sha, uploaded_by),
                )
                upload_id = cur.fetchone()["id"]
                cur.execute(
                    """insert into core.changelog
                       (dashboard_id, dataset_id, upload_id, entity, summary, details)
                       values (%s, %s, %s, %s, %s, %s::jsonb)""",
                    (dash_id, ds_id, upload_id, dataset.slug,
                     f"{dataset.display_name}: identical file re-uploaded, nothing changed",
                     json.dumps({"duplicate_of_upload": previous["id"], "sha256": sha})),
                )
                conn.commit()
                return {"upload_id": upload_id, "status": "duplicate", "changed": False}

            stored = _store(dashboard, dataset_slug, sha, filename, content)
            cur.execute(
                """insert into core.uploads
                   (dashboard_id, dataset_id, filename, byte_size, sha256, stored_path, status, uploaded_by)
                   values (%s, %s, %s, %s, %s, %s, 'parsing', %s) returning id""",
                (dash_id, ds_id, filename, len(content), sha, stored, uploaded_by),
            )
            upload_id = cur.fetchone()["id"]
        conn.commit()

    load_id = None
    try:
        frame = read_table(filename, content)
        resolution = apply_spec(frame, module.COLUMNS[dataset_slug])
        if resolution.missing:
            hint = module.wrong_file_hint(dataset_slug, [c for c in frame.columns]) \
                if hasattr(module, "wrong_file_hint") else ""
            raise IngestError(
                "missing required column(s): " + ", ".join(resolution.missing) + (f". {hint}" if hint else "")
            )
        prepared: pl.DataFrame = module.finalize(dataset_slug, resolution.frame)
        # Optional, dashboard-owned: counts that only exist before rows are collapsed.
        load_stats = module.stats(dataset_slug, resolution.frame, prepared) \
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
                cur.execute("update core.uploads set status = 'loading' where id = %s", (upload_id,))
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

                cur.execute("update core.uploads set status = 'diffing' where id = %s", (upload_id,))
                if previous_load is None:
                    counts, samples = {"added": prepared.height}, []
                    summary = f"{dataset.display_name}: initial load, {prepared.height:,} rows"
                else:
                    counts, samples = _diff(cur, table, dataset.natural_key, load_id,
                                            previous_load, settings.changelog_row_limit)
                    bits = [f"+{counts.get('added', 0):,} added",
                            f"{counts.get('changed', 0):,} changed",
                            f"-{counts.get('removed', 0):,} removed"]
                    summary = f"{dataset.display_name}: " + " · ".join(bits) + f" ({prepared.height:,} rows)"

                unchanged = prepared.height - counts.get("added", 0) - counts.get("changed", 0)
                cur.execute(
                    """insert into core.changelog
                       (dashboard_id, dataset_id, upload_id, load_id, previous_load_id, entity,
                        rows_added, rows_removed, rows_changed, rows_unchanged, rows_sampled, summary, details)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) returning id""",
                    (dash_id, ds_id, upload_id, load_id, previous_load, dataset.slug,
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
                    """update core.uploads set status = 'ready', row_count = %s, finished_at = now()
                       where id = %s""",
                    (prepared.height, upload_id),
                )
            conn.commit()

        return {
            "upload_id": upload_id,
            "load_id": load_id,
            "status": "ready",
            "changed": True,
            "rows": prepared.height,
            "added": counts.get("added", 0),
            "removed": counts.get("removed", 0),
            "changed_rows": counts.get("changed", 0),
            "summary": summary,
            "columns_resolved": resolution.mapping,
        }

    except Exception as exc:  # noqa: BLE001
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if load_id is not None:
                    cur.execute(f"delete from {table} where load_id = %s", (load_id,))
                    cur.execute("delete from core.loads where id = %s", (load_id,))
                cur.execute(
                    "update core.uploads set status = 'failed', error = %s, finished_at = now() where id = %s",
                    (str(exc)[:2000], upload_id),
                )
            conn.commit()
        raise
