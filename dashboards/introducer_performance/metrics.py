"""Introducer performance: the read model.

This is the server-side port of the metric definitions that used to live in the
browser (see legacy/introducer-dashboard.html). Definitions are documented in
context.md; the short version of the two that trip people up:

  * CUR is chosen, never assumed. Nov/Dec intakes roll into the following
    January, so max(intake year) is a barely-started phantom year. CUR is the
    newest year holding at least 10% of the peak year's applications.
  * "Lifetime" means every intake year up to and including CUR, plus rows with
    no usable year. Rows dated after CUR are visible in the funnel table but
    score nothing, so one mistyped year cannot move a tile.

Nothing here is imported by core or by any other dashboard.
"""
import sys
from statistics import median

sys.path.insert(0, "/srv/api")
from app.views import ViewContext, ViewError  # noqa: E402

# --------------------------------------------------------------------------
# SQL
# --------------------------------------------------------------------------

# Row-level flags, shared by every query below. `act`/`clo` split paid deposits
# by whether the application was later closed lost.
_ROWS = """
f as (
  select
    introducer_name                                   as name,
    cycle_year, cycle_index, deposit_fully_paid,
    deposit_fully_paid and not closed_lost            as act,
    deposit_fully_paid and closed_lost                as clo,
    enrolled, visa_granted,
    closed_lost
      and lower(coalesce(application_status, ''))     = 'visa'
      and lower(coalesce(application_sub_status, '')) = 'applied'  as vrej,
    closed_lost
      and lower(coalesce(application_status, '')) like 'coe%%'
      and lower(coalesce(application_status, '')) like '%%receiv%%' as coe
  from applications
  where load_id = %(apps)s
)
"""

# Per-introducer aggregate. `scored` is the lifetime window: up to CUR, plus
# rows whose intake year could not be read at all.
_AGG = """
a as (
  select
    name,
    count(*) filter (where scored)                                as apps_life,
    count(*) filter (where cycle_year = %(cur)s)                  as apps_cur,
    count(*) filter (where act and scored)                        as act_life,
    count(*) filter (where act and cycle_year = %(cur)s)          as act_cur,
    count(*) filter (where act and cycle_year = %(prev)s)         as act_prev,
    count(*) filter (where act and cycle_year < %(prev)s)         as act_before,
    count(*) filter (where clo and scored)                        as clos_life,
    count(*) filter (where clo and cycle_year = %(cur)s)          as clos_cur,
    count(*) filter (where enrolled and scored)                   as enr_life,
    count(*) filter (where enrolled and act and scored)           as enr_dep_life,
    count(*) filter (where visa_granted and act and scored)       as vg_dep_life,
    count(*) filter (where vrej and scored)                       as vrej_life,
    count(*) filter (where vrej and cycle_year = %(cur)s)         as vrej_cur,
    count(*) filter (where coe and scored)                        as coe_life,
    count(*) filter (where coe and cycle_year = %(cur)s)          as coe_cur,
    count(*) filter (where deposit_fully_paid)                    as dep_any,
    -- cadence counts need a real intake year as well as a month
    count(*) filter (where act and cycle_year is not null and cycle_index = 0) as cyc0,
    count(*) filter (where act and cycle_year is not null and cycle_index = 1) as cyc1,
    count(*) filter (where act and cycle_year is not null and cycle_index = 2) as cyc2,
    max(cycle_year * 10 + cycle_index)
      filter (where act and cycle_index is not null and cycle_year <= %(cur)s) as last_key
  from (select *, (cycle_year is null or cycle_year <= %(cur)s) as scored from f) fx
  where name is not null
  group by name
)
"""

_MASTER = """
m as (
  select
    partner_name                                          as name,
    lifecycle_stage                                       as stage,
    latest_contract_status                                as contract,
    country, srm_team as team, srm_owner as srm,
    coalesce(became_customer_year, source_created_year)   as became_y,
    (became_customer_year is null and source_created_year is not null) as became_fallback,
    org_commission                                        as comm,
    contract_commission_type                              as comm_type
  from introducers
  where load_id = %(intro)s
)
"""

