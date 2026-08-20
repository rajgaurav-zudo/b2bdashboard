"""The view cache is keyed by which loads are current, not by a clock.

The risk it carries is serving yesterday's numbers after an upload, so these
tests are about the key and the invalidation rather than the speed.
"""
import sys

import pytest

sys.path.insert(0, "/srv/api")

from app import views  # noqa: E402
from app.config import settings  # noqa: E402


class FakeDash:
    slug = "d1"
    context_sha = "sha-1"
    db_schema = "dash_d1"


@pytest.fixture(autouse=True)
def _clear():
    views._CACHE.clear()
    yield
    views._CACHE.clear()


def key(loads, view="overview", params=None, dash=None, sha=None):
    d = dash or FakeDash()
    if sha:
        d.context_sha = sha
    return views._cache_key(d, view, params or {}, loads)


def test_a_new_load_is_a_different_key():
    """The whole design: an upload creates a new load id, so the previous answer
    becomes unreachable rather than stale."""
    assert key({"applications": 1}) != key({"applications": 2})


def test_rolling_back_returns_to_the_earlier_key():
    """Activating an old load reaches that load's cached answer, which is the same
    value it computed before -- correct, not stale."""
    assert key({"applications": 1}) == key({"applications": 1})


def test_a_second_dataset_changing_also_changes_the_key():
    assert key({"applications": 1, "introducers": 9}) != key({"applications": 1, "introducers": 10})


def test_key_does_not_depend_on_dict_ordering():
    assert key({"applications": 1, "introducers": 2}) == key({"introducers": 2, "applications": 1})


def test_different_params_are_different_entries():
    assert key({"a": 1}, view="tile", params={"id": "dormant"}) != \
           key({"a": 1}, view="tile", params={"id": "active"})


def test_different_views_are_different_entries():
    assert key({"a": 1}, view="overview") != key({"a": 1}, view="members")


def test_a_changed_spec_is_a_changed_answer():
    """context.md is the metric definitions; if it moves, cached numbers computed
    under the old one should not be served."""
    a = key({"a": 1}, sha="sha-1")
    b = key({"a": 1}, sha="sha-2")
    assert a != b


def test_invalidate_drops_only_the_named_dashboard():
    views._CACHE[("d1", "s", "overview", (), ())] = 1
    views._CACHE[("d2", "s", "overview", (), ())] = 2
    assert views.invalidate("d1") == 1
    assert list(views._CACHE) == [("d2", "s", "overview", (), ())]


def test_invalidate_without_a_slug_clears_everything():
    views._CACHE[("d1", "s", "v", (), ())] = 1
    views._CACHE[("d2", "s", "v", (), ())] = 2
    assert views.invalidate() == 2
    assert not views._CACHE


def test_the_cache_is_bounded(monkeypatch):
    """A drill-down can be 1.7MB; without a bound one dashboard's tiles would sit
    in memory forever."""
    monkeypatch.setattr(settings, "view_cache_entries", 3)
    for i in range(10):
        views._CACHE[("d", "s", "v", (("i", i),), ())] = i
        while len(views._CACHE) > settings.view_cache_entries:
            views._CACHE.popitem(last=False)
    assert len(views._CACHE) == 3
    assert [v for v in views._CACHE.values()] == [7, 8, 9]
