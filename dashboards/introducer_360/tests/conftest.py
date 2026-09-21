"""A throwaway load inside a rolled-back transaction.

Metric definitions live in SQL, so testing them against dictionaries would test
nothing. These fixtures insert synthetic rows under a fresh load id, run the real
queries, and roll back -- no load is ever marked current, so the dev database is
left exactly as it was found.
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, "/srv/api")

DASH = Path(__file__).resolve().parent.parent


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"dash_i360_{name}", DASH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def metrics():
    return _module("metrics")


@pytest.fixture(scope="session")
def ingest():
    return _module("ingest")


STAGE_DATES = ("at_draft", "at_ready", "at_applied", "at_offer", "at_deposit",
               "at_coe", "at_visa_applied", "at_visa_granted", "at_enrolled")
APP_COLUMNS = ("app_uid", "introducer_name", *STAGE_DATES, "at_entered",
               "deposit_fully_paid", "deposit_partial", "deferral_initiated",
               "deferral_approved", "closed_lost", "course_category",
               "intake_year", "cycle_index", "application_status")
INTRO_COLUMNS = ("partner_name", "lifecycle_stage", "latest_contract_status",
                 "country", "srm_team", "srm_owner", "became_customer_year")


def _day(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


class Fixture:
    """Builds a book from plain dicts and runs the dashboard's own SQL over it."""

    def __init__(self, conn, dashboard, loads, metrics):
        from app.views import ViewContext
        self.conn = conn
        self.metrics = metrics
        self.ctx = ViewContext(dashboard=dashboard, conn=conn, loads=loads)

    def load(self, applications: list[dict], introducers: list[dict] | None = None) -> None:
        with self.conn.cursor() as cur:
            for i, row in enumerate(introducers or []):
                cur.execute(
                    f"insert into introducers (load_id, row_hash, {', '.join(INTRO_COLUMNS)}) "
                    f"values (%s, %s, {', '.join(['%s'] * len(INTRO_COLUMNS))})",
                    [self.ctx.loads["introducers"], i, *[row.get(c) for c in INTRO_COLUMNS]],
                )
            for i, row in enumerate(applications):
                row = {
                    "app_uid": f"a{i}", "introducer_name": "P1",
                    "deposit_fully_paid": False, "deposit_partial": False,
                    "deferral_initiated": False, "deferral_approved": False,
                    "closed_lost": False, "course_category": "Academic", **row,
                }
                for column in STAGE_DATES:
                    row[column] = _day(row.get(column))
                # what ingest.py computes; recomputed here so a test only has to
                # give the stage dates it cares about
                dates = [row[c] for c in STAGE_DATES if row.get(c)]
                row["at_entered"] = min(dates) if dates else None
                cur.execute(
                    f"insert into applications (load_id, row_hash, {', '.join(APP_COLUMNS)}) "
                    f"values (%s, %s, {', '.join(['%s'] * len(APP_COLUMNS))})",
                    [self.ctx.loads["applications"], i, *[row.get(c) for c in APP_COLUMNS]],
                )

    def overview(self, **params):
        return self.metrics.overview(self.ctx, params)

    def wise(self, **params):
        return self.metrics.introducer_wise(self.ctx, params)

    def introducers(self, **params):
        return self.metrics.introducers(self.ctx, params)

    def widgets(self, **params):
        return {w["id"]: w for w in self.overview(**params)["widgets"]}

    def stages(self, **params):
        return {s["id"]: s for s in self.overview(**params)["stages"]}


@pytest.fixture
def book(metrics):
    from app.db import pool
    from app.registry import get

    pool.open()
    dashboard = get("introducer_360")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f'set local search_path to "{dashboard.db_schema}", public')
            cur.execute(
                """select ds.slug, ds.id as dataset_id, d.id as dashboard_id, ds.source_id
                     from core.datasets ds
                     join core.dashboards d on d.id = ds.dashboard_id and d.slug = %s""",
                (dashboard.slug,),
            )
            ids = {r["slug"]: r for r in cur.fetchall()}
            loads = {}
            for slug, row in ids.items():
                # an upload belongs to a source, not to this dashboard: the file is
                # shared, and what this dashboard did with it is a projection
                cur.execute(
                    """insert into core.uploads
                         (source_id, filename, byte_size, sha256, status)
                       values (%s, 'test', 0, md5(random()::text || %s), 'ready') returning id""",
                    (row["source_id"], slug),
                )
                upload_id = cur.fetchone()["id"]
                cur.execute(
                    """insert into core.loads (dashboard_id, dataset_id, upload_id, row_count)
                       values (%s, %s, %s, 0) returning id""",
                    (row["dashboard_id"], row["dataset_id"], upload_id),
                )
                loads[slug] = cur.fetchone()["id"]
        yield Fixture(conn, dashboard, loads, metrics)
        conn.rollback()          # nothing this test wrote survives
