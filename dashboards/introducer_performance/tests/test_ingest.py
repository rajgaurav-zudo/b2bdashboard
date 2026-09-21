"""Rules from context.md, asserted against the ingest layer.

These are this dashboard's tests. They do not touch any other dashboard.
"""
import importlib.util
import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, "/srv/api")
DASH = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dash_intro_ingest", DASH / "ingest.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)

from app.ingest.reader import apply_spec, normalize_header, read_table  # noqa: E402


def _apps(rows: list[dict]) -> pl.DataFrame:
    frame = pl.DataFrame(rows, schema={k: pl.Utf8 for k in rows[0]}) if rows else pl.DataFrame()
    return ingest.finalize("applications", apply_spec(frame, ingest.COLUMNS["applications"]).frame)


def test_header_normalisation_survives_curly_quotes_and_mojibake():
    # curly quotes become straight ones, so the exact-name match still works
    assert normalize_header("Timestamp of ‘Visa| Granted’ status") == "timestamp of 'visa| granted' status"
    # mojibake cannot be reconstructed into the original header, and it does not need to be:
    # what matters is that the tokens we match on survive the strip
    mangled = normalize_header("Timestamp of âÃÃ²Enrolledâ ÃÃ´ status")
    assert "timestamp" in mangled and "enrolled" in mangled and "status" in mangled


def test_timestamp_columns_resolve_through_mangled_headers():
    csv = (
        "Application Introducer Name,Deposit Paid Status,Application Closed Lost,"
        "Actual Intake Month,Actual Intake Year,Application Status,Application Sub-Status,"
        "Timestamp of ‘Visa| Granted’ status,Timestamp of âÃÃ²Enrolledâ ÃÃ´ status\n"
        "P1,FullyPaid,No,September,2026,Application Sent,,2026-01-02 09:00,2026-03-04 09:00\n"
    ).encode()
    resolution = apply_spec(read_table("x.csv", csv), ingest.COLUMNS["applications"])
    assert not resolution.missing
    assert "visa_granted_raw" in resolution.mapping and "enrolled_raw" in resolution.mapping


@pytest.mark.parametrize(
    "month,year,expect_year,expect_index",
    [
        ("November", "2026", 2027, 0),   # Nov/Dec roll into the FOLLOWING January
        ("December", "2026", 2027, 0),
        ("January", "2026", 2026, 0),
        ("March", "2026", 2026, 0),
        ("May", "2026", 2026, 1),
        ("July", "2026", 2026, 1),
        ("September", "2026", 2026, 2),
        ("October", "2026", 2026, 2),
    ],
)
def test_intake_cycle_mapping(month, year, expect_year, expect_index):
    out = _apps([{
        "Application Introducer Name": "P1", "Deposit Paid Status": "", "Application Closed Lost": "No",
        "Actual Intake Month": month, "Actual Intake Year": year,
        "Application Status": "", "Application Sub-Status": "",
    }])
    assert out["cycle_year"][0] == expect_year
    assert out["cycle_index"][0] == expect_index


def test_deposit_flags():
    out = _apps([
        {"Application Introducer Name": "P1", "Deposit Paid Status": "FullyPaid",
         "Application Closed Lost": "No", "Actual Intake Month": "September", "Actual Intake Year": "2026",
         "Application Status": "", "Application Sub-Status": ""},
        {"Application Introducer Name": "P1", "Deposit Paid Status": "FullyPaid",
         "Application Closed Lost": "Yes", "Actual Intake Month": "September", "Actual Intake Year": "2026",
         "Application Status": "", "Application Sub-Status": ""},
        {"Application Introducer Name": "P1", "Deposit Paid Status": "",
         "Application Closed Lost": "No", "Actual Intake Month": "September", "Actual Intake Year": "2026",
         "Application Status": "", "Application Sub-Status": ""},
    ])
    assert out["deposit_fully_paid"].to_list() == [True, True, False]
    assert out["closed_lost"].to_list() == [False, True, False]


