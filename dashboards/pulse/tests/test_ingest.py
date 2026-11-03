"""Header resolution and parsing, asserted against the ingest layer."""
import sys
from datetime import date

import polars as pl

sys.path.insert(0, "/srv/api")
from app.ingest.reader import apply_spec  # noqa: E402

Q, R = "‚Äò", "‚Äô"   # the mojibake the export wraps stage names in
STAGES = ("Applied", "Offer", "Deposit Fully Paid", "COE Received", "Visa| Applied", "Visa| Granted", "Enrolled")


def _app_frame(**over) -> pl.DataFrame:
    row = {
        "Application Ref No": "A-1", "Student Ref Id": "S-1", "Student Name": "Ada",
        "Application Status": "Offered", "Actual Intake Month": "September", "Actual Intake Year": "2026",
        "StudentAssignedToBusinessArea": "B2B", "StudentAssignedToBusinessRegion": "",
        "CurrentlyAssignedToBusinessTeam": "West Africa 1",
        "ApplicationAssignedToBusinessArea": "B2C",
        "Timestamp of Application marked as Closed": "",
        **{f"Timestamp of {Q}{s}{R} status": "" for s in STAGES},
    }
    row.update({(f"Timestamp of {Q}{k}{R} status" if k in STAGES else k): v for k, v in over.items()})
    return pl.DataFrame([row])


def test_stage_headers_resolve_to_their_own_columns(ingest):
    res = apply_spec(_app_frame(), ingest.COLUMNS["applications"])
    assert not res.missing
    assert "Granted" in res.mapping["at_visa_raw"]
    assert "Visa" not in res.mapping["at_applied_raw"]          # 'Visa| Applied' must not be taken
    assert res.mapping["area_raw"] == "StudentAssignedToBusinessArea"


def test_applications_parse_dates_intake_and_default_scope(ingest):
    frame = _app_frame(**{"Applied": "2026-10-03 09:15:00", "Visa| Granted": "2026-10-05 00:00:00"})
    out = ingest.finalize("applications", apply_spec(frame, ingest.COLUMNS["applications"]).frame)
    row = out.row(0, named=True)
    assert row["at_applied"] == date(2026, 10, 3)
    assert row["at_visa"] == date(2026, 10, 5)
    assert row["intake_ym"] == 202609
    assert (row["area"], row["region"], row["team"]) == ("B2B", "Unassigned", "West Africa 1")


def test_duplicate_application_ids_stay_distinct(ingest):
    frame = pl.concat([_app_frame(), _app_frame()])
    out = ingest.finalize("applications", apply_spec(frame, ingest.COLUMNS["applications"]).frame)
    assert out["app_uid"].n_unique() == 2


def test_log_time_is_the_utc_day(ingest):
    frame = pl.DataFrame([
        {"Introducers Name": "X", "Log Type": "Call", "_id": "1",
         "Log Time": "Mon Oct 05 2026 13:00:11 GMT+0000 (Coordinated Universal Time)"},
        {"Introducers Name": "X", "Log Type": "Call", "_id": "2",
         "Log Time": "Sat Oct 03 2026 01:30:00 GMT+0530 (India Standard Time)"},
    ])
    out = ingest.finalize("logs", apply_spec(frame, ingest.COLUMNS["logs"]).frame)
    assert out["logged_on"].to_list() == [date(2026, 10, 5), date(2026, 10, 2)]


def test_master_dedupes_partners_and_reads_became_customer(ingest):
    frame = pl.DataFrame([
        {"Partner Name": "Acme", "Became Customer Date": "2026-10-02 00:00:00", "BusinessRegion": "MENA-B2B"},
        {"Partner Name": "Acme", "Became Customer Date": "", "BusinessRegion": ""},
    ])
    out = ingest.finalize("introducers", apply_spec(frame, ingest.COLUMNS["introducers"]).frame)
    assert out.height == 1
    assert out.row(0, named=True)["became_customer"] == date(2026, 10, 2)
    assert out.row(0, named=True)["area"] == "Unassigned"
