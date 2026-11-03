"""Which modules a user may open, and the dependencies that hold them to it.

A module is a dashboard (keyed by its slug) or one of the Data pages. Owners and
admins open every module; a member opens the ones ticked for them on the Users
page. With sign-in switched off there is no user, and everything is open.

Every route in `routers/api.py` and every module router carries one of these
dependencies; `tests/test_access.py` fails if a route is added without one.
"""
from fastapi import Depends, HTTPException

from . import registry
from .auth import User, current_user

# the Data pages, which read across dashboards
PLATFORM = {"uploads": "Uploads", "changelog": "Changelog", "downloads": "Downloads"}


def catalogue() -> list[dict]:
    """Every module that can be granted, in the order the Users page lists them."""
    dashboards = sorted(registry.discover(), key=lambda d: d.name.lower())
    return [
        *({"key": d.slug, "name": d.name, "group": "Dashboards"} for d in dashboards),
        *({"key": key, "name": name, "group": "Data"} for key, name in PLATFORM.items()),
    ]


def keys() -> set[str]:
    return {m["key"] for m in catalogue()}


def name(key: str) -> str:
    return next((m["name"] for m in catalogue() if m["key"] == key), key)


def allowed(user: User | None, key: str) -> bool:
    return user is None or user.can(key)


def _check(user: User | None, key: str) -> None:
    if not allowed(user, key):
        raise HTTPException(403, f"you do not have access to {name(key)}; ask an admin to give it to you")


def require(key: str):
    """A dependency admitting only users who may open `key`."""
    def dependency(user: User | None = Depends(current_user)) -> User | None:
        _check(user, key)
        return user
    dependency.module = key          # read by the route audit in the tests
    return dependency


def require_dashboard(slug: str, user: User | None = Depends(current_user)) -> User | None:
    """For routes with the dashboard in the path."""
    _check(user, slug)
    return user


require_dashboard.module = "{slug}"