# Scope: Customer stage, OR any paid deposit at any stage -- including names
# that never made it into the master file.
_BOOK_SELECT = """
select
  coalesce(a.name, m.name)                                            as name,
  case when m.name is null then 'Not in CRM'
       else coalesce(nullif(m.stage, ''), 'Unknown') end              as stage,
  (m.name is not null)                                                as in_crm,
  (a.name is not null)                                                as in_apps,
  coalesce(m.contract, '')                                            as contract,
  coalesce(nullif(m.country, ''), 'Unknown')                          as country,
  coalesce(nullif(m.team, ''), 'Unassigned')                          as team,
  coalesce(nullif(m.srm, ''), 'Unassigned')                           as srm,
  m.became_y,
  coalesce(m.became_fallback, false)                                  as became_fallback,
  coalesce(m.comm, '')                                                as comm,
  coalesce(m.comm_type, '')                                           as comm_type,
  coalesce(a.apps_life, 0) as apps_life, coalesce(a.apps_cur, 0) as apps_cur,
  coalesce(a.act_life, 0)  as act_life,  coalesce(a.act_cur, 0)  as act_cur,
  coalesce(a.act_prev, 0)  as act_prev,  coalesce(a.act_before, 0) as act_before,
  coalesce(a.clos_life, 0) as clos_life, coalesce(a.clos_cur, 0) as clos_cur,
  coalesce(a.enr_life, 0)  as enr_life,
  coalesce(a.enr_dep_life, 0) as enr_dep_life, coalesce(a.vg_dep_life, 0) as vg_dep_life,
  coalesce(a.vrej_life, 0) as vrej_life, coalesce(a.vrej_cur, 0) as vrej_cur,
  coalesce(a.coe_life, 0)  as coe_life,  coalesce(a.coe_cur, 0)  as coe_cur,
  coalesce(a.cyc0, 0) as cyc0, coalesce(a.cyc1, 0) as cyc1, coalesce(a.cyc2, 0) as cyc2,
  coalesce(a.last_key, 0) as last_key
from a
full outer join m on m.name = a.name
where m.stage = 'Customer' or coalesce(a.dep_any, 0) > 0
"""

BOOK_SQL = f"with {_ROWS}, {_AGG}, {_MASTER} {_BOOK_SELECT}"

YEAR_HIST_SQL = """
select cycle_year as y, count(*) as n
  from applications
 where load_id = %(apps)s and cycle_year between 1991 and 2099
 group by 1 order by 1
"""

# Funnel rows are intake-year totals, including years after CUR: the table shows
# them (flagged) so a stray future date is visible rather than silently dropped.
FUNNEL_SQL = f"""
with {_ROWS}, {_AGG}, {_MASTER},
book as ({_BOOK_SELECT})
select
  cycle_year as y,
  count(*)                                        as apps,
  count(*) filter (where act)                     as act,
  count(*) filter (where clo)                     as clos,
  count(*) filter (where act and visa_granted)    as vg,
  count(*) filter (where act and enrolled)        as enr
from f
where cycle_year is not null and name is not null
  and (%(scope)s = 'all' or name in (select name from book))
group by 1 order by 1
"""

NOTES_SQL = """
select
  (select count(*) from introducers where load_id = %(intro)s)                          as master_rows,
  (select count(*) from introducers where load_id = %(intro)s
     and became_customer_year is null)                                                  as blank_became,
  (select count(*) from introducers where load_id = %(intro)s
     and became_customer_year is null and source_created_year is not null)              as used_fallback,
  (select count(*) from introducers where load_id = %(intro)s
     and coalesce(latest_contract_status, '') = '')                                     as no_contract,
  (select count(*) from applications where load_id = %(apps)s)                          as app_rows,
  (select count(*) from applications where load_id = %(apps)s
     and introducer_name is null)                                                       as blank_intro,
  (select count(*) from applications where load_id = %(apps)s
     and introducer_name is null and deposit_fully_paid)                                as blank_intro_deposits,
  (select count(*) from applications where load_id = %(apps)s and cycle_year is null)    as no_year,
  (select count(*) from applications where load_id = %(apps)s
     and closed_lost and enrolled)                                                      as contradictions,
  (select stats from core.loads where id = %(intro)s)                                   as intro_stats
"""

# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

def pick_current_year(hist: list[tuple[int, int]]) -> int | None:
    """Newest intake year holding at least 10% of the peak year -- NOT max(year).

    Nov and Dec roll into the following January, so the newest year in any export
    is a handful of applications for an intake that has barely opened. Scoring
    against it zeroes every tile.
    """
    years = sorted(y for y, _ in hist if 1990 < y < 2100)
    if not years:
        return None
    counts = dict(hist)
    peak = max(counts[y] for y in years)
    cur = years[0]
    for y in years:
        if counts[y] >= 0.10 * peak:
            cur = y
    return cur


def _years(ctx: ViewContext) -> tuple[int, int, list[dict]]:
    hist = ctx.rows(YEAR_HIST_SQL, {"apps": ctx.load("applications")})
    cur = pick_current_year([(r["y"], r["n"]) for r in hist])
    if cur is None:
        raise ViewError("no usable intake years in the applications file")
    return cur, cur - 1, hist


def _book(ctx: ViewContext, cur: int, prev: int) -> list[dict]:
    rows = ctx.rows(BOOK_SQL, {
        "apps": ctx.load("applications"), "intro": ctx.load("introducers"),
        "cur": cur, "prev": prev,
    })
    for r in rows:
        r["close_pct"] = (r["clos_life"] / r["act_life"]) if r["act_life"] else None
        r["enr_rate"] = (r["enr_life"] / r["apps_life"]) if r["apps_life"] else 0.0
        r["is_active"] = r["act_cur"] > 0
        r["is_resurrected"] = r["act_cur"] > 0 and r["act_prev"] == 0 and r["act_before"] > 0
        r["is_dormant"] = r["act_cur"] == 0 and r["act_life"] > 0
        r["is_squanderer"] = r["apps_life"] > 1 and (r["act_life"] + r["clos_life"]) == 0
        r["is_slacker"] = r["stage"] == "Customer" and not r["in_apps"]
        r["is_bad_enrol"] = r["apps_life"] >= 10 and r["enr_rate"] < 0.10
        r["is_bad_close"] = r["act_life"] >= 3 and r["clos_life"] > 0.30 * r["act_life"]
        r["has_visa_rej"] = r["vrej_life"] > 0
        r["has_coe"] = r["coe_life"] > 0
        r["still_applying"] = r["apps_cur"] > 0
        r["cohort"] = r["became_y"]
    return rows


METRICS = {
    "act":  {"label": "active deposits",   "short": "active dep.",  "life": "act_life",  "cur": "act_cur"},
    "clos": {"label": "closed deposits",   "short": "closed dep.",  "life": "clos_life", "cur": "clos_cur"},
    "apps": {"label": "applications",      "short": "applications", "life": "apps_life", "cur": "apps_cur"},
    "vrej": {"label": "visa-stage losses", "short": "visa losses",  "life": "vrej_life", "cur": "vrej_cur"},
    "coe":  {"label": "CoE-stage losses",  "short": "CoE losses",   "life": "coe_life",  "cur": "coe_cur"},
    "none": {"label": "introducers",       "short": "--",           "life": None,        "cur": None},
}


