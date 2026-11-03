"""Master Sales: the read model.

One question: under the chosen business area, region, team, dates and actual
intake, how many reached each stage of the pipeline.

  * **Business area, region and team** are the student's assignment on the
    export (StudentAssignedToBusinessArea, StudentAssignedToBusinessRegion,
    CurrentlyAssignedToBusinessTeam), a hierarchy: a region belongs to one
    area and a team to one region. A blank is Unassigned; the area menu leaves
    Unassigned out. Each is a multi-select; nothing picked is everything. Each
    menu is counted with every other filter but its own, and the view sends
    the area -> region -> team tree so the page can drop picks a parent no
    longer covers.
  * **Date range** reads the stage timestamps. With a range, a stage counts the
    applications whose date for *that* stage falls inside it: "Offered in
    October" is offers made in October, whenever the application was made.
    The default range is this week (Monday to the anchor); `from=all` is all
    time, where a stage counts everything that has ever reached it, including
    the applications whose status says so without a date.
  * **Course level** is Academic (the default), Language or all: the groups of
    Application Course Level the weekly summary uses. `level=language` and
    `level=all` pick the others; a level in neither group counts under all only.
  * **Actual intake** is a range of months (Actual Intake Year + Month),
    `intake_from` to `intake_to` as YYYY-MM, both ends included, or one or
    more quarters of a single year, `intake_q=2026-Q1|2026-Q3`.
  * **Applications or unique applicants.** The same filters counted two ways.
    In unique applicants (`unit=unique`; `students` is an old name for it),
    Applied and Offered count distinct students: one student with three offers
    is one offer. From CoE on each sale counts: a student's applications for
    the same actual intake are one sale, different intakes are different sales.
  * **Scope** is the applications, and unique students, behind the page: those
    with any stage, deposit, part-payment or deferral date in the range (all
    rows under all time), under the other filters.
  * **Created, active, closed.** Each stage's figure is the applications
    created at it: those that reached it (in the range, or ever). Of those,
    *active* still sit at it as their furthest stage and are open, *closed* sit
    at it and are closed lost (Application Closed Lost); the rest have moved
    on. Active and closed are the export's state now, whatever the range.
  * **Deposit is parallel.** It sits beside the ladder, not on it: a deposit
    can be paid at Offered, CoE, Visa applied, Visa granted or Enrolled. The
    view says how many deposits sit at each of those, by the furthest stage the
    application has reached now.
  * **Active, DAA, closed** split Deposit as the weekly summary's YTD sheets
    do: closed is closed lost; of the rest, DAA have a deferral awaiting
    approval (Deferred Initiated and Deferred Approved differ) and active do not.
  * **DAA** is also a card: deposits whose deferral was initiated (in the
    range, by its Timestamp Deferral Initiated), split into awaiting approval,
    approved and closed.
  * **PD** (partially paid) sits beside Deposit, dated by its part-payment
    timestamp: part payments made in the range, split into still part paid,
    since paid in full, and closed.

"Today", for the date presets, is the export's newest stage date, not the clock.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, "/srv/api")
from app.regions import split  # noqa: E402
from app.views import ViewContext, ViewError  # noqa: E402

STAGES = [
    {"id": "applied", "name": "Applied", "rank": 1, "date": "on_applied",
     "help": "Applied to the university"},
    {"id": "offered", "name": "Offered", "rank": 2, "date": "on_offered",
     "help": "Received an offer letter from the university"},
    {"id": "coe", "name": "CoE", "rank": 3, "date": "on_coe",
     "help": "Confirmation of enrolment received from the university"},
    {"id": "visa_applied", "name": "Visa applied", "rank": 4, "date": "on_visa_applied",
     "help": "The student has applied for the visa"},
    {"id": "visa_granted", "name": "Visa granted", "rank": 5, "date": "on_visa_granted",
     "help": "The student's visa has been granted"},
    {"id": "enrolled", "name": "Enrolled", "rank": 6, "date": "on_enrolled",
     "help": "The student has enrolled at the university"},
]
DEPOSIT = {"id": "deposit", "name": "Deposit", "date": "on_deposit",
           "help": "The student has paid the deposit for the course"}
DAA = {"id": "daa", "name": "DAA", "date": "on_deferral_initiated",
       "help": "Deposit paid, deferral initiated: awaiting approval, approved or closed"}
PD = {"id": "pd", "name": "PD", "date": "on_pd",
      "help": "Partially paid deposit: still part paid, since paid in full, or closed"}

# Every date a row can be counted by, for the scope headline.
ALL_DATES = [s["date"] for s in STAGES] + ["on_deposit", "on_pd", "on_deferral_initiated", "on_deferral_approved"]

# unique applicants: Applied and Offered count students, CoE on counts sales
# (a student's applications for one actual intake are one sale)
SALE_KEY = ("student_key || ':' || coalesce((intake_year * 100 + intake_month)::text, app_uid)")
UNITS = {"applications": "applications", "unique": "unique", "students": "unique"}

# filter param -> column. Order is the order of the hero's menus.
DIMENSIONS = {"areas": "business_area", "regions": "business_region", "teams": "business_team"}

UNASSIGNED = "Unassigned"

# level param -> level_group. Academic is the default.
LEVELS = {"academic": "Academic", "language": "Language", "all": None}

TREE_SQL = """
select distinct business_area as area, business_region as region, business_team as team
  from applications where load_id = %(load)s
 order by 1, 2, 3
