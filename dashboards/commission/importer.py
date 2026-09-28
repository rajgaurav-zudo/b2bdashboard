"""The contract register workbook -> DRAFT contracts, through a report a human
reads first.

`preview` parses the upload and stores the whole parse in import_batches.report;
nothing else is written. `commit` turns the report into DRAFT contracts and
amendments through store.py, so imported contracts pass the same save checks as
typed ones and are published the same way, one at a time, by a person.

Parsing follows the spec's section 4. Columns are found by header text because
positions differ per tab. A contract block starts at a non-empty column A and
runs to the next one; values are read through the sheet's merged ranges instead
of being forward-filled. Anything the parser cannot read with confidence is kept
with its cell reference and original text and marked needs_review, never
guessed silently.
"""
import copy
import hashlib
import io
import json
import re
from datetime import date, datetime

from app.registry import get as _dashboard

_dash = _dashboard("commission")
xlsx = _dash.load_module("xlsx")
model = _dash.load_module("model")
store = _dash.load_module("store")
validation = _dash.load_module("validation")

# Tab -> (party_type, region). None region = from the Country column. Pathways
# last, as the spec orders the work.
TABS = {
    "UK - Academic - Commission": ("UNIVERSITY", "UK"),
    "North America": ("UNIVERSITY", "NORTH_AMERICA"),
    "EU & Ireland": ("UNIVERSITY", "EU_IRELAND"),
    "Oceania": ("UNIVERSITY", "OCEANIA"),
    "ROW": ("UNIVERSITY", "ROW"),
    "LanguageBoarding Schools": ("SCHOOL", None),
    "Outbound Agents": ("OUTBOUND_AGENT", None),
    "UK Pathways": ("PATHWAY_PROVIDER", "UK"),
    "US Pathways": ("PATHWAY_PROVIDER", "NORTH_AMERICA"),
    "ROW Pathways": ("PATHWAY_PROVIDER", "ROW"),
}
INVOICING_TAB = "TEST- UK"
INVOICING_TARGET = "UK - Academic - Commission"

HEADERS = {
    "global territory": "territory",
    "territories covered/restrictions": "territories",
    "country": "country",
    "academic year": "academic_year",
    "applicable intake (months)": "intake",
    "rule type": "rule_type",
    "recruitment mode": "mode",
    "course level": "course_level",
    "campus": "campus",
    "commission structure": "structure",
    "pricing": "pricing",
    "commission start range": "start_range",
    "vat": "vat",
    "gross/net": "gross_net",
    "specification/restriction": "spec",
    "target": "target",
    "institution name": "institution",
    "bonus criteria": "b_criteria",
    "bonus structure (rate)": "b_rate",
    "bonus structure (number of students)": "b_count",
    "bonus payment": "b_payment",
    "bonus start range": "b_start",
    "incentive criteria": "i_criteria",
    "incentive structure (rate)": "i_rate",
    "incentive structure (number of students)": "i_count",
    "incentive payment": "i_payment",
    "incentive start range": "i_start",
    "contract start date": "start_date",
    "contract end date": "end_date",
    "invoicing deadline": "inv_deadline",
    "commission receivable timeline": "inv_receivable",
    "general notes on commission claims": "inv_notes",
    "invoicing mechanism": "inv_mechanism",
}

CURRENCY_DEFAULT = {"UK": "GBP", "EU_IRELAND": "EUR", "NORTH_AMERICA": "USD", "OCEANIA": "AUD"}
EU = {"austria", "belgium", "bulgaria", "croatia", "cyprus", "czech republic", "czechia", "denmark", "estonia",
      "finland", "france", "germany", "greece", "hungary", "ireland", "italy", "latvia", "lithuania",
      "luxembourg", "malta", "netherlands", "poland", "portugal", "romania", "slovakia", "slovenia", "spain",
      "sweden", "switzerland", "norway", "iceland", "monaco"}
UK_NAMES = {"uk", "united kingdom", "england", "scotland", "wales", "northern ireland", "great britain"}


# --- small parsers -------------------------------------------------------------

def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _norm_header(h) -> str:
    s = re.sub(r"\s+", " ", _text(h).lower())
    return s.replace(" /", "/").replace("/ ", "/")


MONTH_RE = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
            r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_MONTH = re.compile(r"\b" + MONTH_RE + r"\b", re.I)


def _month_no(token: str) -> int:
    return [m.lower() for m in model.MONTHS].index(token[:3].lower()) + 1


def parse_date(v):
    """A date, the string 'ROLLING', or None."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _text(v)
    if re.fullmatch(r"(?i)rolling.*", s):
        return "ROLLING"
    found = find_dates(s)
    return found[0] if found else None


def find_dates(s: str) -> list[date]:
    """Every full date written in the text: 2025-09-01, 31/10/2027,
    30-Sept-2028, 15th March 2027."""
    out = []
    pats = (
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda m: (int(m[1]), int(m[2]), int(m[3]))),
        (r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", lambda m: (int(m[3]), int(m[2]), int(m[1]))),
        (r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/.]*" + MONTH_RE + r"[a-z]*[\s\-/.,]*(\d{4})\b",
         lambda m: (int(m[3]), _month_no(m[2]), int(m[1]))),
    )
    for pat, parts in pats:
        for m in re.finditer(pat, s, re.I):
            try:
                out.append((m.start(), date(*parts(m))))
            except ValueError:
                pass
    return [d for _, d in sorted(out)]


def find_intakes(s: str) -> list[str]:
    """Month + year pairs that name an intake ('May 2026', '2025-September',
    'January and May 2026'), sorted. A month with a day number in front is a
    date, not an intake, and is left to find_dates."""
    found, pending = [], []
    for m in _MONTH.finditer(s):
        before = s[max(0, m.start() - 8):m.start()]
        if re.search(r"\d{1,2}(?:st|nd|rd|th)?[\s\-/.]*$", before) and not re.search(r"\d{4}\s*[-–/ ]\s*$", before):
            continue
        month = _month_no(m.group(1))
        after = s[m.end():m.end() + 10]
        y = re.match(r"[a-z]*[\s\-,'’.]*(\d{4})\b", after, re.I)
        y = int(y.group(1)) if y else None
        if y is None:
            yb = re.search(r"(\d{4})\s*[-–/ ]\s*$", before)
            y = int(yb.group(1)) if yb else None
        if y is None:
            pending.append(month)
            continue
        for p in pending:
            found.append(model.intake(y, p))
        pending = []
        found.append(model.intake(y, month))
    return sorted(set(found))


def parse_percent(v) -> float | None:
    """22% / 17. 5% / 15.0% / 0.15 -> 15.0."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return round(v * 100, 6) if v <= 1 else float(v)
    s = _text(v).replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)%?", s)
    if not m:
        return None
    n = float(m.group(1))
    return round(n * 100, 6) if "%" not in s and n <= 1 else n


CURRENCIES = (("£", "GBP"), ("GBP", "GBP"), ("POUND", "GBP"), ("€", "EUR"), ("EUR", "EUR"),
              ("CAD", "CAD"), ("C$", "CAD"), ("AUD", "AUD"), ("A$", "AUD"), ("NZD", "NZD"),
              ("USD", "USD"), ("$", "USD"))


