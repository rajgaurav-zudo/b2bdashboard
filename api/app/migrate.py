"""Migration runner.

Core and every dashboard use the same mechanism but separate scopes, so a broken
migration in one dashboard cannot block another. Dashboard SQL is written with
unqualified names and runs with search_path set to that dashboard's schema.
"""
from pathlib import Path

import psycopg

from .config import settings
from .db import pool
from .registry import discover

CORE_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _applied(cur, scope: str) -> set[str]:
    cur.execute("select to_regclass('core.schema_migrations') as t")
    if cur.fetchone()["t"] is None:
        return set()
    cur.execute("select version from core.schema_migrations where scope = %s", (scope,))
    return {r["version"] for r in cur.fetchall()}


def _apply_dir(conn, scope: str, directory: Path, schema: str | None = None) -> list[str]:
    if not directory.is_dir():
        return []
    done = []
    with conn.cursor() as cur:
        applied = _applied(cur, scope)
    for path in sorted(directory.glob("*.sql")):
        if path.name in applied:
            continue
        with conn.cursor() as cur:
            if schema:
                cur.execute(f'create schema if not exists "{schema}"')
                cur.execute(f'set local search_path to "{schema}", public')
            cur.execute(path.read_text())
            cur.execute(
                "insert into core.schema_migrations (scope, version) values (%s, %s)"
                " on conflict do nothing",
                (scope, path.name),
            )
        conn.commit()
        done.append(f"{scope}/{path.name}")
    return done


def run() -> list[str]:
    applied: list[str] = []
    with pool.connection() as conn:
        applied += _apply_dir(conn, "core", CORE_DIR)
        for dash in discover():
            applied += _apply_dir(conn, dash.slug, dash.dir / "migrations", dash.db_schema)
    return applied


if __name__ == "__main__":
    pool.open()
    for line in run() or ["nothing to apply"]:
        print(line)
    pool.close()
