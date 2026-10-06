"""The workbook importer. Test 11 runs on a synthetic copy of the UEL block
(rows 187–195 of the UK tab, moved to rows 3–11) so it does not depend on the
real workbook; the checks against the real workbook run only where a copy is
at /tmp/cs_new.xlsx inside the api container."""
import os

import pytest

WORKBOOK = "/tmp/cs_new.xlsx"
COUNTRIES = [{"name": n, "aliases": a} for n, a in (
    ("Sri Lanka", ["Srilanka"]), ("Kenya", []), ("Afghanistan", []), ("Cameroon", []), ("Myanmar", ["Burma"]),
    ("Sudan", []), ("South Sudan", []), ("Pakistan", []), ("Bangladesh", []), ("India", []),
    ("United States", ["USA", "US"]),
)]

UK_HEADERS = {
    "A": "Institution Name", "B": "Global Territory", "C": "Territories Covered / Restrictions",
    "D": "Academic Year", "E": "Applicable Intake (Months)", "F": "Rule Type", "G": "Recruitment Mode",
    "H": "Course Level", "I": "Commission", "J": "Commission", "K": "Campus", "L": "Commission Structure",
    "M": "Pricing", "N": "Commission Start Range", "O": "VAT", "P": "Gross/Net",
    "Q": "Specification/ Restriction", "R": "Target", "T": "Bonus Criteria", "U": "Bonus Structure (Rate)",
    "V": "Bonus Structure (Number of Students)", "W": "Bonus Payment", "X": "Bonus Start Range",
    "Z": "Contract Start Date", "AA": "Contract End Date",
}

TERRITORY = (
    "Restricted countries: Srilanka, Kenya, Afghanistan, Cameroon, Myanmar, Sudan\n"
    "Pakistan: not accepting applications from May 2026 intake until further notice\n"
    "Bangladesh: closed for recruitment from September 2026 intake (informed on 1-Sept-2026)"
)
SPEC = ("No Commission for:\nDistance learning programmes\nPartner, franchise and validation programmes\n"
        "PhD and MRes\nUCFB campus")

# row -> (H course level, I rate, T criteria, U bonus rate, V bonus count); rows 3–10 are 187–194
ROWS = {
    3: ("Undergraduate", "22%", "September 2026 Intake", 0.02, "50+"),
    4: ("Post Graduate Taught, Presessional English", "20%", None, 0.05, "200+"),
    5: ("pathway (Malvern house)", "20%", None, 0.08, "300+"),
    6: ("Progression Pre-Sessional to PGT", "20%", "May 2026, January 2026 Intake: for all new students",
        0.02, "75+ (Per Intake)"),
    7: ("Pre-Sessional to UG", "22%", "May 2026 and January 2026 Intake combined", 0.05, "350+ (combined)"),
    8: ("Progression Pre-Sessional to PGT, Postgraduate", "15%", None, 0.08, "500+ (combined)"),
    9: ("Progression Pre-Sessional to UG, Undergraduate", "17. 5%", "May 2025 and September 2025 Intake",
        0.05, "350+"),
    10: ("pathway", "20%", None, 0.08, "500+"),
}


