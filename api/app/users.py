"""The people who may use the dashboards, and what each may do.

Storage only: who may change what is decided in `routers/users.py`, and whether
a sign-in is let through in `auth.py`.
"""
from .config import settings
from .db import pool

ROLES = ("owner", "admin", "member")
COLUMNS = "email, name, role, active, modules, added_by, created_at, updated_at, last_sign_in_at"


def normalise(email: str) -> str:
    return (email or "").strip().lower()


def get(email: str) -> dict | None:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(f"select {COLUMNS} from core.users where email = %s", (normalise(email),))
        return cur.fetchone()


def list_all() -> list[dict]:
    with pool.connection() as conn, conn.cursor() as cur:
        # the owner first, then admins, then everyone else by name
        cur.execute(
            f"""select {COLUMNS} from core.users
                 order by array_position(array['owner','admin','member'], role),
                          active desc, lower(coalesce(nullif(name, ''), email))"""
        )
        return cur.fetchall()


def add(email: str, role: str, added_by: str | None, modules: list[str] | None = None) -> dict | None:
    """The new row, or None when the address is already on the list."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""insert into core.users (email, role, added_by, modules) values (%s, %s, %s, %s)
                on conflict (email) do nothing returning {COLUMNS}""",
            (normalise(email), role, added_by, sorted(set(modules or []))),
        )
        return cur.fetchone()


def update(email: str, *, role: str | None = None, active: bool | None = None,
           modules: list[str] | None = None) -> dict | None:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""update core.users
                   set role = coalesce(%s, role), active = coalesce(%s, active),
                       modules = coalesce(%s, modules), updated_at = now()
                 where email = %s returning {COLUMNS}""",
            (role, active, None if modules is None else sorted(set(modules)), normalise(email)),
        )
        return cur.fetchone()


def remove(email: str) -> bool:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("delete from core.users where email = %s", (normalise(email),))
        return cur.rowcount > 0


def signed_in(email: str, name: str) -> None:
    """Record the sign-in, and take the name from Google: nobody types it."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """update core.users set last_sign_in_at = now(), name = coalesce(nullif(%s, ''), name)
                where email = %s""",
            (name, normalise(email)),
        )


def ensure_owner() -> str | None:
    """Make AUTH_OWNER_EMAIL the owner, active, whatever the table says. A
    previous owner stays on as an admin rather than losing access."""
    owner = normalise(settings.auth_owner_email)
    if not owner:
        return None
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "update core.users set role = 'admin', updated_at = now() where role = 'owner' and email <> %s",
            (owner,),
        )
        cur.execute(
            """insert into core.users (email, role, added_by) values (%s, 'owner', 'AUTH_OWNER_EMAIL')
               on conflict (email) do update
                  set role = 'owner', active = true,
                      updated_at = case when core.users.role = 'owner' and core.users.active
                                        then core.users.updated_at else now() end""",
            (owner,),
        )
    return owner
