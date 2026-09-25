"""Stage, backfill and intake parsing, asserted against the ingest layer."""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import polars as pl

sys.path.insert(0, "/srv/api")
DASH = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dash_pipeline_ingest_mod", DASH / "ingest.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)

from app.ingest.reader import apply_spec  # noqa: E402

Q = "‚Äò"   # the mojibake the export wraps stage names in
R = "‚Äô"
BASE = {
    "Application Ref No": "", "Student Ref Id": "S1", "Recruitment Type": "Direct",
    "Application Status": "Applied", "Application Sub-Status": "", "Deposit Paid Status": "",
    "Application Course Level": "Postgraduate", "Application Closed Lost": "No",
    "Intake Month": "January", "Intake Year": "2025",
    "Actual Intake Month": "September", "Actual Intake Year": "2026",
    **{f"Timestamp of {Q}{s}{R} status": "" for s in
       ("Draft", "Ready To Apply", "Applied", "Offer", "Deposit Fully Paid", "COE Received",
        "Visa| Applied", "Visa| Granted", "Enrolled")},
}


STAGES = {"Applied", "Offer", "Deposit Fully Paid", "COE Received",
          "Visa| Applied", "Visa| Granted", "Enrolled"}


def run(*rows: dict) -> pl.DataFrame:
    """Rows as overrides of BASE; a bare stage name stands for its timestamp header."""
    header = lambda k: f"Timestamp of {Q}{k}{R} status" if k in STAGES else k  # noqa: E731
    frame = pl.DataFrame([{**BASE, **{header(k): v for k, v in row.items()}} for row in rows])
    resolution = apply_spec(frame, ingest.COLUMNS["applications"])
    assert not resolution.missing
    return ingest.finalize("applications", resolution.frame)


def test_reads_the_actual_intake_not_the_original():
    out = run({})
    assert out["intake_year"][0] == 2026 and out["intake_month"][0] == 9
    assert out["intake_ym"][0] == 202609


def test_stage_dates_resolve_and_backfill():
    out = run({"Applied": "", "Offer": "", "Visa| Applied": "2026-05-01 00:00:00",
               "Visa| Granted": "2026-06-01 00:00:00"})
    row = out.row(0, named=True)
    assert row["stage"] == 5
    assert row["on_visa"] == date(2026, 6, 1)
    assert row["on_coe"] == date(2026, 5, 1)          # a visa application needs the CoE
    assert row["on_applied"] == row["on_offer"] == row["on_deposit"] == date(2026, 5, 1)
    assert row["on_enrolled"] is None


def test_status_lifts_stage_when_no_date_says_so():
    out = run({"Deposit Paid Status": "FullyPaid", "Applied": "2026-01-01"},
              {"Application Status": "Offered", "Applied": "2026-01-01", "Application Ref No": "X"},
              {"Application Status": "Closed Won", "Application Ref No": "Y"})
    assert out["stage"].to_list() == [3, 2, 1]


def test_every_course_level_and_recruitment_type_is_kept():
    out = run({"Application Course Level": "Language", "Recruitment Type": "InDirect"},
              {"Application Course Level": "", "Application Ref No": "Z"})
    assert out["course_level"].to_list() == ["Language", "Unspecified"]
    assert out["recruitment_type"].to_list() == ["InDirect", "Direct"]


def test_missing_student_ref_falls_back_to_the_application():
    out = run({"Student Ref Id": "", "Application Ref No": "APP9"})
    assert out["student_key"][0] == "app:APP9"