def _col(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def uel_sheet(xlsx):
    from datetime import datetime
    cells = {(1, _col(k)): v for k, v in UK_HEADERS.items()}
    cells[(2, _col("I"))] = "Percentage"
    cells[(2, _col("J"))] = "Number of students"
    put = {"A": "University of East London\nDocklands and Stratford", "B": "Global with restrictions",
           "C": TERRITORY, "D": "2025-2026, 2026-2027", "K": "Docklands", "L": "Per student", "M": "Percentage",
           "O": "Exclusive", "P": "Net", "Z": datetime(2025, 9, 1), "AA": datetime(2026, 12, 31)}
    for k, v in put.items():
        cells[(3, _col(k))] = v
    cells[(3, _col("E"))] = "Applicable until September 2026 Intake"
    cells[(8, _col("E"))] = "Applicable from Jan 2027 intake for all further intakes"
    cells[(3, _col("Q"))] = SPEC
    for r, (h, i, t, u, v) in ROWS.items():
        cells[(r, _col("H"))] = h
        cells[(r, _col("I"))] = i
        cells[(r, _col("U"))] = u
        cells[(r, _col("V"))] = v
        cells[(r, _col("W"))] = "Per student"
        if t:
            cells[(r, _col("T"))] = t
    merged = [(3, c, 11, c) for c in map(_col, ("A", "B", "C", "D", "K", "L", "M", "O", "P", "Z", "AA"))]
    merged += [(3, _col("E"), 7, _col("E")), (8, _col("E"), 11, _col("E")),
               (3, _col("T"), 5, _col("T")), (7, _col("T"), 8, _col("T")), (3, _col("Q"), 11, _col("Q"))]
    return xlsx.Sheet(name="UK - Academic - Commission", cells=cells, merged=merged, max_row=11, max_col=30)


@pytest.fixture
def uel(importer, xlsx):
    parsed = importer.parse_workbook([uel_sheet(xlsx)], COUNTRIES)
    assert len(parsed["contracts"]) == 1
    return parsed["contracts"][0]


def test_11_uel_amendment_5_bonus_flagged(uel):
    """Import UEL: Amendment #5's UG bonus is flagged needs_review because its
    criteria cite May/Sep 2025, before the change applies."""
    a5 = next(a for a in uel["amendments"] if a["number"] == 5)
    assert a5["type"] == "RATE_CHANGE" and a5["from_intake"] == "2027-01"
    ug = next(b for b in a5["changes"]["bonuses"] if "2025" in b["criteria_text"])
    assert ug["needs_review"] is True
    assert "May 2025" in ug["review_note"] and "Sep 2025" in ug["review_note"]
    assert ug["tiers"] == [{"min_count": 350, "max_count": None, "value": 5.0}]


def test_uel_amendments_in_order(uel):
    got = [(a["number"], a["type"], a.get("from_intake"), a.get("until_intake")) for a in uel["amendments"]]
    assert got == [
        (1, "BONUS_INCENTIVE", "2026-01", "2026-05"),
        (2, "SCOPE_CHANGE", "2026-05", None),
        (3, "BONUS_INCENTIVE", "2026-09", "2026-09"),
        (4, "SCOPE_CHANGE", "2026-09", None),
        (5, "RATE_CHANGE", "2027-01", None),
    ]
    a2, a4 = uel["amendments"][1], uel["amendments"][3]
    assert [t["value"] for t in a2["changes"]["add_territory_rules"]] == ["Pakistan"]
    assert [t["value"] for t in a4["changes"]["add_territory_rules"]] == ["Bangladesh"]
    assert a4["received_on"] == "2026-09-01"
    assert all(a["needs_review"] for a in (a2, a4, uel["amendments"][4]))


def test_uel_base_terms(uel):
    assert uel["party_name"] == "University of East London"
    assert uel["intake_scope"] == {"mode": "UP_TO", "until_intake": "2026-09"}
    assert uel["academic_years"] == ["2025-26", "2026-27"]
    assert (uel["start_date"], uel["end_date"]) == ("2025-09-01", "2026-12-31")
    assert (uel["vat_treatment"], uel["vat_rate"], uel["fee_basis"], uel["currency"]) == ("EXCLUSIVE", 20, "NET", "GBP")
    t = uel["terms"]
    assert sorted(x["value"] for x in t["territory_rules"]) == \
        sorted(["Sri Lanka", "Kenya", "Afghanistan", "Cameroon", "Myanmar", "Sudan"])
    assert {e["type"] for e in t["exclusions"]} == \
        {"ONLINE_DISTANCE", "FRANCHISE_PARTNER", "RESEARCH_DEGREE", "CAMPUS"}
    assert next(e for e in t["exclusions"] if e["type"] == "CAMPUS")["campus"] == "UCFB"
    assert [(r["course_levels"], r["value"]) for r in t["rules"]] == [
        (["Undergraduate"], 22), (["Postgraduate Taught", "Pre-sessional English"], 20),
        (["Foundation/IFY", "International Year One", "Accelerated IFY"], 20),
        (["Progression Pre-sessional→PGT"], 20), (["Progression Pre-sessional→UG"], 22),
    ]
    a5 = uel["amendments"][4]
    assert [r["value"] for r in a5["changes"]["rules"]] == [15, 17.5, 20]
    base = {r["id"]: r for r in t["rules"]}
    assert {tuple(base[i]["course_levels"]) for i in a5["target_rule_ids"]} >= {("Undergraduate",)}


def test_value_parsers(importer):
    assert importer.parse_percent("17. 5%") == 17.5
    assert importer.parse_percent(0.15) == 15
    assert importer.parse_range("1- 20") == ({"min_count": 1, "max_count": 20}, None)
    assert importer.parse_range("50+(Per Intake)")[0] == {"min_count": 50, "max_count": None}
    from datetime import datetime
    rng, why = importer.parse_range(datetime(2025, 11, 15))
    assert rng == {"min_count": 11, "max_count": 15} and why
    assert importer.parse_money("£1,000") == (1000.0, "GBP")
    assert importer.find_intakes("January and May 2026 intakes") == ["2026-01", "2026-05"]
    assert importer.find_intakes("informed on 1-Sept-2026") == []
    levels, unmatched = importer.course_levels("Progression Pre-Sessional to UG, Undergraduate")
    assert levels == ["Progression Pre-sessional→UG", "Undergraduate"] and not unmatched


@pytest.mark.skipif(not os.path.exists(WORKBOOK), reason="real workbook not present")
def test_real_workbook_coventry_tiers(importer, xlsx, cur):
    cur.execute("select name, aliases from countries")
    parsed = importer.parse_workbook(xlsx.read(WORKBOOK), cur.fetchall())
    assert len(parsed["contracts"]) > 300
    cov = next(c for c in parsed["contracts"] if c["party_name"] == "Coventry University")
    tiered = next(r for r in cov["terms"]["rules"] if r["structure"] == "TIERED" and r["tiers"])
    assert [(t["min_count"], t["max_count"], t["value"]) for t in tiered["tiers"]] == \
        [(1, 20, 15), (21, 100, 17.5), (101, 150, 20), (151, None, 25)]
    assert tiered["tier_mode"] == "RETROACTIVE"


@pytest.mark.skipif(not os.path.exists(WORKBOOK), reason="real workbook not present")
def test_real_workbook_preview_and_commit(importer, store, cur):
    """Preview writes only the batch; commit makes DRAFT contracts and
    amendments. Rolled back by the cur fixture."""
    with open(WORKBOOK, "rb") as f:
        report = importer.preview(cur, "cs_new.xlsx", f.read(), "test")
    assert report["totals"]["contracts"] == len(report["contracts"]) and "payload" not in report["contracts"][0]
    uel_row = next(c for c in report["contracts"] if c["party_name"] == "University of East London")
    result = importer.commit(cur, report["id"], "test", skip=[])
    assert result["created"] + result["updated"] > 300
    assert not result["failed"], result["failed"][:3]
    cur.execute("""select a.number, a.type, a.needs_review, a.status from amendments a join contracts c on c.id = a.contract_id
                   where c.import_batch_id = %s and c.source_tab = %s and c.source_rows = %s order by a.number""",
                (report["id"], uel_row["tab"], uel_row["rows"]))
    got = cur.fetchall()
    assert [(a["number"], a["type"]) for a in got][-1] == (5, "RATE_CHANGE")
    assert got[-1]["needs_review"] and got[-1]["status"] == "DRAFT"
    with pytest.raises(store.CommissionError):
        importer.commit(cur, report["id"], "test", skip=[])