"""

ANCHOR_SQL = f"""
select max(greatest({', '.join(ALL_DATES)})) as anchor
  from applications where load_id = %(load)s
"""

NOTES_SQL = """
select count(*)                                                    as app_rows,
       count(distinct student_key)                                 as students,
       count(*) filter (where level_group = 'Other')               as other_level,
       count(*) filter (where intake_year is null or intake_month is null) as no_intake,
       count(*) filter (where student_key like 'app:%%')           as no_student_ref,
       count(*) filter (where stage = 0)                           as no_stage,
       count(*) filter (where deposit and on_deposit is null)      as undated_deposit
  from applications where load_id = %(load)s
"""


# --------------------------------------------------------------------------
# filters
# --------------------------------------------------------------------------


def _day(raw: str | None, name: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ViewError(f"{name} must be a date like 2026-10-01, not '{raw}'") from exc


def _month(raw: str | None, name: str) -> int | None:
    """"2026-09" as 202609, the stored intake_year * 100 + intake_month."""
    if not raw:
        return None
    try:
        year, month = (int(p) for p in raw.split("-"))
    except ValueError as exc:
        raise ViewError(f"{name} must be a month like 2026-09, not '{raw}'") from exc
    if not 1 <= month <= 12 or not 1900 <= year <= 2100:
        raise ViewError(f"{name} must be a month like 2026-09, not '{raw}'")
    return year * 100 + month


def _quarters(raw: str | None) -> tuple[int, list[int]] | None:
    """"2026-Q1|2026-Q3" as (2026, [1, 3]). Quarters of one year only."""
    picks = [p for part in split(raw) for p in split(part.replace(",", "|"))]
    if not picks:
        return None
    found = set()
    for pick in picks:
        try:
            year, q = pick.upper().split("-Q")
            year, q = int(year), int(q)
        except ValueError as exc:
            raise ViewError(f"intake_q must be quarters like 2026-Q1, not '{pick}'") from exc
        if not 1 <= q <= 4 or not 1900 <= year <= 2100:
            raise ViewError(f"intake_q must be quarters like 2026-Q1, not '{pick}'")
        found.add((year, q))
    years = {year for year, _ in found}
    if len(years) > 1:
        raise ViewError("intake quarters must all be in the same year")
    return years.pop(), sorted(q for _, q in found)


def _filters(params: dict, anchor: date) -> dict:
    unit = UNITS.get(params.get("unit") or "applications")
    if unit is None:
        raise ViewError(f"unit must be applications or unique, not '{params.get('unit')}'")
    raw_from, raw_to = params.get("from"), params.get("to")
    is_default = not raw_from and not raw_to
    if raw_from == "all" and not raw_to:
        start = end = None
    elif is_default:
        # this week: Monday of the anchor's week to the anchor
        start, end = anchor - timedelta(days=anchor.weekday()), anchor
    else:
        start, end = _day(raw_from, "from"), _day(raw_to, "to")
        if start is None or end is None:
            raise ViewError("a date range needs both from and to")
    if start and end and start > end:
        start, end = end, start
    level = params.get("level") or "academic"
    if level not in LEVELS:
        raise ViewError(f"level must be academic, language or all, not '{level}'")
    lo, hi = _month(params.get("intake_from"), "intake_from"), _month(params.get("intake_to"), "intake_to")
    if (lo is None) != (hi is None):
        raise ViewError("an intake range needs both intake_from and intake_to")
    if lo and hi and lo > hi:
        lo, hi = hi, lo
    quarters = _quarters(params.get("intake_q"))
    if quarters and lo:
        raise ViewError("pick intake quarters or an intake range, not both")
    return {
        "unit": unit, "from": start, "to": end, "default_range": is_default, "level": level,
        "intake": (lo, hi) if lo else None, "intake_q": quarters,
        **{key: sorted(set(split(params.get(key)))) for key in DIMENSIONS},
    }


def _where(f: dict, skip: str | None = None) -> tuple[str, dict]:
    """The scope every figure shares, as SQL plus its parameters. `skip` leaves
    one filter out, for counting that filter's own menu."""
    clauses, args = ["load_id = %(load)s"], {}
    if LEVELS[f["level"]]:
        clauses.append("level_group = %(level)s")
        args["level"] = LEVELS[f["level"]]
    if f["intake"]:
        clauses.append("intake_year * 100 + intake_month between %(intake_lo)s and %(intake_hi)s")
        args["intake_lo"], args["intake_hi"] = f["intake"]
    if f["intake_q"]:
        clauses.append("intake_year = %(intake_year)s and (intake_month + 2) / 3 = any(%(intake_qs)s)")
        args["intake_year"], args["intake_qs"] = f["intake_q"]
    for key, column in DIMENSIONS.items():
        if skip != key and f[key]:
            clauses.append(f"{column} = any(%({key})s)")
            args[key] = f[key]
    return " and ".join(clauses), args


