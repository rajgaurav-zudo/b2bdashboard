"""Stage, backfill, deposit and assignment parsing, asserted against the ingest layer."""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import polars as pl

sys.path.insert(0, "/srv/api")
DASH = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dash_master_sales_ingest_mod", DASH / "ingest.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)

from app.ingest.reader import apply_spec  # noqa: E402

Q = "‚Äò"   # the mojibake the export wraps stage names in
R = "‚Äô"
STAGES = {"Applied", "Offer", "Deposit Fully Paid", "COE Received",
          "Visa| Applied", "Visa| Granted", "Enrolled", "VISA", "DepositPaid| PartiallyPaid"}
BASE = {
    "Application Ref No": "", "Student Ref Id": "S1",
    "Application Status": "Applied", "Deposit Paid Status": "", "Application Closed Lost": "No",
    "Deferred Initiated (No/Yes/All)": "No", "Deferred Approved (No/Yes/All)": "No",
    "Application Course Level": "Postgraduate",
    "Intake Month": "January", "Intake Year": "2025",
    "Actual Intake Month": "September", "Actual Intake Year": "2026",
    "StudentAssignedToBusinessArea": "B2B", "StudentAssignedToBusinessRegion": "India B2B",
    "CurrentlyAssignedToBusinessTeam": "Team A",
    **{f"Timestamp of {Q}{s}{R} status": "" for s in ("Draft", "Ready To Apply", *STAGES)},
    "Timestamp Deferral Initiated": "", "Timestamp Deferral Approved": "",
}


def run(*rows: dict) -> pl.DataFrame:
    """Rows as overrides of BASE; a bare stage name stands for its timestamp header."""
    header = lambda k: f"Timestamp of {Q}{k}{R} status" if k in STAGES else k  # noqa: E731
    frame = pl.DataFrame([{**BASE, **{header(k): v for k, v in row.items()}} for row in rows])
    resolution = apply_spec(frame, ingest.COLUMNS["applications"])
    assert not resolution.missing
    return ingest.finalize("applications", resolution.frame)


def test_reads_the_actual_intake_and_the_business_assignment():
    row = run({}).row(0, named=True)
    assert (row["intake_year"], row["intake_month"]) == (2026, 9)
    assert (row["business_area"], row["business_region"], row["business_team"]) == ("B2B", "India B2B", "Team A")


def test_blank_assignment_is_unassigned():
    row = run({"StudentAssignedToBusinessArea": "", "CurrentlyAssignedToBusinessTeam": " "}).row(0, named=True)
    assert row["business_area"] == row["business_team"] == "Unassigned"


def test_enrolled_backfills_every_rung():
    row = run({"Enrolled": "2026-09-01 00:00:00", "Offer": "2026-03-01 00:00:00"}).row(0, named=True)
    assert row["stage"] == 6
    assert row["on_offered"] == row["on_applied"] == date(2026, 3, 1)
    assert row["on_coe"] == row["on_visa_applied"] == row["on_visa_granted"] == date(2026, 9, 1)


def test_visa_status_proves_only_coe():
    row = run({"Application Status": "Visa"}).row(0, named=True)
    assert row["stage"] == 3 and row["on_coe"] is None


def test_deposit_proves_an_offer_and_nothing_more():
    row = run({"Deposit Fully Paid": "2026-04-01 00:00:00"}).row(0, named=True)
    assert row["deposit"] and row["on_deposit"] == date(2026, 4, 1)
    assert row["stage"] == 2 and row["on_offered"] == date(2026, 4, 1) and row["on_coe"] is None


def test_deposit_status_without_a_date():
    rows = run({"Deposit Paid Status": "FullyPaid"}, {"Deposit Paid Status": "PartiallyPaid"},
               {"Deposit Paid Status": "fullyPaidWaitingForApproval"})
    assert rows["deposit"].to_list() == [True, False, True]
    assert rows["on_deposit"].to_list() == [None, None, None]


def test_course_level_falls_into_academic_language_or_other():
    levels = ["Postgraduate", "Pre-Masters", "Language", "PresessionalEnglish", "Presessional", "", "September"]
    frame = run(*[{"Application Course Level": level} for level in levels])
    assert frame["level_group"].to_list() == ["Academic", "Academic", "Language", "Language",
                                              "Other", "Other", "Other"]


def test_deposit_state_follows_the_ytd_sheets():
    rows = run({"Deposit Paid Status": "FullyPaid"},
               {"Deposit Paid Status": "FullyPaid", "Deferred Initiated (No/Yes/All)": "Yes",
                "Deferred Approved (No/Yes/All)": "Yes"},
               {"Deposit Paid Status": "FullyPaid", "Deferred Initiated (No/Yes/All)": "Yes"},
               {"Deposit Paid Status": "fullyPaidWaitingForApproval", "Deferred Approved (No/Yes/All)": "Yes"},
               {"Deposit Paid Status": "PartiallyPaid"},
               {"Deposit Paid Status": "NotPaid"})
    assert rows["deposit_state"].to_list() == ["Active", "Active", "DAA", "DAA", "PD", None]


def test_a_partial_deposit_proves_an_offer():
    row = run({"Deposit Paid Status": "PartiallyPaid"}).row(0, named=True)
    assert row["stage"] == 2 and not row["deposit"]


def test_part_payment_and_deferral_dates():
    row = run({"Deposit Paid Status": "PartiallyPaid", "DepositPaid| PartiallyPaid": "2026-05-01 00:00:00"}).row(0, named=True)
    assert row["on_pd"] == date(2026, 5, 1) and row["on_offered"] == date(2026, 5, 1)
    assert row["deposit_state"] == "PD" and row["on_deposit"] is None
    row = run({"Deposit Paid Status": "FullyPaid", "Deferred Initiated (No/Yes/All)": "Yes",
               "Timestamp Deferral Initiated": "2026-06-01 00:00:00"}).row(0, named=True)
    assert row["deposit_state"] == "DAA" and row["deferral_initiated"] and not row["deferral_approved"]
    assert row["on_deferral_initiated"] == date(2026, 6, 1) and row["on_deferral_approved"] is None
