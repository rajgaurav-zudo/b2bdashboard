"""Rules from context.md, asserted against the read model.

Every assertion here was previously checked in the browser build; this file is
the regression suite that keeps the SQL port honest.
"""
import pytest


# --------------------------------------------------------------------------
# current intake year
# --------------------------------------------------------------------------

def test_current_year_ignores_a_barely_started_future_intake(metrics):
    # Nov/Dec roll forward, so max(year) is a phantom. 2027 holds 1% of the peak.
    assert metrics.pick_current_year([(2024, 11), (2025, 40), (2026, 87), (2027, 1)]) == 2026


def test_current_year_accepts_a_future_year_that_clears_the_floor(metrics):
    assert metrics.pick_current_year([(2025, 40), (2026, 87), (2027, 20)]) == 2027


@pytest.mark.parametrize("hist,expected", [
    ([], None),
    ([(1900, 5), (2026, 100)], 2026),        # out-of-range years are dropped
    ([(2026, 3)], 2026),                     # a single year is always its own peak
])
def test_current_year_edges(metrics, hist, expected):
    assert metrics.pick_current_year(hist) == expected


# --------------------------------------------------------------------------
# scope
# --------------------------------------------------------------------------

def test_scope_is_customer_stage_or_any_paid_deposit(book, metrics):
    book.load(
        introducers=[
            {"partner_name": "Customer, no apps", "lifecycle_stage": "Customer"},
            {"partner_name": "Lead with deposit", "lifecycle_stage": "Lead"},
            {"partner_name": "Lead, no deposit", "lifecycle_stage": "Lead"},
        ],
        applications=[
            {"introducer_name": "Lead with deposit", "deposit_fully_paid": True,
             "intake_year": 2026, "cycle_index": 2},
            {"introducer_name": "Lead, no deposit", "intake_year": 2026, "cycle_index": 2},
            {"introducer_name": "Ghost", "deposit_fully_paid": True, "intake_year": 2026, "cycle_index": 2},
        ],
    )
    names = book.by_name(metrics)
    assert set(names) == {"Customer, no apps", "Lead with deposit", "Ghost"}
    # a name that only ever appears in the applications export is kept, not dropped
    assert names["Ghost"]["stage"] == "Not in CRM"
    assert names["Ghost"]["in_crm"] is False


def test_deposits_after_cur_still_pull_a_name_into_scope(book, metrics):
    """Scope asks whether a deposit exists at all -- lifetime scoring is a separate rule."""
    book.load(
        introducers=[{"partner_name": "Peak", "lifecycle_stage": "Customer"}],
        applications=(
            # the peak year needs enough volume that a single 2027 row misses the
            # 10%-of-peak floor -- otherwise 2027 legitimately becomes CUR
            [{"introducer_name": "Peak", "deposit_fully_paid": True, "intake_year": 2026,
              "cycle_index": 2} for _ in range(20)]
            + [{"introducer_name": "Future only", "deposit_fully_paid": True, "intake_year": 2027,
                "cycle_index": 0}]
        ),
    )
    names = book.by_name(metrics)
    assert "Future only" in names
    assert names["Future only"]["act_life"] == 0     # scores nothing


# --------------------------------------------------------------------------
# lifetime window
# --------------------------------------------------------------------------

def test_lifetime_spans_every_year_up_to_cur_plus_undated_rows(book, metrics):
    book.load(
        introducers=[{"partner_name": "P", "lifecycle_stage": "Customer"}],
        applications=[
            {"introducer_name": "P", "deposit_fully_paid": True, "intake_year": y, "cycle_index": 2}
            for y in (2024, 2025, 2027, *([2026] * 20))
        ] + [{"introducer_name": "P", "deposit_fully_paid": True, "intake_year": None}],
    )
    p = book.by_name(metrics)["P"]
    assert p["act_cur"] == 20                # 2026 only
    assert p["act_prev"] == 1                # 2025
    assert p["act_before"] == 1              # 2024
    assert p["act_life"] == 23               # 2024+2025+2026*20 + the undated row, never 2027