def _reached(f: dict, stage: dict) -> str:
    """When a row counts at a stage: its date in the range, or ever reached."""
    if stage["id"] == "daa":
        # a deferral counts against a full deposit only
        if f["from"]:
            return "deposit and on_deferral_initiated between %(from)s and %(to)s"
        return "deposit and (deferral_initiated or on_deferral_initiated is not null)"
    if f["from"]:
        return f"{stage['date']} between %(from)s and %(to)s"
    if stage["id"] == "deposit":
        return "deposit"
    if stage["id"] == "pd":
        return "(on_pd is not null or deposit_state = 'PD')"
    return f"stage >= {stage['rank']}"


def _key(f: dict, stage: dict | None = None) -> str | None:
    """What one counts: None for rows; in unique applicants the student up to
    Offered and the sale (student + actual intake) from CoE on."""
    if f["unit"] != "unique":
        return None
    if stage and stage.get("rank", 3) <= 2:
        return "student_key"
    return SALE_KEY


def _count(f: dict, condition: str = "true", stage: dict | None = None) -> str:
    key = _key(f, stage)
    if key:
        return f"count(distinct {key}) filter (where {condition})"
    return f"count(*) filter (where {condition})"


# --------------------------------------------------------------------------
# the view
# --------------------------------------------------------------------------


