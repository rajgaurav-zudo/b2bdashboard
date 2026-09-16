"""Rules from context.md, asserted against the read model.

The three that everything else rests on: a stage is an event rather than a
status, `created = active + closed` within every stage, and "today" is the
export's newest stage date rather than the clock's.
"""
from datetime import date

import pytest

# 2026-06-10 is a Wednesday, so "this week" is Mon 8th - Sun 14th. Every book
# below plants its newest stage date here, which makes it the anchor.
ANCHOR = "2026-06-10"
WEEK = (date(2026, 6, 8), date(2026, 6, 14))


def _row(**kw):
    return {"intake_year": 2026, "cycle_index": 1, **kw}


# --------------------------------------------------------------------------
# the window, resolved without touching the database
# --------------------------------------------------------------------------

def test_week_starts_on_monday(metrics):
    """The design's calendar starts its weeks on Monday, and a range filter
    whose weeks disagree with the calendar that picks them is found by
    arithmetic rather than by reading."""
    assert metrics.week_start(date(2026, 6, 8)) == date(2026, 6, 8)     # Monday itself
    assert metrics.week_start(date(2026, 6, 10)) == date(2026, 6, 8)
    assert metrics.week_start(date(2026, 6, 14)) == date(2026, 6, 8)    # Sunday still belongs


@pytest.mark.parametrize("preset,expected", [
    ("today", (date(2026, 6, 10), date(2026, 6, 10))),
    ("yesterday", (date(2026, 6, 9), date(2026, 6, 9))),
    ("this_week", WEEK),
    ("last_week", (date(2026, 6, 1), date(2026, 6, 7))),
    ("this_month", (date(2026, 6, 1), date(2026, 6, 30))),
    ("last_month", (date(2026, 5, 1), date(2026, 5, 31))),
    ("this_year", (date(2026, 1, 1), date(2026, 12, 31))),
])
def test_presets_resolve_against_the_anchor(metrics, preset, expected):
    assert metrics.resolve_preset(preset, date(2026, 6, 10)) == expected


def test_month_end_is_found_by_arithmetic_not_by_a_table(metrics):
    assert metrics.resolve_preset("this_month", date(2026, 2, 15))[1] == date(2026, 2, 28)
    assert metrics.resolve_preset("this_month", date(2024, 2, 15))[1] == date(2024, 2, 29)


def test_unknown_preset_is_a_view_error(metrics):
    from app.views import ViewError
    with pytest.raises(ViewError):
        metrics.resolve_preset("last_fortnight", date(2026, 6, 10))


def test_last_year_falls_back_on_the_29th_of_february(metrics):
    assert metrics.last_year(date(2026, 6, 10)) == date(2025, 6, 10)
    assert metrics.last_year(date(2024, 2, 29)) == date(2023, 2, 28)


def test_explicit_dates_beat_the_preset_and_are_ordered(metrics):
    window = metrics._range({"range": "this_year", "from": "2026-03-04", "to": "2026-03-01"},
                            date(2026, 6, 10))
    assert (window["from"], window["to"]) == (date(2026, 3, 1), date(2026, 3, 4))
    assert window["id"] == "custom"


def test_custom_without_dates_falls_back_to_the_default_range(metrics):
    """Clearing the range returns to This week, not to nothing: an empty range
    would report an empty pipeline as if it were a quiet week."""
    assert metrics._range({"range": "custom"}, date(2026, 6, 10))["id"] == metrics.DEFAULT_PRESET
    assert metrics._range({}, date(2026, 6, 10))["id"] == "this_week"


def test_introducers_are_pipe_separated(metrics):
    """A partner name may hold a comma and cannot hold a pipe."""
    assert metrics._names({"introducers": "Global Connect, Ltd|Acme"}) == \
        ["Global Connect, Ltd", "Acme"]
    assert metrics._names({"introducers": ""}) == []


def test_an_intake_cycle_needs_a_year(metrics):
    from app.views import ViewError
    assert metrics._intake({"intake_year": "2026", "intake_cycle": "2"}) == (2026, 2)
    assert metrics._intake({}) == (0, -1)
    with pytest.raises(ViewError):
        metrics._intake({"intake_cycle": "1"})
    with pytest.raises(ViewError):
        metrics._intake({"intake_year": "2026", "intake_cycle": "7"})


# --------------------------------------------------------------------------
# the anchor
# --------------------------------------------------------------------------

def test_the_anchor_is_the_newest_stage_date_in_the_file(book):
    book.load([
        _row(at_draft="2026-01-05"),
        _row(at_draft="2026-05-01", at_enrolled=ANCHOR),
    ])
    out = book.overview()
    assert out["anchor"] == date(2026, 6, 10)
    assert (out["range"]["from"], out["range"]["to"]) == WEEK


