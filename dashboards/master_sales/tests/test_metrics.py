"""The rules of context.md, asserted against the dashboard's own SQL."""
import pytest

ALL = {"from": "all"}


def test_the_default_range_is_this_week(book):
    # the anchor is Wednesday 2026-10-28, so this week is Monday 26th to the 28th
    book.load([
        {"student_key": "A", "intake": "2026-09", "on_applied": "2026-10-25"},
        {"student_key": "B", "intake": "2026-09", "on_applied": "2026-10-26"},
        {"student_key": "C", "intake": "2026-09", "on_applied": "2026-10-28"},
    ])
    data = book.overview()
    assert (data["filters"]["from"], data["filters"]["to"]) == ("2026-10-26", "2026-10-28")
    assert data["filters"]["default_range"] and data["stages"][0]["n"] == 2
    assert book.stages(**{"from": "all"})["applied"] == 3


def test_all_time_counts_everything_that_reached_each_stage(book):
    book.load([
        {"student_key": "A", "intake": "2026-09", "on_applied": "2026-01-01"},
        {"student_key": "B", "intake": "2026-09", "on_applied": "2026-01-01", "on_offered": "2026-02-01",
         "on_deposit": "2026-02-10"},
        {"student_key": "C", "intake": "2026-09", "on_applied": "2026-01-01", "on_offered": "2026-02-01",
         "on_coe": "2026-03-01", "on_visa_applied": "2026-04-01", "on_visa_granted": "2026-05-01",
         "on_enrolled": "2026-09-01", "on_deposit": "2026-02-15"},
        # a status-only stage: counts all time, never in a range
        {"student_key": "D", "intake": "2026-09", "stage": 3},
    ])
    assert book.stages(**ALL) == {"applied": 4, "offered": 3, "coe": 2, "visa_applied": 1,
                             "visa_granted": 1, "enrolled": 1, "deposit": 2}
    deposit_at = {d["id"]: d["n"] for d in book.overview(**ALL)["deposit"]["at"]}
    assert deposit_at == {"offered": 1, "coe": 0, "visa_applied": 0, "visa_granted": 0, "enrolled": 1}


def test_a_range_counts_each_stage_by_its_own_date(book):
    book.load([
        {"student_key": "A", "intake": "2026-09", "on_applied": "2025-12-01", "on_offered": "2026-02-01"},
        {"student_key": "B", "intake": "2026-09", "on_applied": "2026-02-05"},
        {"student_key": "C", "intake": "2026-09", "stage": 2},
    ])
    s = book.stages(**{"from": "2026-02-01", "to": "2026-02-28"})
    assert s["applied"] == 1 and s["offered"] == 1


def test_unique_applicants_count_students_once(book):
    book.load([
        {"student_key": "S", "intake": "2026-09", "on_applied": "2026-01-01", "on_offered": "2026-02-01"},
        {"student_key": "S", "intake": "2026-09", "on_applied": "2026-01-02", "on_offered": "2026-02-02"},
    ])
    assert book.stages(**ALL)["offered"] == 2
    assert book.stages(unit="unique", **ALL)["offered"] == 1
    assert book.stages(unit="students", **ALL)["offered"] == 1  # the old name still works


def test_unique_applicants_count_each_sale_from_coe_on(book):
    sale = {"student_key": "S", "on_applied": "2026-01-01", "on_offered": "2026-02-01", "on_coe": "2026-03-01",
            "on_deposit": "2026-02-15"}
    book.load([
        {**sale, "intake": "2026-09"},
        {**sale, "intake": "2026-09"},  # the same sale, applied twice
        {**sale, "intake": "2027-01"},  # a second sale
    ])
    s = book.stages(unit="unique", **ALL)
    assert (s["applied"], s["offered"], s["coe"], s["deposit"]) == (1, 1, 2, 2)
    data = book.overview(unit="unique", **ALL)
    assert data["deposit"]["at"][1]["n"] == 2  # both sales sit at CoE
    assert data["scope"] == {"applications": 3, "applicants": 1}