# --------------------------------------------------------------------------
# tiles
# --------------------------------------------------------------------------

def _cur_year_apps(name, n, **kw):
    return [{"introducer_name": name, "intake_year": 2026, "cycle_index": 2, **kw} for _ in range(n)]


def test_tile_membership(book, metrics):
    book.load(
        introducers=[
            {"partner_name": "Active", "lifecycle_stage": "Customer", "became_customer_year": 2025},
            {"partner_name": "Dormant", "lifecycle_stage": "Customer", "became_customer_year": 2024},
            {"partner_name": "Resurrected", "lifecycle_stage": "Customer", "became_customer_year": 2021},
            {"partner_name": "Squanderer", "lifecycle_stage": "Customer", "became_customer_year": 2026},
            {"partner_name": "Slacker", "lifecycle_stage": "Customer", "became_customer_year": 2023},
        ],
        applications=(
            _cur_year_apps("Active", 12, deposit_fully_paid=True)
            + [{"introducer_name": "Dormant", "deposit_fully_paid": True, "intake_year": 2025,
                "cycle_index": 2}]
            + [{"introducer_name": "Resurrected", "deposit_fully_paid": True, "intake_year": 2024,
                "cycle_index": 2},
               {"introducer_name": "Resurrected", "deposit_fully_paid": True, "intake_year": 2026,
                "cycle_index": 2}]
            + _cur_year_apps("Squanderer", 3)
        ),
    )
    tiles = book.tiles(metrics)
    assert tiles["active"]["n"] == 2                 # Active + Resurrected
    assert tiles["resurrected"]["n"] == 1
    assert tiles["dormant"]["n"] == 1                # deposits earlier, none in CUR
    assert tiles["squanderers"]["n"] == 1            # >1 application, never a deposit
    assert tiles["slackers"]["n"] == 1               # Customer, no applications at all
    assert tiles["coh2025"]["n"] == 1                # Active, became customer in PREV
    assert tiles["cohOld"]["n"] == 1                 # Resurrected, became customer 2021 <= CUR-3


def test_dormant_and_active_never_overlap(book, metrics):
    """The call list must not contain anyone who is currently depositing."""
    book.load(
        introducers=[{"partner_name": f"P{i}", "lifecycle_stage": "Customer"} for i in range(4)],
        applications=(
            _cur_year_apps("P0", 10, deposit_fully_paid=True)
            + [{"introducer_name": "P1", "deposit_fully_paid": True, "intake_year": 2025, "cycle_index": 2}]
            + _cur_year_apps("P1", 2)                    # still applying, no deposit
            + [{"introducer_name": "P2", "deposit_fully_paid": True, "intake_year": 2023, "cycle_index": 0}]
        ),
    )
    overview = book.overview(metrics)
    tiles = {t["id"]: t for t in overview["tiles"]}
    active = {r["name"] for g in book.tile(metrics, id="active")["groups"] for r in g["rows"]}
    dormant = {r["name"] for g in book.tile(metrics, id="dormant")["groups"] for r in g["rows"]}
    assert not (active & dormant)
    assert dormant == {"P1", "P2"}
    assert tiles["dormant"]["stats"]["life"] == 2       # lifetime deposits, not current-year
    assert overview["dormant_still_applying"] == 1      # P1 is submitting but not converting


def test_squanderer_needs_more_than_one_application(book, metrics):
    book.load(
        introducers=[{"partner_name": "One", "lifecycle_stage": "Customer"},
                     {"partner_name": "Two", "lifecycle_stage": "Customer"}],
        applications=_cur_year_apps("One", 1) + _cur_year_apps("Two", 2),
    )
    assert book.tiles(metrics)["squanderers"]["n"] == 1