def tile_defs(cur: int, prev: int) -> list[dict]:
    def cohort(year, name, definition):
        return {
            "id": f"coh{year}", "section": "active", "name": name, "definition": definition,
            "metric": "act", "head": "cur",
            "member": lambda r, y=year: r["is_active"] and r["became_y"] == y,
        }

    return [
        {"id": "active", "section": "active", "name": "Active", "metric": "act", "head": "cur",
         "definition": f"At least one active deposit in the {cur} intake year.",
         "member": lambda r: r["is_active"]},
        cohort(cur, f"Became customer {cur}", f"Active, and first became a customer in {cur}."),
        cohort(prev, f"Became customer {prev}", f"Active, and became a customer in {prev}."),
        cohort(cur - 2, f"Became customer {cur - 2}", f"Active, and became a customer in {cur - 2}."),
        {"id": "cohOld", "section": "active", "name": f"Became customer ≤{cur - 3}",
         "metric": "act", "head": "cur",
         "definition": f"Active, and became a customer in {cur - 3} or earlier.",
         "member": lambda r: r["is_active"] and r["became_y"] is not None and r["became_y"] <= cur - 3},
        {"id": "resurrected", "section": "active", "name": "Resurrected", "metric": "act",
         "head": "cur", "invert": True,
         "definition": f"Deposits in {cur}, none in {prev}, but deposits before that. Win-backs that landed.",
         "member": lambda r: r["is_resurrected"]},

        {"id": "dormant", "section": "leak", "name": "Dormant", "metric": "act", "head": "life",
         "definition": f"Paid deposits in an earlier year, none in {cur}. This is the call list.",
         "member": lambda r: r["is_dormant"]},
        {"id": "squanderers", "section": "leak", "name": "Squanderers", "metric": "apps", "head": "life",
         "definition": "More than one application, never a paid deposit of any kind. "
                       "See the naming critique below.",
         "member": lambda r: r["is_squanderer"]},
        {"id": "slackers", "section": "leak", "name": "Slackers", "metric": "none", "head": "count",
         "definition": "Customer-stage partners with no applications on record, ever.",
         "member": lambda r: r["is_slacker"]},

        {"id": "badEnrol", "section": "quality", "name": "Bad converters — enrolment",
         "metric": "apps", "head": "life",
         "definition": "10+ applications and under 10% of them reach enrolment. "
                       "This threshold is miscalibrated — see below.",
         "member": lambda r: r["is_bad_enrol"]},
        {"id": "badClose", "section": "quality", "name": "Bad converters — closures",
         "metric": "clos", "head": "life",
         "definition": "3+ active deposits, with closed deposits above 30% of them.",
         "member": lambda r: r["is_bad_close"]},
        {"id": "visaRej", "section": "quality", "name": "Visa rejected", "metric": "vrej", "head": "life",
         "definition": "Applications closed lost at status Visa · Applied.",
         "member": lambda r: r["has_visa_rej"]},
        {"id": "coeLost", "section": "quality", "name": "CoE closed lost", "metric": "coe", "head": "life",
         "definition": "Applications closed lost after the CoE was received.",
         "member": lambda r: r["has_coe"]},
    ]


def tile_stats(tile: dict, book: list[dict]) -> tuple[list[dict], dict]:
    members = [r for r in book if tile["member"](r)]
    metric = METRICS[tile["metric"]]
    life = sum(r[metric["life"]] for r in members) if metric["life"] else 0
    now = sum(r[metric["cur"]] for r in members) if metric["cur"] else 0
    contracts = [str(r["contract"] or "").lower() for r in members]
    return members, {
        "n": len(members), "life": life, "cur": now,
        "contract_active": contracts.count("active"),
        "contract_expired": contracts.count("expired"),
    }


def _public(tile: dict, stats: dict) -> dict:
    out = {k: v for k, v in tile.items() if k != "member"}
    metric = METRICS[tile["metric"]]
    out["metric_label"] = metric["label"]
    out["metric_short"] = metric["short"]
    out["stats"] = stats
    return out

# --------------------------------------------------------------------------
# views
# --------------------------------------------------------------------------

def _median(values: list[float]) -> float:
    return median(values) if values else 0.0