def test_the_scope_follows_the_range(book):
    book.load([
        {"student_key": "A", "intake": "2026-09", "on_applied": "2026-10-27"},
        {"student_key": "A", "intake": "2026-09", "on_applied": "2025-01-01", "on_pd": "2026-10-27"},
        {"student_key": "B", "intake": "2026-09", "on_applied": "2025-01-01"},
    ])
    assert book.overview()["scope"] == {"applications": 2, "applicants": 1}
    assert book.overview(**ALL)["scope"] == {"applications": 3, "applicants": 2}


def test_intake_quarters_of_one_year(book):
    from app.views import ViewError
    book.load([
        {"student_key": "A", "intake": "2026-01", "on_applied": "2026-01-01"},
        {"student_key": "B", "intake": "2026-05", "on_applied": "2026-01-01"},
        {"student_key": "C", "intake": "2026-09", "on_applied": "2026-01-01"},
        {"student_key": "D", "intake": "2027-01", "on_applied": "2026-01-01"},
    ])
    data = book.overview(intake_q="2026-Q1|2026-Q3", **ALL)
    assert data["stages"][0]["n"] == 2 and data["filters"]["intake_q"] == ["2026-Q1", "2026-Q3"]
    for bad in ({"intake_q": "2026-Q1|2027-Q1"}, {"intake_q": "2026-Q5"},
                {"intake_q": "2026-Q1", "intake_from": "2026-01", "intake_to": "2026-03"}):
        with pytest.raises(ViewError):
            book.overview(**bad, **ALL)


def test_assignment_and_intake_filters_and_menus(book):
    book.load([
        {"student_key": "A", "intake": "2026-09", "on_applied": "2026-01-01"},
        {"student_key": "B", "intake": "2027-01", "on_applied": "2026-01-01",
         "business_area": "B2C", "business_region": "UK B2C", "business_team": "Team B"},
    ])
    assert book.stages(areas="B2C", **ALL)["applied"] == 1
    assert book.stages(**ALL, intake_from="2026-09", intake_to="2026-12")["applied"] == 1
    assert book.stages(**ALL, intake_from="2027-03", intake_to="2026-07")["applied"] == 2   # either order
    data = book.overview(areas="B2C")
    # the area menu ignores its own pick, the others follow it
    assert {o["name"] for o in data["options"]["areas"]} == {"B2B", "B2C"}
    assert [o["name"] for o in data["options"]["teams"]] == ["Team B"]
    assert {(t["area"], t["team"]) for t in data["options"]["tree"]} == {("B2B", "Team A"), ("B2C", "Team B")}


def test_the_area_menu_leaves_out_unassigned(book):
    book.load([
        {"student_key": "A", "intake": "2026-09", "on_applied": "2026-01-01"},
        {"student_key": "B", "intake": "2026-09", "on_applied": "2026-01-01", "business_area": "Unassigned"},
    ])
    data = book.overview(**ALL)
    assert [o["name"] for o in data["options"]["areas"]] == ["B2B"]
    assert data["stages"][0]["n"] == 2


@pytest.mark.parametrize("params", [{"unit": "x"}, {"from": "2026-01-01"},
                                    {"intake_from": "2026-13", "intake_to": "2026-12"},
                                    {"intake_from": "2026-01"}])
def test_bad_params_are_refused(book, params):
    from app.views import ViewError
    book.load([{"student_key": "A", "intake": "2026-09", "on_applied": "2026-01-01"}])
    with pytest.raises(ViewError):
        book.overview(**params)


def test_each_stage_splits_created_into_active_and_closed(book):
    book.load([
        {"student_key": "A", "intake": "2026-09", "on_applied": "2026-01-01", "stage": 1},
        {"student_key": "B", "intake": "2026-09", "on_applied": "2026-01-01", "stage": 1, "closed_lost": True},
        {"student_key": "C", "intake": "2026-09", "on_applied": "2026-01-01", "on_offered": "2026-02-01",
         "stage": 2, "closed_lost": True, "deposit": True, "on_deposit": "2026-02-02"},
        {"student_key": "D", "intake": "2026-09", "on_applied": "2026-01-01", "on_offered": "2026-02-01",
         "stage": 2, "deposit": True, "on_deposit": "2026-02-02"},
    ])
    data = book.overview(**ALL)
    applied, offered = data["stages"][0], data["stages"][1]
    assert (applied["n"], applied["active"], applied["closed"]) == (4, 1, 1)
    assert (offered["n"], offered["active"], offered["closed"]) == (2, 1, 1)
    deposit = data["deposit"]
    assert (deposit["n"], deposit["active"], deposit["daa"], deposit["closed"]) == (2, 1, 0, 1)


