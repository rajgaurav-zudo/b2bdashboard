"""Contracts built through store.py inside a transaction that is rolled back, so
the acceptance tests run the same code the API does and leave nothing behind."""
import sys
from datetime import date

import pytest

sys.path.insert(0, "/srv/api")

TODAY = date(2026, 9, 25)


def _mod(name):
    from app.registry import get
    return get("commission").load_module(name)


@pytest.fixture(scope="session")
def store():
    return _mod("store")


@pytest.fixture(scope="session")
def calc():
    return _mod("calc")


@pytest.fixture(scope="session")
def importer():
    return _mod("importer")


@pytest.fixture(scope="session")
def xlsx():
    return _mod("xlsx")


@pytest.fixture
def cur():
    from app.db import pool
    from app.registry import get

    pool.open()
    with pool.connection() as conn:
        with conn.cursor() as c:
            c.execute(f'set local search_path to "{get("commission").db_schema}", public')
            yield c
        conn.rollback()


def pct_rule(rid, name, levels, value):
    return {"id": rid, "name": name, "course_levels": levels, "pricing": "PERCENT", "structure": "PER_STUDENT",
            "value": value, "fee_year_scope": "YEAR_1"}


def uplift(bid, rule_ids, at, value, criteria, scope="INTAKE", intakes=None):
    return {"id": bid, "applies_to_rule_ids": rule_ids, "kind": "RATE_UPLIFT", "count_scope": scope,
            "count_intakes": intakes or [], "tier_mode": "RETROACTIVE", "criteria_text": criteria,
            "tiers": [{"min_count": at, "max_count": None, "value": value}]}


PATHWAY = ["Foundation/IFY", "International Year One", "Accelerated IFY"]

UEL_BASE = {
    "party_name": "University of East London", "party_type": "UNIVERSITY", "region": "UK",
    "start_date": "2025-09-01", "end_date": "2026-12-31", "currency": "GBP",
    "vat_treatment": "EXCLUSIVE", "vat_rate": 20, "fee_basis": "NET",
    "territory_type": "GLOBAL_WITH_RESTRICTIONS", "academic_years": ["2025-26", "2026-27"],
    "intake_scope": {"mode": "UP_TO", "until_intake": "2026-09"},
    "terms": {
        "campuses": ["Docklands", "Stratford"],
        "territory_rules": [{"type": "EXCLUDE", "scope": "NATIONALITY", "value": v}
                            for v in ("Sri Lanka", "Kenya", "Afghanistan", "Cameroon", "Myanmar", "Sudan")],
        "rules": [
            pct_rule("r_ug", "Undergraduate", ["Undergraduate"], 22),
            pct_rule("r_pgt", "PGT and Pre-sessional", ["Postgraduate Taught", "Pre-sessional English"], 20),
            pct_rule("r_path", "Pathway (IFY / IYO / IFP)", PATHWAY, 20),
            pct_rule("r_pspgt", "Pre-sessional → PGT", ["Progression Pre-sessional→PGT"], 20),
            pct_rule("r_psug", "Pre-sessional → UG", ["Progression Pre-sessional→UG"], 22),
        ],
        "exclusions": [
            {"type": "ONLINE_DISTANCE", "note": "distance learning"},
            {"type": "FRANCHISE_PARTNER", "note": "partner, franchise and validation programmes"},
            {"type": "RESEARCH_DEGREE", "note": "PhD and MRes"},
            {"type": "CAMPUS", "campus": "UCFB", "note": "UCFB"},
            {"type": "FEDERAL_AID", "note": "FAFSA-funded students"},
        ],
    },
}


def amendment(store, cur, cid, **kw):
    base = {"reference": f"Email {kw.get('number', '')}", "document_file": "amendment.pdf", "scope_mode": "INTAKE"}
    return store.create_amendment(cur, cid, {**base, **kw}, "test")


@pytest.fixture
def uel(store, cur):
    """UEL with base terms published and amendments #1–#4 published; #5 left
    as a draft (it cannot be published: it sits outside validity)."""
    c = store.create_contract(cur, UEL_BASE, "test")
    cid = c["id"]
    store.publish_contract(cur, cid, "test", today=TODAY)
    a = {}
    a[1] = amendment(store, cur, cid, number=1, type="BONUS_INCENTIVE", received_on="2025-12-01",
                     from_intake="2026-01", until_intake="2026-05",
                     summary="Jan + May 2026 progression bonuses",
                     changes={"bonuses": [
                         uplift("b_pspgt", ["r_pspgt"], 75, 2, "PS→PGT +2% at 75 per intake"),
                         uplift("b_psug", ["r_psug"], 350, 5, "PS→UG +5% at 350 (Jan + May combined)",
                                scope="COMBINED_INTAKES", intakes=["2026-01", "2026-05"]),
                     ]})
    a[2] = amendment(store, cur, cid, number=2, type="SCOPE_CHANGE", received_on="2026-03-15",
                     from_intake="2026-05", summary="Pakistan excluded from May 2026",
                     changes={"add_territory_rules": [{"type": "EXCLUDE", "scope": "NATIONALITY", "value": "Pakistan"}]})
    a[3] = amendment(store, cur, cid, number=3, type="BONUS_INCENTIVE", received_on="2026-06-01",
                     from_intake="2026-09", until_intake="2026-09", summary="Sep 2026 uplifts",
                     changes={"bonuses": [
                         uplift("b_ug", ["r_ug"], 50, 2, "UG +2% at 50 per intake"),
                         uplift("b_pgt", ["r_pgt"], 200, 5, "PGT +5% at 200 per intake"),
                         uplift("b_path", ["r_path"], 300, 8, "Pathway +8% at 300 per intake"),
                     ]})
    a[4] = amendment(store, cur, cid, number=4, type="SCOPE_CHANGE", received_on="2026-09-01",
                     from_intake="2026-09", summary="Bangladesh excluded from Sep 2026",
                     changes={"add_territory_rules": [{"type": "EXCLUDE", "scope": "NATIONALITY", "value": "Bangladesh"}]})
    for n in (1, 2, 3, 4):
        a[n] = store.publish_amendment(cur, a[n]["id"], "test", today=TODAY)
    a[5] = amendment(store, cur, cid, number=5, type="RATE_CHANGE", received_on="2026-09-10",
                     from_intake="2027-01", summary="New rates from Jan 2027",
                     target_rule_ids=["r_ug", "r_pgt", "r_path", "r_pspgt", "r_psug"],
                     changes={"rules": [
                         pct_rule("r_ug27", "UG and PS→UG", ["Undergraduate", "Progression Pre-sessional→UG"], 17.5),
                         pct_rule("r_pg27", "PG and PS→PGT", ["Postgraduate Taught", "Progression Pre-sessional→PGT"], 15),
                         pct_rule("r_path27", "Pathway and Pre-sessional", PATHWAY + ["Pre-sessional English"], 20),
                     ]})
    return {"id": cid, "amendments": a}
