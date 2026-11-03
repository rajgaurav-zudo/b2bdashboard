"""B2B Pulse: the read model.

One question: what happened in this date range? Every number is a count of
events whose day falls inside it:

  * **Onboarded** -- introducers by Became Customer Date (master).
  * **Activity** -- introducer logs by Log Time.
  * **Applied, Offer, Deposit, CoE, Visa, Enrolled, Closed** -- applications by
    the timestamp of that stage. An application that reached Offer and Deposit
    in the same week counts once in each.

Scope:

  * **Area, region, team** are the CRM's Business* columns. An application has
    its own; an introducer has its own; a log takes its introducer's from the
    master, or failing that the most common one among the introducers managed
    by the log's `Managed By Team`.
  * **Actual intake** narrows the application stages only. Onboarding and
    activity have no intake, so they are left as they are rather than zeroed.
  * **Country** is the introducer's (master), falling back to the student's
    country for an application whose introducer is not on the master.

With no range picked the page shows the current Edvoy week, Saturday to today.
Every total is set against the period of the same length just before it.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, "/srv/api")
from app.regions import split  # noqa: E402
from app.views import ViewContext, ViewError  # noqa: E402

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

METRICS = [
    {"id": "onboarded", "name": "Onboarded", "def": "Introducers whose Became Customer Date is in the range."},
    {"id": "logs", "name": "Activity", "def": "Introducer logs whose Log Time is in the range."},
    {"id": "applied", "name": "Applied", "def": "Applications with the Applied timestamp in the range."},
    {"id": "offer", "name": "Offer", "def": "Applications with the Offer timestamp in the range."},
    {"id": "deposit", "name": "Deposit", "def": "Applications with the Deposit Fully Paid timestamp in the range."},
    {"id": "coe", "name": "CoE", "def": "Applications with the COE Received timestamp in the range."},
    {"id": "visa", "name": "Visa granted", "def": "Applications with the Visa Granted timestamp in the range."},
    {"id": "enrolled", "name": "Enrolled", "def": "Applications with the Enrolled timestamp in the range."},
    {"id": "closed", "name": "Closed", "def": "Applications marked as closed in the range."},
]
IDS = [m["id"] for m in METRICS]
APP_METRICS = {"applied": "at_applied", "offer": "at_offer", "deposit": "at_deposit", "coe": "at_coe",
               "visa": "at_visa", "enrolled": "at_enrolled", "closed": "at_closed"}

# The dashboard is B2B's alone: every number, option and record is held to
# this business area, whatever the request asks for.
AREA = "B2B"

# What a breakdown row is keyed on. Each is never null, so a row's key can be
# sent straight back to ask for its records.
DIMS = {
    "region": "region",
    "team": "team",
    "country": "coalesce(country, 'Unknown')",
    "introducer": "coalesce(introducer, '(no introducer)')",
}
BREAKDOWN_LIMIT = 60
RECORDS_LIMIT = 2000

# A log's scope where its introducer is not on the master: the area, region and
# team most introducers managed by that SRM team carry.
_TEAM_SCOPE = """
select distinct on (srm_team) srm_team, area, region, team
  from (select srm_team, area, region, team, count(*) as n
          from introducers where load_id = %(il)s and srm_team is not null
         group by 1, 2, 3, 4) t
 order by srm_team, n desc