def test_visa_and_coe_losses_read_status_not_deposit(book, metrics):
    book.load(
        introducers=[{"partner_name": "P", "lifecycle_stage": "Customer"}],
        applications=[
            {"introducer_name": "P", "closed_lost": True, "application_status": "Visa",
             "application_sub_status": "Applied", "intake_year": 2026, "cycle_index": 2},
            {"introducer_name": "P", "closed_lost": True, "application_status": "CoE Received",
             "intake_year": 2026, "cycle_index": 2},
            # closed lost at an earlier stage: neither tile
            {"introducer_name": "P", "closed_lost": True, "application_status": "Application Sent",
             "intake_year": 2026, "cycle_index": 2},
            # visa applied but NOT closed lost: still in flight, not a loss
            {"introducer_name": "P", "application_status": "Visa",
             "application_sub_status": "Applied", "intake_year": 2026, "cycle_index": 2},
        ],
    )
    p = book.by_name(metrics)["P"]
    assert p["vrej_life"] == 1
    assert p["coe_life"] == 1


def test_bad_converter_thresholds(book, metrics):
    book.load(
        introducers=[{"partner_name": n, "lifecycle_stage": "Customer"}
                     for n in ("Low enrol", "Good enrol", "Closer", "Small")],
        applications=(
            _cur_year_apps("Low enrol", 12, deposit_fully_paid=True)
            + _cur_year_apps("Good enrol", 9, deposit_fully_paid=True, enrolled=True)   # under 10 apps
            + [{"introducer_name": "Closer", "deposit_fully_paid": True, "closed_lost": c,
                "intake_year": 2026, "cycle_index": 2}
               for c in (False, False, False, True, True)]                              # 2/3 > 30%
            + [{"introducer_name": "Small", "deposit_fully_paid": True, "closed_lost": c,
                "intake_year": 2026, "cycle_index": 2}
               for c in (False, False, True)]                                           # only 2 active
        ),
    )
    tiles = book.tiles(metrics)
    assert tiles["badEnrol"]["n"] == 1        # 10+ apps and under 10% enrolled
    assert tiles["badClose"]["n"] == 1        # 3+ active deposits and closures above 30%


# --------------------------------------------------------------------------
# funnel and drill-down
# --------------------------------------------------------------------------

def test_funnel_keeps_future_years_visible_but_unscored(book, metrics):
    book.load(
        introducers=[{"partner_name": "P", "lifecycle_stage": "Customer"}],
        applications=(
            _cur_year_apps("P", 20, deposit_fully_paid=True)
            + [{"introducer_name": "P", "deposit_fully_paid": True, "intake_year": 2027, "cycle_index": 0}]
        ),
    )
    overview = book.overview(metrics)
    years = {r["y"]: r for r in overview["funnel"]["scope"]}
    assert 2027 in years and years[2027]["act"] == 1
    assert overview["totals"]["act_life"] == 20          # the 2027 row scores nothing


def test_funnel_scopes_differ_only_by_out_of_scope_names(book, metrics):
    book.load(
        introducers=[{"partner_name": "P", "lifecycle_stage": "Customer"}],
        applications=_cur_year_apps("P", 10, deposit_fully_paid=True) + _cur_year_apps("Nobody", 4),
    )
    overview = book.overview(metrics)
    scope = {r["y"]: r["apps"] for r in overview["funnel"]["scope"]}
    everyone = {r["y"]: r["apps"] for r in overview["funnel"]["all"]}
    assert scope[2026] == 10
    assert everyone[2026] == 14


