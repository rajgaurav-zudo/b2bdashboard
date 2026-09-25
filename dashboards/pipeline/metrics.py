"""Pipeline: the read model.

One question: for the students of an intake, how far has each got, and how does
that compare with the same intake a year earlier.

  * **A student, not an application.** Everything is counted on `student_key`
    (Student Ref Id). A student's super status is the furthest stage any of
    their applications *inside the scope* has reached: two applications at
    Applied and one at Offer is one student at Offer.
  * **Scope is the actual intake.** A calendar year is its twelve intake months;
    quarters narrow it to their months. An academic year runs from
    ACADEMIC_START_MONTH to the month before it a year later, and its quarters
    count from that start.
  * **Pipeline and funnel are the same students read two ways.** The pipeline
    puts each student in exactly one stage (their super status), so its rows sum
    to the total. The funnel is cumulative: a student at Deposit is also counted
    at Offer and Applied, so each row reads against the one above.
  * **Active or closed lost.** A student is closed lost when every one of their
    in-scope applications is closed lost; one live application keeps them
    active.
  * **Region and Team** are the introducer's SRM team on the introducers
    master, as on Introducer Performance, so the two agree about who is whose.
    An application with no introducer, or one missing from the master, is
    Unassigned (region Other). Like course level, they pick applications before
    the roll-up: a student's stage is the furthest among their applications in
    the picked teams.
  * **Last year, twice.** "At this point" replays the stage dates up to the same
    day a year earlier than the export's newest date, so a partial intake is set
    against a partial intake. "Final" is where last year's students stand now.
    Closed lost carries no date, so the at-this-point figure has no active/lost
    split.

"Today" is the export's newest stage date, not the clock.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, "/srv/api")
from app.regions import narrow, options, split  # noqa: E402
from app.views import ViewContext, ViewError  # noqa: E402

# The academic year starts in August and runs to July. One constant: moving the
# start month moves the year, its quarters and its label together.
ACADEMIC_START_MONTH = 8
FIRST_YEAR = 2022
YEARS_AHEAD = 2

STAGES = [
    {"id": "applied", "name": "Applied", "date": "on_applied"},
    {"id": "offer", "name": "Offer", "date": "on_offer"},
    {"id": "deposit", "name": "Deposit", "date": "on_deposit"},
    {"id": "coe", "name": "CoE", "date": "on_coe"},
    {"id": "visa", "name": "Visa granted", "date": "on_visa"},
    {"id": "enrolled", "name": "Enrolled", "date": "on_enrolled"},
]

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# the furthest stage reached on or before %(cut)s, from the backfilled dates
_AS_AT = "case " + " ".join(
    f"when {s['date']} <= %(cut)s then {rank}"
    for rank, s in reversed(list(enumerate(STAGES, start=1)))
) + " else 0 end"

# The applications of the scope's intake months, each with its team. The
# introducers table is keyed on (load_id, partner_name), so the join cannot
# duplicate an application; with no master loaded every team is Unassigned.
_SCOPED = """
select a.*, coalesce(nullif(m.srm_team, ''), 'Unassigned') as team
  from applications a
  left join introducers m on m.load_id = %(intro)s and m.partner_name = a.introducer_name
 where a.load_id = %(load)s
   and a.intake_ym = any(%(yms)s)
"""

# One row per (super status, super status at the cut-off, closed lost), counted
# in students. Everything on the page is summed from this in Python, so the
# pipeline, the funnel and the three periods cannot disagree about who is in.
STUDENTS_SQL = f"""
with s as (
  select student_key,
         max(stage)          as stage,
         max({_AS_AT})       as stage_asat,
         bool_and(closed_lost) as lost
    from ({_SCOPED}) a
   where (%(all_levels)s or course_level = any(%(levels)s))
     and (%(all_teams)s or team = any(%(teams)s))
   group by 1
)
select stage, stage_asat, lost, count(*) as n
  from s where stage > 0
 group by 1, 2, 3
"""

ANCHOR_SQL = f"""
select max(greatest({', '.join(s['date'] for s in STAGES)})) as anchor
  from applications where load_id = %(load)s
"""

# Each menu is counted with every other filter applied but its own, so a number
# beside an option is what picking it would show. Every level on the load is
# listed, even at zero for this scope.
LEVELS_SQL = f"""
select l.name, coalesce(n.n, 0) as n
  from (select distinct course_level as name from applications where load_id = %(load)s) l
  left join (select course_level as name, count(distinct student_key) as n
               from ({_SCOPED}) a
              where stage > 0 and (%(all_teams)s or team = any(%(teams)s))
              group by 1) n using (name)
 order by 2 desc, 1
