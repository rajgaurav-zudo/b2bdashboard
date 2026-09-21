"""Rules from context.md, asserted against the ingest layer.

These are this dashboard's tests. They do not touch any other dashboard.
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, "/srv/api")
DASH = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dash_logs_ingest", DASH / "ingest.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)

from app.ingest.reader import apply_spec, read_table  # noqa: E402

HEADER = ("Introducers Name,Log Type,Log Time,Managed By Team,Created By,Note\n")
# What the live CRM actually exports: nine columns, `_id` first.
REAL_HEADER = ('"_id","Introducers Name","Log Type","Call Type","Log Time",'
               '"Outcome","Note","Managed By Team","Created By"\n')
JS_TIME = "Mon Aug 24 2026 10:55:45 GMT+0000 (Coordinated Universal Time)"


def _rows(rows: list[dict]) -> pl.DataFrame:
    frame = pl.DataFrame(rows, schema={k: pl.Utf8 for k in rows[0]})
    return ingest.finalize("logs", apply_spec(frame, ingest.COLUMNS["logs"]).frame)


def _one(**overrides) -> dict:
    return {"_id": "", "Introducers Name": "P1", "Log Type": "Call", "Call Type": "",
            "Log Time": "2026-08-12 14:33", "Outcome": "", "Note": "",
            "Managed By Team": "Team A", "Created By": "Ana", **overrides}


# --------------------------------------------------------------------------
# columns
# --------------------------------------------------------------------------

def test_the_six_required_columns_resolve_from_the_real_header():
    csv = (HEADER + "P1,Call,2026-08-12 14:33,Team A,Ana,Called.\n").encode()
    resolution = apply_spec(read_table("logs.csv", csv), ingest.COLUMNS["logs"])
    assert not resolution.missing
    assert resolution.mapping["introducer_name"] == "Introducers Name"
    assert resolution.mapping["log_type"] == "Log Type"
    assert resolution.mapping["log_time"] == "Log Time"
    assert resolution.mapping["note"] == "Note"


def test_log_time_is_not_stolen_by_log_type():
    """Both headers start with the same word; neither may take the other's column."""
    resolution = apply_spec(
        read_table("logs.csv", (HEADER + "P1,Call,2026-08-12,Team A,Ana,x\n").encode()),
        ingest.COLUMNS["logs"],
    )
    assert resolution.mapping["log_type"] != resolution.mapping["log_time"]


def test_the_applications_export_is_recognised_as_the_wrong_file():
    headers = ["Application Introducer Name", "Deposit Paid Status", "Application Status"]
    assert "applications" in ingest.wrong_file_hint("logs", headers)
    assert "introducers master" in ingest.wrong_file_hint("logs", ["Partner Name", "Lifecycle Stage"])


# --------------------------------------------------------------------------
# dates and weeks
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("2026-08-12 14:33", date(2026, 8, 12)),
    ("2026-08-12T14:33:00", date(2026, 8, 12)),
    ("2026-08-12", date(2026, 8, 12)),
    ("12/08/2026 14:33", date(2026, 8, 12)),      # day-first, as in the other export
    ("12/08/2026", date(2026, 8, 12)),
    ("12 Aug 2026", date(2026, 8, 12)),
])
def test_log_time_parses_and_drops_the_time_of_day(raw, expected):
    assert _rows([_one(**{"Log Time": raw})])["logged_on"][0] == expected


@pytest.mark.parametrize("day,saturday", [
    ("2026-08-15", date(2026, 8, 15)),   # Saturday -- the week starts on itself
    ("2026-08-16", date(2026, 8, 15)),   # Sunday
    ("2026-08-19", date(2026, 8, 15)),   # Wednesday
    ("2026-08-21", date(2026, 8, 15)),   # Friday -- last day of the same week
    ("2026-08-22", date(2026, 8, 22)),   # the next Saturday starts a new week
    ("2026-08-14", date(2026, 8, 8)),    # Friday, previous week
])
def test_a_week_runs_saturday_to_friday(day, saturday):
    assert _rows([_one(**{"Log Time": day})])["week_start"][0] == saturday


def test_week_bucketing_agrees_with_the_read_model():
    """ingest and metrics must never disagree about which week a day is in."""
    metrics_spec = importlib.util.spec_from_file_location("dash_logs_metrics", DASH / "metrics.py")
    metrics = importlib.util.module_from_spec(metrics_spec)
    metrics_spec.loader.exec_module(metrics)

    days = [date(2026, 8, 1) + __import__("datetime").timedelta(days=i) for i in range(40)]
    frame = _rows([_one(**{"Log Time": d.isoformat()}) for d in days])
    assert list(frame["week_start"]) == [metrics.week_start(d) for d in days]


