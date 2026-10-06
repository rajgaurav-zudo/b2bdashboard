"""A throwaway load inside a rolled-back transaction, as the other dashboards
do it: synthetic rows under fresh load ids, the real SQL over them, rollback."""
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/srv/api")

DASH = Path(__file__).resolve().parent.parent


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"dash_pulse_{name}", DASH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def metrics():
    return _module("metrics")


@pytest.fixture(scope="session")
def ingest():
    return _module("ingest")


SCOPE = {"area": "B2B", "region": "Africa B2B", "team": "West Africa 1"}


class Book:
    def __init__(self, conn, dashboard, loads, metrics):
        from app.views import ViewContext
        self.conn = conn
        self.metrics = metrics
        self.ctx = ViewContext(dashboard=dashboard, conn=conn, loads=loads)
        self.n = 0

    def _insert(self, table: str, row: dict) -> None:
        self.n += 1
        dataset = "logs" if table == "logs" else table
        cols = ["load_id", "row_hash", *row]
        with self.conn.cursor() as cur:
            cur.execute(
                f"insert into {table} ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
                [self.ctx.loads[dataset], self.n, *row.values()],
            )

    def introducer(self, name: str, became: str | None = None, **kw) -> None:
        self._insert("introducers", {"partner_name": name, "became_customer": became, **SCOPE, **kw})

    def application(self, uid: str, **kw) -> None:
        self._insert("applications", {"app_uid": uid, **SCOPE, **kw})

    def log(self, uid: str, introducer: str, day: str, **kw) -> None:
        self._insert("logs", {"log_uid": uid, "introducer_name": introducer, "logged_on": day, **kw})

    def overview(self, **params):
        return self.metrics.overview(self.ctx, params)

    def values(self, **params) -> dict:
        return {m["id"]: m["value"] for m in self.overview(**params)["metrics"]}

    def records(self, **params):
        return self.metrics.records(self.ctx, params)


@pytest.fixture
def book(metrics):
    from app.db import pool
    from app.registry import get

    pool.open()
    dashboard = get("pulse")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f'set local search_path to "{dashboard.db_schema}", public')
            cur.execute(
                """select ds.slug, ds.id as dataset_id, d.id as dashboard_id, ds.source_id
                     from core.datasets ds
                     join core.dashboards d on d.id = ds.dashboard_id and d.slug = %s""",
                (dashboard.slug,),
            )
            loads = {}
            for ds in cur.fetchall():
                cur.execute(
                    """insert into core.uploads (source_id, filename, byte_size, sha256, status)
                       values (%s, 'test', 0, md5(random()::text), 'ready') returning id""",
                    (ds["source_id"],),
                )
                upload_id = cur.fetchone()["id"]
                cur.execute(
                    """insert into core.loads (dashboard_id, dataset_id, upload_id, row_count)
                       values (%s, %s, %s, 0) returning id""",
                    (ds["dashboard_id"], ds["dataset_id"], upload_id),
                )
                loads[ds["slug"]] = cur.fetchone()["id"]
        yield Book(conn, dashboard, loads, metrics)
        conn.rollback()