def test_drilldown_groups_and_sorts(book, metrics):
    book.load(
        introducers=[
            {"partner_name": "IN big", "lifecycle_stage": "Customer", "country": "India"},
            {"partner_name": "IN small", "lifecycle_stage": "Customer", "country": "India"},
            {"partner_name": "NG one", "lifecycle_stage": "Customer", "country": "Nigeria"},
        ],
        applications=(
            _cur_year_apps("IN big", 9, deposit_fully_paid=True)
            + _cur_year_apps("IN small", 2, deposit_fully_paid=True)
            + _cur_year_apps("NG one", 4, deposit_fully_paid=True)
        ),
    )
    result = book.tile(metrics, id="active", group_by="country", sort="act_cur", dir="desc")
    assert [g["key"] for g in result["groups"]] == ["India", "Nigeria"]
    assert result["groups"][0]["cur"] == 11
    assert [r["name"] for r in result["groups"][0]["rows"]] == ["IN big", "IN small"]

    ascending = book.tile(metrics, id="active", group_by="country", sort="act_cur", dir="asc")
    assert [r["name"] for r in ascending["groups"][0]["rows"]] == ["IN small", "IN big"]


def test_unknown_tile_and_sort_are_refused(book, metrics):
    from app.views import ViewError
    book.load(introducers=[{"partner_name": "P", "lifecycle_stage": "Customer"}],
              applications=_cur_year_apps("P", 2, deposit_fully_paid=True))
    with pytest.raises(ViewError):
        book.tile(metrics, id="nope")
    with pytest.raises(ViewError):
        book.tile(metrics, id="active", sort="drop table")


# --------------------------------------------------------------------------
# cadence and data notes
# --------------------------------------------------------------------------

def test_cadence_needs_twenty_deposits_and_a_real_intake_year(book, metrics):
    book.load(
        introducers=[{"partner_name": "Sep heavy", "lifecycle_stage": "Customer", "country": "Nepal"},
                     {"partner_name": "Thin", "lifecycle_stage": "Customer", "country": "Ghana"}],
        applications=(
            _cur_year_apps("Sep heavy", 21, deposit_fully_paid=True)
            + [{"introducer_name": "Sep heavy", "deposit_fully_paid": True,
                "intake_year": None, "cycle_index": 0}]           # month without a year: not cadence
            + _cur_year_apps("Thin", 5, deposit_fully_paid=True)
        ),
    )
    cadence = {c["country"]: c for c in book.overview(metrics)["cadence"]}
    assert set(cadence) == {"Nepal"}
    assert cadence["Nepal"]["sep"] == 21 and cadence["Nepal"]["act"] == 21
    assert cadence["Nepal"]["peak"] == "Sep"
    assert cadence["Nepal"]["top"] == 1.0


def test_data_notes_count_the_traps(book, metrics):
    book.load(
        introducers=[
            {"partner_name": "Dated", "lifecycle_stage": "Customer", "became_customer_year": 2024,
             "latest_contract_status": "Active"},
            {"partner_name": "Fallback", "lifecycle_stage": "Customer", "source_created_year": 2023},
            {"partner_name": "No year", "lifecycle_stage": "Customer"},
        ],
        applications=(
            _cur_year_apps("Dated", 10, deposit_fully_paid=True)
            + [{"introducer_name": None, "deposit_fully_paid": True, "intake_year": 2026, "cycle_index": 2},
               {"introducer_name": None, "intake_year": 2026, "cycle_index": 2},
               {"introducer_name": "Dated", "intake_year": None},
               {"introducer_name": "Dated", "closed_lost": True, "enrolled": True,
                "intake_year": 2026, "cycle_index": 2}]
        ),
    )
    data = book.overview(metrics)["data"]
    assert data["master_rows"] == 3
    assert data["blank_became"] == 2          # Fallback + No year
    assert data["used_fallback"] == 1         # only Fallback has a Created At year
    assert data["no_contract"] == 2
    assert data["blank_intro"] == 2           # unattributed applications
    assert data["blank_intro_deposits"] == 1  # ... one of them a paid deposit
    assert data["no_year"] == 1
    assert data["contradictions"] == 1        # closed lost yet carrying an enrolled timestamp


