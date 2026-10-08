"""The Google Sheet sync, with Google replaced by a stand-in: what is sent,
and what the reader is told when it does not go through."""
import json
import sys

import pytest

sys.path.insert(0, "/srv/api")

from app.reports import sheets_sync  # noqa: E402

SHEET = "sheet-123"
ACCOUNT = "sync@example.iam.gserviceaccount.com"


class Reply:
    def __init__(self, status: int, body: dict | None = None):
        self.status_code, self.ok, self._body = status, status < 400, body or {}

    def json(self):
        return self._body


class Google:
    """Records the request and answers with `reply`, or raises it."""

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def patch(self, url, **kw):
        self.calls.append((url, kw))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def setup(tmp_path, monkeypatch):
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"type": "service_account", "client_email": ACCOUNT}))
    monkeypatch.setattr(sheets_sync.settings, "google_service_account_file", str(key))
    monkeypatch.setattr(sheets_sync.settings, "google_sheet_id", SHEET)
    monkeypatch.setattr(sheets_sync.settings, "upload_dir", str(tmp_path))

    def answer(reply):
        google = Google(reply)
        monkeypatch.setattr(sheets_sync, "_session", lambda: google)
        return google
    return answer


def test_sync_overwrites_the_same_sheet_and_remembers_when(setup):
    google = setup(Reply(200, {"id": SHEET}))
    assert sheets_sync.last_synced() is None
    out = sheets_sync.push(b"workbook")
    [(url, kw)] = google.calls
    assert url == f"https://www.googleapis.com/upload/drive/v3/files/{SHEET}"
    assert kw["params"]["uploadType"] == "media"
    assert kw["data"] == b"workbook"
    assert kw["headers"]["Content-Type"] == sheets_sync.XLSX
    assert out["sheet_url"] == f"https://docs.google.com/spreadsheets/d/{SHEET}/edit"
    assert sheets_sync.last_synced() == out["synced_at"]


def test_sync_is_off_without_a_sheet_or_a_key(setup, monkeypatch):
    google = setup(Reply(200))
    monkeypatch.setattr(sheets_sync.settings, "google_sheet_id", "")
    assert not sheets_sync.configured()
    with pytest.raises(sheets_sync.SyncError) as err:
        sheets_sync.push(b"workbook")
    assert err.value.status == 409
    monkeypatch.setattr(sheets_sync.settings, "google_sheet_id", SHEET)
    monkeypatch.setattr(sheets_sync.settings, "google_service_account_file", "/nowhere.json")
    assert not sheets_sync.configured()
    assert google.calls == []


@pytest.mark.parametrize("status, says", [(403, "Share the sheet with"), (404, "cannot find the sheet")])
def test_a_sheet_not_shared_or_missing_names_the_account(setup, status, says):
    setup(Reply(status, {"error": {"message": "nope"}}))
    with pytest.raises(sheets_sync.SyncError) as err:
        sheets_sync.push(b"workbook")
    assert says in str(err.value) and ACCOUNT in str(err.value)
    assert sheets_sync.last_synced() is None


def test_other_failures_pass_on_what_google_said(setup):
    setup(Reply(500, {"error": {"message": "Backend Error"}}))
    with pytest.raises(sheets_sync.SyncError, match="Backend Error"):
        sheets_sync.push(b"workbook")
    setup(ConnectionError("timed out"))
    with pytest.raises(sheets_sync.SyncError, match="Could not reach Google: timed out"):
        sheets_sync.push(b"workbook")
    assert sheets_sync.last_synced() is None
