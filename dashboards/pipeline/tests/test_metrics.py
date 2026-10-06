"""The rules of context.md, asserted against the dashboard's own SQL."""
import pytest


def test_student_sits_at_their_furthest_application(book):
    # two applications at Applied and one at Offer: one student, at Offer
    book.load([
        {"student_key": "S1", "intake": "2026-09", "on_applied": "2026-01-10"},
        {"student_key": "S1", "intake": "2026-09", "on_applied": "2026-01-11"},
        {"student_key": "S1", "intake": "2026-09", "on_applied": "2026-01-12", "on_offer": "2026-02-01"},
    ])
    s = book.stages(year="2026")
    assert s["applied"]["now"]["pipeline"]["total"] == 0
    assert s["offer"]["now"]["pipeline"]["total"] == 1
    assert s["applied"]["now"]["funnel"]["total"] == 1
    assert s["offer"]["now"]["funnel"]["total"] == 1


def test_pipeline_sums_to_total_and_funnel_is_cumulative(book):
    book.load([
        {"student_key": "A", "intake": "2026-01", "on_applied": "2025-10-01"},
        {"student_key": "B", "intake": "2026-01", "on_applied": "2025-10-01", "on_offer": "2025-11-01",
         "on_deposit": "2025-12-01"},
        {"student_key": "C", "intake": "2026-05", "on_applied": "2026-01-01", "on_offer": "2026-02-01",
         "on_deposit": "2026-03-01", "on_coe": "2026-03-10", "on_visa": "2026-04-01",
         "on_enrolled": "2026-05-05"},
    ])
    data = book.overview(year="2026")
    pipe = sum(s["now"]["pipeline"]["total"] for s in data["stages"])
    assert pipe == data["totals"]["now"]["total"] == 3
    funnel = [s["now"]["funnel"]["total"] for s in data["stages"]]
    assert funnel == [3, 2, 2, 1, 1, 1]


def test_quarters_narrow_to_their_intake_months(book):
    book.load([
        {"student_key": "Jan", "intake": "2026-01", "on_applied": "2025-10-01"},
        {"student_key": "Sep", "intake": "2026-09", "on_applied": "2026-03-01"},
        {"student_key": "Oct", "intake": "2026-10", "on_applied": "2026-03-01"},
    ])
    assert book.overview(year="2026", quarters="1")["totals"]["now"]["total"] == 1
    assert book.overview(year="2026", quarters="3")["totals"]["now"]["total"] == 1
    assert book.overview(year="2026", quarters="1|4")["totals"]["now"]["total"] == 2
    assert book.overview(year="2026")["totals"]["now"]["total"] == 3


def test_academic_year_runs_august_to_july(book):
    book.load([
        {"student_key": "Jul25", "intake": "2025-07", "on_applied": "2025-01-01"},
        {"student_key": "Aug25", "intake": "2025-08", "on_applied": "2025-01-01"},
        {"student_key": "Jan26", "intake": "2026-01", "on_applied": "2025-06-01"},
        {"student_key": "Jul26", "intake": "2026-07", "on_applied": "2026-01-01"},
        {"student_key": "Aug26", "intake": "2026-08", "on_applied": "2026-01-01"},
    ])
    data = book.overview(mode="academic", year="2025")
    assert data["totals"]["now"]["total"] == 3
    assert data["scope"]["label"].startswith("Academic year 2025-2026")
    # academic Q1 is Aug-Oct, Q2 Nov-Jan
    assert book.overview(mode="academic", year="2025", quarters="1")["totals"]["now"]["total"] == 1
    assert book.overview(mode="academic", year="2025", quarters="2")["totals"]["now"]["total"] == 1
    assert book.overview(mode="academic", year="2025", quarters="4")["totals"]["now"]["total"] == 1


def test_course_level_filter_is_multi_select_and_empty_means_all(book):
    book.load([
        {"student_key": "P", "intake": "2026-09", "on_applied": "2026-01-01", "course_level": "Postgraduate"},
        {"student_key": "U", "intake": "2026-09", "on_applied": "2026-01-01", "course_level": "Undergraduate"},
        {"student_key": "L", "intake": "2026-09", "on_applied": "2026-01-01", "course_level": "Language"},
    ])
    assert book.overview(year="2026")["totals"]["now"]["total"] == 3
    assert book.overview(year="2026", levels="Language")["totals"]["now"]["total"] == 1
    assert book.overview(year="2026", levels="Postgraduate|Undergraduate")["totals"]["now"]["total"] == 2
    levels = {r["name"]: r["n"] for r in book.overview(year="2026")["options"]["levels"]}
    assert levels == {"Postgraduate": 1, "Undergraduate": 1, "Language": 1}


