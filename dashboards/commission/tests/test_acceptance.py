"""The spec's acceptance tests (section 9): UEL 1–10, Coventry tiers 12–13.
Test 11 (import flags the #5 bonus) is in test_importer.py."""
import pytest

from datetime import date

TODAY = date(2026, 9, 25)          # the same "today" the uel fixture publishes on


@pytest.fixture
def run(store, cur, uel):
    def go(intake, **student):
        s = {"course_level": "Undergraduate", "nationality": "India", "fee": 12000, "count": 1, **student}
        return store.simulate(cur, uel["id"], intake, s)["result"]
    return go


def test_1_sep26_ug_base_rate(run):
    r = run("2026-09")
    assert r["eligible"] and r["amount"] == 2640
    assert r["rate"] == 22


def test_2_sep26_ug_uplift_at_50(run):
    r = run("2026-09", count=50)
    assert r["amount"] == 2880 and r["rate"] == 24
    assert any(b["source"] == "Amendment #3" and b["reached"] for b in r["bonuses"])


def test_3_bangladesh_excluded_sep26(run):
    r = run("2026-09", nationality="Bangladesh")
    assert not r["eligible"] and r["amount"] == 0
    assert r["source"] == "Amendment #4"


def test_4_pakistan_eligible_jan26(run):
    r = run("2026-01", nationality="Pakistan")
    assert r["eligible"] and r["rate"] == 22


def test_5_pakistan_excluded_may26(run):
    r = run("2026-05", nationality="Pakistan")
    assert not r["eligible"] and r["source"] == "Amendment #2"


def test_6_jan26_psug_bonus_at_350(run):
    r = run("2026-01", course_level="Progression Pre-sessional→UG", count=350)
    assert r["amount"] == 3240 and r["rate"] == 27


def test_7_jan26_psug_one_short(run):
    r = run("2026-01", course_level="Progression Pre-sessional→UG", count=349)
    assert r["amount"] == 2640
    psug = next(b for b in r["bonuses"] if b["id"] == "b_psug")
    assert not psug["reached"] and psug["progress"] == "349 of 350"


def test_8_phd_excluded(run):
    r = run("2026-09", course_level="Doctorate/PhD")
    assert not r["eligible"] and r["amount"] == 0 and r.get("excluded")


def test_9_jan27_no_contract(run):
    r = run("2027-01")
    assert r["blocked"] and not r["eligible"]
    assert r["reason"].startswith("No valid contract for Jan 2027")


def test_10_publishing_5_blocked_outside_validity(store, cur, uel):
    with pytest.raises(store.CommissionError) as exc:
        store.publish_amendment(cur, uel["amendments"][5]["id"], "test", today=TODAY)
    assert exc.value.status == 409
    assert "outside the contract's validity" in str(exc.value)


def test_extension_lifts_the_block(store, cur, uel):
    ext = store.create_amendment(cur, uel["id"], {
        "type": "EXTENSION", "reference": "Renewal letter", "received_on": "2026-09-20",
        "document_file": "renewal.pdf", "scope_mode": "INTAKE", "changes": {"new_end_date": "2027-12-31"}}, "test")
    store.publish_amendment(cur, ext["id"], "test", today=TODAY)
    store.publish_amendment(cur, uel["amendments"][5]["id"], "test", today=TODAY)
    # the base intake scope still runs up to Sep 2026, so Jan 2027 needs the scope widened too
    r = store.effective(cur, uel["id"], "2027-01")
    assert not r["ok"] and "up to Sep 2026" in r["reason"]


def test_ucfb_and_fafsa_excluded(run):
    assert not run("2026-01", campus="UCFB")["eligible"]
    assert not run("2026-01", flags=["federal_aid"])["eligible"]


def test_conflicting_rate_changes_need_supersedes(store, cur, uel):
    cid = uel["id"]
    common = {"reference": "x", "received_on": "2026-02-01", "document_file": "x.pdf", "scope_mode": "INTAKE",
              "from_intake": "2026-05", "until_intake": "2026-05", "target_rule_ids": ["r_ug"],
              "changes": {"rules": [{"id": "r_ug_may", "name": "UG May", "course_levels": ["Undergraduate"],
                                     "pricing": "PERCENT", "structure": "PER_STUDENT", "value": 23,
                                     "fee_year_scope": "YEAR_1"}]}}
    first = store.create_amendment(cur, cid, {"type": "RATE_CHANGE", **common}, "test")
    store.publish_amendment(cur, first["id"], "test", today=TODAY)
    second = store.create_amendment(cur, cid, {"type": "RATE_CHANGE", **common}, "test")
    with pytest.raises(store.CommissionError):
        store.publish_amendment(cur, second["id"], "test", today=TODAY)
    store.update_amendment(cur, second["id"], {"supersedes_amendment_id": first["id"]}, "test")
    store.publish_amendment(cur, second["id"], "test", today=TODAY)


