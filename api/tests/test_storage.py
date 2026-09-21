"""The upload archive."""
import gzip
import sys

import pytest

sys.path.insert(0, "/srv/api")

from app import storage as store  # noqa: E402


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


def test_a_gzipped_archive_comes_back_as_the_original(tmp_path):
    """Copies from the old hosted bucket were gzipped; they read back plain."""
    (tmp_path / "a.csv.gz").write_bytes(gzip.compress(b"a,b\n1,2\n"))
    assert store.LocalStorage(str(tmp_path)).get("a.csv.gz") == b"a,b\n1,2\n"