def test_student_is_lost_only_when_every_application_is(book):
    book.load([
        {"student_key": "Live", "intake": "2026-09", "on_applied": "2026-01-01", "on_offer": "2026-02-01",
         "closed_lost": True},
        {"student_key": "Live", "intake": "2026-09", "on_applied": "2026-01-01"},
        {"student_key": "Dead", "intake": "2026-09", "on_applied": "2026-01-01", "closed_lost": True},
    ])
    s = book.stages(year="2026")
    assert s["offer"]["now"]["pipeline"] == {"total": 1, "active": 1, "lost": 0}
    assert s["applied"]["now"]["pipeline"] == {"total": 1, "active": 0, "lost": 1}


def test_last_year_at_this_point_replays_dates_to_the_cutoff(book):
    # the anchor is the newest stage date: 2026-06-01, so the cut-off is 2025-06-01
    book.load([
        {"student_key": "Now", "intake": "2026-09", "on_applied": "2026-06-01"},
        {"student_key": "Early", "intake": "2025-09", "on_applied": "2025-02-01", "on_offer": "2025-05-01",
         "on_deposit": "2025-07-01"},
        {"student_key": "Late", "intake": "2025-09", "on_applied": "2025-08-01"},
    ])
    data = book.overview(year="2026")
    assert data["cutoff"] == "2025-06-01"
    s = {x["id"]: x for x in data["stages"]}
    assert data["totals"]["ly_asat"]["total"] == 1          # Late had not applied yet
    assert s["offer"]["ly_asat"]["pipeline"]["total"] == 1  # Early was at Offer then
    assert s["deposit"]["ly_asat"]["funnel"]["total"] == 0
    assert data["totals"]["ly_final"]["total"] == 2
    assert s["deposit"]["ly_final"]["funnel"]["total"] == 1
    assert s["offer"]["ly_asat"]["pipeline"]["active"] is None


def test_bad_params_are_refused(book, metrics):
    from app.views import ViewError
    book.load([{"student_key": "S", "intake": "2026-09", "on_applied": "2026-01-01"}])
    for params in ({"mode": "fiscal"}, {"year": "1999"}, {"quarters": "5"}, {"year": "x"}):
        with pytest.raises(ViewError):
            book.overview(**params)


def test_region_and_team_pick_applications_before_the_roll_up(book):
    book.master({"Lagos Ed": "West Africa B2B SRMs 1", "Dhaka Ed": "Bangladesh B2B SRMs", "No Team": None})
    book.load([
        # one student, two teams: Offer through Lagos, Applied through Dhaka
        {"student_key": "S1", "intake": "2026-09", "introducer_name": "Lagos Ed",
         "on_applied": "2026-01-02", "on_offer": "2026-02-01"},
        {"student_key": "S1", "intake": "2026-09", "introducer_name": "Dhaka Ed", "on_applied": "2026-01-05"},
        {"student_key": "S2", "intake": "2026-09", "introducer_name": "Dhaka Ed", "on_applied": "2026-01-05"},
        {"student_key": "S3", "intake": "2026-09", "on_applied": "2026-01-05"},                 # direct
        {"student_key": "S4", "intake": "2026-09", "introducer_name": "No Team", "on_applied": "2026-01-05"},
        {"student_key": "S5", "intake": "2026-09", "introducer_name": "Not On Master", "on_applied": "2026-01-05"},
    ])

    def total(**params):
        return book.overview(year="2026", **params)["totals"]["now"]["total"]

    assert total() == 5
    assert total(regions="Africa") == 1
    assert book.stages(year="2026", teams="Bangladesh B2B SRMs")["offer"]["now"]["funnel"]["total"] == 0
    assert total(teams="Bangladesh B2B SRMs") == 2
    assert total(teams="Unassigned") == 3                            # direct, blank team, not on master
    assert total(regions="Other") == 3
    assert total(regions="Africa", teams="Bangladesh B2B SRMs") == 0  # team outside the region
    assert total(regions="Africa|Bangladesh") == 2

    out = book.overview(year="2026", regions="Africa")
    assert out["filters"]["regions"] == ["Africa"]
    teams = {t["team"]: t for t in out["options"]["team_options"]}
    assert teams["Unassigned"]["n"] == 3 and teams["Unassigned"]["region"] == "Other"
    assert {r["region"] for r in out["options"]["region_options"]} == {"Africa", "Bangladesh", "Other"}