def test_a_file_with_no_stage_dates_says_so(book):
    """An export from before the timestamp columns existed loads cleanly and
    would otherwise render a page of zeroes."""
    from app.views import ViewError
    book.load([_row(deposit_fully_paid=True)])
    with pytest.raises(ViewError):
        book.overview()


# --------------------------------------------------------------------------
# a stage is an event
# --------------------------------------------------------------------------

def test_a_stage_counts_entries_in_the_window_not_the_status_today(book):
    book.load([
        _row(at_applied="2026-06-09", at_enrolled=ANCHOR),   # applied inside the week
        _row(at_applied="2026-06-01"),                       # last week
        _row(at_applied="2026-06-14"),                       # Sunday still belongs
    ])
    assert book.widgets()["applied"]["created"] == 2
    assert book.widgets(range="last_week")["applied"]["created"] == 1


def test_one_application_appears_in_every_stage_it_passed_through(book):
    book.load([_row(at_draft="2026-06-08", at_applied="2026-06-09",
                    at_offer="2026-06-09", at_enrolled=ANCHOR)])
    widgets = book.widgets()
    assert [widgets[w]["created"] for w in ("draft", "applied", "offer", "enrolled")] == [1, 1, 1, 1]


def test_created_is_active_plus_closed_in_every_stage(book):
    book.load([
        _row(at_applied="2026-06-09", at_enrolled=ANCHOR),
        _row(at_applied="2026-06-09", closed_lost=True),
        _row(at_applied="2026-06-10", closed_lost=True),
    ])
    applied = book.widgets()["applied"]
    assert (applied["created"], applied["active"], applied["closed"]) == (3, 1, 2)
    for stage in book.overview()["stages"]:
        assert stage["created"] == stage["active"] + stage["closed"]
    assert applied["closed_pct"] == 67          # read against the number above it


def test_percentages_are_zero_rather_than_a_division_by_zero(book):
    book.load([_row(at_enrolled=ANCHOR)])
    draft = book.widgets()["draft"]
    assert (draft["created"], draft["active_pct"], draft["closed_pct"]) == (0, 0, 0)


# --------------------------------------------------------------------------
# the two stages that are states
# --------------------------------------------------------------------------

def test_states_ignore_the_window_entirely(book):
    """A partial deposit and an initiated deferral have no timestamp, so
    narrowing them by a date range would mean borrowing another column's date."""
    book.load([
        _row(at_draft="2020-01-01", deposit_partial=True),
        _row(at_draft="2020-01-01", deposit_fully_paid=True, deferral_initiated=True),
        _row(at_enrolled=ANCHOR),
    ])
    for preset in ("today", "this_week", "this_year"):
        awaiting = book.widgets(range=preset)["awaiting"]
        assert awaiting["created"] == 2, preset
    assert book.widgets()["awaiting"]["windowed"] is False      # the card says "as of"


def test_a_settled_deferral_is_not_awaiting_approval(book):
    book.load([
        _row(at_enrolled=ANCHOR, deposit_fully_paid=True, deferral_initiated=True),
        _row(deposit_fully_paid=True, deferral_initiated=True, deferral_approved=True),
        _row(deposit_fully_paid=True),
        _row(deferral_initiated=True),          # initiated without a paid deposit is not DAA
    ])
    stages = book.stages()
    assert stages["deferral"]["created"] == 1


def test_states_still_answer_to_the_introducer_and_intake_filters(book):
    book.load([
        _row(at_enrolled=ANCHOR, introducer_name="A"),
        _row(introducer_name="A", deposit_partial=True),
        _row(introducer_name="B", deposit_partial=True),
        _row(introducer_name="A", deposit_partial=True, intake_year=2025),
    ])
    assert book.widgets(introducers="A")["awaiting"]["created"] == 2
    assert book.widgets(introducers="A", intake_year="2026")["awaiting"]["created"] == 1


# --------------------------------------------------------------------------
# the group cards
# --------------------------------------------------------------------------

def test_a_group_is_the_sum_of_its_members(book):
    """An application that paid a deposit, received a CoE and applied for a visa
    inside the window entered three stages and is counted three times -- exactly
    as it would be on three separate cards."""
    book.load([
        _row(at_deposit="2026-06-09", at_coe="2026-06-09",
             at_visa_applied="2026-06-10", at_enrolled=ANCHOR),
        _row(at_deposit="2026-06-11"),
    ])
    deposits = book.widgets()["deposits"]
    assert deposits["created"] == 4
    assert [m["created"] for m in deposits["members"]] == [2, 1, 1]
    assert deposits["kind"] == "group" and deposits["windowed"] is True


