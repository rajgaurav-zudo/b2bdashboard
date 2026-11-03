"""Module access: a member opens only the dashboards and Data pages given to them.

The audit at the top is the one that keeps this true over time: every API route
must name its module, so a new endpoint cannot quietly be open to every member.
The rest go through the real app. Refusals happen before any query runs; the
few allowed calls read from the local database and never write to it.
"""
import sys

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

sys.path.insert(0, "/srv/api")

from app import access, auth, users  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import pool  # noqa: E402
from app.main import app  # noqa: E402

OWNER = "raj@edvoy.com"
# not module routes: signing in, managing users, and the menu's own list (which
# filters itself to the user's modules)
UNGATED = {("POST", "/api/auth/google"), ("GET", "/api/auth/me"), ("GET", "/api/dashboards")}


def _module(route: APIRoute) -> str | None:
    return next((getattr(d.dependency, "module", None) for d in route.dependencies
                 if getattr(d.dependency, "module", None)), None)


def test_every_api_route_names_its_module():
    missing = [
        f"{method} {route.path}"
        for route in app.routes if isinstance(route, APIRoute) and route.path.startswith("/api/")
        and not route.path.startswith("/api/users")
        for method in route.methods
        if (method, route.path) not in UNGATED and _module(route) is None
    ]
    assert missing == []


def test_each_module_router_is_gated_on_its_own_dashboard():
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/modules/"):
            assert _module(route) == route.path.split("/")[3], route.path


# --- through the app ---------------------------------------------------------------

@pytest.fixture
def people(monkeypatch):
    rows = {
        OWNER: {"email": OWNER, "name": "", "role": "owner", "active": True, "modules": []},
        "admin@edvoy.com": {"email": "admin@edvoy.com", "name": "", "role": "admin", "active": True, "modules": []},
        "member@edvoy.com": {"email": "member@edvoy.com", "name": "", "role": "member", "active": True,
                             "modules": ["pipeline", "downloads"]},
        "nothing@edvoy.com": {"email": "nothing@edvoy.com", "name": "", "role": "member", "active": True,
                              "modules": []},
    }
    monkeypatch.setattr(users, "get", lambda e: rows.get(users.normalise(e)))
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_session_secret", "s" * 48)
    monkeypatch.setattr(settings, "auth_allowed_domains", ["edvoy.com"])
    monkeypatch.setattr(settings, "auth_owner_email", OWNER)
    return rows


@pytest.fixture
def client():
    return TestClient(app)          # no lifespan: nothing migrates or boots


@pytest.fixture(scope="module")
def db():
    """The local pool, for the calls that get past the check and read. Module
    scoped: a closed pool cannot be opened again."""
    try:
        pool.open()
        pool.wait(timeout=10)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no local database: {exc}")
    yield
    pool.close()


def as_(email):
    token, _ = auth.issue_session(auth.User("s", email))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/dashboards/commission"),
    ("GET", "/api/dashboards/commission/views/overview"),
    ("GET", "/api/uploads"),
    ("GET", "/api/sources"),
    ("POST", "/api/sources/anything/uploads"),
    ("POST", "/api/dashboards/pipeline/loads/1/activate"),      # rolling back is an Uploads act
    ("GET", "/api/changelog"),
    ("GET", "/api/changelog/1/rows"),
])
def test_a_member_is_refused_modules_they_were_not_given(people, client, method, path):
    res = client.request(method, path, headers=as_("member@edvoy.com"))
    assert res.status_code == 403
    assert "ask an admin" in res.json()["detail"]


def test_a_module_router_refuses_a_member_without_that_dashboard(people, client):
    path = next(r.path for r in app.routes
                if isinstance(r, APIRoute) and r.path.startswith("/api/modules/commission") and "GET" in r.methods)
    res = client.get(path.replace("{", "").replace("}", ""), headers=as_("member@edvoy.com"))
    assert res.status_code == 403


def test_the_menu_lists_only_the_members_dashboards(people, client, db):
    assert [d["slug"] for d in client.get("/api/dashboards", headers=as_("member@edvoy.com")).json()] == ["pipeline"]
    assert client.get("/api/dashboards", headers=as_("nothing@edvoy.com")).json() == []


def test_a_member_opens_what_they_were_given(people, client, db):
    member = as_("member@edvoy.com")
    assert client.get("/api/dashboards/pipeline", headers=member).status_code == 200
    assert client.get("/api/downloads", headers=member).status_code == 200


@pytest.mark.parametrize("who", [OWNER, "admin@edvoy.com"])
def test_owners_and_admins_open_everything(people, client, db, who):
    listed = {d["slug"] for d in client.get("/api/dashboards", headers=as_(who)).json()}
    assert {d.slug for d in access.registry.discover()} <= listed
    assert client.get("/api/dashboards/commission", headers=as_(who)).status_code == 200
    assert client.get("/api/changelog", headers=as_(who)).status_code == 200


def test_taking_a_module_away_applies_at_the_next_request(people, client):
    member = as_("member@edvoy.com")
    people["member@edvoy.com"]["modules"] = ["pipeline"]
    assert client.get("/api/downloads", headers=member).status_code == 403


def test_me_reports_the_modules(people, client):
    me = client.get("/api/auth/me", headers=as_("member@edvoy.com")).json()
    assert me["modules"] == ["downloads", "pipeline"]


def test_with_sign_in_off_everything_is_open():
    assert access.allowed(None, "commission")
