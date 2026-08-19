"""Dashboard-owned read models.

Core knows nothing about any dashboard's metrics. A dashboard may ship a
`metrics.py` exposing `VIEWS: dict[str, Callable[[ViewContext, dict], Any]]`;
core resolves the current load for every dataset, sets the search_path to that
dashboard's schema, and hands the module a connection. Changing one dashboard's
metrics cannot affect another's.
"""
from dataclasses import dataclass
from typing import Any

from .db import pool
from .registry import Dashboard


class ViewError(Exception):
    """A view was asked for something it cannot answer (bad params, no data)."""


@dataclass
class ViewContext:
    dashboard: Dashboard
    conn: Any
    loads: dict[str, int | None]        # dataset slug -> current load id

    def load(self, dataset: str) -> int:
        load_id = self.loads.get(dataset)
        if load_id is None:
            raise ViewError(f"no data loaded for dataset '{dataset}' — upload it first")
        return load_id

    def rows(self, sql: str, params: dict | None = None) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params or {})
            return cur.fetchall()

    def one(self, sql: str, params: dict | None = None) -> dict | None:
        rows = self.rows(sql, params)
        return rows[0] if rows else None


def _current_loads(conn, slug: str) -> dict[str, int | None]:
    with conn.cursor() as cur:
        cur.execute(
            """select ds.slug, l.id as load_id
                 from core.datasets ds
                 join core.dashboards d on d.id = ds.dashboard_id and d.slug = %s
                 left join core.loads l on l.dataset_id = ds.id and l.is_current""",
            (slug,),
        )
        return {r["slug"]: r["load_id"] for r in cur.fetchall()}


def available(dashboard: Dashboard) -> list[str]:
    try:
        return sorted(dashboard.load_module("metrics").VIEWS)
    except FileNotFoundError:
        return []


def render(dashboard: Dashboard, view: str, params: dict) -> Any:
    try:
        views = dashboard.load_module("metrics").VIEWS
    except FileNotFoundError as exc:
        raise KeyError(f"{dashboard.slug} defines no views") from exc
    if view not in views:
        raise KeyError(f"{dashboard.slug} has no view '{view}' (have: {', '.join(sorted(views))})")

    with pool.connection() as conn:
        with conn.cursor() as cur:
            # read-only: dashboard SQL is written unqualified against its own schema
            cur.execute(f'set local search_path to "{dashboard.db_schema}", public')
        ctx = ViewContext(dashboard=dashboard, conn=conn, loads=_current_loads(conn, dashboard.slug))
        result = views[view](ctx, params)
        conn.rollback()
        return result
