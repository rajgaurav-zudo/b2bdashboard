"""Where the raw uploaded file is kept.

The parsed rows go to Postgres; this is the original export, kept so a load can
be explained or replayed later. It lives on the filesystem under UPLOAD_DIR,
behind a small interface so a hosted backend can be added when hosting is
decided.

The stored file is the export as it arrived -- for the applications export that
means all 50 source columns, including the student names and nationalities the
ingest layer drops. Wherever it ends up must be private for that reason, and it
is worth deciding how long these are kept.
"""
import gzip
from pathlib import Path
from typing import Protocol

from .config import settings


class StorageError(Exception):
    """Something went wrong archiving the original export.

    `too_large` separates "this file cannot be stored here at all" -- a plan
    limit, which no retry fixes -- from a transport failure, which one might.
    """

    def __init__(self, message: str, *, too_large: bool = False):
        super().__init__(message)
        self.too_large = too_large


class Storage(Protocol):
    def put(self, key: str, content: bytes, content_type: str) -> str:
        """Store the bytes and return a locator to record against the upload."""

    def get(self, locator: str) -> bytes:
        """Return the original bytes for a locator produced by put()."""

    @property
    def label(self) -> str:
        ...


class LocalStorage:
    """Files under UPLOAD_DIR. Fine for development; a container filesystem is
    not somewhere an audit trail should live."""

    def __init__(self, root: str):
        self.root = Path(root)

    def put(self, key: str, content: bytes, content_type: str) -> str:  # noqa: ARG002
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():                       # content is addressed by hash
            path.write_bytes(content)
        return str(path)

    def get(self, locator: str) -> bytes:
        path = Path(locator)
        if not path.is_absolute():
            path = self.root / locator
        if not path.is_file():
            raise StorageError(f"nothing archived at {locator}")
        return _maybe_gunzip(path.read_bytes())

    @property
    def label(self) -> str:
        return f"local:{self.root}"


_GZIP_MAGIC = b"\x1f\x8b"


def _maybe_gunzip(payload: bytes) -> bytes:
    """Decompress if it is gzip, return it untouched otherwise.

    Sniffed rather than decided from the key: an archive copied down from the
    old hosted bucket is gzipped, and it has to come back as the original file. The magic number is two bytes no CSV or workbook starts with.
    """
    return gzip.decompress(payload) if payload[:2] == _GZIP_MAGIC else payload


def build() -> Storage:
    return LocalStorage(settings.upload_dir)


_storage: Storage | None = None


def storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = build()
    return _storage