def test_backdated_amendment_opens_a_recalc_batch(store, cur, uel):
    cur.execute("select reason from recalc_batches where contract_id = %s", (uel["id"],))
    reasons = [r["reason"] for r in cur.fetchall()]
    assert any("#4" in r for r in reasons)          # Sep 2026, published 25 Sep 2026


def test_every_write_is_audited(store, cur, uel):
    entries = store.audit_entries(cur, uel["id"])
    actions = {(e["entity"], e["action"]) for e in entries}
    assert {("contract", "create"), ("contract_version", "publish"), ("amendment", "publish")} <= actions


def test_inactive_means_no_terms_from_its_date(store, cur, uel):
    store.set_status(cur, uel["id"], "INACTIVE", "Terminated by the university", "2026-05-01", "test")
    assert store.effective(cur, uel["id"], "2026-01")["ok"]
    assert not store.effective(cur, uel["id"], "2026-05")["ok"]


def test_tiers_and_milestones_block_save(store, cur):
    bad = {**UEL_TIERED, "terms": {"rules": [{**TIERED_RULE, "tiers": [
        {"min_count": 1, "max_count": 20, "value": 15}, {"min_count": 22, "max_count": None, "value": 17.5}]}]}}
    with pytest.raises(store.CommissionError) as exc:
        store.create_contract(cur, bad, "test")
    assert exc.value.status == 422
    bad = {**UEL_TIERED, "terms": {"rules": [TIERED_RULE], "milestones": [{"trigger": "ENROLLED", "pct": 60}]}}
    with pytest.raises(store.CommissionError):
        store.create_contract(cur, bad, "test")


def test_timeline_marks_the_gap(store, cur, uel):
    t = store.timeline(cur, uel["id"], TODAY)
    cols = {c["intake"]: c for c in t["columns"] if c["in_default"]}
    assert cols["2026-09"]["ok"] and not cols["2027-01"]["ok"]
    assert "2027-01" in [a["intake"] for a in t["alerts"]]


def test_list_raises_the_next_intake_gap(store, cur, uel):
    row = next(r for r in store.list_contracts(cur, TODAY) if r["id"] == uel["id"])
    assert {"kind": "gap", "message": "No terms for Jan 2027"} in row["alerts"]
    assert row["days_to_expiry"] == 97


# --- Coventry tiers -----------------------------------------------------------

TIERS = [{"min_count": 1, "max_count": 20, "value": 15}, {"min_count": 21, "max_count": 100, "value": 17.5},
         {"min_count": 101, "max_count": 150, "value": 20}, {"min_count": 151, "max_count": None, "value": 25}]
TIERED_RULE = {"id": "r_cov", "name": "All courses", "course_levels": ["Undergraduate"], "pricing": "PERCENT",
               "structure": "TIERED", "tiers": TIERS, "tier_mode": "RETROACTIVE", "count_metric": "ENROLMENT",
               "count_scope": "ACADEMIC_YEAR", "fee_year_scope": "YEAR_1"}
UEL_TIERED = {"party_name": "Coventry University", "party_type": "UNIVERSITY", "region": "UK"}


def test_12_retroactive_true_up(calc):
    entries = calc.accrue(TIERED_RULE, [10000] * 21)
    commission = [e for e in entries if e["kind"] == "COMMISSION"]
    assert commission[19]["rate"] == 15 and commission[20]["rate"] == 17.5
    true_ups = [e for e in entries if e["kind"] == "TRUE_UP"]
    assert sorted(e["student"] for e in true_ups) == list(range(1, 21))
    assert all(e["rate"] == 2.5 and e["amount"] == 250 for e in true_ups)


def test_13_marginal_no_true_up(calc):
    entries = calc.accrue({**TIERED_RULE, "tier_mode": "MARGINAL"}, [10000] * 21)
    assert not [e for e in entries if e["kind"] == "TRUE_UP"]
    assert entries[-1]["rate"] == 17.5 and entries[0]["rate"] == 15


def test_retroactive_simulator_rates_everyone_at_the_count(calc):
    terms = {"ok": True, "currency": "GBP", "rules": [TIERED_RULE], "bonuses": [], "territory_rules": [],
             "exclusions": []}
    r = calc.calculate(terms, {"course_level": "Undergraduate", "fee": 10000, "count": 21, "position": 3})
    assert r["amount"] == 1750
    r = calc.calculate({**terms, "rules": [{**TIERED_RULE, "tier_mode": "MARGINAL"}]},
                       {"course_level": "Undergraduate", "fee": 10000, "count": 21, "position": 3})
    assert r["amount"] == 1500