def test_course_level_defaults_to_academic(book):
    book.load([
        {"student_key": "A", "intake": "2026-09", "on_applied": "2026-01-01"},
        {"student_key": "B", "intake": "2026-09", "on_applied": "2026-01-01", "level_group": "Language"},
        {"student_key": "C", "intake": "2026-09", "on_applied": "2026-01-01", "level_group": "Other"},
    ])
    assert book.overview(**ALL)["filters"]["level"] == "academic"
    assert book.stages(**ALL)["applied"] == 1
    assert book.stages(**ALL, level="language")["applied"] == 1
    assert book.stages(**ALL, level="all")["applied"] == 3
    from app.views import ViewError
    with pytest.raises(ViewError):
        book.overview(level="masters")


def test_deposit_splits_into_active_daa_and_closed(book):
    paid = {"intake": "2026-09", "on_applied": "2026-01-01", "on_offered": "2026-02-01",
            "stage": 2, "deposit": True, "on_deposit": "2026-02-02"}
    book.load([
        {"student_key": "A", **paid},
        {"student_key": "B", **paid, "deposit_state": "DAA"},
        {"student_key": "C", **paid, "deposit_state": "DAA", "closed_lost": True},
        {"student_key": "D", **paid, "closed_lost": True},
    ])
    deposit = book.overview(**ALL)["deposit"]
    assert (deposit["n"], deposit["active"], deposit["daa"], deposit["closed"]) == (4, 1, 1, 2)


def test_pd_is_dated_by_its_part_payment(book):
    offer = {"intake": "2026-09", "on_applied": "2025-01-01", "on_offered": "2025-02-01"}
    book.load([
        {"student_key": "A", "intake": "2026-09", "on_applied": "2026-10-27"},
        {"student_key": "B", **offer, "deposit_state": "PD", "on_pd": "2026-10-27"},
        {"student_key": "C", **offer, "deposit_state": "PD", "on_pd": "2026-10-27", "closed_lost": True},
        {"student_key": "D", **offer, "on_pd": "2026-10-27", "on_deposit": "2026-10-28"},  # since paid in full
        {"student_key": "E", **offer, "deposit_state": "PD", "on_pd": "2025-03-01"},  # an older part payment
        {"student_key": "F", **offer, "deposit_state": "PD"},  # undated: all time only
    ])
    pd = book.overview()["pd"]
    assert (pd["n"], pd["active"], pd["paid"], pd["closed"]) == (3, 1, 1, 1)
    pd = book.overview(**ALL)["pd"]
    assert (pd["n"], pd["active"], pd["paid"], pd["closed"]) == (5, 3, 1, 1)


def test_daa_is_dated_by_the_deferral(book):
    paid = {"intake": "2026-09", "on_applied": "2025-01-01", "on_offered": "2025-02-01", "on_deposit": "2025-03-01"}
    book.load([
        {"student_key": "A", **paid, "deposit_state": "DAA", "on_deferral_initiated": "2026-10-27"},
        {"student_key": "B", **paid, "on_deferral_initiated": "2026-10-27", "on_deferral_approved": "2026-10-28"},
        {"student_key": "C", **paid, "deposit_state": "DAA", "on_deferral_initiated": "2026-10-27",
         "closed_lost": True},
        {"student_key": "D", **paid, "deposit_state": "DAA", "on_deferral_initiated": "2025-06-01"},
        {"student_key": "E", **paid},  # no deferral
    ])
    daa = book.overview()["daa"]
    assert (daa["n"], daa["awaiting"], daa["approved"], daa["closed"]) == (3, 1, 1, 1)
    daa = book.overview(**ALL)["daa"]
    assert (daa["n"], daa["awaiting"], daa["approved"], daa["closed"]) == (4, 2, 1, 1)