@pytest.mark.parametrize("raw", ["", "n/a", "--", "not recorded", "null"])
def test_a_log_with_no_readable_date_is_skipped(raw):
    frame = _rows([_one(**{"Log Time": raw}), _one()])
    assert frame.height == 1


def test_skipped_rows_are_counted_on_the_load():
    raw = pl.DataFrame([_one(**{"Log Time": "n/a"}), _one(), _one(**{"Note": ""})],
                       schema={k: pl.Utf8 for k in _one()})
    resolved = apply_spec(raw, ingest.COLUMNS["logs"]).frame
    final = ingest.finalize("logs", resolved)
    counts = ingest.stats("logs", resolved, final)
    assert counts == {"input_rows": 3, "undated_rows": 1, "duplicate_ids": 0,
                      "blank_note_rows": 2, "blank_introducer_rows": 0}


# --------------------------------------------------------------------------
# the natural key
# --------------------------------------------------------------------------

def test_identical_logs_on_the_same_day_stay_distinct():
    frame = _rows([_one(**{"Note": "Called."}), _one(**{"Note": "Called."})])
    assert frame.height == 2
    assert frame["log_uid"].n_unique() == 2


def test_the_key_is_stable_across_re_uploads():
    rows = [_one(**{"Note": "A"}), _one(**{"Note": "B"}), _one(**{"Note": "A"})]
    assert list(_rows(rows)["log_uid"]) == list(_rows(rows)["log_uid"])


def test_changing_a_field_changes_the_key():
    before = _rows([_one(**{"Created By": "Ana"})])["log_uid"][0]
    after = _rows([_one(**{"Created By": "Ben"})])["log_uid"][0]
    assert before != after


# --------------------------------------------------------------------------
# note sentiment
# --------------------------------------------------------------------------

def _score(note: str):
    row = _rows([_one(**{"Note": note})])
    return row["note_score"][0], row["note_hits"][0]


def test_a_note_with_no_lexicon_term_is_unscored_not_zero():
    score, hits = _score("Sent the intake calendar.")
    assert score is None and hits == 0


def test_a_blank_note_is_unscored():
    score, hits = _score("")
    assert score is None and hits == 0


@pytest.mark.parametrize("note", [
    "Very interested in the September intake.",
    "Great meeting, agreed the terms. Signed today.",
])
def test_positive_notes_score_positive(note):
    score, hits = _score(note)
    assert hits > 0 and score > 0


@pytest.mark.parametrize("note", [
    "Frustrated about the delayed offer letters, escalated.",
    "Complaint about commission. Disappointed.",
])
def test_negative_notes_score_negative(note):
    score, hits = _score(note)
    assert hits > 0 and score < 0


def test_negation_is_struck_out_before_positives_are_counted():
    """'not interested' must not cancel itself against the 'interested' inside it."""
    score, hits = _score("Not interested at the moment.")
    assert hits == 1 and score == pytest.approx(-1.0)


def test_no_response_beats_the_bare_word_response():
    score, _ = _score("No response after three emails.")
    assert score == pytest.approx(-1.0)


def test_a_mixed_note_lands_between_the_extremes():
    score, hits = _score("Positive call, but frustrated about the delay.")
    assert hits >= 2 and -1.0 < score < 1.0


def test_short_words_do_not_fire_inside_longer_ones():
    """'won' must not match 'wonderful' -- terms are closed with a word boundary."""
    score, hits = _score("A wonderful window into their process.")
    assert hits == 0 and score is None


def test_stems_still_match_their_family():
    for note in ("Escalated to the team.", "Escalation raised.", "Escalating now."):
        _, hits = _score(note)
        assert hits == 1, note


def test_the_score_never_leaves_the_minus_one_to_one_range():
    notes = ["Great, excellent, strong, happy, confident.",
             "Poor, bad, weak, slow, difficult, rejected.",
             "Interested but delayed and stuck."]
    frame = _rows([_one(**{"Note": n}) for n in notes])
    assert all(-1.0 <= s <= 1.0 for s in frame["note_score"])


def test_note_words_counts_words_not_characters():
    assert _rows([_one(**{"Note": "Called, no answer."})])["note_words"][0] == 3


# --------------------------------------------------------------------------
# the live export
# --------------------------------------------------------------------------
# The CRM writes JavaScript's Date.toString() and ships three columns the
# original spec did not name. Reading it wrongly is not a parse error: every row
# is silently undated, the table loads empty, and the dashboard goes dark.