def test_not_in_crm_revenue_is_reported_not_dropped(book, metrics):
    book.load(
        introducers=[{"partner_name": "Known", "lifecycle_stage": "Customer"}],
        applications=(
            _cur_year_apps("Known", 10, deposit_fully_paid=True)
            + _cur_year_apps("Ghost", 3, deposit_fully_paid=True)
            + [{"introducer_name": "Ghost", "deposit_fully_paid": True, "closed_lost": True,
                "intake_year": 2026, "cycle_index": 2}]
        ),
    )
    not_in_crm = book.overview(metrics)["not_in_crm"]
    assert not_in_crm == {"n": 1, "act": 3, "clos": 1}


# --------------------------------------------------------------------------
# deposit states (sources/context.md)
# --------------------------------------------------------------------------

def test_tiles_report_daa_and_pd_for_the_current_year(book, metrics):
    """DAA is carved out of the tile's active deposits; PD is a separate pool.
    Both are reported per tile, in CUR, for that tile's members only."""
    apps = [
        # 20 plain active deposits in 2026, so 2026 is unambiguously CUR
        *[{"introducer_name": "Alpha", "deposit_fully_paid": True,
           "intake_year": 2026, "cycle_index": 2} for _ in range(20)],
        # 3 more that are paid, deferred, and still waiting on the decision
        *[{"introducer_name": "Alpha", "deposit_fully_paid": True, "deferral_initiated": True,
           "intake_year": 2026, "cycle_index": 2} for _ in range(3)],
        # 4 whose deferral was approved: settled, so they count as active deposits
        *[{"introducer_name": "Alpha", "deposit_fully_paid": True, "deferral_initiated": True,
           "deferral_approved": True, "intake_year": 2026, "cycle_index": 2} for _ in range(4)],
        # 2 partial deposits -- not fully paid, so not in the active count at all
        *[{"introducer_name": "Alpha", "deposit_partial": True,
           "intake_year": 2026, "cycle_index": 2} for _ in range(2)],
        # last year's deferral must not leak into the current year's DAA
        {"introducer_name": "Alpha", "deposit_fully_paid": True, "deferral_initiated": True,
         "intake_year": 2025, "cycle_index": 2},
    ]
    book.load(
        introducers=[{"partner_name": "Alpha", "lifecycle_stage": "Customer",
                      "became_customer_year": 2026}],
        applications=apps,
    )
    stats = book.tiles(metrics)["active"]
    # 20 plain + 4 approved deferrals; the 3 awaiting a decision are NOT in it
    assert stats["cur"] == 24
    assert stats["daa"] == 3           # reported beside the headline, not inside it
    assert stats["pd"] == 2            # partial deposits are their own pool


def test_an_approved_deferral_is_an_ordinary_active_deposit(book, metrics):
    """`Initiated = Yes` with `Approved = Yes` is a settled deferral: it has a
    decision and an intake, so it counts in the headline and is not DAA. Only
    the undecided ones move. This is the half of the deferral population that
    would otherwise be mislabelled -- 2,135 of 2,201 rows in the real export."""
    apps = [
        *[{"introducer_name": "Gamma", "deposit_fully_paid": True,
           "intake_year": 2026, "cycle_index": 2} for _ in range(20)],
        *[{"introducer_name": "Gamma", "deposit_fully_paid": True, "deferral_initiated": True,
           "deferral_approved": True, "intake_year": 2026, "cycle_index": 2} for _ in range(5)],
    ]
    book.load(
        introducers=[{"partner_name": "Gamma", "lifecycle_stage": "Customer"}],
        applications=apps,
    )
    stats = book.tiles(metrics)["active"]
    assert stats["cur"] == 25
    assert stats["daa"] == 0
    assert stats["pd"] == 0