def parse_money(v) -> tuple[float, str] | None:
    """£1,000 / GBP 1,000 / $2,500 / 500 Pounds -> (amount, currency)."""
    s = _text(v)
    up = s.upper()
    cur = next((code for sym, code in CURRENCIES if sym in up), None)
    if not cur:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", s)
    return (float(m.group(0).replace(",", "")), cur) if m else None


def parse_range(v) -> tuple[dict | None, str | None]:
    """'1- 20', '151+', '1-10 International Students' -> ({min_count, max_count},
    problem). A date-typed cell is an Excel-mangled range: 2025-11-15 was
    '11-15', so the candidate is rebuilt from month and day and flagged."""
    if v is None or v == "":
        return None, None
    if isinstance(v, (datetime, date)):
        return ({"min_count": v.month, "max_count": v.day},
                f"cell holds the date {v:%Y-%m-%d}; read as {v.month}-{v.day}, check the range")
    if isinstance(v, (int, float)):
        return {"min_count": int(v), "max_count": int(v)}, None
    s = _text(v)
    m = re.match(r"\s*(\d+)\s*(?:-|–|to)\s*(\d+)", s)
    if m:
        return {"min_count": int(m.group(1)), "max_count": int(m.group(2))}, None
    m = re.match(r"\s*(\d+)\s*\+", s) or re.match(r"\s*(?:above|over|more than)\s*(\d+)", s, re.I)
    if m:
        return {"min_count": int(m.group(1)), "max_count": None}, None
    return None, f"cannot read a student range from {s[:60]!r}"


def academic_years(v) -> tuple[list[str], str | None]:
    if v is None or v == "":
        return [], None
    if isinstance(v, (int, float)):
        return [], f"academic year is the number {v}"
    out = []
    for m in re.finditer(r"(\d{4})\s*[-/–]\s*(\d{2,4})", _text(v)):
        out.append(f"{m.group(1)}-{m.group(2)[-2:]}")
    return sorted(set(out)), (None if out else f"cannot read academic years from {_text(v)[:60]!r}")


def start_range_mode(v) -> str | None:
    s = _text(v).lower()
    if "first student" in s:
        return "RETROACTIVE"
    if "within" in s:
        return "MARGINAL"
    return None


# --- course levels ------------------------------------------------------------

PATHWAY_LEVELS = ["Foundation/IFY", "International Year One", "Accelerated IFY"]
LEVEL_PATTERNS = (
    (r"(progression.*pre.?sessional|pre.?sessional\s*(to|→|->)).*(pgt|post ?grad|master|pg\b)", ["Progression Pre-sessional→PGT"]),
    (r"(progression.*pre.?sessional|pre.?sessional\s*(to|→|->)).*(ug\b|under ?grad|bachelor)", ["Progression Pre-sessional→UG"]),
    (r"progression.*(ify|foundation).*(ug\b|under ?grad|degree)", ["Progression IFY→UG"]),
    (r"progression.*(ug\b|under ?grad).*(pg\b|post ?grad|master)", ["Progression UG→PG"]),
    (r"progression.*(year ?2|second year|2nd year|year two)", ["Progression UG Year 2+"]),
    (r"pre.?sessional", ["Pre-sessional English"]),
    (r"accelerated", ["Accelerated IFY"]),
    (r"international year one|\biy1\b|\biyo\b|year one", ["International Year One"]),
    (r"pre.?master", ["Pre-Masters"]),
    (r"pathway", PATHWAY_LEVELS),
    (r"foundation|\bify\b|\bifp\b", ["Foundation/IFY"]),
    (r"\bmres\b", ["MRes"]),
    (r"phd|doctora", ["Doctorate/PhD"]),
    (r"post ?grad\w* research|\bpgr\b|research degree|\bmphil\b", ["Postgraduate Research"]),
    (r"post ?grad|\bpgt\b|\bpg\b|master|\bmba\b|\bmsc\b|\bllm\b", ["Postgraduate Taught"]),
    (r"under ?grad|\bug\b|bachelor|\bba\b|\bbsc\b", ["Undergraduate"]),
    (r"study abroad|exchange|semester abroad", ["Study Abroad"]),
    (r"summer|short course|winter school", ["Short course / Summer school"]),
    (r"gcse", ["GCSE"]),
    (r"a.?level", ["A-Level"]),
    (r"diploma|\bhnd\b|\bhnc\b|certificate", ["Diploma/HND/HNC"]),
    (r"boarding|high school|secondary school", ["Boarding school"]),
    (r"language|english|\besl\b|\bielts\b|young learner|junior course|adult course", ["Language course"]),
)


ALL_COURSES = re.compile(r"^all\b.*\b(courses?|programmes?|programs?)$", re.I)


def course_levels(v) -> tuple[list[str], list[str]]:
    """(levels, fragments that matched nothing). The text is split into
    fragments and each fragment takes its first matching pattern, so
    'Progression Pre-Sessional to PGT' is a progression, not a PGT."""
    s = _text(v)
    levels: list[str] = []
    unmatched = []
    for frag in re.split(r",|\n|;|/|&|\+|\band\b", re.sub(r"\([^)]*\)", " ", s), flags=re.I):
        f = frag.strip(" .:-*•\t").lower()
        if len(re.sub(r"[^a-z]", "", f)) < 2 or ALL_COURSES.match(f):
            continue
        for pat, out in LEVEL_PATTERNS:
            if re.search(pat, f):
                levels += [lv for lv in out if lv not in levels]
                break
        else:
            unmatched.append(frag.strip())
    if not levels:
        for pat, out in LEVEL_PATTERNS:           # the parentheses held the only clue
            if re.search(pat, s.lower()):
                levels = list(out)
                break
    return levels, unmatched


# --- places -------------------------------------------------------------------

