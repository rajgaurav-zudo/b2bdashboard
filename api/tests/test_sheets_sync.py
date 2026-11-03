"""The Google Sheet sync, with Google replaced by a stand-in: what is sent,
and what the reader is told when it does not go through."""
import json
import sys
import threading

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


def wait():
    """Until the sync's thread has finished."""
    for t in threading.enumerate():
        if t.name == "google-sheet-sync":
            t.join(5)
    return sheets_sync.status()


def test_a_sync_runs_in_the_background_and_counts_its_steps(setup):
    google = setup(Reply(200, {"id": SHEET}))
    gate, seen = threading.Event(), []

    def build(progress):
        progress("Reading")
        gate.wait(5)
        seen.append(sheets_sync.status())
        progress("Writing")
        return b"workbook"

    started = sheets_sync.start(build, [50, 20])
    assert started["state"] == "running" and started["total"] == 3
    with pytest.raises(sheets_sync.SyncError, match="already running") as err:
        sheets_sync.start(build, [50, 20])
    assert err.value.status == 409
    gate.set()
    done = wait()
    assert seen[0]["step"] == 0 and seen[0]["label"] == "Reading" and seen[0]["percent"] == 0
    assert done["state"] == "done" and done["step"] == done["total"] == 3 and done["percent"] == 100
    assert done["synced_at"] == sheets_sync.last_synced() is not None
    assert google.calls[0][1]["data"] == b"workbook"


def test_a_failed_sync_says_why_and_can_be_run_again(setup):
    setup(Reply(403))

    def build(progress):
        progress("Reading")
        return b"workbook"

    sheets_sync.start(build, [1])
    failed = wait()
    assert failed["state"] == "failed" and "Share the sheet with" in failed["error"]
    assert failed["synced_at"] is None

    def broken(progress):
        raise ValueError("bad column")

    sheets_sync.start(broken, [1])
    assert wait()["error"] == "The sync failed: bad column"
