"""Where the raw uploaded file is kept.

The parsed rows go to Postgres; this is the original export, kept so a load can
be explained or replayed later. Two backends behind one interface: the local
filesystem for development, and a private Supabase bucket for anything that has
to outlive a container.

The stored object is the file as it arrived, gzipped -- for the applications
export that means all 50 source columns, including the student names and
nationalities the ingest layer drops. The bucket is private and reachable only
with the service role key for that reason, and it is worth deciding how long
these are kept.

Local storage writes the file plainly and Supabase storage gzips it. That is not
an oversight: compression exists to fit under a hosted per-object limit, and a
development archive is more useful when `head` works on it.
"""
import gzip
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

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

    @property
    def label(self) -> str:
        return f"local:{self.root}"


class SupabaseStorage:
    """A private bucket, written with the service role key.

    Uses the plain upload endpoint rather than resumable: these are single files
    of ~100MB from a server with a stable connection, and a resumable session
    would add a protocol to maintain for no benefit at this size.

    **The object is gzipped.** Supabase enforces a per-object ceiling at the
    project level that is lower than the bucket's own `file_size_limit` and, on
    the free plan, cannot be raised: 50MB, measured. The applications export is
    114MB, so it was rejected with `EntityTooLarge` and the whole ingest failed
    at the archive step. Gzipped it is 21MB and fits with room to spare.

    Level 6 rather than 1: 1.6s instead of 0.7s on the 114MB export, for 21MB
    instead of 27MB. The second of CPU is paid once per upload; the megabytes
    are paid for as long as the archive is kept, against a 1GB free quota.

    Already-compressed formats do not shrink -- .xlsx is a zip, so a 48MB one
    stays 48MB. There is no fix for a >50MB .xlsx short of a paid plan, so that
    case raises rather than pretending.
    """

    COMPRESS_LEVEL = 6

    def __init__(self, url: str, service_key: str, bucket: str, timeout: float):
        self.base = f"{url.rstrip('/')}/storage/v1"
        self.bucket = bucket
        self.timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
        }

    def put(self, key: str, content: bytes, content_type: str) -> str:
        # .gz in the key and application/gzip as the type: the object describes
        # itself, so anything fetching it later needs no convention from here.
        body = gzip.compress(content, compresslevel=self.COMPRESS_LEVEL)
        key = f"{key}.gz"
        target = f"{self.base}/object/{quote(self.bucket)}/{quote(key)}"
        try:
            response = httpx.post(
                target,
                content=body,
                headers={
                    **self._headers,
                    "Content-Type": "application/gzip",
                    # the type of what is inside, so the archive still knows
                    # whether it holds a csv or a workbook
                    "x-metadata-original-content-type": content_type,
                    # keys are content-addressed, so a repeat upload is the same
                    # bytes; overwrite rather than fail the whole ingest
                    "x-upsert": "true",
                },
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise StorageError(f"could not reach storage: {exc}") from exc
        if response.status_code >= 400:
            if "EntityTooLarge" in response.text or response.status_code == 413:
                raise StorageError(
                    f"the archive copy is too large for this Supabase plan: "
                    f"{len(content) / 1048576:.0f}MB compresses to "
                    f"{len(body) / 1048576:.0f}MB, over the 50MB per-object limit. "
                    f"Compressed formats such as .xlsx do not shrink -- export the "
                    f"same data as .csv, which does.",
                    too_large=True,
                )
            raise StorageError(
                f"storage rejected the file ({response.status_code}): {response.text[:300]}"
            )
        return f"{self.bucket}/{key}"

    @property
    def label(self) -> str:
        return f"supabase:{self.bucket}"


def build() -> Storage:
    """Supabase when it is configured, the filesystem otherwise.

    Chosen from configuration rather than a flag so that a deployment with the
    keys set cannot accidentally keep writing to a container filesystem.
    """
    wanted = settings.storage_backend.lower()
    can_use_supabase = bool(settings.supabase_url and settings.supabase_service_role_key)

    if wanted == "supabase" or (wanted == "auto" and can_use_supabase):
        if not can_use_supabase:
            raise StorageError(
                "STORAGE_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
            )
        return SupabaseStorage(
            settings.supabase_url,
            settings.supabase_service_role_key,
            settings.supabase_storage_bucket,
            settings.storage_timeout,
        )
    return LocalStorage(settings.upload_dir)


_storage: Storage | None = None


def storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = build()
    return _storage
