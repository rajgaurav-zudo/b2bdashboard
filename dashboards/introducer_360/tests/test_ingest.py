"""Rules from context.md, asserted against the ingest layer.

The dashboard exists for the `at_*` columns, so most of what is worth testing
here is about them: that nine similarly-worded headers resolve to nine different
columns, that whatever the export writes into them parses as a date, and that
`at_entered` is the least of them rather than any one of them.
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, "/srv/api")
DASH = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dash_i360_ingest_mod", DASH / "ingest.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)

from app.ingest.reader import apply_spec, read_table  # noqa: E402

BASE = {
    "Application Introducer Name": "P1",
    "Application Status": "Application Sent",
    "Application Sub-Status": "",
    "Deposit Paid Status": "",
    "Application Closed Lost": "No",
    "Actual Intake Month": "September",
    "Actual Intake Year": "2026",
}

# every stage header the export writes, in the order the funnel runs
STAGE_HEADERS = [
    ("Timestamp of 'Draft' status", "at_draft"),
    ("Timestamp of 'Ready To Apply' status", "at_ready"),
    ("Timestamp of 'Applied' status", "at_applied"),
    ("Timestamp of 'Offer' status", "at_offer"),
    ("Timestamp of 'Deposit Fully Paid' status", "at_deposit"),
    ("Timestamp of 'CoE Received' status", "at_coe"),
    ("Timestamp of 'Visa| Applied' status", "at_visa_applied"),
    ("Timestamp of 'Visa| Granted' status", "at_visa_granted"),
    ("Timestamp of 'Enrolled' status", "at_enrolled"),
]


def _apps(rows: list[dict]) -> pl.DataFrame:
    keys = list(rows[0])
    frame = pl.DataFrame(rows, schema={k: pl.Utf8 for k in keys})
    return ingest.finalize("applications", apply_spec(frame, ingest.COLUMNS["applications"]).frame)


# --------------------------------------------------------------------------
# the nine timestamps
# --------------------------------------------------------------------------

def test_every_stage_header_resolves_to_its_own_column():
    """Nine headers differing by one word each, none of them stealing another.

    `Applied` is the loose one: it is a substring of `Visa| Applied`, so it is
    resolved last and this is the test that keeps it there.
    """
    headers = [h for h, _ in STAGE_HEADERS]
    csv = (",".join(list(BASE) + headers) + "\n"
           + ",".join(list(BASE.values()) + [f"2026-0{i + 1}-01 00:00:00" for i in range(9)])
           + "\n").encode()
    resolution = apply_spec(read_table("x.csv", csv), ingest.COLUMNS["applications"])

    assert not resolution.missing
    for header, column in STAGE_HEADERS:
        assert resolution.mapping[f"{column}_raw"] == header
    # nine targets, nine distinct source columns
    taken = [resolution.mapping[f"{c}_raw"] for _, c in STAGE_HEADERS]
    assert len(set(taken)) == 9


def test_stage_headers_resolve_through_curly_quotes_and_mojibake():
    rows = [{**BASE,
             "Timestamp of ‘Visa| Applied’ status": "2026-02-01",
             "Timestamp of ‘Visa| Granted’ status": "2026-03-01",
             "Timestamp of âÃÃ²Enrolledâ ÃÃ´ status": "2026-04-01"}]
    out = _apps(rows)
    assert out["at_visa_applied"][0] == date(2026, 2, 1)
    assert out["at_visa_granted"][0] == date(2026, 3, 1)
    assert out["at_enrolled"][0] == date(2026, 4, 1)


@pytest.mark.parametrize("written,expected", [
    ("2026-03-04 09:30:00", date(2026, 3, 4)),
    ("2026-03-04T09:30:00", date(2026, 3, 4)),
    ("2026-03-04 09:30", date(2026, 3, 4)),
    ("2026-03-04", date(2026, 3, 4)),
    ("04/03/2026 09:30", date(2026, 3, 4)),
    ("04/03/2026", date(2026, 3, 4)),
    ("2026/03/04", date(2026, 3, 4)),
    ("04-03-2026", date(2026, 3, 4)),
    ("4 Mar 2026", date(2026, 3, 4)),
    ("Mar 4, 2026", date(2026, 3, 4)),
    ("04-Mar-2026", date(2026, 3, 4)),
    ("", None),
    ("not a date", None),
])
def test_stage_timestamps_parse_in_every_shape_the_export_uses(written, expected):
    out = _apps([{**BASE, "Timestamp of 'Draft' status": written}])
    assert out["at_draft"][0] == expected


def test_at_entered_is_the_least_stage_date_not_the_draft_one():
    """A third of the export has an Applied date and no Draft one, so entry has
    to be the earliest thing that happened rather than the first stage."""
    out = _apps([
        {**BASE, "Timestamp of 'Draft' status": "2026-05-01",
         "Timestamp of 'Applied' status": "2026-02-01"},
        {**BASE, "Timestamp of 'Draft' status": "",
         "Timestamp of 'Applied' status": "2026-02-01"},
        {**BASE, "Timestamp of 'Draft' status": "", "Timestamp of 'Applied' status": ""},
    ])
    assert out["at_entered"].to_list() == [date(2026, 2, 1), date(2026, 2, 1), None]


def test_an_export_without_the_timestamp_columns_still_loads():
    """The columns are optional. Such a file loads and shows an empty pipeline,
    which is what `stats()` records rather than leaving to be inferred."""
    raw = pl.DataFrame([BASE], schema={k: pl.Utf8 for k in BASE})
    out = ingest.finalize("applications", apply_spec(raw, ingest.COLUMNS["applications"]).frame)
    assert out["at_entered"].to_list() == [None]
    assert ingest.stats("applications", raw, out)["no_stage_dates"] == 1


def test_stats_counts_the_rows_no_introducer_owns():
    rows = [{**BASE, "Application Introducer Name": "P1"},
            {**BASE, "Application Introducer Name": ""}]
    raw = pl.DataFrame(rows, schema={k: pl.Utf8 for k in rows[0]})
    out = ingest.finalize("applications", apply_spec(raw, ingest.COLUMNS["applications"]).frame)
    assert ingest.stats("applications", raw, out)["no_introducer"] == 1


# --------------------------------------------------------------------------
# value rules shared with the introducer performance dashboard
# --------------------------------------------------------------------------

def test_deposit_states_stay_distinct():
    """sources/context.md's three states. Two dashboards disagreeing about what
    `FullyPaid` means would be a bug, not a preference."""
    out = _apps([
        {**BASE, "Deposit Paid Status": "FullyPaid",
         "Deferred Initiated (No/Yes/All)": "No", "Deferred Approved (No/Yes/All)": "No"},
        {**BASE, "Deposit Paid Status": "FullyPaid",
         "Deferred Initiated (No/Yes/All)": "Yes", "Deferred Approved (No/Yes/All)": "No"},
        {**BASE, "Deposit Paid Status": "PartiallyPaid",
         "Deferred Initiated (No/Yes/All)": "No", "Deferred Approved (No/Yes/All)": "No"},
        # a deposit waiting for approval is neither fully paid nor partial
        {**BASE, "Deposit Paid Status": "fullyPaidWaitingForApproval",
         "Deferred Initiated (No/Yes/All)": "No", "Deferred Approved (No/Yes/All)": "No"},
        {**BASE, "Deposit Paid Status": "FullyPaid",
         "Deferred Initiated (No/Yes/All)": "Yes", "Deferred Approved (No/Yes/All)": "Yes"},
    ])
    assert out["deposit_fully_paid"].to_list() == [True, True, False, False, True]
    assert out["deposit_partial"].to_list() == [False, False, True, False, False]
    assert out["deferral_initiated"].to_list() == [False, True, False, False, True]
    assert out["deferral_approved"].to_list() == [False, False, False, False, True]


@pytest.mark.parametrize("level,expected", [
    ("Language", "Language"),
    ("PresessionalEnglish", "Pre-sessional English"),
    ("Pre-Sessional English (10 - week Course)", "Pre-sessional English"),
    ("Postgraduate", "Academic"),
    ("SomeLevelInventedNextYear", "Academic"),   # Academic is the residue, not a list
])
def test_course_category_mapping(level, expected):
    out = _apps([{**BASE, "Application Course Level": level}])
    assert out["course_category"].to_list() == [expected]


def test_course_level_column_is_optional_and_defaults_to_academic():
    assert _apps([BASE])["course_category"].to_list() == ["Academic"]


@pytest.mark.parametrize("month,expect_index", [
    ("January", 0), ("March", 0), ("November", 0), ("December", 0),
    ("May", 1), ("July", 1),
    ("September", 2), ("October", 2),
])
def test_intake_cycle_mapping(month, expect_index):
    out = _apps([{**BASE, "Actual Intake Month": month}])
    assert out["cycle_index"][0] == expect_index


def test_intake_year_is_the_literal_one_the_export_wrote():
    """Unlike the performance dashboard's cycle year, nothing here rolls a
    November intake into the following January: the filter names the year the
    file names."""
    out = _apps([{**BASE, "Actual Intake Month": "November", "Actual Intake Year": "2026"}])
    assert out["intake_year"][0] == 2026


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

def test_app_uid_prefers_the_ref_no():
    out = _apps([{**BASE, "Application Ref No": "APP-1"}, {**BASE, "Application Ref No": "APP-2"}])
    assert out["app_uid"].to_list() == ["APP-1", "APP-2"]


def test_app_uid_is_unique_for_identical_rows_without_a_ref_no():
    out = _apps([BASE, BASE, BASE])
    assert out["app_uid"].n_unique() == 3          # the natural key must survive duplicate rows


def test_wrong_file_hint():
    assert "applications export" in ingest.wrong_file_hint("introducers", ["Application Introducer Name"])
    assert "introducers master" in ingest.wrong_file_hint("applications", ["Lifecycle Stage"])


def test_introducers_dedupe_and_customer_year():
    frame = pl.DataFrame({
        "Partner Name": [" P1 ", "P1", "P2"],
        "Lifecycle Stage": ["Customer", "Customer", "Signing"],
        "Became Customer Date": ["2024-03-04", "2024-03-04", ""],
    })
    out = ingest.finalize("introducers", apply_spec(frame, ingest.COLUMNS["introducers"]).frame)
    assert out.height == 2                                   # duplicate collapsed, name trimmed
    assert out.filter(pl.col("partner_name") == "P1")["became_customer_year"][0] == 2024
    assert out.filter(pl.col("partner_name") == "P2")["became_customer_year"][0] is None