def test_approved_without_initiated_falls_into_no_state(book, metrics):
    """The definition is a sum of two cells -- (No, No) and (Yes, Yes) -- so
    `Approved = Yes` with `Initiated = No` is in neither, and DAA needs an
    initiation it does not have. It is therefore reported by nothing. This is
    deliberate: a row in that state is a CRM contradiction, and folding it into
    the headline would hide it. 3 rows in the 1 Sep export, none of them a live
    full deposit, so it costs no figure today. If the count ever moves off zero,
    the fix is in the CRM, not here."""
    apps = [
        *[{"introducer_name": "Gamma", "deposit_fully_paid": True,
           "intake_year": 2026, "cycle_index": 2} for _ in range(20)],
        *[{"introducer_name": "Gamma", "deposit_fully_paid": True,
           "deferral_approved": True, "intake_year": 2026, "cycle_index": 2}
          for _ in range(4)],
    ]
    book.load(
        introducers=[{"partner_name": "Gamma", "lifecycle_stage": "Customer"}],
        applications=apps,
    )
    stats = book.tiles(metrics)["active"]
    assert stats["cur"] == 20
    assert stats["daa"] == 0


def test_the_reported_year_is_the_intake_year_not_the_cycle_year(book, metrics):
    """`Actual Intake Year` is the definition. `cycle_year` -- Nov/Dec rolled
    forward into the following January -- is still derived at ingest and still
    stored, but nothing in the read model may read it. Setting the two columns
    to different values is the only way to catch a silent relapse: with every
    row at intake 2025 and cycle 2026, CUR is 2025."""
    book.load(
        introducers=[{"partner_name": "Gamma", "lifecycle_stage": "Customer"}],
        applications=[{"introducer_name": "Gamma", "deposit_fully_paid": True,
                       "intake_year": 2025, "cycle_year": 2026, "cycle_index": 2}
                      for _ in range(20)],
    )
    cur, _, _ = metrics._years(book.ctx)
    assert cur == 2025
    assert book.tiles(metrics)["active"]["cur"] == 20


def test_the_active_tile_counts_daa_and_pd_across_the_whole_book(book, metrics):
    """Active membership needs a *paid* deposit, so a partner whose only
    current-year money is awaiting approval never became a member and their DAA
    fell off the headline card. The Active tile sums DAA and PD over the book,
    so all three of its figures describe one population. Delta is not a member
    and must not be counted in `n` or `cur` -- only in the two state figures."""
    book.load(
        introducers=[{"partner_name": "Gamma", "lifecycle_stage": "Customer"},
                     {"partner_name": "Delta", "lifecycle_stage": "Customer"}],
        applications=[
            *[{"introducer_name": "Gamma", "deposit_fully_paid": True,
               "intake_year": 2026, "cycle_index": 2} for _ in range(20)],
            {"introducer_name": "Delta", "deposit_fully_paid": True,
             "deferral_initiated": True, "intake_year": 2026, "cycle_index": 2},
            {"introducer_name": "Delta", "deposit_partial": True,
             "intake_year": 2026, "cycle_index": 2},
        ],
    )
    stats = book.tiles(metrics)["active"]
    assert stats["n"] == 1
    assert stats["cur"] == 20
    assert stats["daa"] == 1
    assert stats["pd"] == 1


def test_daa_and_pd_ignore_closed_lost(book, metrics):
    """A deferral or a partial on a closed-lost application is not live money."""
    apps = [
        *[{"introducer_name": "Beta", "deposit_fully_paid": True,
           "intake_year": 2026, "cycle_index": 2} for _ in range(20)],
        {"introducer_name": "Beta", "deposit_fully_paid": True, "deferral_initiated": True,
         "closed_lost": True, "intake_year": 2026, "cycle_index": 2},
        {"introducer_name": "Beta", "deposit_partial": True, "deferral_initiated": True,
         "intake_year": 2026, "cycle_index": 2},
        {"introducer_name": "Beta", "deposit_partial": True,
         "closed_lost": True, "intake_year": 2026, "cycle_index": 2},
    ]
    book.load(
        introducers=[{"partner_name": "Beta", "lifecycle_stage": "Customer"}],
        applications=apps,
    )
    stats = book.tiles(metrics)["active"]
    assert stats["daa"] == 0
    # a live partial deposit with a deferral initiated is PD, not DAA:
    # DAA is defined on paid deposits only
    assert stats["pd"] == 1