def test_app_uid_is_unique_for_identical_rows():
    row = {"Application Introducer Name": "P1", "Deposit Paid Status": "", "Application Closed Lost": "No",
           "Actual Intake Month": "May", "Actual Intake Year": "2025",
           "Application Status": "", "Application Sub-Status": ""}
    out = _apps([row, row, row])
    assert out["app_uid"].n_unique() == 3          # the natural key must survive duplicate rows


def test_introducers_dedupe_and_date_fallback():
    frame = pl.DataFrame({
        "Partner Name": [" P1 ", "P1", "P2"],
        "Lifecycle Stage": ["Customer", "Customer", "Signing"],
        "Became Customer Date": ["2024-03-04", "2024-03-04", ""],
        "Created At": ["2023-01-01", "2023-01-01", "2025-06-06"],
    })
    out = ingest.finalize("introducers", apply_spec(frame, ingest.COLUMNS["introducers"]).frame)
    assert out.height == 2                                   # duplicate collapsed, name trimmed
    assert out.filter(pl.col("partner_name") == "P1")["became_customer_year"][0] == 2024
    p2 = out.filter(pl.col("partner_name") == "P2")
    assert p2["became_customer_year"][0] is None             # blank stays blank in ingest
    assert p2["source_created_year"][0] == 2025              # the fallback is available to metrics


def test_wrong_file_hint():
    assert "applications export" in ingest.wrong_file_hint("introducers", ["Application Introducer Name"])
    assert "introducers master" in ingest.wrong_file_hint("applications", ["Lifecycle Stage"])


def test_deposit_states_partial_and_deferral():
    """The three states of sources/context.md. PD is disjoint from fully paid;
    DAA rides on top of a paid deposit rather than replacing it."""
    base = {"Application Closed Lost": "No", "Actual Intake Month": "September",
            "Actual Intake Year": "2026", "Application Status": "", "Application Sub-Status": ""}
    out = _apps([
        {**base, "Application Introducer Name": "P1", "Deposit Paid Status": "FullyPaid",
         "Deferred Initiated (No/Yes/All)": "No", "Deferred Approved (No/Yes/All)": "No"},
        {**base, "Application Introducer Name": "P2", "Deposit Paid Status": "FullyPaid",
         "Deferred Initiated (No/Yes/All)": "Yes", "Deferred Approved (No/Yes/All)": "No"},
        {**base, "Application Introducer Name": "P3", "Deposit Paid Status": "PartiallyPaid",
         "Deferred Initiated (No/Yes/All)": "No", "Deferred Approved (No/Yes/All)": "No"},
        # waiting-for-approval is neither fully paid nor partial -- it has no state.
        # This is a *deposit* approval, unrelated to the deferral approval column.
        {**base, "Application Introducer Name": "P4",
         "Deposit Paid Status": "fullyPaidWaitingForApproval",
         "Deferred Initiated (No/Yes/All)": "No", "Deferred Approved (No/Yes/All)": "No"},
        {**base, "Application Introducer Name": "P5", "Deposit Paid Status": "DepositRejected",
         "Deferred Initiated (No/Yes/All)": "No", "Deferred Approved (No/Yes/All)": "No"},
        # initiated and already approved: a settled deferral, not an awaiting one
        {**base, "Application Introducer Name": "P6", "Deposit Paid Status": "FullyPaid",
         "Deferred Initiated (No/Yes/All)": "Yes", "Deferred Approved (No/Yes/All)": "Yes"},
    ])
    assert out["deposit_fully_paid"].to_list() == [True, True, False, False, False, True]
    assert out["deposit_partial"].to_list()    == [False, False, True, False, False, False]
    assert out["deferral_initiated"].to_list() == [False, True, False, False, False, True]
    assert out["deferral_approved"].to_list()  == [False, False, False, False, False, True]


def test_deferral_column_is_optional():
    """Exports that predate the deferral columns must load, reading as not deferred."""
    out = _apps([
        {"Application Introducer Name": "P1", "Deposit Paid Status": "FullyPaid",
         "Application Closed Lost": "No", "Actual Intake Month": "September",
         "Actual Intake Year": "2026", "Application Status": "", "Application Sub-Status": ""},
    ])
    assert out["deferral_initiated"].to_list() == [False]
    assert out["deferral_approved"].to_list() == [False]
    assert out["deposit_partial"].to_list() == [False]