REAL_ROW = (
    '"6a8c23540e503fcd7c5b38a2","VIPRA CONSULT","F2FVisits","",'
    f'"{JS_TIME}","","Compliance training for a student","West Africa B2B SRMs 1",'
    '"Obechi  Rachel Ogiga"\n'
)


def test_the_live_export_loads_rather_than_emptying_the_table():
    """The regression that took the dashboard dark: 6,977 rows, 0 loaded."""
    frame = read_table("logs.csv", (REAL_HEADER + REAL_ROW).encode())
    resolution = apply_spec(frame, ingest.COLUMNS["logs"])
    assert not resolution.missing
    out = ingest.finalize("logs", resolution.frame)
    assert out.height == 1
    assert out["logged_on"][0] == date(2026, 8, 24)
    assert out["week_start"][0] == date(2026, 8, 22)      # the Saturday before


def test_every_column_of_the_live_export_resolves():
    resolution = apply_spec(read_table("logs.csv", (REAL_HEADER + REAL_ROW).encode()),
                            ingest.COLUMNS["logs"])
    assert resolution.mapping == {
        "log_id": "_id", "call_type": "Call Type", "log_type": "Log Type",
        "log_time": "Log Time", "introducer_name": "Introducers Name",
        "outcome": "Outcome", "managed_by_team": "Managed By Team",
        "created_by": "Created By", "note": "Note",
    }


def test_call_type_does_not_steal_the_log_type_column():
    """Both headers end in "type"; the looser token match must not swap them."""
    row = REAL_ROW.replace('"F2FVisits","",', '"Call","Inbound",')
    out = ingest.finalize("logs", apply_spec(
        read_table("x.csv", (REAL_HEADER + row).encode()), ingest.COLUMNS["logs"]).frame)
    assert out["log_type"][0] == "Call"
    assert out["call_type"][0] == "Inbound"


@pytest.mark.parametrize("raw,expected", [
    ("Mon Aug 24 2026 10:55:45 GMT+0000 (Coordinated Universal Time)", date(2026, 8, 24)),
    ("Wed Oct 08 2025 09:49:35 GMT+0000 (Coordinated Universal Time)", date(2025, 10, 8)),
    # the offset is honoured, not assumed: 23:30 at +0530 is still the 6th in UTC
    ("Tue Jan 06 2026 23:30:00 GMT+0530 (India Standard Time)", date(2026, 1, 6)),
    # and 00:10 at -0500 is the 15th in UTC, not the 14th
    ("Sat Aug 15 2026 00:10:00 GMT-0500 (Eastern Daylight Time)", date(2026, 8, 15)),
])
def test_javascript_date_strings_parse_to_the_utc_day(raw, expected):
    assert _rows([_one(**{"Log Time": raw})])["logged_on"][0] == expected


def test_the_older_formats_still_parse_alongside_the_javascript_one():
    """Adding the live format must not cost the formats already supported."""
    frame = _rows([_one(**{"Log Time": JS_TIME}), _one(**{"Log Time": "2026-08-12"}),
                   _one(**{"Log Time": "12/08/2026 14:33"})])
    assert frame.height == 3
    assert list(frame["logged_on"]) == [date(2026, 8, 24), date(2026, 8, 12), date(2026, 8, 12)]


def test_the_crm_id_is_the_natural_key_when_the_export_has_one():
    """A real id survives someone editing the note; a content hash does not."""
    before = _rows([_one(**{"_id": "abc123", "Note": "first version"})])
    after = _rows([_one(**{"_id": "abc123", "Note": "corrected version"})])
    assert before["log_uid"][0] == after["log_uid"][0] == "abc123"


def test_a_repeated_id_is_kept_once_and_counted():
    raw = pl.DataFrame([_one(**{"_id": "dup"}), _one(**{"_id": "dup"}), _one(**{"_id": "ok"})],
                       schema={k: pl.Utf8 for k in _one()})
    resolved = apply_spec(raw, ingest.COLUMNS["logs"]).frame
    final = ingest.finalize("logs", resolved)
    assert final.height == 2
    assert ingest.stats("logs", resolved, final)["duplicate_ids"] == 1


def test_without_an_id_the_content_hash_is_still_used():
    frame = _rows([_one(**{"Note": "a"}), _one(**{"Note": "a"})])
    assert frame.height == 2                       # two identical logs stay distinct
    assert frame["log_uid"].n_unique() == 2


def test_outcome_and_call_type_are_kept():
    out = _rows([_one(**{"Outcome": "NoAnswer", "Call Type": "Outbound"})])
    assert out["outcome"][0] == "NoAnswer"
    assert out["call_type"][0] == "Outbound"
