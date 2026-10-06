"""A throwaway load inside a rolled-back transaction, as Introducer 360 does it:
synthetic rows under a fresh load id, the real SQL over them, then rollback."""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, "/srv/api")

DASH = Path(__file__).resolve().parent.parent


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"dash_pipeline_{name}", DASH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def metrics():
    return _module("metrics")


@pytest.fixture(scope="session")
def ingest():
    return _module("ingest")


DATES = ("on_applied", "on_offer", "on_deposit", "on_coe", "on_visa", "on_enrolled")
COLUMNS = ("app_uid", "student_key", "introducer_name", "course_level", "closed_lost",
           "intake_year", "intake_month", "intake_ym", "stage", *DATES)


class Book:
    def __init__(self, conn, dashboard, loads, metrics):
        from app.views import ViewContext
        self.conn = conn
        self.metrics = metrics
        self.ctx = ViewContext(dashboard=dashboard, conn=conn, loads=loads)

    def master(self, teams: dict[str, str | None]) -> None:
        """Introducers on the master file, partner name -> SRM team."""
        with self.conn.cursor() as cur:
            for i, (name, team) in enumerate(teams.items()):
                cur.execute(
                    "insert into introducers (load_id, partner_name, srm_team, row_hash) values (%s, %s, %s, %s)",
                    [self.ctx.loads["introducers"], name, team, i],
                )

    def load(self, rows: list[dict]) -> None:
        """Each row gives a student, an intake ("2026-09") and the stage dates it
        cares about; stage and backfill are left to the row unless given."""
        with self.conn.cursor() as cur:
            for i, row in enumerate(rows):
                year, month = (int(p) for p in row.pop("intake").split("-"))
                dates = {c: date.fromisoformat(row[c]) if isinstance(row.get(c), str) else row.get(c)
                         for c in DATES}
                reached = [rank for rank, c in enumerate(DATES, start=1) if dates[c]]
                full = {
                    "app_uid": f"a{i}", "course_level": "Postgraduate", "closed_lost": False,
                    "intake_year": year, "intake_month": month, "intake_ym": year * 100 + month,
                    "stage": max(reached, default=0), **row, **dates,
                }
                cur.execute(
                    f"insert into applications (load_id, row_hash, {', '.join(COLUMNS)}) "
                    f"values (%s, %s, {', '.join(['%s'] * len(COLUMNS))})",
                    [self.ctx.loads["applications"], i, *[full.get(c) for c in COLUMNS]],
                )

    def overview(self, **params):
        return self.metrics.overview(self.ctx, params)

    def stages(self, **params):
        return {s["id"]: s for s in self.overview(**params)["stages"]}


@pytest.fixture
def book(metrics):
    from app.db import pool
    from app.registry import get

    pool.open()
    dashboard = get("pipeline")
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