"""


def _branch(metric: str) -> str:
    """One metric's events: metric, day, area, region, team, country, introducer,
    intake_ym and ref (the row's key in its own table)."""
    if metric == "onboarded":
        return """
select 'onboarded'::text as metric, i.became_customer as day, i.area, i.region, i.team,
       i.country, i.partner_name as introducer, null::int as intake_ym, i.partner_name as ref
  from introducers i
 where i.load_id = %(il)s and i.became_customer between %(lo)s and %(hi)s"""
    if metric == "logs":
        return """
select 'logs'::text, l.logged_on,
       coalesce(m.area, ts.area, 'Unassigned'), coalesce(m.region, ts.region, 'Unassigned'),
       coalesce(m.team, ts.team, 'Unassigned'), m.country, l.introducer_name, null::int, l.log_uid
  from logs l
  left join introducers m on m.load_id = %(il)s and m.partner_name = l.introducer_name
  left join team_scope ts on ts.srm_team = l.managed_by_team
 where l.load_id = %(ll)s and l.logged_on between %(lo)s and %(hi)s"""
    col = APP_METRICS[metric]
    return f"""
select '{metric}'::text, a.{col}, a.area, a.region, a.team,
       coalesce(m.country, a.student_country), a.introducer_name, a.intake_ym, a.app_uid
  from applications a
  left join introducers m on m.load_id = %(il)s and m.partner_name = a.introducer_name
 where a.load_id = %(al)s and a.{col} between %(lo)s and %(hi)s
   and (%(all_intakes)s or a.intake_ym = any(%(intakes)s))"""


def _events(metrics: list[str]) -> str:
    """The `ev` CTE: every event of these metrics in [lo, hi], scope-filtered."""
    union = "\nunion all".join(_branch(m) for m in metrics)
    return f"""
with team_scope as ({_TEAM_SCOPE}),
raw (metric, day, area, region, team, country, introducer, intake_ym, ref) as ({union}),
ev as (
  select * from raw
   where (%(all_areas)s or area = any(%(areas)s))
     and (%(all_regions)s or region = any(%(regions)s))
     and (%(all_teams)s or team = any(%(teams)s))
)"""


def _edvoy_week_start(day: date) -> date:
    """The Saturday on or before `day`: Edvoy weeks run Saturday to Friday."""
    return day - timedelta(days=(day.weekday() + 2) % 7)


def _day(raw: str | None, name: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ViewError(f"{name} must be a date like 2026-10-03, not '{raw}'") from exc


def _filters(ctx: ViewContext, params: dict, today: date | None = None) -> dict:
    today = today or date.today()
    lo, hi = _day(params.get("from"), "from"), _day(params.get("to"), "to")
    if lo is None and hi is None:
        lo, hi = _edvoy_week_start(today), today
    lo, hi = lo or hi, hi or lo
    if lo > hi:
        lo, hi = hi, lo
    try:
        intakes = sorted({int(x) for x in split(params.get("intakes"))})
    except ValueError as exc:
        raise ViewError("intakes must be year*100+month numbers like 202609") from exc
    out = {
        "lo": lo, "hi": hi,
        "il": ctx.loads.get("introducers"), "al": ctx.loads.get("applications"), "ll": ctx.loads.get("logs"),
        "intakes": intakes, "all_intakes": not intakes,
        "areas": [AREA], "all_areas": False,
    }
    for key in ("regions", "teams"):
        chosen = sorted(set(split(params.get(key))))
        out[key], out[f"all_{key}"] = chosen, not chosen
    return out


def _intake_label(ym: int) -> str:
    return f"{MONTH_NAMES[ym % 100 - 1]} {ym // 100}"


def _blank() -> dict:
    return {m: 0 for m in IDS}


def _bucket(lo: date, hi: date) -> str:
    span = (hi - lo).days + 1
    return "day" if span <= 62 else "week" if span <= 26 * 7 else "month"


def _bucket_of(day: date, unit: str) -> date:
    if unit == "week":
        return _edvoy_week_start(day)
    if unit == "month":
        return day.replace(day=1)
    return day


def _next_bucket(start: date, unit: str) -> date:
    if unit == "month":
        return (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start + timedelta(days=7 if unit == "week" else 1)


def overview(ctx: ViewContext, params: dict) -> dict:
    if all(v is None for v in ctx.loads.values()):
        raise ViewError("no data loaded yet — upload the introducers, applications and logs exports")
    f = _filters(ctx, params)
    lo, hi = f["lo"], f["hi"]
    span = (hi - lo).days + 1
    prev_lo, prev_hi = lo - timedelta(days=span), lo - timedelta(days=1)
    by = params.get("by") or "region"
    if by not in DIMS:
        raise ViewError(f"by must be one of {', '.join(DIMS)}")

    # one pass over both periods: the previous one only feeds the deltas
    p = {**f, "lo": prev_lo}
    rows = ctx.rows(
        _events(IDS) + f"""
select metric, day, {DIMS[by]} as key, count(*)::int as n
  from ev group by 1, 2, 3""",
        p,
    )

    totals, previous = _blank(), _blank()
    unit = _bucket(lo, hi)
    trend: dict[date, dict] = {}
    cursor = _bucket_of(lo, unit)
    while cursor <= hi:          # every bucket, so an empty day still draws
        trend[cursor] = _blank()
        cursor = _next_bucket(cursor, unit)
    breakdown: dict[str, dict] = {}
    for r in rows:
        if r["day"] < lo:
            previous[r["metric"]] += r["n"]
            continue
        totals[r["metric"]] += r["n"]
        trend[_bucket_of(r["day"], unit)][r["metric"]] += r["n"]
        breakdown.setdefault(r["key"], _blank())[r["metric"]] += r["n"]

    ranked = sorted(breakdown.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))

    return {
        "range": {"from": lo.isoformat(), "to": hi.isoformat(), "days": span,
                  "default": not params.get("from") and not params.get("to")},
        "previous": {"from": prev_lo.isoformat(), "to": prev_hi.isoformat()},
        "metrics": [{**m, "value": totals[m["id"]], "previous": previous[m["id"]]} for m in METRICS],
        "trend": {
            "unit": unit,
            # a bucket's records are its days inside the range
            "points": [{"start": max(lo, k).isoformat(),
                        "end": min(hi, _next_bucket(k, unit) - timedelta(days=1)).isoformat(),
                        **v} for k, v in trend.items()],
        },
        "breakdown": {
            "by": by,
            "rows": [{"key": k, **v} for k, v in ranked[:BREAKDOWN_LIMIT]],
            "more": max(0, len(ranked) - BREAKDOWN_LIMIT),
        },
        "options": _options(ctx, f),
        "loaded": {k: v is not None for k, v in ctx.loads.items()},
        "chosen": {"areas": f["areas"], "regions": f["regions"], "teams": f["teams"],
                   "intakes": f["intakes"]},
    }


def _options(ctx: ViewContext, f: dict) -> dict:
    """Every B2B region and team either file holds, each with how many rows
    carry it; every B2B actual intake with its application count."""
    scope = ctx.rows(
        """select area, region, team, sum(n)::int as n from (
             select area, region, team, count(*) as n from introducers
              where load_id = %(il)s and area = any(%(areas)s) group by 1, 2, 3
             union all
             select area, region, team, count(*) from applications
              where load_id = %(al)s and area = any(%(areas)s) group by 1, 2, 3
           ) t group by 1, 2, 3""",
        f,
    )
    areas: dict[str, int] = {}
    regions: dict[str, dict] = {}
    teams: dict[str, dict] = {}
    for r in scope:
        areas[r["area"]] = areas.get(r["area"], 0) + r["n"]
        reg = regions.setdefault(r["region"], {"name": r["region"], "n": 0, "areas": set()})
        reg["n"] += r["n"]
        reg["areas"].add(r["area"])
        tm = teams.setdefault(r["team"], {"name": r["team"], "n": 0, "regions": set(), "areas": set()})
        tm["n"] += r["n"]
        tm["regions"].add(r["region"])
        tm["areas"].add(r["area"])
    intakes = ctx.rows(
        """select intake_ym, count(*)::int as n from applications
            where load_id = %(al)s and area = any(%(areas)s) and intake_ym is not null group by 1 order by 1 desc""",
        f,
    )

    def listed(d: dict) -> list[dict]:
        return sorted(({k: sorted(v) if isinstance(v, set) else v for k, v in x.items()} for x in d.values()),
                      key=lambda x: (x["name"] == "Unassigned", -x["n"], x["name"]))

    return {
        "areas": sorted(({"name": k, "n": v} for k, v in areas.items()),
                        key=lambda x: (x["name"] == "Unassigned", -x["n"], x["name"])),
        "regions": listed(regions),
        "teams": listed(teams),
        "intakes": [{"id": r["intake_ym"], "name": _intake_label(r["intake_ym"]), "n": r["n"]} for r in intakes],
    }


# --------------------------------------------------------------------------
# the records behind a number
# --------------------------------------------------------------------------

_DETAIL = {
    "onboarded": (
        """select ev.day, i.partner_name, i.country, i.introducer_status, i.srm_owner, i.srm_team,
                  i.area, i.region, i.team
             from ev join introducers i on i.load_id = %(il)s and i.partner_name = ev.ref""",
        [("day", "Became customer"), ("partner_name", "Introducer"), ("country", "Country"),
         ("introducer_status", "Status"), ("srm_owner", "SRM"), ("srm_team", "SRM team"),
         ("region", "Region"), ("team", "Team")],
    ),
    "logs": (
        """select ev.day, l.introducer_name, l.log_type, l.call_type, l.outcome, l.created_by,
                  l.managed_by_team, ev.region, ev.team, l.note
             from ev join logs l on l.load_id = %(ll)s and l.log_uid = ev.ref""",
        [("day", "Logged"), ("introducer_name", "Introducer"), ("log_type", "Type"),
         ("call_type", "Call type"), ("outcome", "Outcome"), ("created_by", "By"),
         ("managed_by_team", "Managed by"), ("region", "Region"), ("team", "Team"), ("note", "Note")],
    ),
}
_APP_DETAIL = (
    """select ev.day, a.application_id, a.student_name, a.introducer_name, a.institution, a.course_name,
              a.course_level, a.intake_ym, a.application_status, a.deposit_paid_status,
              a.region, a.team, a.student_country
         from ev join applications a on a.load_id = %(al)s and a.app_uid = ev.ref""",
    [("day", "Date"), ("application_id", "Application"), ("student_name", "Student"),
     ("introducer_name", "Introducer"), ("institution", "Institution"), ("course_name", "Course"),
     ("course_level", "Level"), ("intake", "Intake"), ("application_status", "Status"),
     ("deposit_paid_status", "Deposit"), ("region", "Region"), ("team", "Team"),
     ("student_country", "Student country")],
)


def records(ctx: ViewContext, params: dict) -> dict:
    metric = params.get("metric") or ""
    if metric not in IDS:
        raise ViewError(f"metric must be one of {', '.join(IDS)}")
    f = _filters(ctx, params)
    dim, key = params.get("dim") or "", params.get("key")
    where = ""
    if dim:
        if dim not in DIMS:
            raise ViewError(f"dim must be one of {', '.join(DIMS)}")
        if key is None:
            raise ViewError("key is needed with dim")
        where = f"where {DIMS[dim]} = %(key)s"
    sql, columns = _DETAIL.get(metric, _APP_DETAIL)
    p = {**f, "key": key}
    base = _events([metric]) + f", picked as (select * from ev {where})"
    total = ctx.one(base + " select count(*)::int as n from picked", p)["n"]
    rows = ctx.rows(
        base + " " + sql.replace("from ev ", "from picked ev ").replace("from ev\n", "from picked ev\n")
        + f" order by ev.day desc limit {RECORDS_LIMIT}",
        p,
    )
    out = []
    for r in rows:
        r = dict(r)
        r["day"] = r["day"].isoformat() if r.get("day") else None
        if "intake_ym" in r:
            r["intake"] = _intake_label(r.pop("intake_ym")) if r.get("intake_ym") else None
        out.append(r)
    name = next(m["name"] for m in METRICS if m["id"] == metric)
    return {
        "metric": metric, "name": name,
        "range": {"from": f["lo"].isoformat(), "to": f["hi"].isoformat()},
        "dim": dim or None, "key": key,
        "columns": [{"id": c, "name": n} for c, n in columns],
        "rows": out, "total": total, "limit": RECORDS_LIMIT,
    }


VIEWS = {"overview": overview, "records": records}