"""

# Every team on the master plus Unassigned, with students in scope.
TEAMS_SQL = f"""
select t.team, coalesce(n.n, 0) as n
  from (select coalesce(nullif(srm_team, ''), 'Unassigned') as team
          from introducers where load_id = %(intro)s
        union select 'Unassigned') t
  left join (select team, count(distinct student_key) as n
               from ({_SCOPED}) a
              where stage > 0 and (%(all_levels)s or course_level = any(%(levels)s))
              group by 1) n using (team)
 order by 1
"""

NOTES_SQL = """
select count(*)                                                    as app_rows,
       count(*) filter (where intake_ym is null)                   as no_intake,
       count(*) filter (where student_key like 'app:%%')           as no_student_ref,
       count(*) filter (where stage = 0)                           as no_stage,
       count(*) filter (where stage >= 3 and on_deposit is null)   as undated_deposit
  from applications where load_id = %(load)s
"""

# --------------------------------------------------------------------------
# scope
# --------------------------------------------------------------------------


def _months(mode: str, year: int, quarters: list[int]) -> list[tuple[int, int]]:
    """(year, month) of every intake month in the scope, in order."""
    start = 1 if mode == "calendar" else ACADEMIC_START_MONTH
    out = []
    for q in quarters:
        for i in range(3 * (q - 1), 3 * q):
            offset = start - 1 + i
            out.append((year + offset // 12, offset % 12 + 1))
    return out


def _quarter_label(mode: str, q: int) -> str:
    months = _months(mode, 2000, [q])
    return f"Q{q} {MONTH_NAMES[months[0][1] - 1]}–{MONTH_NAMES[months[-1][1] - 1]}"


def _year_label(mode: str, year: int) -> str:
    return str(year) if mode == "calendar" else f"{year}-{year + 1}"


def _scope_label(mode: str, year: int, quarters: list[int]) -> str:
    months = _months(mode, year, quarters)
    head = _year_label(mode, year) if mode == "calendar" else f"Academic year {_year_label(mode, year)}"
    if len(quarters) == 4:
        span = ""
    else:
        span = " · " + ", ".join(f"Q{q}" for q in quarters)
    first, last = months[0], months[-1]
    return (f"{head}{span} (intakes {MONTH_NAMES[first[1] - 1]} {first[0]}"
            f" – {MONTH_NAMES[last[1] - 1]} {last[0]})")


def _year_back(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:                     # 29 February
        return day.replace(year=day.year - 1, day=28)


def _default_year(mode: str, anchor: date) -> int:
    if mode == "calendar":
        return anchor.year
    return anchor.year if anchor.month >= ACADEMIC_START_MONTH else anchor.year - 1


def _filters(params: dict, anchor: date, today: date) -> dict:
    mode = params.get("mode") or "calendar"
    if mode not in ("calendar", "academic"):
        raise ViewError(f"mode must be calendar or academic, not '{mode}'")
    years = list(range(FIRST_YEAR, today.year + YEARS_AHEAD + 1))
    raw_year = params.get("year")
    if raw_year:
        try:
            year = int(raw_year)
        except ValueError as exc:
            raise ViewError(f"year must be a number, not '{raw_year}'") from exc
        if year not in years:
            raise ViewError(f"year must be between {years[0]} and {years[-1]}")
    else:
        year = min(max(_default_year(mode, anchor), years[0]), years[-1])
    try:
        quarters = sorted({int(q) for q in split(params.get("quarters"))})
    except ValueError as exc:
        raise ViewError("quarters must be 1 to 4") from exc
    if any(q not in (1, 2, 3, 4) for q in quarters):
        raise ViewError("quarters must be 1 to 4")
    return {
        "mode": mode, "year": year, "years": years,
        "quarters": quarters,                  # [] means the whole year
        "levels": split(params.get("levels")),
        "teams": sorted(set(split(params.get("teams")))),
        "regions": sorted(set(split(params.get("regions")))),
    }


# --------------------------------------------------------------------------
# the view
# --------------------------------------------------------------------------


def _blank() -> dict:
    return {"total": 0, "active": 0, "lost": 0}


def _tally(rows: list[dict], key: str, with_lost: bool) -> dict:
    """Pipeline (exclusive) and funnel (cumulative) per stage from the grouped rows."""
    pipeline = {rank: _blank() for rank in range(1, len(STAGES) + 1)}
    for row in rows:
        rank = row[key]
        if rank < 1:
            continue
        cell = pipeline[rank]
        cell["total"] += row["n"]
        if with_lost:
            cell["lost" if row["lost"] else "active"] += row["n"]
    funnel = {}
    for rank in range(len(STAGES), 0, -1):
        above = funnel.get(rank + 1, _blank())
        funnel[rank] = {k: pipeline[rank][k] + above[k] for k in ("total", "active", "lost")}
    if not with_lost:
        for cell in (*pipeline.values(), *funnel.values()):
            cell["active"] = cell["lost"] = None
    return {"pipeline": pipeline, "funnel": funnel}


def overview(ctx: ViewContext, params: dict) -> dict:
    load = ctx.load("applications")
    anchor = (ctx.one(ANCHOR_SQL, {"load": load}) or {}).get("anchor")
    if anchor is None:
        raise ViewError("the loaded applications file has no stage dates")
    f = _filters(params, anchor, date.today())
    quarters = f["quarters"] or [1, 2, 3, 4]
    cut = _year_back(anchor)

    def yms(year: int) -> list[int]:
        return [y * 100 + m for y, m in _months(f["mode"], year, quarters)]

    # Region and Team come to one list of teams, or None for every team. It can
    # be empty -- a team picked outside the picked regions -- and then matches
    # nobody, which is what was asked for.
    intro = ctx.loads.get("introducers")
    base = {"load": load, "intro": intro, "all_levels": not f["levels"], "levels": f["levels"] or [""]}
    team_counts = ctx.rows(TEAMS_SQL, {**base, "yms": yms(f["year"])})
    teams = narrow(f["teams"], f["regions"], [r["team"] for r in team_counts])
    common = {**base, "cut": cut, "all_teams": teams is None, "teams": teams or [""]}
    now_rows = ctx.rows(STUDENTS_SQL, {**common, "yms": yms(f["year"])})
    ly_rows = ctx.rows(STUDENTS_SQL, {**common, "yms": yms(f["year"] - 1)})

    now = _tally(now_rows, "stage", True)
    ly_final = _tally(ly_rows, "stage", True)
    ly_asat = _tally(ly_rows, "stage_asat", False)

    stages = []
    for rank, stage in enumerate(STAGES, start=1):
        stages.append({
            "id": stage["id"], "name": stage["name"],
            "now": {"pipeline": now["pipeline"][rank], "funnel": now["funnel"][rank]},
            "ly_asat": {"pipeline": ly_asat["pipeline"][rank], "funnel": ly_asat["funnel"][rank]},
            "ly_final": {"pipeline": ly_final["pipeline"][rank], "funnel": ly_final["funnel"][rank]},
        })

    mode = f["mode"]
    level_rows = ctx.rows(LEVELS_SQL, {**common, "yms": yms(f["year"])})
    team_options, region_options = options(team_counts)
    return {
        "anchor": anchor.isoformat(),
        "cutoff": cut.isoformat(),
        "filters": {"mode": mode, "year": f["year"], "quarters": f["quarters"], "levels": f["levels"],
                    "teams": f["teams"], "regions": f["regions"]},
        "options": {
            "modes": [{"id": "calendar", "label": "Calendar year"},
                      {"id": "academic", "label": "Academic year"}],
            "years": [{"value": y, "label": _year_label(mode, y)} for y in f["years"]],
            "quarters": [{"q": q, "label": _quarter_label(mode, q)} for q in (1, 2, 3, 4)],
            "levels": [{"name": r["name"], "n": r["n"]} for r in level_rows],
            "academic_start": MONTH_NAMES[ACADEMIC_START_MONTH - 1],
            "team_options": team_options,
            "region_options": region_options,
        },
        "scope": {
            "label": _scope_label(mode, f["year"], quarters),
            "last_year": _scope_label(mode, f["year"] - 1, quarters),
        },
        "totals": {
            "now": now["funnel"][1],
            "ly_asat": ly_asat["funnel"][1],
            "ly_final": ly_final["funnel"][1],
        },
        "stages": stages,
        "data": ctx.one(NOTES_SQL, {"load": load}),
    }


VIEWS = {"overview": overview}
