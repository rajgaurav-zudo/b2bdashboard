"""The pool must not hand out a connection the server has already dropped.

Supabase's pooler closes connections it considers idle and the client is not
told, so a pooled connection can be half-open: `closed` is False, the socket is
dead, and the failure appears on the next query as

    OperationalError: consuming input failed: SSL SYSCALL error: EOF detected

which is a 500 on whatever endpoint happened to draw that connection -- a
dashboard load, a changelog, or an upload that had already parsed the file. It
looked intermittent because it depended on how long the app had been quiet.

These tests reproduce that state directly rather than waiting for a pooler to
produce it, and run against whatever DATABASE_URL is configured.
"""
import os
import socket
import sys

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

sys.path.insert(0, "/srv/api")

from app.config import settings  # noqa: E402
from app.db import pool  # noqa: E402

_KWARGS = {"row_factory": dict_row, "autocommit": False, "prepare_threshold": None}


def _half_open(p: ConnectionPool) -> None:
    """Kill the server end of a pooled connection without telling psycopg.

    Shutting down a dup of the socket is what a pooler dropping the connection
    looks like from here: the next read fails, and nothing before it does.
    """
    with p.connection() as conn:
        assert not conn.closed
        fd = os.dup(conn.pgconn.socket)
        sock = socket.socket(fileno=fd)
        sock.shutdown(socket.SHUT_RDWR)
        sock.detach()
        os.close(fd)


@pytest.fixture
def unchecked():
    """A pool configured the way this one used to be."""
    p = ConnectionPool(settings.database_url, min_size=1, max_size=1, open=True,
                       kwargs=_KWARGS)
    yield p
    p.close()


@pytest.fixture
def checked():
    """The same pool with the setting that fixes it, isolated from the real one
    so the test cannot leave the application's pool in a strange state."""
    p = ConnectionPool(settings.database_url, min_size=1, max_size=1, open=True,
                       kwargs=_KWARGS, check=ConnectionPool.check_connection)
    yield p
    p.close()


def test_an_unchecked_pool_serves_the_dead_connection(unchecked):
    """The bug, so the fix has something to be measured against."""
    _half_open(unchecked)
    with pytest.raises(Exception) as err:
        with unchecked.connection() as conn, conn.cursor() as cur:
            cur.execute("select 1 as n")
    # The wording is a property of the transport, not of the defect: over TLS
    # psycopg reports "SSL SYSCALL error: EOF detected", and over a plain local
    # socket the same half-open connection reports "server closed the connection
    # unexpectedly". Assert the failure, not the wording of one deployment.
    assert isinstance(err.value, psycopg.OperationalError)
    assert any(fragment in str(err.value) for fragment in
               ("EOF detected", "SSL SYSCALL", "server closed the connection"))


def test_a_checked_pool_replaces_it_instead(checked):
    _half_open(checked)
    with checked.connection() as conn, conn.cursor() as cur:
        cur.execute("select 1 as n")
        assert cur.fetchone()["n"] == 1


def test_the_application_pool_checks_connections():
    """The guard on the setting itself. Everything above tests psycopg's
    behaviour; this tests that this application asked for it."""
    assert pool._check is not None
    assert pool.max_lifetime <= 1800, "recycle before a pooler or firewall does"
