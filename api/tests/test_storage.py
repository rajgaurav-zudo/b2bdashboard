"""Backend selection and the upload call.

The selection rules matter more than they look: getting them wrong means a
deployment quietly writing its only copy of the source exports to a container
filesystem that disappears on the next release.
"""
import sys

import httpx
import pytest

sys.path.insert(0, "/srv/api")

from app import storage as store  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    store._storage = None
    yield
    store._storage = None


def test_local_storage_writes_the_file(tmp_path):
    backend = store.LocalStorage(str(tmp_path))
    where = backend.put("dash/dataset/abc.csv", b"a,b\n1,2\n", "text/csv")
    assert (tmp_path / "dash" / "dataset" / "abc.csv").read_bytes() == b"a,b\n1,2\n"
    assert where.endswith("dash/dataset/abc.csv")


def test_local_storage_does_not_rewrite_an_existing_key(tmp_path):
    """Keys are content hashes, so a repeat is the same bytes. Skipping the write
    keeps a re-upload cheap."""
    backend = store.LocalStorage(str(tmp_path))
    backend.put("d/s/abc.csv", b"original", "text/csv")
    backend.put("d/s/abc.csv", b"different", "text/csv")
    assert (tmp_path / "d" / "s" / "abc.csv").read_bytes() == b"original"


def test_auto_picks_supabase_when_it_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "auto")
    monkeypatch.setattr(settings, "supabase_url", "https://p.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "key")
    assert isinstance(store.build(), store.SupabaseStorage)


def test_auto_falls_back_to_local_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "auto")
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    assert isinstance(store.build(), store.LocalStorage)


def test_local_is_honoured_even_when_supabase_is_available(monkeypatch):
    """Development sets STORAGE_BACKEND=local so test uploads do not reach the
    bucket, even though the keys are present in .env."""
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "supabase_url", "https://p.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "key")
    assert isinstance(store.build(), store.LocalStorage)


def test_asking_for_supabase_without_credentials_is_an_error(monkeypatch):
    """Silently downgrading to local would be the dangerous outcome: the deploy
    looks configured and the archive is on a disposable disk."""
    monkeypatch.setattr(settings, "storage_backend", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    with pytest.raises(store.StorageError):
        store.build()


def test_supabase_put_targets_the_bucket_and_upserts(monkeypatch):
    seen = {}

    def fake_post(url, content, headers, timeout):  # noqa: ARG001
        seen["url"] = url
        seen["headers"] = headers
        seen["bytes"] = content
        return httpx.Response(200, text="{}")

    monkeypatch.setattr(store.httpx, "post", fake_post)
    backend = store.SupabaseStorage("https://p.supabase.co", "svc", "uploads", 30)
    locator = backend.put("dash/apps/abc.csv", b"data", "text/csv")

    assert seen["url"] == "https://p.supabase.co/storage/v1/object/uploads/dash/apps/abc.csv"
    assert seen["headers"]["Authorization"] == "Bearer svc"
    assert seen["headers"]["x-upsert"] == "true"
    assert seen["bytes"] == b"data"
    assert locator == "uploads/dash/apps/abc.csv"


def test_a_rejected_upload_raises_rather_than_reporting_success(monkeypatch):
    monkeypatch.setattr(
        store.httpx, "post",
        lambda *a, **k: httpx.Response(413, text="Payload too large"),
    )
    backend = store.SupabaseStorage("https://p.supabase.co", "svc", "uploads", 30)
    with pytest.raises(store.StorageError) as err:
        backend.put("k", b"x" * 10, "text/csv")
    assert "413" in str(err.value)


def test_an_unreachable_storage_service_raises(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(store.httpx, "post", boom)
    backend = store.SupabaseStorage("https://p.supabase.co", "svc", "uploads", 30)
    with pytest.raises(store.StorageError) as err:
        backend.put("k", b"x", "text/csv")
    assert "could not reach storage" in str(err.value)
