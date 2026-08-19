from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

# psycopg3 promotes a query to a server-side prepared statement once it has been
# executed `prepare_threshold` times on a connection. Behind a transaction-mode
# pooler (Supabase's port 6543, PgBouncer) the server connection changes between
# transactions, so the next execution fails with `prepared statement "_pg3_0"
# does not exist` -- intermittently, only under load, only after the fifth call.
# This workload is a handful of large queries rather than high QPS, so the
# prepared-statement win is not worth the failure mode.
#
# Session-mode poolers (port 5432) do not have this problem; disabling anyway
# keeps one connection string from behaving differently to another.
_KWARGS = {
    "row_factory": dict_row,
    "autocommit": False,
    "prepare_threshold": None if settings.disable_prepared_statements else 5,
}

pool = ConnectionPool(
    settings.database_url,
    min_size=settings.db_pool_min,
    max_size=settings.db_pool_max,
    open=False,
    kwargs=_KWARGS,
)
