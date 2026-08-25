"""The read model, run against real SQL over a throwaway load.

Every definition asserted here is one written down in context.md. If a rule
changes there, one of these should fail.
"""
from datetime import date, timedelta

import pytest

# Three consecutive Saturdays, comfortably in the past so nothing here depends
# on when the suite is run.
W1, W2, W3 = date(2026, 1, 3), date(2026, 1, 10), date(2026, 1, 17)


def _log(day, **overrides):
    return {"logged_on": day, **overrides}


def _scored(day, score, hits=2, **overrides):
    return _log(day, **{"note": "synthetic", "note_words": 1,
                        "note_score": score, "note_hits": hits, **overrides})


# --------------------------------------------------------------------------
# week arithmetic
# --------------------------------------------------------------------------

@pytest.mark.parametrize("day,saturday", [
    (date(2026, 8, 15), date(2026, 8, 15)),   # Saturday
    (date(2026, 8, 16), date(2026, 8, 15)),   # Sunday
    (date(2026, 8, 21), date(2026, 8, 15)),   # Friday, same week
    (date(2026, 8, 22), date(2026, 8, 22)),   # next Saturday
])
def test_week_start_is_the_saturday_on_or_before(metrics, day, saturday):
    assert metrics.week_start(day) == saturday


def test_current_week_is_the_newest_that_has_already_started(metrics):
    """Not max(week): an export pulled mid-week carries a barely-begun one."""
    weeks = [W1, W2, W3]
    # standing in W2, the week beginning W3 has not started yet
    assert metrics.pick_current_week(weeks, today=W2 + timedelta(days=3)) == W2
    # once W3 has begun it is the anchor, even on its first day
    assert metrics.pick_current_week(weeks, today=W3) == W3
    assert metrics.pick_current_week(weeks, today=W3 + timedelta(days=40)) == W3


def test_current_week_falls_back_to_the_oldest_when_the_whole_file_is_future(metrics):
    assert metrics.pick_current_week([W2, W3], today=W1) == W2


def test_no_weeks_at_all_is_a_view_error(metrics, logs):
    from app.views import ViewError
    with pytest.raises(ViewError):
        logs.overview()


# --------------------------------------------------------------------------
# section 1: the selected week
# --------------------------------------------------------------------------

def test_delta_compares_the_selected_week_to_the_one_before_it(logs):
    logs.load([
        *[_log(W1, log_type="Call") for _ in range(5)],
        *[_log(W2, log_type="Call") for _ in range(8)],
        *[_log(W2, log_type="Email") for _ in range(2)],
    ])
    week = logs.overview(week=W2.isoformat())["week_kpis"]
    assert week["total"] == 10 and week["previous_total"] == 5 and week["delta"] == 5
    by_type = {r["type"]: r for r in week["by_type"]}
    assert by_type["Call"]["n"] == 8 and by_type["Call"]["delta"] == 3
    assert by_type["Email"]["n"] == 2 and by_type["Email"]["delta"] == 2


def test_the_delta_ignores_the_table_range(logs):
    """A 1-week table range must not change what Δ compares against."""
    logs.load([_log(W1), _log(W1), *[_log(W2) for _ in range(4)]])
    narrow = logs.overview(week=W2.isoformat(), weeks="1")
    assert narrow["range"]["from"] == W2                     # the table is one week
    assert narrow["week_kpis"]["delta"] == 2                 # Δ still sees W1


def test_share_of_week_sums_to_one(logs):
    logs.load([*[_log(W2, log_type="Call") for _ in range(3)],
               *[_log(W2, log_type="Email") for _ in range(1)]])
    shares = [r["share"] for r in logs.overview(week=W2.isoformat())["week_kpis"]["by_type"]]
    assert sum(shares) == pytest.approx(1.0)


def test_a_blank_log_type_is_named_not_dropped(logs):
    logs.load([_log(W2, log_type=None), _log(W2, log_type="Call")])
    types = {r["type"] for r in logs.overview(week=W2.isoformat())["week_kpis"]["by_type"]}
    assert types == {"Unspecified", "Call"}


def test_the_oldest_week_in_the_file_has_no_previous_week(logs):
    logs.load([_log(W1), _log(W2)])
    first = logs.overview(week=W1.isoformat())
    assert first["previous_week"] is None
    assert first["week_kpis"]["previous_total"] == 0
    assert first["has_earlier"] is False and first["has_later"] is True