def test_every_widget_the_design_asks_for_is_on_the_page(metrics, book):
    book.load([_row(at_enrolled=ANCHOR)])
    assert [w["id"] for w in book.overview()["widgets"]] == metrics.WIDGETS
    assert len(metrics.WIDGETS) == 8          # eight on one line, no horizontal scroll


# --------------------------------------------------------------------------
# compare
# --------------------------------------------------------------------------

def test_compare_is_off_unless_asked_for(book):
    book.load([_row(at_applied="2026-06-09", at_enrolled=ANCHOR)])
    assert book.overview()["compare"] is False
    assert "previous" not in book.widgets()["applied"]


def test_compare_reads_the_same_window_a_year_earlier(book):
    book.load([
        _row(at_applied="2026-06-09", at_enrolled=ANCHOR),
        _row(at_applied="2026-06-10"),
        _row(at_applied="2025-06-09"),          # inside last year's same week
        _row(at_applied="2025-07-09"),          # outside it
    ])
    applied = book.widgets(compare="1")["applied"]
    assert applied["created"] == 2 and applied["previous"]["created"] == 1
    assert applied["delta"] == 100.0


def test_a_delta_against_nothing_is_none_rather_than_infinity(book):
    book.load([_row(at_applied="2026-06-09", at_enrolled=ANCHOR)])
    assert book.widgets(compare="1")["applied"]["delta"] is None


def test_a_state_has_no_last_year_to_be_compared_with(book):
    book.load([_row(at_enrolled=ANCHOR), _row(deposit_partial=True)])
    awaiting = book.widgets(compare="1")["awaiting"]
    assert "previous" not in awaiting
    assert book.stages(compare="1")["partial"].get("delta") is None


# --------------------------------------------------------------------------
# the filters, against the database
# --------------------------------------------------------------------------

def test_the_introducer_filter_selects_and_survives_a_comma(book):
    book.load([
        _row(at_applied="2026-06-09", introducer_name="Global Connect, Ltd", at_enrolled=ANCHOR),
        _row(at_applied="2026-06-09", introducer_name="Acme"),
        _row(at_applied="2026-06-09", introducer_name="Other"),
    ])
    assert book.widgets(introducers="Global Connect, Ltd")["applied"]["created"] == 1
    assert book.widgets(introducers="Global Connect, Ltd|Acme")["applied"]["created"] == 2
    assert book.overview(introducers="Acme")["scope_line"].startswith("Acme · ")


def test_the_intake_filter_narrows_by_year_then_by_cycle(book):
    book.load([
        _row(at_applied="2026-06-09", at_enrolled=ANCHOR, intake_year=2026, cycle_index=1),
        _row(at_applied="2026-06-09", intake_year=2026, cycle_index=2),
        _row(at_applied="2026-06-09", intake_year=2025, cycle_index=1),
    ])
    assert book.widgets()["applied"]["created"] == 3                       # any intake
    assert book.widgets(intake_year="2026")["applied"]["created"] == 2
    assert book.widgets(intake_year="2026", intake_cycle="1")["applied"]["created"] == 1
    intake = book.overview(intake_year="2026")["intake"]
    assert [r["y"] for r in intake["years"]] == [2026, 2025]
    assert [c["n"] for c in intake["cycles"]] == [0, 1, 1]                  # Jan, May, Sep


def test_the_commitment_panel_looks_past_the_intake_filter(book):
    """It compares one intake with the one before it, so it cannot be run inside
    a base already narrowed to a single intake -- that compares a year with
    itself and reports zero."""
    book.load([
        _row(at_enrolled=ANCHOR, intake_year=2026),
        _row(intake_year=2026, at_deposit="2026-03-01", deposit_fully_paid=True),
        _row(intake_year=2025, at_deposit="2025-03-01", deposit_fully_paid=True),  # before the cut
        _row(intake_year=2025, at_deposit="2025-11-01", deposit_fully_paid=True),  # after it
    ])
    commitment = book.overview(intake_year="2026")["commitment"]
    assert commitment["intake_year"] == 2026
    assert commitment["now_paid"] == 1
    assert commitment["prev_paid_to_date"] == 1        # cut at 2025-06-10
    assert commitment["prev_paid_total"] == 2


# --------------------------------------------------------------------------
# the tables
# --------------------------------------------------------------------------

def test_the_leaderboard_ranks_by_what_the_window_produced(book):
    book.load([
        _row(at_offer="2026-06-09", introducer_name="Quiet week", at_enrolled=ANCHOR),
        _row(at_applied="2026-01-02", introducer_name="Quiet week"),
        _row(at_applied="2026-01-03", introducer_name="Quiet week"),
        _row(at_draft="2026-06-08", introducer_name="Busy week"),
        _row(at_applied="2026-06-09", introducer_name="Busy week"),
        _row(at_offer="2026-06-10", introducer_name="Busy week"),
    ])
    assert [r["name"] for r in book.overview()["top"]] == ["Busy week", "Quiet week"]