def overview(ctx: ViewContext, params: dict):
    cur, prev, hist = _years(ctx)
    book = _book(ctx, cur, prev)

    tiles = []
    for tile in tile_defs(cur, prev):
        _, stats = tile_stats(tile, book)
        tiles.append(_public(tile, stats))

    totals = {k: sum(r[k] for r in book) for k in
              ("act_life", "clos_life", "apps_life", "act_cur", "clos_cur", "enr_life")}

    by_stage: dict[str, dict] = {}
    for r in book:
        s = by_stage.setdefault(r["stage"], {"stage": r["stage"], "n": 0, "act": 0, "clos": 0, "act_cur": 0})
        s["n"] += 1
        s["act"] += r["act_life"]
        s["clos"] += r["clos_life"]
        s["act_cur"] += r["act_cur"]

    # Recruitment cadence differs by market: some run a single annual September
    # cycle, others spread across all three. Flattening that mislabels the
    # steadiest partners as lapsed.
    cadence: dict[str, dict] = {}
    for r in book:
        total = r["cyc0"] + r["cyc1"] + r["cyc2"]
        if not total:
            continue
        c = cadence.setdefault(r["country"], {"country": r["country"], "n": 0, "act": 0,
                                              "jan": 0, "may": 0, "sep": 0})
        c["n"] += 1
        c["act"] += total
        c["jan"] += r["cyc0"]
        c["may"] += r["cyc1"]
        c["sep"] += r["cyc2"]
    cadence_list = [c for c in cadence.values() if c["act"] >= 20]
    for c in cadence_list:
        c["sep_share"] = c["sep"] / c["act"]
        c["top"] = max(c["jan"], c["may"], c["sep"]) / c["act"]
        c["peak"] = "Sep" if c["sep"] >= c["jan"] and c["sep"] >= c["may"] else (
            "Jan" if c["jan"] >= c["may"] else "May")

    notes = ctx.one(NOTES_SQL, {"apps": ctx.load("applications"), "intro": ctx.load("introducers")}) or {}
    not_in_crm = [r for r in book if not r["in_crm"]]
    dormant_live = [r for r in book if r["is_dormant"] and r["still_applying"]]

    return {
        "current_year": cur, "previous_year": prev,
        "year_histogram": hist,
        "book_size": len(book),
        "totals": totals,
        "tiles": tiles,
        "by_stage": sorted(by_stage.values(), key=lambda s: -s["act"]),
        "cadence": sorted(cadence_list, key=lambda c: -c["act"]),
        "funnel": {
            "scope": ctx.rows(FUNNEL_SQL, {"apps": ctx.load("applications"),
                                           "intro": ctx.load("introducers"),
                                           "cur": cur, "prev": prev, "scope": "scope"}),
            "all": ctx.rows(FUNNEL_SQL, {"apps": ctx.load("applications"),
                                         "intro": ctx.load("introducers"),
                                         "cur": cur, "prev": prev, "scope": "all"}),
        },
        "not_in_crm": {
            "n": len(not_in_crm),
            "act": sum(r["act_life"] for r in not_in_crm),
            "clos": sum(r["clos_life"] for r in not_in_crm),
        },
        "dormant_still_applying": len(dormant_live),
        "critique": _critique(book, totals),
        "data": notes,
    }


def _critique(book: list[dict], totals: dict) -> dict:
    enrol_base = [r for r in book if r["apps_life"] >= 10]
    close_base = [r for r in book if r["act_life"] >= 3]

    def under(p):
        return sum(1 for r in enrol_base if r["enr_rate"] < p)

    def over(p):
        return sum(1 for r in close_base if r["clos_life"] / r["act_life"] > p)

    visa_by_country: dict[str, dict] = {}
    for r in book:
        if not r["vrej_life"]:
            continue
        v = visa_by_country.setdefault(r["country"], {"country": r["country"], "n": 0, "apps": 0})
        v["n"] += r["vrej_life"]
        v["apps"] += r["apps_life"]

    return {
        "enrolment": {
            "base": len(enrol_base),
            "under_10": under(0.10), "under_5": under(0.05), "under_3": under(0.03),
            "org_rate": (totals["enr_life"] / totals["apps_life"]) if totals["apps_life"] else 0.0,
            "median_rate": _median([r["enr_rate"] for r in enrol_base]),
            # a rule that flags most of the population describes the business
            "miscalibrated": under(0.10) > 0.5 * len(enrol_base),
        },
        "closures": {
            "base": len(close_base),
            "over_30": over(0.30), "over_50": over(0.50), "over_100": over(1.00),
            "median_ratio": _median([r["clos_life"] / r["act_life"] for r in close_base]),
            "miscalibrated": over(0.30) > 0.4 * len(close_base),
        },
        "visa_by_country": sorted(visa_by_country.values(), key=lambda v: -v["n"])[:4],
    }


