"""A throwaway load inside a rolled-back transaction.

Metric definitions live in SQL, so testing them against dictionaries would test
nothing. These fixtures insert synthetic rows under a fresh load id, run the real
queries, and roll back -- no load is ever marked current, so the dev database is
left exactly as it was found.
"""
import importlib.util
import sys
from datetime import date

import pytest

sys.path.insert(0, "/srv/api")
from pathlib import Path  # noqa: E402

DASH = Path(__file__).resolve().parent.parent


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"dash_logs_{name}", DASH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def metrics():
    return _module("metrics")


@pytest.fixture(scope="session")
def ingest():
    return _module("ingest")


COLUMNS = ("log_uid", "logged_on", "week_start", "log_type", "introducer_name",
           "managed_by_team", "created_by", "note", "note_words", "note_score", "note_hits")


class Fixture:
    """Builds a set of logs from plain dicts and runs the dashboard's own SQL over it."""

    def __init__(self, conn, dashboard, loads, metrics):
        from app.views import ViewContext
        self.conn = conn
        self.metrics = metrics
        self.ctx = ViewContext(dashboard=dashboard, conn=conn, loads=loads)

    def load(self, rows: list[dict]) -> None:
        with self.conn.cursor() as cur:
            for i, row in enumerate(rows):
                day = row["logged_on"]
                if isinstance(day, str):
                    day = date.fromisoformat(day)
                row = {
                    "log_uid": f"l{i}", "log_type": "Call", "introducer_name": "P1",
                    "managed_by_team": "Team A", "created_by": "Ana", "note": None,
                    "note_words": 0, "note_score": None, "note_hits": 0,
                    **row,
                    "logged_on": day,
                    "week_start": self.metrics.week_start(day),
                }
                cur.execute(
                    f"insert into logs (load_id, row_hash, {', '.join(COLUMNS)}) "
                    f"values (%s, %s, {', '.join(['%s'] * len(COLUMNS))})",
                    [self.ctx.loads["logs"], i, *[row.get(c) for c in COLUMNS]],
                )

    def overview(self, **params):
        return self.metrics.overview(self.ctx, params)

    def rows(self, **params):
        return self.metrics.rows(self.ctx, params)

    def leaderboard(self, **params):
        return self.metrics.leaderboard(self.ctx, params)


@pytest.fixture
def logs(metrics):
    from app.db import pool
    from app.registry import get

    pool.open()
    dashboard = get("logs")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f'set local search_path to "{dashboard.db_schema}", public')
            cur.execute(
                """select ds.slug, ds.id as dataset_id, d.id as dashboard_id, ds.source_id
                     from core.datasets ds
                     join core.dashboards d on d.id = ds.dashboard_id and d.slug = %s""",
                (dashboard.slug,),
            )
            row = {r["slug"]: r for r in cur.fetchall()}["logs"]
            # an upload belongs to a source, not to this dashboard: the file is
            # shared, and what this dashboard did with it is a projection
            cur.execute(
                """insert into core.uploads (source_id, filename, byte_size, sha256, status)
                   values (%s, 'test', 0, md5(random()::text), 'ready') returning id""",
                (row["source_id"],),
            )
            upload_id = cur.fetchone()["id"]
            cur.execute(
                """insert into core.loads (dashboard_id, dataset_id, upload_id, row_count)
                   values (%s, %s, %s, 0) returning id""",
                (row["dashboard_id"], row["dataset_id"], upload_id),
            )
            loads = {"logs": cur.fetchone()["id"]}
        yield Fixture(conn, dashboard, loads, metrics)
        conn.rollback()          # nothing this test wrote survives