def test_a_week_the_file_does_not_hold_is_refused(logs):
    from app.views import ViewError
    logs.load([_log(W2)])
    with pytest.raises(ViewError):
        logs.overview(week=W1.isoformat())


# --------------------------------------------------------------------------
# section 2: week on week
# --------------------------------------------------------------------------

def test_the_series_holds_one_count_per_week_per_type(logs):
    logs.load([_log(W1, log_type="Call"), _log(W2, log_type="Call"),
               _log(W2, log_type="Email"), _log(W3, log_type="Call")])
    series = logs.overview(week=W3.isoformat())["series"]
    assert series["weeks"] == [W1, W2, W3]
    by_type = {s["type"]: s["counts"] for s in series["by_type"]}
    assert by_type["Call"] == [1, 1, 1]
    assert by_type["Email"] == [0, 1, 0]          # a week with none of a type is a zero
    assert series["totals"] == [1, 2, 1]


def test_the_chart_window_is_capped_by_chart_weeks(logs):
    logs.load([_log(W1), _log(W2), _log(W3)])
    assert logs.overview(week=W3.isoformat(), chart_weeks="2")["series"]["weeks"] == [W2, W3]


def test_the_chart_ends_at_the_selected_week(logs):
    logs.load([_log(W1), _log(W2), _log(W3)])
    assert logs.overview(week=W2.isoformat())["series"]["weeks"] == [W1, W2]


# --------------------------------------------------------------------------
# section 3: top performers
# --------------------------------------------------------------------------

def test_top_tables_rank_by_volume_and_honour_top_n(logs):
    logs.load([*[_log(W2, created_by="Ana") for _ in range(5)],
               *[_log(W2, created_by="Ben") for _ in range(3)],
               *[_log(W2, created_by="Cy") for _ in range(1)]])
    top = logs.overview(week=W2.isoformat(), top="2")["top"]["creators"]
    assert [r["name"] for r in top] == ["Ana", "Ben"]
    assert top[0]["n"] == 5


def test_the_introducer_sub_line_keeps_two_names_and_counts_the_rest(logs):
    logs.load([_log(W2, introducer_name="P1", managed_by_team=t, created_by=c)
               for t, c in zip(["T1", "T2", "T3", "T4"], ["Ana", "Ben", "Cy", "Dee"])])
    row = logs.overview(week=W2.isoformat())["top"]["introducers"][0]
    assert row["teams"] == ["T1", "T2"] and row["teams_more"] == 2
    assert row["creators"] == ["Ana", "Ben"] and row["creators_more"] == 2


def test_the_sub_line_reports_no_overflow_when_there_is_none(logs):
    logs.load([_log(W2, introducer_name="P1", managed_by_team="T1", created_by="Ana")])
    row = logs.overview(week=W2.isoformat())["top"]["introducers"][0]
    assert row["teams"] == ["T1"] and row["teams_more"] == 0 and row["creators_more"] == 0


def test_the_tables_span_the_range_not_the_selected_week(logs):
    logs.load([*[_log(W1) for _ in range(4)], *[_log(W2) for _ in range(1)]])
    wide = logs.overview(week=W2.isoformat(), weeks="2")
    narrow = logs.overview(week=W2.isoformat(), weeks="1")
    assert wide["top"]["introducers"][0]["n"] == 5
    assert narrow["top"]["introducers"][0]["n"] == 1
    assert wide["range"]["rows"] == 5 and narrow["range"]["rows"] == 1


def test_blank_attribution_is_named_rather_than_lost(logs):
    logs.load([_log(W2, created_by=None, managed_by_team=None, introducer_name=None)])
    top = logs.overview(week=W2.isoformat())["top"]
    assert top["creators"][0]["name"] == "Unattributed"
    assert top["teams"][0]["name"] == "Unassigned"
    assert top["introducers"][0]["name"] == "Unnamed"


# --------------------------------------------------------------------------
# section 4: sentiment
# --------------------------------------------------------------------------

def test_unscored_notes_count_as_neutral_not_as_missing(logs):
    """Two positives among two silent notes is +0.5, not +1.0."""
    logs.load([_scored(W2, 1.0), _scored(W2, 1.0), _log(W2, note="quiet"), _log(W2, note="quiet")])
    sentiment = logs.overview(week=W2.isoformat())["sentiment"]
    assert sentiment["n"] == 4 and sentiment["scored"] == 2
    assert sentiment["index"] == pytest.approx(0.5)


