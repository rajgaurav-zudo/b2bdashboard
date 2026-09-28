"""Names, enums and small helpers shared by every other module here.

Nothing in this file touches the database, so validation, resolution and the
calculation can be tested as plain functions over dicts.
"""
import re
import uuid
from datetime import date

PARTY_TYPES = ("UNIVERSITY", "PATHWAY_PROVIDER", "OUTBOUND_AGENT", "SCHOOL")
REGIONS = ("UK", "NORTH_AMERICA", "EU_IRELAND", "OCEANIA", "ROW")
STATUSES = ("DRAFT", "ACTIVE", "INACTIVE", "EXPIRED")
VAT = ("INCLUSIVE", "EXCLUSIVE", "NOT_APPLICABLE")
FEE_BASIS = ("GROSS", "NET")
TERRITORY = ("GLOBAL", "GLOBAL_WITH_RESTRICTIONS", "NOT_GLOBAL")
INTAKE_SCOPE_MODES = ("ENTIRE_YEAR", "INTAKES", "UP_TO")
PRICING = ("PERCENT", "FLAT")
STRUCTURE = ("PER_STUDENT", "TIERED")
FEE_YEAR_SCOPE = ("YEAR_1", "ALL_YEARS")
TIER_MODE = ("RETROACTIVE", "MARGINAL")
COUNT_METRIC = ("ENROLMENT", "CAS", "APPLICATION", "DEPOSIT")
COUNT_SCOPE = ("INTAKE", "ACADEMIC_YEAR", "COMBINED_INTAKES", "CONTRACT_YEAR", "CUSTOM_WINDOW")
BONUS_KIND = ("RATE_UPLIFT", "FIXED_PER_STUDENT", "LUMP_SUM")
TERRITORY_RULE_TYPE = ("INCLUDE", "EXCLUDE")
TERRITORY_SCOPE = ("COUNTRY", "NATIONALITY", "RESIDENCE", "REGION")
EXCLUSION_TYPES = ("ONLINE_DISTANCE", "PRESESSIONAL", "HOME_FEE", "RUK_FEE", "NON_FEE_PAYING",
                   "FEDERAL_AID", "FRANCHISE_PARTNER", "RESEARCH_DEGREE", "CAMPUS", "OTHER")
MILESTONE_TRIGGERS = ("CAS_ISSUED", "ENROLLED", "FEE_CLEARED", "N_WEEKS_ENROLLED", "CENSUS")
PAYMENT_CONDITIONS = ("FEE_FULLY_CLEARED", "FEE_PCT_RECEIVED")
AGENT_CHANGE = ("FIRST_INTRODUCER", "CURRENT_AGENT", "SPLIT")
AMENDMENT_TYPES = ("RATE_CHANGE", "RULE_ADDITION", "BONUS_INCENTIVE", "INTAKE_NOTE",
                   "SCOPE_CHANGE", "EXTENSION", "SUSPENSION")
SCOPE_MODES = ("INTAKE", "DATE_WINDOW", "BOTH")
APPLICABILITY = ("INTAKE_START", "APPLICATION_DATE", "CAS_DATE", "DEPOSIT_DATE", "ENROLMENT_DATE")

COURSE_LEVELS = (
    "Undergraduate", "Postgraduate Taught", "Postgraduate Research", "Doctorate/PhD", "MRes",
    "Foundation/IFY", "Accelerated IFY", "International Year One", "Pre-Masters",
    "Pre-sessional English", "Progression IFY→UG", "Progression Pre-sessional→UG",
    "Progression Pre-sessional→PGT", "Progression UG→PG", "Progression UG Year 2+",
    "Study Abroad", "Short course / Summer school", "GCSE", "A-Level", "Diploma/HND/HNC",
    "Language course", "Boarding school",
)

# Which course levels an exclusion type rules out on its own, without the
# exclusion having to list them.
EXCLUSION_LEVELS = {
    "RESEARCH_DEGREE": ("Postgraduate Research", "Doctorate/PhD", "MRes"),
    "PRESESSIONAL": ("Pre-sessional English",),
}
# ...and which student flags it matches (the simulator's checkboxes)
EXCLUSION_FLAGS = {
    "ONLINE_DISTANCE": "online_distance", "HOME_FEE": "home_fee", "RUK_FEE": "ruk_fee",
    "NON_FEE_PAYING": "non_fee_paying", "FEDERAL_AID": "federal_aid",
    "FRANCHISE_PARTNER": "franchise_partner",
}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTH_NAMES = ("january", "february", "march", "april", "may", "june", "july", "august",
               "september", "october", "november", "december")
MAJOR_MONTHS = (1, 5, 9)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# --- intakes ------------------------------------------------------------------
# An intake is 'YYYY-MM'. Compared as strings they sort correctly.

def intake(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def intake_start(value: str) -> date:
    y, m = value.split("-")
    return date(int(y), int(m), 1)


def intake_label(value: str) -> str:
    y, m = value.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def add_months(value: str, n: int) -> str:
    y, m = (int(p) for p in value.split("-"))
    idx = y * 12 + (m - 1) + n
    return intake(idx // 12, idx % 12 + 1)


def intake_of(d: date) -> str:
    return intake(d.year, d.month)


def major_intakes_around(today: date, before: int = 2, after: int = 4) -> list[str]:
    """The previous `before` and next `after` major intakes (Jan/May/Sep) around
    today; the intake in progress this month counts as next."""
    here = intake_of(today)
    majors = [intake(y, m) for y in range(today.year - 3, today.year + 4) for m in MAJOR_MONTHS]
    past = [i for i in majors if i < here]
    future = [i for i in majors if i >= here]
    return (past[-before:] if before else []) + future[:after]


def academic_year_of(value: str) -> str:
    """Sep 2025 .. Aug 2026 is '2025-26'."""
    y, m = (int(p) for p in value.split("-"))
    start = y if m >= 9 else y - 1
    return f"{start}-{str(start + 1)[-2:]}"


# --- names --------------------------------------------------------------------

def normalize_name(name: str) -> str:
    s = name.lower().replace("&", " and ")
    s = re.sub(r"\buniversity of\b", " ", s)
    s = re.sub(r"\bthe\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(s.split())


def same_place(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and normalize_name(a) == normalize_name(b)


def fmt_money(amount: float, currency: str | None) -> str:
    sym = {"GBP": "£", "USD": "$", "EUR": "€", "CAD": "C$", "AUD": "A$", "NZD": "NZ$"}.get(currency or "", "")
    return f"{sym}{amount:,.2f}" if sym else f"{amount:,.2f} {currency or ''}".strip()
