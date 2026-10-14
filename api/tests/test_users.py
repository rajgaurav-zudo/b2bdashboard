"""The user list: who may sign in, and who may change that.

Two halves. The SQL runs against the local database inside one transaction
that is rolled back at the end, so the real list (and its owner) is untouched.
The rules -- who may add, promote, switch off and remove whom -- run through the
API against an in-memory list.
"""
import sys
import time
from contextlib import contextmanager

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

sys.path.insert(0, "/srv/api")

from app import auth, users  # noqa: E402
from app.config import settings  # noqa: E402
from app.routers import users as users_router  # noqa: E402

DATABASE_URL = "postgresql://b2b:b2b@db:5432/b2bdash"


# --- the SQL -------------------------------------------------------------------

@pytest.fixture
def db(monkeypatch):
    try:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=5)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no local database: {exc}")

    class _OneTransaction:
        @contextmanager
        def connection(self):
            yield conn

    monkeypatch.setattr(users, "pool", _OneTransaction())
    with conn.cursor() as cur:
        cur.execute("select to_regclass('core.users') as t")
        if cur.fetchone()["t"] is None:
            pytest.skip("core.users not migrated yet")
    yield conn
    conn.rollback()
    conn.close()


def test_the_owner_is_written_at_boot_and_the_old_one_kept_as_admin(db, monkeypatch):
    monkeypatch.setattr(settings, "auth_owner_email", "first.owner@edvoy.com")
    users.ensure_owner()
    monkeypatch.setattr(settings, "auth_owner_email", " Next.Owner@Edvoy.com ")
    assert users.ensure_owner() == "next.owner@edvoy.com"

    assert users.get("next.owner@edvoy.com")["role"] == "owner"
    assert users.get("first.owner@edvoy.com")["role"] == "admin"
    with db.cursor() as cur:
        cur.execute("select count(*) as n from core.users where role = 'owner'")
        assert cur.fetchone()["n"] == 1


def test_a_switched_off_owner_is_switched_back_on(db, monkeypatch):
    monkeypatch.setattr(settings, "auth_owner_email", "the.owner@edvoy.com")
    users.ensure_owner()
    users.update("the.owner@edvoy.com", active=False)
    users.ensure_owner()
    assert users.get("the.owner@edvoy.com")["active"] is True


def test_add_change_sign_in_and_remove(db):
    row = users.add("New.Person@edvoy.com", "member", "the.owner@edvoy.com")
    assert (row["email"], row["role"], row["active"]) == ("new.person@edvoy.com", "member", True)
    assert users.add("new.person@edvoy.com", "admin", "x") is None          # already there

    assert users.update("new.person@edvoy.com", active=False)["active"] is False
    assert users.update("new.person@edvoy.com", role="admin")["role"] == "admin"

    users.signed_in("new.person@edvoy.com", "New Person")
    row = users.get("new.person@edvoy.com")
    assert row["name"] == "New Person" and row["last_sign_in_at"] is not None

    assert users.remove("new.person@edvoy.com") is True
    assert users.get("new.person@edvoy.com") is None


def test_a_second_owner_is_refused_by_the_database(db, monkeypatch):
    monkeypatch.setattr(settings, "auth_owner_email", "the.owner@edvoy.com")
    users.ensure_owner()
    users.add("someone@edvoy.com", "member", None)
    with pytest.raises(psycopg.errors.UniqueViolation):
        users.update("someone@edvoy.com", role="owner")


# --- the rules -----------------------------------------------------------------

CLIENT_ID = "1234-abc.apps.googleusercontent.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OWNER = "raj@edvoy.com"


@pytest.fixture
def people(monkeypatch):
    """An in-memory user list standing in for core.users."""
    rows: dict[str, dict] = {}

    def put(email, role="member", active=True):
        rows[email] = {"email": email, "name": "", "role": role, "active": active, "added_by": None,
                       "created_at": None, "updated_at": None, "last_sign_in_at": None}

    def add(email, role, added_by):
        if email in rows:
            return None
        put(email, role)
        rows[email]["added_by"] = added_by
        return rows[email]

    def update(email, *, role=None, active=None):
        row = rows[users.normalise(email)]
        row["role"] = role or row["role"]
        row["active"] = row["active"] if active is None else active
        return row

    monkeypatch.setattr(users, "get", lambda e: rows.get(users.normalise(e)))
    monkeypatch.setattr(users, "list_all", lambda: list(rows.values()))
    monkeypatch.setattr(users, "add", add)
    monkeypatch.setattr(users, "update", update)
    monkeypatch.setattr(users, "remove", lambda e: rows.pop(users.normalise(e), None) is not None)
    monkeypatch.setattr(users, "signed_in", lambda e, n: None)

    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "auth_session_secret", "s" * 48)
    monkeypatch.setattr(settings, "auth_allowed_domains", ["edvoy.com"])
    monkeypatch.setattr(settings, "auth_owner_email", OWNER)

    class _Signing:
        key = KEY.public_key()

    class _Client:
        def get_signing_key_from_jwt(self, _token):
            return _Signing()

    monkeypatch.setattr(auth, "_jwk_client", _Client())
    put(OWNER, "owner")
    put("admin@edvoy.com", "admin")
    put("other.admin@edvoy.com", "admin")
    put("member@edvoy.com", "member")
    yield put, rows
    auth._jwk_client = None


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(users_router.router, prefix="/api/users")
    return TestClient(app)


def as_(email):
    token, _ = auth.issue_session(auth.User("s", email))
    return {"Authorization": f"Bearer {token}"}