def test_deposit_figures_are_academic_only(book, metrics):
    """Language and pre-sessional deposits are reported separately, not in the
    headline. Scope is NOT narrowed: a language-only partner stays in the book."""
    apps = [
        *[{"introducer_name": "Alpha", "deposit_fully_paid": True, "course_category": "Academic",
           "intake_year": 2026, "cycle_index": 2} for _ in range(20)],
        *[{"introducer_name": "Alpha", "deposit_fully_paid": True, "course_category": "Language",
           "intake_year": 2026, "cycle_index": 2} for _ in range(7)],
        *[{"introducer_name": "Alpha", "deposit_partial": True, "course_category": "Language",
           "intake_year": 2026, "cycle_index": 2} for _ in range(2)],
        {"introducer_name": "Alpha", "deposit_fully_paid": True, "deferral_initiated": True,
         "course_category": "Pre-sessional English", "intake_year": 2026, "cycle_index": 2},
        # a partner who has only ever sold language courses must stay in scope
        {"introducer_name": "LangOnly", "deposit_fully_paid": True, "course_category": "Language",
         "intake_year": 2026, "cycle_index": 2},
    ]
    book.load(
        introducers=[{"partner_name": "Alpha", "lifecycle_stage": "Customer"},
                     {"partner_name": "LangOnly", "lifecycle_stage": "Lead"}],
        applications=apps,
    )
    stats = book.tiles(metrics)["active"]
    assert stats["cur"] == 20          # the 7 language deposits are not in it
    assert stats["pd"] == 0            # nor the language partials

    names = book.by_name(metrics)
    assert "LangOnly" in names, "a language-only deposit must still pull a name into scope"

    split = {r["category"]: r for r in book.overview(metrics)["course_split"]}
    assert split["Academic"]["act_cur"] == 20
    assert split["Language"]["act_cur"] == 8        # 7 from Alpha + 1 from LangOnly
    assert split["Language"]["pd"] == 2
    assert split["Language"]["n"] == 2
    assert split["Pre-sessional English"]["daa"] == 1
    assert split["Pre-sessional English"]["act_cur"] == 0   # DAA is not a deposit


# --------------------------------------------------------------------------
# filters: date range, team, intake, compare
# --------------------------------------------------------------------------

def _dep(name, year, month, cycle, n=1, **kw):
    return [{"introducer_name": name, "deposit_fully_paid": True, "intake_year": year,
             "intake_month_num": month, "cycle_index": cycle, **kw} for _ in range(n)]


def test_the_default_window_is_the_whole_current_year(book, metrics):
    book.load(
        introducers=[{"partner_name": "P", "lifecycle_stage": "Customer"}],
        applications=_dep("P", 2026, 9, 2, n=20) + _dep("P", 2025, 1, 0),
    )
    period = book.overview(metrics)["period"]
    assert (period["from"], period["to"], period["label"]) == ("2026-01", "2026-12", "2026")
    assert period["prior_label"] == "2025" and period["is_default"]
    # spelling the default out is the same request
    assert book.by_name(metrics, **{"from": "2026-01", "to": "2026-12"}) == book.by_name(metrics)


def test_a_month_window_counts_only_intakes_inside_it(book, metrics):
    book.load(
        introducers=[{"partner_name": "P", "lifecycle_stage": "Customer"}],
        applications=(_dep("P", 2026, 9, 2, n=20) + _dep("P", 2026, 1, 0, n=3)
                      + _dep("P", 2025, 9, 2, n=2) + _dep("P", 2024, 9, 2)
                      # no month: its year straddles the window, so it is in neither
                      + _dep("P", 2025, None, None)),
    )
    p = book.by_name(metrics, **{"from": "2025-09", "to": "2026-05"})["P"]
    assert p["act_cur"] == 5            # Sep 2025 x2 + Jan 2026 x3, not Sep 2026
    assert p["act_prev"] == 1           # Sep 2024 - May 2025
    assert p["act_life"] == 7           # everything up to May 2026, month-less 2025 included
    period = book.overview(metrics, **{"from": "2025-09", "to": "2026-05"})["period"]
    assert period["label"] == "Sep 2025 – May 2026"
    assert period["prior_label"] == "Sep 2024 – May 2025"
    assert not period["is_default"]


