"""A throwaway load inside a rolled-back transaction, as Pipeline does it:
synthetic rows under a fresh load id, the real SQL over them, then rollback."""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, "/srv/api")

DASH = Path(__file__).resolve().parent.parent


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"dash_master_sales_{name}", DASH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def metrics():
    return _module("metrics")


LADDER = ("on_applied", "on_offered", "on_coe", "on_visa_applied", "on_visa_granted", "on_enrolled")
COLUMNS = ("app_uid", "student_key", "business_area", "business_region", "business_team",
           "intake_year", "intake_month", "stage", *LADDER, "deposit", "on_deposit", "closed_lost", "level_group",
           "deposit_state", "on_pd", "deferral_initiated", "on_deferral_initiated", "deferral_approved",
           "on_deferral_approved")
DATED = (*LADDER, "on_deposit", "on_pd", "on_deferral_initiated", "on_deferral_approved")


class Book:
    def __init__(self, conn, dashboard, loads, metrics):
        from app.views import ViewContext
        self.conn = conn
        self.metrics = metrics
        self.ctx = ViewContext(dashboard=dashboard, conn=conn, loads=loads)

    def load(self, rows: list[dict]) -> None:
        """Each row gives a student, an intake ("2026-09") and the dates it cares
        about; stage and deposit follow from the dates unless given."""
        with self.conn.cursor() as cur:
            for i, row in enumerate(rows):
                year, month = (int(p) for p in row.pop("intake").split("-"))
                dates = {c: date.fromisoformat(row[c]) if isinstance(row.get(c), str) else row.get(c)
                         for c in DATED}
                reached = [rank for rank, c in enumerate(LADDER, start=1) if dates[c]]
                full = {
                    "app_uid": f"a{i}", "business_area": "B2B", "business_region": "India B2B",
                    "business_team": "Team A", "intake_year": year, "intake_month": month,
                    "stage": max(reached, default=0), "deposit": dates["on_deposit"] is not None, "closed_lost": False, "level_group": "Academic",
                    **row, **dates,
                }
                full.setdefault("deposit_state", "Active" if full["deposit"] else None)
                full.setdefault("deferral_initiated", full["on_deferral_initiated"] is not None)
                full.setdefault("deferral_approved", full["on_deferral_approved"] is not None)
                cur.execute(
                    f"insert into applications (load_id, row_hash, {', '.join(COLUMNS)}) "
                    f"values (%s, %s, {', '.join(['%s'] * len(COLUMNS))})",
                    [self.ctx.loads["applications"], i, *[full.get(c) for c in COLUMNS]],
                )

    def overview(self, **params):
        return self.metrics.overview(self.ctx, params)

    def stages(self, **params):
        data = self.overview(**params)
        return {s["id"]: s["n"] for s in data["stages"]} | {"deposit": data["deposit"]["n"]}


@pytest.fixture
def book(metrics):
    from app.db import pool
    from app.registry import get

    pool.open()
    dashboard = get("master_sales")
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