_SORTABLE = {
    "name": lambda r: str(r["name"]).lower(),
    "stage": lambda r: str(r["stage"]).lower(),
    "country": lambda r: str(r["country"]).lower(),
    "team": lambda r: str(r["team"]).lower(),
    "srm": lambda r: str(r["srm"]).lower(),
    "became_y": lambda r: r["became_y"] if r["became_y"] is not None else -1,
    "apps_life": lambda r: r["apps_life"], "apps_cur": lambda r: r["apps_cur"],
    "act_life": lambda r: r["act_life"], "act_cur": lambda r: r["act_cur"],
    "clos_life": lambda r: r["clos_life"], "clos_cur": lambda r: r["clos_cur"],
    "vrej_life": lambda r: r["vrej_life"], "coe_life": lambda r: r["coe_life"],
    "enr_rate": lambda r: r["enr_rate"],
    "close_pct": lambda r: (r["close_pct"] if r["close_pct"] is not None else -1),
    "last_key": lambda r: r["last_key"],
}

_ROW_FIELDS = (
    "name", "stage", "in_crm", "in_apps", "contract", "country", "team", "srm",
    "became_y", "became_fallback", "comm", "comm_type",
    "apps_life", "apps_cur", "act_life", "act_cur", "clos_life", "clos_cur",
    "enr_life", "vrej_life", "vrej_cur", "coe_life", "coe_cur",
    "enr_rate", "close_pct", "last_key", "still_applying", "is_resurrected",
)


def tile(ctx: ViewContext, params: dict):
    """Drill-down for one tile, optionally grouped by one of this dashboard's dimensions."""
    tile_id = params.get("id")
    cur, prev, _ = _years(ctx)
    definitions = {t["id"]: t for t in tile_defs(cur, prev)}
    if tile_id not in definitions:
        raise ViewError(f"unknown tile '{tile_id}' (have: {', '.join(definitions)})")

    group_by = params.get("group_by") or "none"
    dimensions = {"country": "country", "team": "team", "srm": "srm", "stage": "stage"}
    if group_by != "none" and group_by not in dimensions:
        raise ViewError(f"cannot group by '{group_by}'")

    sort = params.get("sort") or ("act_life" if definitions[tile_id]["head"] == "life" else "act_cur")
    if sort not in _SORTABLE:
        raise ViewError(f"cannot sort by '{sort}'")
    descending = (params.get("dir") or "desc") == "desc"
    limit = max(1, min(int(params.get("limit") or 200), 2000))

    book = _book(ctx, cur, prev)
    definition = definitions[tile_id]
    members, stats = tile_stats(definition, book)
    key = _SORTABLE[sort]
    metric = METRICS[definition["metric"]]

    def trim(rows):
        rows = sorted(rows, key=key, reverse=descending)
        return [{k: r[k] for k in _ROW_FIELDS} for r in rows[:limit]]

    if group_by == "none":
        groups = [{"key": "All", "n": len(members),
                   "life": stats["life"], "cur": stats["cur"], "rows": trim(members)}]
    else:
        buckets: dict[str, list[dict]] = {}
        for r in members:
            buckets.setdefault(r[dimensions[group_by]], []).append(r)
        groups = [{
            "key": k,
            "n": len(rows),
            "life": sum(r[metric["life"]] for r in rows) if metric["life"] else 0,
            "cur": sum(r[metric["cur"]] for r in rows) if metric["cur"] else 0,
            "rows": trim(rows),
        } for k, rows in buckets.items()]
        groups.sort(key=lambda g: (-g["life"], -g["n"], g["key"]))

    return {
        "current_year": cur, "previous_year": prev,
        "tile": _public(definition, stats),
        "group_by": group_by, "sort": sort, "dir": "desc" if descending else "asc",
        "row_limit": limit,
        "groups": groups,
    }


VIEWS = {"overview": overview, "tile": tile}
