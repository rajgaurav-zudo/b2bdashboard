"""A throwaway load inside a rolled-back transaction.

Metric definitions live in SQL, so testing them against dictionaries would test
nothing. These fixtures insert synthetic rows under a fresh load id, run the real
queries, and roll back -- no load is ever marked current, so the dev database is
left exactly as it was found.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/srv/api")
DASH = Path(__file__).resolve().parent.parent


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"dash_intro_{name}", DASH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def metrics():
    return _module("metrics")


APP_COLUMNS = (
    "app_uid", "introducer_name", "deposit_fully_paid", "deposit_partial",
    "deferral_initiated", "deferral_approved", "course_category", "closed_lost", "intake_year",
    # cycle_year is still stored but no longer read: settable so a test can
    # set the two apart and catch the read model relapsing onto it.
    "cycle_year",
    "cycle_index", "application_status", "application_sub_status", "visa_granted", "enrolled",
)
INTRO_COLUMNS = (
    "partner_name", "lifecycle_stage", "latest_contract_status", "country",
    "srm_team", "srm_owner", "became_customer_year", "source_created_year",
)


class Fixture:
    """Builds a book from plain dicts and runs the dashboard's own SQL over it."""

    def __init__(self, conn, dashboard, loads):
        from app.views import ViewContext
        self.conn = conn
        self.ctx = ViewContext(dashboard=dashboard, conn=conn, loads=loads)

    def load(self, introducers: list[dict], applications: list[dict]) -> None:
        with self.conn.cursor() as cur:
            for i, row in enumerate(introducers):
                values = [row.get(c) for c in INTRO_COLUMNS]
                cur.execute(
                    f"insert into introducers (load_id, row_hash, {', '.join(INTRO_COLUMNS)}) "
                    f"values (%s, %s, {', '.join(['%s'] * len(INTRO_COLUMNS))})",
                    [self.ctx.loads["introducers"], i, *values],
                )
            for i, row in enumerate(applications):
                row = {"app_uid": f"a{i}", "deposit_fully_paid": False, "deposit_partial": False,
                       "deferral_initiated": False, "deferral_approved": False,
                       "course_category": "Academic", "closed_lost": False,
                       "visa_granted": False, "enrolled": False, **row}
                values = [row.get(c) for c in APP_COLUMNS]
                cur.execute(
                    f"insert into applications (load_id, row_hash, {', '.join(APP_COLUMNS)}) "
                    f"values (%s, %s, {', '.join(['%s'] * len(APP_COLUMNS))})",
                    [self.ctx.loads["applications"], i, *values],
                )

    def overview(self, metrics):
        return metrics.overview(self.ctx, {})

    def tile(self, metrics, **params):
        return metrics.tile(self.ctx, params)

    def by_name(self, metrics):
        cur, prev, _ = metrics._years(self.ctx)
        return {r["name"]: r for r in metrics._book(self.ctx, cur, prev)}

    def tiles(self, metrics):
        return {t["id"]: t["stats"] for t in self.overview(metrics)["tiles"]}


@pytest.fixture
def book():
    from app.db import pool
    from app.registry import get

    pool.open()
    dashboard = get("introducer_performance")
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
        yield Fixture(conn, dashboard, loads)
        conn.rollback()          # nothing this test wrote survives
