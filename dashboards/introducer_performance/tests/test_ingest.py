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
