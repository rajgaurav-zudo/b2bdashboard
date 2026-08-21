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
    # TCP keepalives. A pooled connection sitting idle behind a NAT or a load
    # balancer gets dropped silently; without these the client learns about it
    # only when it next writes, which is mid-query. 30s idle then five probes
    # means a dead link surfaces in about a minute instead of at OS defaults
    # (two hours), and it also keeps a long COPY from being reaped as idle.
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
}

# Why `check`: Supabase's pooler closes connections it considers idle, and the
# client is not told. The pool would then hand a dead connection to a request,
# which failed as `OperationalError: consuming input failed: SSL SYSCALL error:
# EOF detected` -- a 500 on whatever endpoint happened to draw that connection,
# including uploads that had already parsed the file. `check_connection` costs
# one round trip on checkout and discards the corpse instead, so the caller gets
# a live connection or a clear connection error, never a half-open socket.
#
# max_lifetime recycles connections before a pooler or a firewall decides to,
# and max_idle returns the pool to min_size during the long quiet periods this
# workload actually has. Neither replaces the check -- min_size connections are
# exempt from max_idle, and those are exactly the ones that go stale overnight.
pool = ConnectionPool(
    settings.database_url,
    min_size=settings.db_pool_min,
    max_size=settings.db_pool_max,
    open=False,
    kwargs=_KWARGS,
    check=ConnectionPool.check_connection,
    max_idle=settings.db_pool_max_idle,
    max_lifetime=settings.db_pool_max_lifetime,
    # a failed connection attempt should surface as an error to the caller
    # rather than blocking the request for the pool's default two minutes
    timeout=settings.db_pool_timeout,
)
