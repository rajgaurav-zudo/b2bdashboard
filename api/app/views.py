"""Dashboard-owned read models.

Core knows nothing about any dashboard's metrics. A dashboard may ship a
`metrics.py` exposing `VIEWS: dict[str, Callable[[ViewContext, dict], Any]]`;
core resolves the current load for every dataset, sets the search_path to that
dashboard's schema, and hands the module a connection. Changing one dashboard's
metrics cannot affect another's.
"""
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from .config import settings
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


# A view is a pure function of (dashboard, view, params, current load ids), so the
# load ids are part of the key rather than a time-to-live: an upload creates a new
# load, which is a new key, and the previous answer is unreachable rather than
# merely stale. Rolling back to an earlier load returns to that load's key and
# hits its cached answer, which is the same value it computed before.
#
# This exists because the read models are worth caching once the database is not
# local: shipping one dashboard's book across a 174ms link costs ~2.4s of the
# ~4s an overview takes, and it recomputes the same answer every time.
_CACHE: "OrderedDict[tuple, Any]" = OrderedDict()


def _cache_key(dashboard: Dashboard, view: str, params: dict, loads: dict) -> tuple:
    return (
        dashboard.slug,
        dashboard.context_sha,                     # a changed spec is a changed answer
        view,
        tuple(sorted(params.items())),
        tuple(sorted(loads.items())),
    )


def invalidate(slug: str | None = None) -> int:
    """Drop cached views. Called after an upload or a rollback.

    Load ids already make a stale answer unreachable; this keeps the dictionary
    from holding results nothing will ask for again.
    """
    keys = [k for k in _CACHE if slug is None or k[0] == slug]
    for key in keys:
        _CACHE.pop(key, None)
    return len(keys)


def render(dashboard: Dashboard, view: str, params: dict) -> Any:
    try:
        views = dashboard.load_module("metrics").VIEWS
    except FileNotFoundError as exc:
        raise KeyError(f"{dashboard.slug} defines no views") from exc
    if view not in views:
        raise KeyError(f"{dashboard.slug} has no view '{view}' (have: {', '.join(sorted(views))})")

    with pool.connection() as conn:
        # Which loads are current is the one thing that must not be cached: it is
        # what makes every other answer valid.
        loads = _current_loads(conn, dashboard.slug)
        key = _cache_key(dashboard, view, params, loads)
        if (hit := _CACHE.get(key)) is not None:
            _CACHE.move_to_end(key)
            return hit

        with conn.cursor() as cur:
            # read-only: dashboard SQL is written unqualified against its own schema
            cur.execute(f'set local search_path to "{dashboard.db_schema}", public')
        ctx = ViewContext(dashboard=dashboard, conn=conn, loads=loads)
        result = views[view](ctx, params)
        conn.rollback()

    _CACHE[key] = result
    while len(_CACHE) > settings.view_cache_entries:
        _CACHE.popitem(last=False)                 # oldest use first
    return result
