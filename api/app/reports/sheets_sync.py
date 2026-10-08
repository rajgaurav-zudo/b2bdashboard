"""Overwrite one Google Sheet with the weekly summary workbook.

The workbook the Downloads page builds is uploaded over the sheet as a new
revision of the same Drive file, and Google converts it to a spreadsheet in
place. The sheet keeps its id, its link and its sharing; its contents are
replaced whole every time, so anything typed into it by hand is lost.

Access is a service account that has been shared on that one sheet as Editor
and on nothing else. Its JSON key and the sheet id come from the settings;
either missing turns the sync off.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings

SCOPES = ["https://www.googleapis.com/auth/drive"]
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files/{id}"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TIMEOUT = 120


class SyncError(Exception):
    """A sync that did not happen, with what to do about it. `status` is the
    HTTP status the API answers with."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def configured() -> bool:
    return bool(settings.google_sheet_id and settings.google_service_account_file
                and Path(settings.google_service_account_file).is_file())


def sheet_url() -> str | None:
    if not settings.google_sheet_id:
        return None
    return f"https://docs.google.com/spreadsheets/d/{settings.google_sheet_id}/edit"


def _record() -> Path:
    """When the last sync went through. Kept beside the uploads, which are
    already the API's writable, git-ignored state."""
    return Path(settings.upload_dir) / ".google-sheet-sync.json"


def last_synced() -> str | None:
    try:
        return json.loads(_record().read_text())["synced_at"]
    except (OSError, ValueError, KeyError):
        return None


def _account() -> str:
    try:
        return json.loads(Path(settings.google_service_account_file).read_text())["client_email"]
    except (OSError, ValueError, KeyError):
        return "the service account"


def _session():
    """An HTTP session that signs its requests as the service account."""
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        settings.google_service_account_file, scopes=SCOPES)
    return AuthorizedSession(creds)


def push(content: bytes) -> dict:
    """Replace the sheet's contents with `content`, an xlsx workbook."""
    if not configured():
        raise SyncError("Google Sheet sync is not set up: it needs GOOGLE_SHEET_ID and the service "
                        "account key in secrets/google-service-account.json.", 409)
    try:
        res = _session().patch(
            UPLOAD.format(id=settings.google_sheet_id),
            params={"uploadType": "media", "supportsAllDrives": "true", "fields": "id,modifiedTime"},
            data=content, headers={"Content-Type": XLSX}, timeout=TIMEOUT)
    except Exception as exc:   # auth and transport errors alike: nothing was written
        raise SyncError(f"Could not reach Google: {exc}") from exc
    if res.status_code in (401, 403):
        raise SyncError(f"Google refused the sync. Share the sheet with {_account()} as Editor.")
    if res.status_code == 404:
        raise SyncError(f"Google cannot find the sheet. Check GOOGLE_SHEET_ID, and that the sheet "
                        f"is shared with {_account()}.")
    if not res.ok:
        try:
            why = res.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            why = f"HTTP {res.status_code}"
        raise SyncError(f"Google rejected the sync: {why}")
    synced_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        _record().write_text(json.dumps({"synced_at": synced_at}))
    except OSError:
        pass   # the sheet is updated; only the "last synced" line goes stale
    return {"synced_at": synced_at, "sheet_url": sheet_url()}