def overview(ctx: ViewContext, params: dict) -> dict:
    load = ctx.load("applications")
    anchor = (ctx.one(ANCHOR_SQL, {"load": load}) or {}).get("anchor")
    if anchor is None:
        raise ViewError("the loaded applications file has no stage dates")
    f = _filters(params, anchor)
    where, args = _where(f)
    base = {"load": load, "from": f["from"], "to": f["to"], **args}

    def sits(stage: dict) -> str:
        return f"stage = {stage['rank']}"

    # Deposit, DAA and PD sit at no rung: closed is closed lost, the open ones
    # split by the state they are in now.
    held = {
        DEPOSIT["id"]: (DEPOSIT, {"active": "deposit_state = 'Active'", "daa": "deposit_state = 'DAA'"}),
        DAA["id"]: (DAA, {"awaiting": "deposit_state = 'DAA'", "approved": "deferral_approved"}),
        PD["id"]: (PD, {"active": "deposit_state = 'PD'", "paid": "deposit"}),
    }
    figures_sql = [
        f"{_count(f, _reached(f, s), s)} as {s['id']}, "
        f"{_count(f, f'{_reached(f, s)} and {sits(s)} and not closed_lost', s)} as {s['id']}_active, "
        f"{_count(f, f'{_reached(f, s)} and {sits(s)} and closed_lost', s)} as {s['id']}_closed"
        for s in STAGES
    ]
    for name, (card, states) in held.items():
        reached = _reached(f, card)
        figures_sql.append(f"{_count(f, reached, card)} as {name}")
        figures_sql.append(f"{_count(f, f'{reached} and closed_lost', card)} as {name}_closed")
        figures_sql += [f"{_count(f, f'{reached} and {cond} and not closed_lost', card)} as {name}_{state}"
                        for state, cond in states.items()]
    # the scope: any date in the range, or every row under all time
    in_range = (" or ".join(f"{d} between %(from)s and %(to)s" for d in ALL_DATES)) if f["from"] else "true"
    figures_sql.append(f"count(*) filter (where {in_range}) as scope_applications")
    figures_sql.append(f"count(distinct student_key) filter (where {in_range}) as scope_applicants")
    counts = ctx.one(
        "select " + ", ".join(figures_sql) + f" from applications where {where}",
        base,
    ) or {}

    def figures(stage: dict, *states: str) -> dict:
        return {"id": stage["id"], "name": stage["name"], "help": stage["help"],
                "n": counts.get(stage["id"], 0),
                **{state: counts.get(f"{stage['id']}_{state}", 0) for state in states or ("active",)},
                "closed": counts.get(f"{stage['id']}_closed", 0)}

    # Where the deposits sit now: by each deposit's furthest stage, or in
    # unique applicants by the furthest stage among that sale's deposits.
    key = _key(f, DEPOSIT) or "app_uid"
    split_rows = ctx.rows(
        f"""select stage, count(*) as n
              from (select {key}, max(stage) as stage from applications
                     where {where} and {_reached(f, DEPOSIT)} group by 1) d
             group by 1""",
        base,
    )
    by_stage = {r["stage"]: r["n"] for r in split_rows}

    def menu(skip: str, column: str) -> list[dict]:
        clause, extra = _where(f, skip)
        rows = ctx.rows(
            f"select {column} as name, {_count(f, stage=STAGES[0])} as n from applications where {clause} group by 1",
            {"load": load, **extra},
        )
        return rows

    dims = {}
    for param, column in DIMENSIONS.items():
        rows = menu(param, column)
        found = {r["name"] for r in rows}
        # a pick with nothing behind it any more stays listed, so it can be removed
        rows += [{"name": name, "n": 0} for name in f[param] if name not in found]
        dims[param] = sorted(rows, key=lambda r: (r["name"] == UNASSIGNED, -r["n"], r["name"]))
    dims["areas"] = [r for r in dims["areas"] if r["name"] != UNASSIGNED]

    return {
        "anchor": anchor.isoformat(),
        "filters": {
            "unit": f["unit"],
            "from": f["from"].isoformat() if f["from"] else None,
            "to": f["to"].isoformat() if f["to"] else None,
            "default_range": f["default_range"],
            "level": f["level"],
            "intake_from": _ym(f["intake"][0]) if f["intake"] else None,
            "intake_to": _ym(f["intake"][1]) if f["intake"] else None,
            "intake_q": [f"{f['intake_q'][0]}-Q{q}" for q in f["intake_q"][1]] if f["intake_q"] else [],
            **{key: f[key] for key in DIMENSIONS},
        },
        "options": {
            **dims,
            "tree": ctx.rows(TREE_SQL, {"load": load}),
        },
        "scope": {"applications": counts.get("scope_applications", 0),
                  "applicants": counts.get("scope_applicants", 0)},
        "stages": [figures(s) for s in STAGES],
        "deposit": {
            **figures(DEPOSIT, "active", "daa"),
            "at": [{"id": s["id"], "name": s["name"], "n": by_stage.get(s["rank"], 0)} for s in STAGES[1:]],
        },
        "daa": figures(DAA, "awaiting", "approved"),
        "pd": figures(PD, "active", "paid"),
        "data": ctx.one(NOTES_SQL, {"load": load}),
    }


def _ym(value: int) -> str:
    return f"{value // 100}-{value % 100:02d}"


VIEWS = {"overview": overview}