def test_rows_no_introducer_owns_are_named_rather_than_dropped(book):
    book.load([
        _row(at_applied="2026-06-09", at_enrolled=ANCHOR, introducer_name=None),
        _row(at_applied="2026-06-09", introducer_name="Acme"),
    ])
    assert "Not attributed" in {r["name"] for r in book.overview()["top"]}


def test_the_wise_table_totals_agree_with_the_pipeline(book):
    book.load([
        _row(at_applied="2026-06-09", introducer_name="A", at_enrolled=ANCHOR),
        _row(at_applied="2026-06-09", introducer_name="B", closed_lost=True),
        _row(at_offer="2026-06-10", introducer_name="A"),
        _row(deposit_partial=True, introducer_name="B"),
    ])
    wise = book.wise()
    per_row = sum(r["total"]["created"] for r in wise["rows"])
    assert per_row == wise["totals"]["total"]["created"]
    assert [s["id"] for s in wise["stage_names"]] == [s["id"] for s in book.overview()["stages"]]


def test_the_wise_total_counts_stages_entered_and_not_the_states(book):
    """A total that added the states would be part window and part all time, and
    would move when the window did not."""
    book.load([
        _row(at_applied="2026-06-09", at_offer="2026-06-10", introducer_name="A",
             at_enrolled=ANCHOR),
        _row(deposit_partial=True, introducer_name="A"),
    ])
    row = next(r for r in book.wise()["rows"] if r["name"] == "A")
    cells = {c["id"]: c["created"] for c in row["cells"]}
    assert cells["partial"] == 1                    # the column still reports it
    assert row["total"]["created"] == 3             # applied, offer, enrolled
    assert book.wise()["totals"]["total"]["created"] == 3


def test_the_picker_lists_partners_by_lifetime_work_not_by_the_window(book):
    """A partner who did nothing this week is exactly the one someone opens this
    dashboard to look at."""
    book.load([
        _row(at_enrolled=ANCHOR, introducer_name="Recent"),
        _row(at_draft="2019-01-01", introducer_name="Dormant", deposit_fully_paid=True),
        _row(at_draft="2019-01-02", introducer_name="Dormant"),
    ])
    rows = book.introducers()["rows"]
    assert rows[0]["name"] == "Dormant" and rows[0]["n"] == 2 and rows[0]["deposits"] == 1
    assert [r["name"] for r in book.introducers(q="rec")["rows"]] == ["Recent"]


# --------------------------------------------------------------------------
# the 360 half
# --------------------------------------------------------------------------

def test_the_profile_needs_one_introducer_and_the_master_file(book):
    book.load(
        [_row(at_enrolled=ANCHOR, introducer_name="Acme"),
         _row(at_applied="2026-06-09", introducer_name="Acme")],
        introducers=[{"partner_name": "Acme", "lifecycle_stage": "Customer",
                      "country": "India", "srm_team": "North", "became_customer_year": 2023}],
    )
    profile = book.overview(introducers="Acme")["profile"]
    assert (profile["stage"], profile["country"], profile["since"]) == ("Customer", "India", 2023)
    assert book.overview()["profile"] is None                       # nobody selected
    assert book.overview(introducers="Acme|Other")["profile"] is None


def test_the_pipeline_is_readable_without_the_master_file(book):
    """A null load id matches no rows, so an unloaded master costs the profile
    card and nothing else -- not a 409 on the whole page."""
    book.ctx.loads["introducers"] = None
    book.load([_row(at_applied="2026-06-09", at_enrolled=ANCHOR, introducer_name="Acme")])
    out = book.overview(introducers="Acme")
    assert out["profile"] is None
    assert out["widgets"][2]["created"] == 1
    assert out["data"]["master_rows"] == 0


def test_lifetime_ignores_the_window_but_not_the_introducer(book):
    book.load([
        _row(at_applied="2019-01-01", at_offer="2019-02-01", introducer_name="Acme"),
        _row(at_enrolled=ANCHOR, introducer_name="Acme", deposit_fully_paid=True),
        _row(at_applied="2019-01-01", introducer_name="Other"),
    ])
    lifetime = book.overview(introducers="Acme")["lifetime"]
    assert (lifetime["apps"], lifetime["applied"], lifetime["offers"]) == (2, 1, 1)
    assert lifetime["deposits_live"] == 1
    assert lifetime["first_seen"] == date(2019, 1, 1)
    assert lifetime["last_seen"] == date(2026, 6, 10)