def test_the_index_counts_positives_and_negatives_against_each_other(logs):
    logs.load([_scored(W2, 1.0), _scored(W2, -1.0)])
    sentiment = logs.overview(week=W2.isoformat())["sentiment"]
    assert sentiment["positive"] == 1 and sentiment["negative"] == 1
    assert sentiment["index"] == pytest.approx(0.0)


def test_quotes_are_the_strongest_notes_on_each_side(logs):
    logs.load([
        _scored(W2, 1.0, hits=4, note="signed and onboarded", introducer_name="Best"),
        _scored(W2, 0.2, hits=2, note="mildly good", introducer_name="Mild"),
        _scored(W2, -1.0, hits=3, note="complaint escalated", introducer_name="Worst"),
    ])
    quotes = logs.overview(week=W2.isoformat())["sentiment"]["quotes"]
    assert quotes["pos"][0]["introducer"] == "Best"
    assert quotes["neg"][0]["introducer"] == "Worst"
    assert all(q["score"] < 0 for q in quotes["neg"])


def test_sentiment_follows_the_same_scope_as_the_tables(logs):
    logs.load([_scored(W1, -1.0), _scored(W2, 1.0)])
    assert logs.overview(week=W2.isoformat(), weeks="1")["sentiment"]["index"] == pytest.approx(1.0)
    assert logs.overview(week=W2.isoformat(), weeks="2")["sentiment"]["index"] == pytest.approx(0.0)


# --------------------------------------------------------------------------
# filters
# --------------------------------------------------------------------------

def test_the_team_filter_narrows_everything(logs):
    logs.load([*[_log(W2, managed_by_team="T1") for _ in range(3)],
               *[_log(W2, managed_by_team="T2") for _ in range(7)],
               *[_log(W1, managed_by_team="T1") for _ in range(1)]])
    filtered = logs.overview(week=W2.isoformat(), team="T1")
    assert filtered["week_kpis"]["total"] == 3          # the KPI row moved
    assert filtered["week_kpis"]["previous_total"] == 1
    assert filtered["series"]["totals"] == [1, 3]      # so did the chart
    assert filtered["range"]["rows"] == 4              # and the tables


def test_the_type_filter_narrows_the_tables_but_not_the_kpi_row(logs):
    """The KPI row and the chart are *by* type; filtering them leaves one bar."""
    logs.load([*[_log(W2, log_type="Call") for _ in range(6)],
               *[_log(W2, log_type="Email") for _ in range(4)]])
    filtered = logs.overview(week=W2.isoformat(), type="Call")
    assert filtered["week_kpis"]["total"] == 10                      # unchanged
    assert len(filtered["series"]["by_type"]) == 2                   # unchanged
    assert filtered["range"]["rows"] == 6                            # scoped
    assert filtered["top"]["creators"][0]["n"] == 6


def test_the_filter_menus_list_the_whole_file_not_the_selected_week(logs):
    logs.load([_log(W1, log_type="Meeting", managed_by_team="Gone"), _log(W2, log_type="Call")])
    overview = logs.overview(week=W2.isoformat())
    assert {r["type"] for r in overview["log_types"]} == {"Meeting", "Call"}
    assert "Gone" in {r["team"] for r in overview["teams"]}


# --------------------------------------------------------------------------
# drill-down
# --------------------------------------------------------------------------

def test_rows_returns_the_logs_behind_the_range(logs):
    logs.load([_log(W1, note="old"), _log(W2, note="new")])
    assert len(logs.rows(week=W2.isoformat(), weeks="2")["rows"]) == 2


def test_only_week_restricts_the_drill_down_to_the_selected_week(logs):
    logs.load([_log(W1, note="old"), _log(W2, note="new")])
    only = logs.rows(week=W2.isoformat(), weeks="2", only="week")
    assert [r["note"] for r in only["rows"]] == ["new"]


def test_rows_honours_the_limit(logs):
    logs.load([_log(W2) for _ in range(10)])
    assert len(logs.rows(week=W2.isoformat(), limit="3")["rows"]) == 3


def test_a_non_numeric_parameter_is_a_readable_error(logs):
    from app.views import ViewError
    logs.load([_log(W2)])
    with pytest.raises(ViewError, match="must be a number"):
        logs.overview(week=W2.isoformat(), weeks="two")
    with pytest.raises(ViewError, match="YYYY-MM-DD"):
        logs.overview(week="last tuesday")