def test_deferral_column_resolves_from_the_real_header():
    csv = (
        "Application Introducer Name,Deposit Paid Status,Deferred Initiated (No/Yes/All),"
        "Deferred Approved (No/Yes/All),Application Closed Lost\n"
        "P1,FullyPaid,Yes,No,No\n"
    ).encode()
    resolution = apply_spec(read_table("x.csv", csv), ingest.COLUMNS["applications"])
    # the two deferral columns must not steal each other -- they differ by one word
    assert resolution.mapping["deferral_initiated_raw"] == "Deferred Initiated (No/Yes/All)"
    assert resolution.mapping["deferral_approved_raw"] == "Deferred Approved (No/Yes/All)"


@pytest.mark.parametrize("level,expected", [
    ("Language", "Language"),
    ("PresessionalEnglish", "Pre-sessional English"),
    ("Presessional", "Pre-sessional English"),
    ("Pre-Sessional English (10 - week Course)", "Pre-sessional English"),
    ("Postgraduate", "Academic"),
    ("Undergraduate", "Academic"),
    ("Foundation", "Academic"),
    ("Doctorate", "Academic"),
    ("PreMasters", "Academic"),
    ("ALevel", "Academic"),
    ("GCSEgradesAC", "Academic"),
    ("SomeLevelInventedNextYear", "Academic"),   # Academic is the residue, not a list
])
def test_course_category_mapping(level, expected):
    out = _apps([{
        "Application Introducer Name": "P1", "Deposit Paid Status": "FullyPaid",
        "Application Closed Lost": "No", "Actual Intake Month": "September",
        "Actual Intake Year": "2026", "Application Status": "", "Application Sub-Status": "",
        "Application Course Level": level,
    }])
    assert out["course_category"].to_list() == [expected]


def test_course_level_column_is_optional_and_defaults_to_academic():
    """An export without the column must keep reporting the deposits it always did.

    Deposits are Academic-only, so calling these rows Unspecified would make a
    load from an older export report zero deposits while reporting success."""
    out = _apps([{
        "Application Introducer Name": "P1", "Deposit Paid Status": "FullyPaid",
        "Application Closed Lost": "No", "Actual Intake Month": "September",
        "Actual Intake Year": "2026", "Application Status": "", "Application Sub-Status": "",
    }])
    assert out["course_category"].to_list() == ["Academic"]
    assert out["course_level"].to_list() == [None]


def test_blank_course_level_is_unspecified_when_the_file_has_levels():
    """A gap in a file that does carry the column is a finding, not an Academic row."""
    base = {"Deposit Paid Status": "FullyPaid", "Application Closed Lost": "No",
            "Actual Intake Month": "September", "Actual Intake Year": "2026",
            "Application Status": "", "Application Sub-Status": ""}
    out = _apps([
        {**base, "Application Introducer Name": "P1", "Application Course Level": "Postgraduate"},
        {**base, "Application Introducer Name": "P2", "Application Course Level": ""},
    ])
    assert out["course_category"].to_list() == ["Academic", "Unspecified"]


def test_course_level_is_not_stolen_by_course_name():
    csv = (
        "Application Introducer Name,Deposit Paid Status,Course Name,Application Course Level\n"
        "P1,FullyPaid,BSc Computer Science,Undergraduate\n"
    ).encode()
    resolution = apply_spec(read_table("x.csv", csv), ingest.COLUMNS["applications"])
    assert resolution.mapping["course_level"] == "Application Course Level"


def test_application_id_resolves_from_the_real_header():
    """The export calls it `Application Ref No`, not `Application Id`. Getting
    this wrong is silent: every row loads, and every app_uid quietly falls back
    to a content hash instead of the CRM's own key."""
    out = _apps([
        {"Application Ref No": "A-2026052320864",
         "Application Introducer Name": "Alpha",
         "Deposit Paid Status": "PartiallyPaid"},
    ])
    assert out["application_id"].to_list() == ["A-2026052320864"]
    assert out["app_uid"].to_list() == ["A-2026052320864"]