class Places:
    """Country names found in free text, longest name first so 'South Sudan'
    is not also 'Sudan'. Short upper-case aliases (UK, US, UAE) match case-
    sensitively so 'informed to us' is not the United States."""

    def __init__(self, countries: list[dict]):
        names = []
        for c in countries:
            for n in [c["name"], *(c.get("aliases") or [])]:
                names.append((n, c["name"]))
        self.names = sorted(names, key=lambda p: -len(p[0]))

    def find(self, text: str) -> list[str]:
        s = text
        out = []
        for n, canonical in self.names:
            flags = 0 if (len(n) <= 3 and n.isupper()) else re.I
            pat = re.compile(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", flags)
            if pat.search(s):
                s = pat.sub(" ", s)
                if canonical not in out:
                    out.append(canonical)
        return out


def region_for_country(country: str) -> str:
    c = _text(country).lower()
    if not c:
        return "ROW"
    if c in UK_NAMES:
        return "UK"
    if c in ("usa", "us", "united states", "united states of america", "canada"):
        return "NORTH_AMERICA"
    if c in EU:
        return "EU_IRELAND"
    if c in ("australia", "new zealand"):
        return "OCEANIA"
    return "ROW"


NEGATIVE = re.compile(r"exclu|except|cannot|can not|can't|not accept|closed|suspend|stop|not allowed|"
                      r"restricted|not eligible|no commission|not submit|prohibit|ban", re.I)


# --- the sheet ----------------------------------------------------------------

class Grid:
    """A sheet read through its merged ranges."""

    def __init__(self, sheet):
        self.sheet = sheet
        self.origin: dict[tuple[int, int], tuple[int, int]] = {}
        for r1, c1, r2, c2 in sheet.merged:
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    self.origin[(r, c)] = (r1, c1)
        self.max_row = max([r for r, _ in sheet.cells] + [m[2] for m in sheet.merged] + [0])
        self.cols: dict[str, int] = {}
        self._map_headers()

    def _map_headers(self):
        incentive_at = None
        heads = {}
        for c in range(2, 60):
            h = _norm_header(self.at(1, c))
            if h:
                heads[c] = h
            if h == "incentive criteria":
                incentive_at = c
        for c, h in heads.items():
            if h == "commission":
                sub = _norm_header(self.at(2, c))
                self.cols.setdefault("pct" if sub.startswith("percent") else "count", c)
            elif h in ("institution/centre name", "applicable period"):
                side = "i" if incentive_at and c >= incentive_at - 2 else "b"
                self.cols.setdefault(f"{side}_{'inst' if h.startswith('inst') else 'period'}", c)
            elif h in HEADERS:
                self.cols.setdefault(HEADERS[h], c)

    def col(self, key: str) -> int | None:
        return self.cols.get(key)

    def at(self, r: int, c: int | None):
        if c is None:
            return None
        o = self.origin.get((r, c), (r, c))
        return self.sheet.value(*o)

    def get(self, r: int, key: str):
        return self.at(r, self.cols.get(key))

    def own(self, r: int, key: str) -> bool:
        """The cell starts here (unmerged, or the top of its merge) and has a value."""
        c = self.cols.get(key)
        if c is None:
            return False
        o = self.origin.get((r, c), (r, c))
        return o[0] == r and _text(self.sheet.value(*o)) != ""

    def origin_row(self, r: int, key: str) -> int | None:
        c = self.cols.get(key)
        return None if c is None else self.origin.get((r, c), (r, c))[0]

    def ref(self, r: int, key_or_col) -> str:
        c = key_or_col if isinstance(key_or_col, int) else self.cols.get(key_or_col)
        if c is None:
            return f"'{self.sheet.name}'!{r}"
        o = self.origin.get((r, c), (r, c))
        return f"'{self.sheet.name}'!{xlsx.col_letter(o[1])}{o[0]}"

    def blocks(self) -> list[tuple[int, int]]:
        starts = [r for r in range(3, self.max_row + 1)
                  if self.origin.get((r, 1), (r, 1))[0] == r and _text(self.sheet.value(r, 1))]
        out = []
        for i, s in enumerate(starts):
            end = (starts[i + 1] - 1) if i + 1 < len(starts) else self.max_row
            while end > s and not any(_text(self.at(end, c)) for c in range(2, 40)
                                      if self.origin.get((end, c), (end, c))[0] == end):
                end -= 1
            out.append((s, end))
        return out


# --- one contract block --------------------------------------------------------

class Block:
    def __init__(self, grid: Grid, tab: str, r1: int, r2: int, places: Places):
        self.g, self.tab, self.r1, self.r2, self.places = grid, tab, r1, r2, places
        self.review: list[dict] = []

    def flag(self, cell: str, text, message: str):
        self.review.append({"cell": cell, "text": _text(text)[:500], "message": message})

    def rows(self):
        return range(self.r1, self.r2 + 1)

    def unique(self, key: str):
        """(row, value) of each distinct cell in the column within the block."""
        seen = set()
        for r in self.rows():
            c = self.g.col(key)
            if c is None:
                return
            o = self.g.origin.get((r, c), (r, c))
            if o in seen:
                continue
            seen.add(o)
            v = self.g.sheet.value(*o)
            if _text(v):
                yield o[0], v

    # -- header ------------------------------------------------------------------
    def header(self, party_type: str, region: str | None) -> dict:
        g, r = self.g, self.r1
        a = _text(g.sheet.value(r, 1))
        name = a.split("\n")[0].strip()
        h = {"party_name": name, "party_type": party_type, "source_tab": self.tab,
             "source_rows": f"{self.r1}–{self.r2}"}
        country = _text(g.get(r, "country"))
        if country:
            h["country"] = country
        h["region"] = region or region_for_country(country.split("\n")[0])

        terr = _text(g.get(r, "territory"))
        low = terr.lower()
        if re.search(r"inactive|closed|not active", low):
            eff = find_dates(terr)
            h["inactive"] = {"reason": terr, "effective_date": eff[0].isoformat() if eff else None}
            self.flag(g.ref(r, "territory"), terr, "the workbook marks this contract inactive; set the status "
                      "after publishing, and choose the territory type")
        elif low.startswith("not global"):
            h["territory_type"] = "NOT_GLOBAL"
        elif "restriction" in low:
            h["territory_type"] = "GLOBAL_WITH_RESTRICTIONS"
        elif low.startswith("global"):
            h["territory_type"] = "GLOBAL"
        elif terr:
            self.flag(g.ref(r, "territory"), terr, "unrecognised global territory value")

        years, why = academic_years(g.get(r, "academic_year"))
        h["academic_years"] = years
        if why:
            self.flag(g.ref(r, "academic_year"), g.get(r, "academic_year"), why)

        for key in ("start_date", "end_date"):
            raw = g.get(r, key)
            d = parse_date(raw)
            if d == "ROLLING":
                h["is_rolling"] = True
            elif d:
                h[key] = d.isoformat()
            elif _text(raw):
                self.flag(g.ref(r, key), raw, f"cannot read the contract {key.split('_')[0]} date")
        if "end_date" not in h and not h.get("is_rolling"):
            m = re.search(r"(?:active until|valid until|until|expir\w*)[:\s]*(.+)", a, re.I)
            if m and find_dates(m.group(1)):
                h["end_date"] = find_dates(m.group(1))[0].isoformat()
                self.flag(f"'{self.tab}'!A{r}", a, "end date read from the provider name cell")

        vat = _text(g.get(r, "vat"))
        if vat:
            v = vat.lower()
            if "no vat" in v or v in ("n/a", "na", "none", "not applicable"):
                h["vat_treatment"] = "NOT_APPLICABLE"
            elif v.startswith("exclusive"):
                h["vat_treatment"] = "EXCLUSIVE"
            elif v.startswith("inclusive"):
                h["vat_treatment"] = "INCLUSIVE"
            else:
                self.flag(g.ref(r, "vat"), vat, "VAT text is not Exclusive / Inclusive / No VAT")
            if h.get("vat_treatment") in ("EXCLUSIVE", "INCLUSIVE") and h["region"] == "UK":
                h["vat_rate"] = 20

        gn = _text(g.get(r, "gross_net")).lower()
        if gn in ("gross", "net"):
            h["fee_basis"] = gn.upper()
        elif gn:
            self.flag(g.ref(r, "gross_net"), g.get(r, "gross_net"), "mixed or unrecognised Gross/Net text")
        return h

    # -- intake scope and "Applicable from" segments ---------------------------
    def segments(self) -> tuple[dict, dict[int, str]]:
        """(base intake scope, {row: from_intake}) -- rows under an
        'Applicable from X intake' cell belong to a RATE_CHANGE from X."""
        scope, seg = {"mode": "ENTIRE_YEAR"}, {}
        if self.g.col("intake") is None:
            return scope, seg
        for r0, v in self.unique("intake"):
            s = _text(v)
            low = s.lower()
            intakes = find_intakes(s)
            cell = self.g.ref(r0, "intake")
            if "from" in low and intakes and r0 > self.r1:
                for r in self.rows():
                    if self.g.origin_row(r, "intake") == r0:
                        seg[r] = intakes[0]
            elif "entire" in low or "all intake" in low:
                pass
            elif "until" in low and intakes:
                scope = {"mode": "UP_TO", "until_intake": intakes[-1]}
            elif intakes:
                scope = {"mode": "INTAKES", "intakes": intakes}
            elif "from" in low and intakes:
                scope = {"mode": "ENTIRE_YEAR"}
                self.flag(cell, s, "applicable-from text on the first row; check the intake scope")
            else:
                self.flag(cell, s, "cannot read the applicable intakes")
        return scope, seg

    # -- rules -----------------------------------------------------------------
    def rules(self, seg: dict[int, str], institutions: bool) -> list[dict]:
        g = self.g
        out, cur = [], None
        campus_cells = {o for o, _ in self.unique("campus")}
        many_campuses = len(campus_cells) > 1
        for r in self.rows():
            starts = g.own(r, "course_level")
            has_value = _text(g.get(r, "pct")) != "" and g.origin_row(r, "pct") == r
            inst = _text(g.get(r, "institution")) if institutions else None
            if cur and institutions and inst and inst != cur["_inst"] and has_value:
                starts = True
            if starts or (cur is None and has_value):
                cur = {"_rows": [], "_segment": seg.get(r), "_inst": inst,
                       "_level_row": g.origin_row(r, "course_level") if starts else r}
                out.append(cur)
            if cur is not None and has_value:
                cur["_rows"].append(r)
        kept = [x for x in out if x["_rows"]]
        firsts = [min(x["_level_row"], x["_rows"][0]) for x in kept]
        result = []
        for i, x in enumerate(kept):
            rule = self._rule(x, many_campuses)
            last = firsts[i + 1] - 1 if i + 1 < len(kept) else self.r2
            rule["_rows_all"] = list(range(firsts[i], last + 1))
            result.append(rule)
        return result

    def _rule(self, x: dict, many_campuses: bool) -> dict:
        g = self.g
        r0 = x["_level_row"]
        level_text = _text(g.get(r0, "course_level"))
        levels, unmatched = course_levels(level_text)
        notes = []
        rule = {"id": model.new_id("r"), "name": (level_text.split("\n")[0][:80] or "Commission"),
                "course_levels": levels, "fee_year_scope": "YEAR_1",
                "source_cell": g.ref(r0, "course_level") if level_text else g.ref(x["_rows"][0], "pct"),
                "source_text": level_text[:500], "_segment": x["_segment"]}
        inst_name = (x["_inst"] or "").split("\n")[0].strip()
        if model.normalize_name(inst_name):
            rule["institution_name"] = inst_name
        elif x["_inst"]:
            notes.append(f"institution name {x['_inst'][:40]!r} is not a name")
        if not levels and ALL_COURSES.match(level_text.strip(" .")):
            pass                                    # empty levels = every course
        elif not levels:
            notes.append(f"no course level recognised in {level_text[:80]!r}" if level_text else "no course level given")
        elif unmatched:
            notes.append("unrecognised course text: " + "; ".join(u[:40] for u in unmatched[:3]))
        if many_campuses and _text(g.get(x["_rows"][0], "campus")):
            rule["campus"] = _text(g.get(x["_rows"][0], "campus")).split("\n")[0]

        pricing_text = _text(g.get(r0, "pricing")).lower()
        structure_text = _text(g.get(r0, "structure")).lower()
        tiers, currency = [], None
        for r in x["_rows"]:
            raw = g.get(r, "pct")
            pct = parse_percent(raw)
            money = parse_money(raw) if pct is None else None
            if money:
                currency = money[1]
            value = pct if pct is not None else (money[0] if money else None)
            if value is None:
                notes.append(f"{g.ref(r, 'pct')}: cannot read a commission value from {_text(raw)[:40]!r}")
            rng, why = parse_range(g.get(r, "count")) if g.origin_row(r, "count") == r else (None, None)
            if why and (len(x["_rows"]) > 1 or isinstance(g.get(r, "count"), (datetime, date))):
                notes.append(f"{g.ref(r, 'count')}: {why}")
            tiers.append({"value": value, **(rng or {"min_count": None, "max_count": None}), "_row": r})
        flat = bool(currency) or "flat" in pricing_text
        rule["pricing"] = "FLAT" if flat else "PERCENT"
        if currency:
            rule["currency"] = currency
        count_text = _text(g.get(x["_rows"][0], "count")).lower() + " " + _text(g.get(r0, "spec")).lower()
        if re.search(r"all years|each year|every year|full (course|programme|duration)|entire duration", count_text):
            rule["fee_year_scope"] = "ALL_YEARS"

        tiered = len(tiers) > 1
        if len(tiers) > 1 and structure_text and "tier" not in structure_text:
            notes.append(f"structure says {structure_text!r} but there are {len(tiers)} value rows")
        if not tiered:
            rule["structure"] = "PER_STUDENT"
            rule["value"] = tiers[0]["value"]
            rng_text = _text(g.get(x["_rows"][0], "count"))
            if rng_text and not re.match(r"\s*\d", rng_text):
                rule["note"] = rng_text[:500]
        else:
            rule["structure"] = "TIERED"
            rule["tier_mode"] = start_range_mode(g.get(r0, "start_range")) or "RETROACTIVE"
            if not start_range_mode(g.get(r0, "start_range")):
                notes.append("tier mode not stated; assumed retroactive (from first student)")
            rule["count_metric"] = "ENROLMENT"
            rule["count_scope"] = "ACADEMIC_YEAR"
            clean = [{k: t[k] for k in ("min_count", "max_count", "value")} for t in tiers]
            probs = validation.tier_problems(clean) if len(clean) >= 2 else ["only one tier row"]
            if any(t["min_count"] is None for t in clean):
                probs.append("a tier has no student range")
            if probs:
                rule["tiers"], rule["tiers_raw"] = [], clean
                notes.append("tiers need fixing before publishing: " + "; ".join(dict.fromkeys(probs)))
            else:
                rule["tiers"] = clean
        if notes:
            rule["needs_review"] = True
            rule["review_note"] = " · ".join(notes)
        return rule

    # -- bonuses (inline T..X on university tabs) -------------------------------
    def bonuses(self, rules: list[dict]) -> list[dict]:
        g = self.g
        if g.col("b_rate") is None or g.col("b_inst") is not None:
            return []
        row_rule = {}
        for rule in rules:
            for r in rule.get("_rows_all", []):
                row_rule[r] = rule
        out, cur = [], None
        for r in self.rows():
            rate_here = g.origin_row(r, "b_rate") == r and _text(g.get(r, "b_rate"))
            crit_row = g.origin_row(r, "b_criteria") if _text(g.get(r, "b_criteria")) else None
            rule = row_rule.get(r)
            if not rate_here:
                continue
            key = (crit_row, rule["id"] if rule else None)
            same = cur and (cur["_key"] == key or (crit_row is None and cur["_rule"] is rule))
            if not same:
                cur = {"_key": key, "_rule": rule, "_crit_row": crit_row, "_rows": [], "_segment": rule["_segment"] if rule else None}
                out.append(cur)
            cur["_rows"].append(r)
        return [self._bonus(b, "b") for b in out]

    def _bonus(self, x: dict, side: str, criteria: str | None = None, cell: str | None = None) -> dict:
        g = self.g
        crit_row = x.get("_crit_row")
        text = criteria if criteria is not None else (_text(g.get(crit_row, f"{side}_criteria")) if crit_row else "")
        notes, tiers, kinds = [], [], set()
        first = x["_rows"][0]
        payment = _text(g.get(first, f"{side}_payment")).lower()
        for r in x["_rows"]:
            raw = g.get(r, f"{side}_rate")
            pct = None
            if isinstance(raw, (int, float)) and raw < 1:
                pct = round(raw * 100, 6)
            elif re.fullmatch(r"\s*\d+(\.\d+)?\s*%\s*", _text(raw)) or re.fullmatch(r"\s*0?\.\d+\s*", _text(raw)):
                pct = parse_percent(raw)
            money = None if pct is not None else parse_money(raw)
            if pct is None and money is None:
                m = re.fullmatch(r"\s*(\d[\d,]*(?:\.\d+)?)\s*", _text(raw))
                if m:
                    money = (float(m.group(1).replace(",", "")), None)
            if pct is not None:
                kinds.add("RATE_UPLIFT")
                value = pct
            elif money:
                kinds.add("LUMP_SUM" if "lump" in payment else "FIXED_PER_STUDENT")
                value = money[0]
            else:
                value = None
                notes.append(f"{g.ref(r, side + '_rate')}: cannot read a bonus value from {_text(raw)[:40]!r}")
            count_raw = g.get(r, f"{side}_count") if g.origin_row(r, f"{side}_count") == r else None
            rng, why = parse_range(count_raw)
            if why:
                notes.append(f"{g.ref(r, side + '_count')}: {why}")
            tiers.append({"min_count": (rng or {}).get("min_count"), "max_count": (rng or {}).get("max_count"),
                          "value": value})
        if payment and not re.search(r"per student|lump", payment):
            notes.append(f"unrecognised bonus payment {payment!r}")
        kind = sorted(kinds)[0] if len(kinds) == 1 else ("RATE_UPLIFT" if not kinds else sorted(kinds)[0])
        if len(kinds) > 1:
            notes.append("bonus mixes percentage and money values")
        if len(tiers) == 1 and tiers[0]["min_count"] is None:
            tiers[0]["min_count"] = 1
            notes.append("no student threshold given; assumed from the first student")
        counts_text = " ".join(_text(g.get(r, f"{side}_count")) for r in x["_rows"])
        blob = f"{text} {counts_text}".lower()
        intakes = find_intakes(text)
        b = {"id": model.new_id("b"), "name": (text.split("\n")[0][:80] or "Bonus"), "kind": kind,
             "criteria_text": text[:1000], "count_metric": "ENROLMENT",
             "tier_mode": start_range_mode(g.get(first, f"{side}_start")) or "RETROACTIVE",
             "count_scope": "INTAKE", "count_intakes": [], "tiers": tiers,
             "source_cell": cell or (g.ref(crit_row, f"{side}_criteria") if crit_row else g.ref(first, f"{side}_rate")),
             "_intakes": intakes, "_dates": find_dates(text), "_segment": x.get("_segment")}
        if "combined" in blob and len(intakes) >= 2:
            b["count_scope"] = "COMBINED_INTAKES"
            b["count_intakes"] = intakes
        elif "per intake" in blob or "single intake" in blob:
            b["count_scope"] = "INTAKE"
        elif "academic year" in blob or "per year" in blob:
            b["count_scope"] = "ACADEMIC_YEAR"
        if x.get("_rule"):
            if re.search(r"all (courses|programmes|programs)", text, re.I):
                b["applies_to_rule_ids"] = []
            else:
                b["applies_to_rule_ids"] = [x["_rule"]["id"]]
        probs = validation.tier_problems(tiers) if len(tiers) >= 2 else []
        if probs:
            b["tiers"], b["tiers_raw"] = [], tiers
            notes.append("tiers need fixing before publishing: " + "; ".join(dict.fromkeys(probs)))
        if notes:
            b["needs_review"] = True
            b["review_note"] = " · ".join(notes)
        return b

    # -- side tables (pathways / outbound) -------------------------------------
    def side_bonuses(self, rules: list[dict]) -> list[dict]:
        g = self.g
        out = []
        for side, label in (("b", "Bonus"), ("i", "Incentive")):
            if g.col(f"{side}_rate") is None:
                continue
            cur = None
            for r in self.rows():
                starts = g.own(r, f"{side}_inst") or g.own(r, f"{side}_criteria") or g.own(r, f"{side}_period")
                rate_here = g.origin_row(r, f"{side}_rate") == r and _text(g.get(r, f"{side}_rate"))
                if starts and (cur is None or r not in cur["_rows_span"]):
                    cur = {"_rows": [], "_start": r, "_rows_span": set()}
                    out.append((side, label, cur))
                    for key in (f"{side}_inst", f"{side}_criteria", f"{side}_period"):
                        c = g.col(key)
                        o = g.origin.get((r, c), (r, c)) if c else None
                        if o:
                            for m in g.sheet.merged:
                                if (m[0], m[1]) == o:
                                    cur["_rows_span"].update(range(m[0], m[2] + 1))
                if rate_here and cur is not None:
                    cur["_rows"].append(r)
        result = []
        by_inst: dict[str, list[str]] = {}
        for rule in rules:
            if rule.get("institution_name"):
                by_inst.setdefault(model.normalize_name(rule["institution_name"]), []).append(rule["id"])
        for side, label, x in out:
            if not x["_rows"]:
                continue
            r = x["_start"]
            period = _text(g.get(r, f"{side}_period"))
            crit = _text(g.get(r, f"{side}_criteria"))
            text = "\n".join(t for t in (crit, period) if t)
            b = self._bonus(x, side, criteria=text, cell=g.ref(r, f"{side}_criteria"))
            b["name"] = f"{label}: {(crit or period).split(chr(10))[0][:70]}"
            names = [n.strip(" •-\t") for n in re.split(r"\n|,", _text(g.get(r, f"{side}_inst"))) if n.strip(" •-\t")]
            ids = []
            for n in names:
                ids += by_inst.get(model.normalize_name(n), [])
            b["institution_names"] = names
            b["applies_to_rule_ids"] = ids
            if names and not ids:
                b["needs_review"] = True
                b["review_note"] = ((b.get("review_note") + " · ") if b.get("review_note") else "") + \
                    "names institutions this contract has no rules for: " + ", ".join(n[:40] for n in names[:4])
            result.append(b)
        return result

    # -- territories -------------------------------------------------------------
    def territories(self, territory_type: str | None) -> tuple[list[dict], list[dict]]:
        """(base territory rules, scope-change amendments)."""
        rules, amendments = [], []
        for r0, v in self.unique("territories"):
            cell = self.g.ref(r0, "territories")
            text = _text(v)
            lines, carry = [], ""
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if carry:
                    line, carry = f"{carry} {line}", ""
                if line.endswith(":"):
                    carry = line
                    continue
                lines.append(line)
            if carry:
                lines.append(carry)
            for line in lines:
                countries = self.places.find(line)
                intakes, dates = find_intakes(line), find_dates(line)
                neg = NEGATIVE.search(line)
                if (intakes or dates) and countries:
                    received = None
                    if dates and re.search(r"inform|notif|received|email|announce", line, re.I):
                        received = dates[-1].isoformat()
                    frm = intakes[0] if intakes else model.intake_of(dates[0])
                    until = None
                    if len(intakes) > 1 and not re.search(r"further|onward|until further", line, re.I):
                        until = intakes[-1]
                    add = [{"type": "EXCLUDE", "scope": "NATIONALITY", "value": c, "source_cell": cell,
                            "source_clause": line} for c in countries] if neg else []
                    amendments.append({
                        "type": "SCOPE_CHANGE", "from_intake": frm, "until_intake": until, "scope_mode": "INTAKE",
                        "received_on": received, "needs_review": True, "source_cell": cell,
                        "summary": line[:200], "changes": {"add_territory_rules": add, "note": line},
                    })
                    if not neg:
                        self.flag(cell, line, "territory change with a date that does not read as a restriction")
                    continue
                if not countries:
                    continue
                if neg:
                    after = self.places.find(line[neg.start():]) or countries
                    for c in after:
                        rules.append({"type": "EXCLUDE", "scope": "NATIONALITY", "value": c,
                                      "source_cell": cell, "source_clause": line[:500]})
                elif territory_type == "NOT_GLOBAL":
                    for c in countries:
                        rules.append({"type": "INCLUDE", "scope": "COUNTRY", "value": c,
                                      "source_cell": cell, "source_clause": line[:500]})
            if text and not rules and not amendments and not re.search(r"worldwide|global|all countries", text, re.I):
                self.flag(cell, text, "no countries recognised in the territory text")
        seen, uniq = set(), []
        for t in rules:
            k = (t["type"], t["value"])
            if k not in seen:
                seen.add(k)
                uniq.append(t)
        return uniq, amendments

    # -- specification / restriction -------------------------------------------
    def conditions(self) -> dict:
        out = {"exclusions": [], "agent_change_rules": [], "payment_conditions": [], "other_conditions": []}
        seen = set()

        def excl(kind, cell, clause, **extra):
            key = (kind, extra.get("campus"))
            if key in seen:
                return
            seen.add(key)
            out["exclusions"].append({"type": kind, "source_cell": cell, "source_clause": clause[:500], **extra})

        for r0, v in self.unique("spec"):
            cell = self.g.ref(r0, "spec")
            text = _text(v)
            negative = False
            rest = []
            for line in text.split("\n"):
                s = line.strip()
                if not s:
                    negative = False
                    continue
                low = s.lower()
                if re.search(r"no commission|not (be )?payable|not eligible|not commissionable|non.?commissionable|"
                             r"shall not|will not be paid|exclud|not applicable for", low):
                    negative = True
                used = False
                if re.search(r"fafsa|federal (student )?aid|title iv", low):
                    excl("FEDERAL_AID", cell, s)
                    used = True
                if re.search(r"change of agent|changes? (their )?(agent|representative)|agent dispute|"
                             r"previous agent|another agent|50:50|split", low):
                    kind = "SPLIT" if re.search(r"50:50|split|half", low) else (
                        "CURRENT_AGENT" if re.search(r"current|latest|new agent", low) else "FIRST_INTRODUCER")
                    out["agent_change_rules"].append({"type": kind, "text": s[:500], "source_cell": cell,
                                                      "needs_review": True})
                    self.flag(cell, s, "agent-change rule: confirm how commission is shared")
                    used = True
                if re.search(r"cleared (in|into|to)|funds? (have )?cleared|cleared funds", low):
                    out["payment_conditions"].append({"type": "FEE_FULLY_CLEARED", "text": s[:500], "source_cell": cell})
                    used = True
                if re.search(r"(upon|on) (cas|becoming an enrolled|enrol)", low) and "%" in s:
                    self.flag(cell, s, "payment milestones in the text; enter them as milestones")
                if negative:
                    if re.search(r"online|distance", low):
                        excl("ONLINE_DISTANCE", cell, s); used = True
                    if re.search(r"pre.?sessional", low):
                        excl("PRESESSIONAL", cell, s); used = True
                    if re.search(r"home fee|home student|home status", low):
                        excl("HOME_FEE", cell, s); used = True
                    if re.search(r"\bruk\b|rest of (the )?uk", low):
                        cap = re.search(r"maximum of (\d+)", low)
                        excl("RUK_FEE", cell, s, **({"cap_count": int(cap.group(1)), "cap_scope": "ACADEMIC_YEAR"} if cap else {}))
                        used = True
                    if re.search(r"franchise|validation|validated|partner", low):
                        excl("FRANCHISE_PARTNER", cell, s); used = True
                    if re.search(r"ph\.?d|\bmres\b|research|doctora", low):
                        excl("RESEARCH_DEGREE", cell, s); used = True
                    if re.search(r"scholarship|sponsor|non.?fee|fee waiver", low):
                        excl("NON_FEE_PAYING", cell, s); used = True
                    for m in re.finditer(r"\b([A-Z][A-Za-z]+)\s+campus", s):
                        excl("CAMPUS", cell, s, campus=m.group(1)); used = True
                if not used:
                    rest.append(s)
            if rest:
                out["other_conditions"].append({"text": "\n".join(rest)[:2000], "source_cell": cell})
        return out

    def targets(self) -> list[dict]:
        out = []
        for r0, v in self.unique("target"):
            text = _text(v)
            t = {"text": text[:1000], "source_cell": self.g.ref(r0, "target")}
            nums = re.findall(r"\b(\d{2,5})\b", text)
            if len(nums) == 1:
                t["count"] = int(nums[0])
            out.append(t)
        return out

    def campuses(self) -> list[str]:
        out = []
        for _, v in self.unique("campus"):
            for c in re.split(r"\n|,", _text(v)):
                c = c.strip()
                if c and c not in out:
                    out.append(c)
        return out


# --- a contract from a block ---------------------------------------------------

def _strip(d):
    """Drop the parser's private _keys."""
    if isinstance(d, dict):
        return {k: _strip(v) for k, v in d.items() if not k.startswith("_")}
    if isinstance(d, list):
        return [_strip(v) for v in d]
    if isinstance(d, date):
        return d.isoformat()
    return d


TYPE_ORDER = {"BONUS_INCENTIVE": 0, "SCOPE_CHANGE": 1, "RATE_CHANGE": 2}


def parse_block(grid: Grid, tab: str, r1: int, r2: int, places: Places) -> dict:
    party_type, region = TABS[tab]
    blk = Block(grid, tab, r1, r2, places)
    header = blk.header(party_type, region)
    scope, seg = blk.segments()
    header["intake_scope"] = scope
    pathways = party_type in ("PATHWAY_PROVIDER", "OUTBOUND_AGENT")

    rules = blk.rules(seg, institutions=pathways)
    bonuses = blk.side_bonuses(rules) if pathways else blk.bonuses(rules)
    territory_rules, amendments = blk.territories(header.get("territory_type"))
    cond = blk.conditions()

    currency = next((r["currency"] for r in rules if r.get("currency")), None)
    if not currency:
        country = (header.get("country") or "").lower()
        currency = {"canada": "CAD", "new zealand": "NZD"}.get(country) or CURRENCY_DEFAULT.get(header["region"])
    header["currency"] = currency

    base_rules = [r for r in rules if not r["_segment"]]
    base_bonuses = []
    bonus_groups: dict[tuple, list[dict]] = {}
    rate_changes: dict[str, dict] = {}
    for x in rules:
        if x["_segment"]:
            rate_changes.setdefault(x["_segment"], {"rules": [], "bonuses": []})["rules"].append(x)
    for b in bonuses:
        if b["_segment"]:
            frm = b["_segment"]
            before = [i for i in b["_intakes"] if i < frm]
            if before:
                b["needs_review"] = True
                b["review_note"] = ((b.get("review_note") + " · ") if b.get("review_note") else "") + (
                    f"criteria cite {', '.join(model.intake_label(i) for i in before)}, before this change "
                    f"applies ({model.intake_label(frm)})")
            rate_changes.setdefault(frm, {"rules": [], "bonuses": []})["bonuses"].append(b)
        elif b["_intakes"]:
            bonus_groups.setdefault(("I", tuple(b["_intakes"])), []).append(b)
        elif len(b["_dates"]) >= 2:
            bonus_groups.setdefault(("D", b["_dates"][0], b["_dates"][-1]), []).append(b)
        else:
            base_bonuses.append(b)

    for key, group in bonus_groups.items():
        if key[0] == "I":
            intakes = list(key[1])
            a = {"type": "BONUS_INCENTIVE", "scope_mode": "INTAKE", "from_intake": intakes[0],
                 "until_intake": intakes[-1], "summary": f"Bonus for {', '.join(model.intake_label(i) for i in intakes)}"}
        else:
            a = {"type": "BONUS_INCENTIVE", "scope_mode": "DATE_WINDOW", "window_start": key[1].isoformat(),
                 "window_end": key[2].isoformat(), "applicability_basis": "APPLICATION_DATE", "needs_review": True,
                 "from_intake": model.intake_of(key[1]),
                 "summary": f"Bonus for {key[1]:%d %b %Y} – {key[2]:%d %b %Y}; confirm which student date counts"}
        a.update({"source_cell": group[0]["source_cell"], "changes": {"bonuses": group},
                  "needs_review": a.get("needs_review") or any(b.get("needs_review") for b in group)})
        amendments.append(a)

    for frm, ch in rate_changes.items():
        levels = {lv for r in ch["rules"] for lv in r["course_levels"]}
        targets = [r["id"] for r in base_rules if levels & set(r["course_levels"])]
        cell = grid.ref(min(r_["_rows_all"][0] for r_ in ch["rules"]) if ch["rules"] else r1, "intake")
        amendments.append({
            "type": "RATE_CHANGE", "scope_mode": "INTAKE", "from_intake": frm, "until_intake": None,
            "target_rule_ids": targets, "needs_review": True, "source_cell": cell,
            "summary": f"New rates from {model.intake_label(frm)} (imported)",
            "changes": {"rules": ch["rules"], "bonuses": ch["bonuses"]},
        })
        if not targets:
            blk.flag(cell, _text(grid.get(r1, "intake")), f"rate change from {model.intake_label(frm)} replaces no "
                     "base rule; choose the rules it replaces")

    amendments.sort(key=lambda a: (a.get("from_intake") or "9999", TYPE_ORDER.get(a["type"], 9)))
    for n, a in enumerate(amendments, start=1):
        a["number"] = n
        a["reference"] = f"Workbook {a['source_cell']}"

    terms = {"rules": base_rules, "bonuses": base_bonuses, "territory_rules": territory_rules,
             "campuses": blk.campuses(), "targets": blk.targets(), **cond}
    if blk.review:
        terms["review_items"] = blk.review
    contract = _strip({**header, "terms": terms})
    contract["amendments"] = _strip(amendments)
    return contract


# --- the workbook ---------------------------------------------------------------

def parse_workbook(sheets: list, countries: list[dict]) -> dict:
    places = Places(countries)
    by_name = {s.name: s for s in sheets}
    contracts, unknown_tabs = [], []
    for name in TABS:
        if name not in by_name:
            continue
        grid = Grid(by_name[name])
        for r1, r2 in grid.blocks():
            contracts.append(parse_block(grid, name, r1, r2, places))
    for s in sheets:
        if s.name not in TABS and s.name != INVOICING_TAB:
            unknown_tabs.append(s.name)

    unmatched_invoicing = []
    if INVOICING_TAB in by_name:
        grid = Grid(by_name[INVOICING_TAB])
        targets = {model.normalize_name(c["party_name"]): c for c in contracts if c["source_tab"] == INVOICING_TARGET}
        for r1, _ in grid.blocks():
            name = _text(grid.sheet.value(r1, 1)).split("\n")[0].strip()
            inv = {k: _text(grid.get(r1, f"inv_{k}")) for k in ("deadline", "receivable", "notes", "mechanism")}
            if not any(inv.values()):
                continue
            inv = {k: v for k, v in inv.items() if v}
            inv["source_cell"] = f"'{INVOICING_TAB}'!A{r1}"
            target = targets.get(model.normalize_name(name))
            if target:
                target["terms"]["invoicing"] = inv
            else:
                unmatched_invoicing.append({"name": name, "cell": inv["source_cell"]})
    return {"contracts": contracts, "unknown_tabs": unknown_tabs, "unmatched_invoicing": unmatched_invoicing}


# --- preview / commit ------------------------------------------------------------

def _review_list(c: dict) -> list[dict]:
    """Everything in one parsed contract that a person has to look at."""
    t = c["terms"]
    out = [{"cell": i["cell"], "message": i["message"], "text": i.get("text")} for i in t.get("review_items") or []]
    for kind in ("rules", "bonuses"):
        for x in t.get(kind) or []:
            if x.get("needs_review"):
                out.append({"cell": x.get("source_cell"), "message": x.get("review_note") or "check this", "text": x.get("name")})
    for a in c.get("amendments") or []:
        if a.get("needs_review"):
            out.append({"cell": a.get("source_cell"), "message": f"Amendment #{a['number']} ({a['type'].replace('_', ' ').lower()}) "
                        "is a draft to confirm", "text": a.get("summary")})
        for x in (a.get("changes") or {}).get("rules", []) + (a.get("changes") or {}).get("bonuses", []):
            if x.get("needs_review"):
                out.append({"cell": x.get("source_cell"), "message": f"Amendment #{a['number']}: {x.get('review_note') or 'check this'}",
                            "text": x.get("name")})
    return out


def _institution_match(cur, name: str) -> dict:
    norm = model.normalize_name(name)
    cur.execute("select id, name from institutions where normalized_name = %s", (norm,))
    row = cur.fetchone()
    if row:
        return {"match": "exact", "id": row["id"], "name": row["name"]}
    cur.execute("select id, name, normalized_name from institutions")
    cands = [{"id": r["id"], "name": r["name"]} for r in cur.fetchall()
             if norm and (norm in r["normalized_name"] or r["normalized_name"] in norm) and len(r["normalized_name"]) > 3]
    return {"match": "ambiguous", "candidates": cands[:5]} if cands else {"match": "new"}


def preview(cur, filename: str, body: bytes, user: str | None) -> dict:
    sha = hashlib.sha256(body).hexdigest()
    try:
        sheets = xlsx.read(io.BytesIO(body))
    except Exception as exc:                       # not a zip, or not a workbook
        raise store.CommissionError(f"cannot read {filename} as an .xlsx workbook ({exc})", 422) from exc
    cur.execute("select name, aliases from countries")
    parsed = parse_workbook(sheets, cur.fetchall())
    if not parsed["contracts"]:
        raise store.CommissionError("no contract tabs found in the workbook", 422,
                                    {"tabs": [s.name for s in sheets]})

    cur.execute("""select c.id, c.status, c.source_tab, i.normalized_name from contracts c
                   join institutions i on i.id = c.party_id order by c.id""")
    existing: dict[tuple, list[dict]] = {}
    for r in cur.fetchall():
        existing.setdefault((r["source_tab"], r["normalized_name"]), []).append(r)
    seen: dict[tuple, int] = {}
    rows = []
    for index, c in enumerate(parsed["contracts"]):
        key = (c["source_tab"], model.normalize_name(c["party_name"]))
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        match = (existing.get(key) or [])[occurrence:occurrence + 1]
        if not match:
            action, cid, why = "create", None, None
        elif match[0]["status"] == "DRAFT":
            action, cid, why = "update", match[0]["id"], "replaces the existing draft"
        else:
            action, cid, why = "skip", match[0]["id"], f"already {match[0]['status'].lower()}; edit it by amendment"
        review = _review_list(c)
        rows.append({
            "index": index, "tab": c["source_tab"], "rows": c["source_rows"], "party_name": c["party_name"],
            "party_type": c["party_type"], "region": c["region"], "action": action, "contract_id": cid, "why": why,
            "institution": _institution_match(cur, c["party_name"]),
            "counts": {"rules": len(c["terms"]["rules"]), "bonuses": len(c["terms"]["bonuses"]),
                       "territory_rules": len(c["terms"]["territory_rules"]),
                       "exclusions": len(c["terms"]["exclusions"]), "amendments": len(c["amendments"])},
            "review": review, "payload": c,
        })
    totals = {"contracts": len(rows), "review": sum(len(r["review"]) for r in rows),
              **{a: sum(r["action"] == a for r in rows) for a in ("create", "update", "skip")}}
    report = {"contracts": rows, "totals": totals, "unknown_tabs": parsed["unknown_tabs"],
              "unmatched_invoicing": parsed["unmatched_invoicing"]}
    cur.execute("insert into import_batches (filename, sha256, report, created_by) values (%s, %s, %s::jsonb, %s) returning id",
                (filename, sha, json.dumps(report, default=str), user))
    return batch(cur, cur.fetchone()["id"])


def _batch_row(cur, batch_id: int) -> dict:
    cur.execute("select * from import_batches where id = %s", (batch_id,))
    row = cur.fetchone()
    if not row:
        raise store.CommissionError(f"no import batch {batch_id}", 404)
    return row


def batch(cur, batch_id: int) -> dict:
    row = _batch_row(cur, batch_id)
    report = copy.deepcopy(row["report"])
    for c in report["contracts"]:
        c.pop("payload", None)
    cur.execute("select count(*) as n from import_batches where sha256 = %s and committed and id <> %s",
                (row["sha256"], batch_id))
    return {"id": row["id"], "filename": row["filename"], "sha256": row["sha256"], "committed": row["committed"],
            "created_by": row["created_by"], "created_at": row["created_at"].isoformat(),
            "previously_committed": cur.fetchone()["n"] > 0, **report}


def _link_institutions(cur, items: list[dict], country, region, covered: set):
    for x in items or []:
        name = x.pop("institution_name", None)
        if name and not x.get("institution_id"):
            x["institution_id"] = store.ensure_institution(cur, name, country, region)
            covered.add(x["institution_id"])


def commit(cur, batch_id: int, user: str | None, skip: list[int]) -> dict:
    row = _batch_row(cur, batch_id)
    if row["committed"]:
        raise store.CommissionError("this import has already been committed", 409)
    skip = {int(s) for s in skip}
    result = {"created": 0, "updated": 0, "skipped": 0, "failed": [], "contract_ids": []}
    for c in row["report"]["contracts"]:
        if c["index"] in skip or c["action"] == "skip":
            result["skipped"] += 1
            continue
        data = copy.deepcopy(c["payload"])
        amendments = data.pop("amendments", [])
        if c["action"] == "update":
            cur.execute("select status from contracts where id = %s", (c["contract_id"],))
            now = cur.fetchone()
            if not now or now["status"] != "DRAFT":
                result["skipped"] += 1
                result["failed"].append({"index": c["index"], "party_name": c["party_name"],
                                         "message": "no longer a draft; left alone"})
                continue
        cur.execute("savepoint import_one")
        try:
            country, region = data.get("country"), data.get("region")
            covered: set = set()
            _link_institutions(cur, data["terms"]["rules"], country, region, covered)
            for a in amendments:
                _link_institutions(cur, (a.get("changes") or {}).get("rules"), country, region, covered)
            data["covered_institution_ids"] = sorted(covered)
            data["import_batch_id"] = batch_id
            if c["action"] == "update":
                cid = c["contract_id"]
                store.update_contract(cur, cid, data, user)
                cur.execute("select id from amendments where contract_id = %s and status = 'DRAFT'", (cid,))
                for a in cur.fetchall():
                    store.delete_amendment(cur, a["id"], user)
                cur.execute("select coalesce(max(number), 0) as n from amendments where contract_id = %s", (cid,))
                offset = cur.fetchone()["n"]
                result["updated"] += 1
            else:
                cid = store.create_contract(cur, data, user)["id"]
                offset = 0
                result["created"] += 1
            for a in amendments:
                store.create_amendment(cur, cid, {**a, "number": a["number"] + offset}, user)
            cur.execute("release savepoint import_one")
            result["contract_ids"].append(cid)
        except store.CommissionError as exc:
            cur.execute("rollback to savepoint import_one")
            result["failed"].append({"index": c["index"], "party_name": c["party_name"], "message": str(exc),
                                     **exc.detail})
    cur.execute("update import_batches set committed = true where id = %s", (batch_id,))
    return result