# --------------------------------------------------------------------------
# section 3: the log-type columns, the lifetime figure, and "view more"
# --------------------------------------------------------------------------

def test_each_row_carries_a_count_per_log_type_that_sums_to_its_total(logs):
    logs.load([*[_log(W2, log_type="Call", created_by="Ana") for _ in range(4)],
               *[_log(W2, log_type="Email", created_by="Ana") for _ in range(2)],
               *[_log(W2, log_type="Call", created_by="Ben") for _ in range(1)]])
    rows = {r["name"]: r for r in logs.overview(week=W2.isoformat())["top"]["creators"]}
    assert rows["Ana"]["by_type"] == {"Call": 4, "Email": 2}
    assert rows["Ana"]["n"] == sum(rows["Ana"]["by_type"].values()) == 6
    # a type this name never used is absent rather than zero
    assert "Email" not in rows["Ben"]["by_type"]


def test_the_type_columns_follow_the_selected_range(logs):
    logs.load([_log(W1, log_type="Call"), _log(W2, log_type="Email")])
    narrow = logs.overview(week=W2.isoformat(), weeks="1")["top"]["creators"][0]
    wide = logs.overview(week=W2.isoformat(), weeks="2")["top"]["creators"][0]
    assert narrow["by_type"] == {"Email": 1}
    assert wide["by_type"] == {"Call": 1, "Email": 1}


def test_lifetime_ignores_the_range(logs):
    """The total answers for what is on screen; lifetime for the whole file."""
    logs.load([*[_log(W1) for _ in range(3)], _log(W2)])
    row = logs.overview(week=W2.isoformat(), weeks="1")["top"]["introducers"][0]
    assert row["n"] == 1 and row["lifetime"] == 4


def test_lifetime_ignores_the_filters_too(logs):
    logs.load([_log(W2, log_type="Call", introducer_name="P1"),
               _log(W2, log_type="Email", introducer_name="P1")])
    row = logs.overview(week=W2.isoformat(), type="Call")["top"]["introducers"][0]
    assert row["n"] == 1 and row["lifetime"] == 2


def test_the_tables_report_how_many_names_they_were_drawn_from(logs):
    logs.load([_log(W2, created_by=f"Person {i}") for i in range(15)])
    overview = logs.overview(week=W2.isoformat(), top="10")
    assert len(overview["top"]["creators"]) == 10
    assert overview["top_totals"]["creators"] == 15       # what "view more (5)" counts


def test_view_more_returns_every_row_in_the_same_order(logs):
    logs.load([_log(W2, created_by=f"Person {i:02d}") for i in range(15)])
    top = logs.overview(week=W2.isoformat(), top="10")["top"]["creators"]
    full = logs.metrics.leaderboard(logs.ctx, {"dimension": "creators", "week": W2.isoformat()})
    assert full["total"] == len(full["rows"]) == 15
    # the ten already on the page are the first ten here, in the same order
    assert [r["name"] for r in full["rows"][:10]] == [r["name"] for r in top]


def test_view_more_reads_the_same_scope_as_the_table_it_came_from(logs):
    """Opening the pane must not silently widen the range or drop a filter."""
    logs.load([_log(W1, log_type="Call"), _log(W2, log_type="Call"), _log(W2, log_type="Email")])
    full = logs.metrics.leaderboard(
        logs.ctx, {"dimension": "introducers", "week": W2.isoformat(), "weeks": "1", "type": "Call"})
    assert full["range"]["from"] == W2 and full["filters"]["type"] == "Call"
    assert [r["n"] for r in full["rows"]] == [1]


@pytest.mark.parametrize("dimension", ["creators", "teams", "introducers"])
def test_every_dimension_is_offered(logs, dimension):
    logs.load([_log(W2)])
    full = logs.metrics.leaderboard(logs.ctx, {"dimension": dimension, "week": W2.isoformat()})
    assert full["rows"] and full["label"]


def test_an_unknown_dimension_is_a_readable_error(logs):
    from app.views import ViewError
    logs.load([_log(W2)])
    with pytest.raises(ViewError, match="unknown dimension"):
        logs.metrics.leaderboard(logs.ctx, {"dimension": "log_type", "week": W2.isoformat()})