def google_token(email, hd="edvoy.com"):
    return jwt.encode({"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "1", "email": email,
                       "email_verified": True, "hd": hd, "exp": int(time.time()) + 600},
                      KEY, algorithm="RS256")


def test_the_owner_signs_in_as_owner(people, client):
    res = client.post("/api/auth/google", json={"credential": google_token(OWNER)})
    assert res.status_code == 200
    assert res.json()["role"] == "owner"
    assert client.get("/api/auth/me", headers=as_(OWNER)).json()["role"] == "owner"


def test_someone_in_the_domain_but_not_on_the_list_cannot_sign_in(people, client):
    res = client.post("/api/auth/google", json={"credential": google_token("new.joiner@edvoy.com")})
    assert res.status_code == 403
    assert OWNER in res.json()["detail"]


def test_a_switched_off_user_cannot_sign_in(people, client):
    put, _ = people
    put("left@edvoy.com", active=False)
    res = client.post("/api/auth/google", json={"credential": google_token("left@edvoy.com")})
    assert res.status_code == 403


def test_removing_someone_ends_their_session_at_the_next_request(people, client):
    headers = as_("member@edvoy.com")
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    client.delete("/api/users/member@edvoy.com", headers=as_(OWNER))
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_a_role_change_applies_without_signing_in_again(people, client):
    headers = as_("member@edvoy.com")
    client.patch("/api/users/member@edvoy.com", json={"role": "admin"}, headers=as_(OWNER))
    assert client.get("/api/auth/me", headers=headers).json()["role"] == "admin"


def test_a_member_cannot_see_the_list(people, client):
    assert client.get("/api/users", headers=as_("member@edvoy.com")).status_code == 403


def test_the_owner_adds_admins_and_members(people, client):
    res = client.post("/api/users", json={"email": " New.Admin@Edvoy.com ", "role": "admin"}, headers=as_(OWNER))
    assert res.status_code == 201
    assert (res.json()["email"], res.json()["role"], res.json()["added_by"]) == ("new.admin@edvoy.com", "admin", OWNER)


def test_an_admin_adds_members_but_not_admins(people, client):
    admin = as_("admin@edvoy.com")
    assert client.post("/api/users", json={"email": "a@edvoy.com"}, headers=admin).status_code == 201
    assert client.post("/api/users", json={"email": "b@edvoy.com", "role": "admin"},
                       headers=admin).status_code == 403


def test_only_addresses_in_the_domain_can_be_added(people, client):
    res = client.post("/api/users", json={"email": "someone@gmail.com"}, headers=as_(OWNER))
    assert res.status_code == 400


def test_adding_someone_twice_is_a_conflict(people, client):
    assert client.post("/api/users", json={"email": "member@edvoy.com"}, headers=as_(OWNER)).status_code == 409


def test_nobody_can_make_an_owner(people, client):
    res = client.post("/api/users", json={"email": "x@edvoy.com", "role": "owner"}, headers=as_(OWNER))
    assert res.status_code == 400
    res = client.patch("/api/users/member@edvoy.com", json={"role": "owner"}, headers=as_(OWNER))
    assert res.status_code == 400


@pytest.mark.parametrize("change", [
    lambda c, h: c.patch(f"/api/users/{OWNER}", json={"active": False}, headers=h),
    lambda c, h: c.patch(f"/api/users/{OWNER}", json={"role": "member"}, headers=h),
    lambda c, h: c.delete(f"/api/users/{OWNER}", headers=h),
])
@pytest.mark.parametrize("who", [OWNER, "admin@edvoy.com"])
def test_the_owner_cannot_be_changed_from_the_app(people, client, change, who):
    assert change(client, as_(who)).status_code == 403
    _, rows = people
    assert rows[OWNER]["role"] == "owner" and rows[OWNER]["active"]


def test_an_admin_manages_members(people, client):
    admin = as_("admin@edvoy.com")
    assert client.patch("/api/users/member@edvoy.com", json={"active": False}, headers=admin).status_code == 200
    assert client.delete("/api/users/member@edvoy.com", headers=admin).status_code == 204


def test_an_admin_cannot_promote_change_or_remove_admins(people, client):
    admin = as_("admin@edvoy.com")
    assert client.patch("/api/users/member@edvoy.com", json={"role": "admin"}, headers=admin).status_code == 403
    assert client.patch("/api/users/other.admin@edvoy.com", json={"active": False},
                        headers=admin).status_code == 403
    assert client.delete("/api/users/other.admin@edvoy.com", headers=admin).status_code == 403


def test_nobody_changes_their_own_access(people, client):
    assert client.delete("/api/users/admin@edvoy.com", headers=as_("admin@edvoy.com")).status_code == 403


def test_the_owner_manages_admins(people, client):
    owner = as_(OWNER)
    assert client.patch("/api/users/admin@edvoy.com", json={"role": "member"}, headers=owner).json()["role"] == "member"
    assert client.delete("/api/users/other.admin@edvoy.com", headers=owner).status_code == 204


def test_changing_someone_not_on_the_list_is_404(people, client):
    assert client.delete("/api/users/ghost@edvoy.com", headers=as_(OWNER)).status_code == 404


def test_preflight_needs_an_owner_inside_the_domain(people, monkeypatch):
    assert auth.preflight() == []
    monkeypatch.setattr(settings, "auth_owner_email", "raj@gmail.com")
    assert any("AUTH_OWNER_EMAIL" in p for p in auth.preflight())