def test_a_reversed_range_is_swapped_and_a_bad_one_refused(book, metrics):
    book.load(introducers=[], applications=_dep("P", 2026, 9, 2, n=20))
    assert book.by_name(metrics, **{"from": "2026-12", "to": "2026-01"}) == book.by_name(metrics)
    for bad in ({"from": "2026-13"}, {"to": "Sept"}, {"cycles": "5"}):
        with pytest.raises(metrics.ViewError):
            book.overview(metrics, **bad)


def test_the_team_filter_keeps_only_that_teams_introducers(book, metrics):
    book.load(
        introducers=[
            {"partner_name": "North", "lifecycle_stage": "Customer", "srm_team": "North"},
            {"partner_name": "South", "lifecycle_stage": "Customer", "srm_team": "South"},
            {"partner_name": "Blank", "lifecycle_stage": "Customer", "srm_team": ""},
        ],
        applications=(_dep("North", 2026, 9, 2, n=20) + _dep("South", 2026, 9, 2, n=4)
                      + _dep("Ghost", 2026, 9, 2)),
    )
    assert set(book.by_name(metrics, teams="North")) == {"North"}
    # blank teams and names missing from the CRM are both Unassigned
    assert set(book.by_name(metrics, teams="South|Unassigned")) == {"South", "Blank", "Ghost"}

    out = book.overview(metrics, teams="South")
    assert out["totals"]["act_cur"] == 4
    assert out["filters"]["teams"] == ["South"]
    # the options are counted without the Team filter, so every team stays pickable
    assert {o["team"]: o["n"] for o in out["team_options"]} == {"North": 1, "South": 1, "Unassigned": 2}
    assert [r["act"] for r in out["funnel"]["all"]] == [4]


def test_the_intake_filter_keeps_only_those_cycles(book, metrics):
    book.load(
        introducers=[{"partner_name": "P", "lifecycle_stage": "Customer"}],
        applications=_dep("P", 2026, 9, 2, n=20) + _dep("P", 2026, 1, 0, n=3) + _dep("P", 2026, 5, 1),
    )
    assert book.by_name(metrics, cycles="0,1")["P"]["act_cur"] == 4
    assert book.by_name(metrics, cycles="2")["P"]["act_cur"] == 20
    # all three is no filter
    assert book.overview(metrics, cycles="0,1,2")["filters"]["cycles"] == []


def test_compare_is_the_same_filters_a_year_earlier(book, metrics):
    book.load(
        introducers=[{"partner_name": "P", "lifecycle_stage": "Customer", "became_customer_year": 2026},
                     {"partner_name": "Q", "lifecycle_stage": "Customer", "became_customer_year": 2025}],
        applications=(_dep("P", 2026, 9, 2, n=20) + _dep("Q", 2025, 9, 2, n=6)
                      + _dep("Q", 2025, 1, 0, n=2)),
    )
    assert book.overview(metrics)["compare"] is None
    cmp = book.overview(metrics, compare="1")["compare"]
    assert cmp["label"] == "2025"
    assert cmp["totals"]["act_cur"] == 8
    assert cmp["tiles"]["active"]["n"] == 1
    # cohorts are compared newest against newest: coh2026 now with coh2025 then
    assert cmp["tiles"]["coh2026"]["n"] == 1

    cmp = book.overview(metrics, compare="1", cycles="2")["compare"]
    assert cmp["totals"]["act_cur"] == 6
