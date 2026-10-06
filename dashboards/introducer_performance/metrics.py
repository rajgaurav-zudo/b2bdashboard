"""Introducer performance: the read model.

This is the server-side port of the metric definitions that used to live in the
browser (see legacy/introducer-dashboard.html). Definitions are documented in
context.md; the short version of the two that trip people up:

  * The reported year is `Actual Intake Year`, literally -- the definition in
    sources/context.md. `cycle_year` is still derived at ingest (Nov/Dec roll
    into the following January) and still sits in the table, but nothing here
    reads it; switching back is a rename.
  * CUR is chosen, never assumed. The newest intake year in the export is a
    barely-started phantom, so CUR is the newest year holding at least 10% of
    the peak year's applications.
  * "Lifetime" means every intake year up to and including CUR, plus rows with
    no usable year. Rows dated after CUR are visible in the funnel table but
    score nothing, so one mistyped year cannot move a tile.
  * The filters (see `Filters`) replace CUR with an intake-month window. With no
    filters the window is the whole CUR year and every figure is as above; the
    "current year" wording in the definitions then becomes the window's label.

Nothing here is imported by core or by any other dashboard.
"""
import sys
from collections import Counter, OrderedDict
from dataclasses import dataclass, field, replace
from statistics import median

sys.path.insert(0, "/srv/api")
from app.regions import narrow, options, split  # noqa: E402
from app.views import ViewContext, ViewError  # noqa: E402

# --------------------------------------------------------------------------
# SQL
# --------------------------------------------------------------------------

# Row-level flags, shared by every query below.
#
# Two layers. `f0` carries the deposit states as they are, for every course
# category. `f` then narrows the four reported deposit flags to Academic, because
# the dashboard's deposit figures are Academic-only -- Language and pre-sessional
# are reported in their own section, from `f0`, and mixing a six-week language
# course into the same average as a three-year degree hides both.
#
# Scope is deliberately NOT narrowed: `dep_any` below still counts a deposit of
# any category, so an introducer who only ever sold language courses stays in the
# book and is visible in the course section rather than vanishing from it.
_ROWS = """
f0 as (
  select
    introducer_name                                   as name,
    intake_year, cycle_index, deposit_fully_paid, closed_lost, k_lo, k_hi,
    coalesce(course_category, 'Academic')             as course_category,
    -- the headline deposit, written as the definition writes it: a sum of two
    -- deferral states, no deferral at all and a settled one. An *approved*
    -- deferral has a decision and an intake, so it counts here; only the
    -- undecided ones move to DAA. This is an explicit sum rather than "not
    -- awaiting approval", so the (No, Yes) cell -- approved without ever being
    -- initiated, 3 rows in the 1 Sep export and none of them live -- is
    -- reported by nothing rather than folded in silently. See context.md.
    deposit_fully_paid and not closed_lost
      and ((not deferral_initiated and not deferral_approved)
        or (deferral_initiated and deferral_approved))        as dep_live,
    -- awaiting approval: initiated, and not yet decided. Disjoint from dep_live.
    deposit_fully_paid and not closed_lost
      and deferral_initiated and not deferral_approved        as daa_live,
    -- PD is disjoint from both -- a partial deposit is not fully paid.
    deposit_partial and not closed_lost               as pd_live,
    enrolled, visa_granted,
    closed_lost
      and lower(coalesce(application_status, ''))     = 'visa'
      and lower(coalesce(application_sub_status, '')) = 'applied'  as vrej,
    closed_lost
      and lower(coalesce(application_status, '')) like 'coe%%'
      and lower(coalesce(application_status, '')) like '%%receiv%%' as coe,
    -- The window flags. A row sits in a window when its whole span does: one
    -- month when the month is known, otherwise all twelve of its year, so a
    -- month-less row counts only in windows that cover its entire year. The
    -- default window is the whole CUR year, where this is `intake_year = CUR`.
    k_lo >= %(lo)s  and k_hi <= %(hi)s                  as in_cur,
    k_lo >= %(plo)s and k_hi <= %(phi)s                 as in_prev,
    k_hi < %(plo)s                                      as in_before,
    -- lifetime: up to the window's end, plus rows with no usable year
    intake_year is null or k_hi <= %(hi)s               as scored
  from applications
  cross join lateral (select
    intake_year * 12 + coalesce(intake_month_num - 1, 0)  as k_lo,
    intake_year * 12 + coalesce(intake_month_num - 1, 11) as k_hi) k
  where load_id = %(apps)s
    -- the Intake filter; a row with no cycle has no intake to match
    and (%(cycles)s::int[] is null or cycle_index = any(%(cycles)s::int[]))
),
f as (
  select *,
    dep_live  and course_category = 'Academic'                     as act,
    deposit_fully_paid and closed_lost
              and course_category = 'Academic'                     as clo,
    daa_live  and course_category = 'Academic'                     as daa,
    pd_live   and course_category = 'Academic'                     as pdep
  from f0
)
"""

# Per-introducer aggregate. "cur" is the window, "prev" the prior window and
# "life" is `scored`; the flags themselves are in `f0`.
_AGG = """
a as (
  select
    name,
    count(*) filter (where scored)                                as apps_life,
    count(*) filter (where in_cur)                                as apps_cur,
    count(*) filter (where act and scored)                        as act_life,
    count(*) filter (where act and in_cur)                        as act_cur,
    count(*) filter (where act and in_prev)                       as act_prev,
    count(*) filter (where act and in_before)                     as act_before,
    count(*) filter (where clo and scored)                        as clos_life,
    count(*) filter (where clo and in_cur)                        as clos_cur,
    count(*) filter (where enrolled and scored)                   as enr_life,
    count(*) filter (where enrolled and act and scored)           as enr_dep_life,
    count(*) filter (where visa_granted and act and scored)       as vg_dep_life,
    count(*) filter (where vrej and scored)                       as vrej_life,
    count(*) filter (where vrej and in_cur)                       as vrej_cur,
    count(*) filter (where coe and scored)                        as coe_life,
    count(*) filter (where coe and in_cur)                        as coe_cur,
    count(*) filter (where deposit_fully_paid)                    as dep_any,
    count(*) filter (where daa and in_cur)                        as daa_cur,
    count(*) filter (where pdep and in_cur)                       as pd_cur,
    -- cadence counts need a real intake year as well as a month
    count(*) filter (where act and intake_year is not null and cycle_index = 0) as cyc0,
    count(*) filter (where act and intake_year is not null and cycle_index = 1) as cyc1,
    count(*) filter (where act and intake_year is not null and cycle_index = 2) as cyc2,
    max(intake_year * 10 + cycle_index)
      filter (where act and cycle_index is not null and k_hi <= %(hi)s) as last_key
  from f
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
  coalesce(a.daa_cur, 0)   as daa_cur,   coalesce(a.pd_cur, 0) as pd_cur,
  coalesce(a.cyc0, 0) as cyc0, coalesce(a.cyc1, 0) as cyc1, coalesce(a.cyc2, 0) as cyc2,
  coalesce(a.last_key, 0) as last_key
from a
full outer join m on m.name = a.name
where (m.stage = 'Customer' or coalesce(a.dep_any, 0) > 0)
  -- the Team filter; a name missing from the CRM has no team, so is Unassigned
  and (%(teams)s::text[] is null
       or coalesce(nullif(m.team, ''), 'Unassigned') = any(%(teams)s::text[]))
"""

BOOK_SQL = f"with {_ROWS}, {_AGG}, {_MASTER} {_BOOK_SELECT}"

# Every team a row can be filed under, for turning a Region into teams. Names
# missing from the CRM have no team, so Unassigned is always one of them.
KNOWN_TEAMS_SQL = """
select distinct coalesce(nullif(srm_team, ''), 'Unassigned') as team
  from introducers where load_id = %(intro)s
union select 'Unassigned'
"""

YEAR_HIST_SQL = """
select intake_year as y, count(*) as n
  from applications
 where load_id = %(apps)s and intake_year between 1991 and 2099
 group by 1 order by 1
"""

# Funnel rows are intake-year totals, including years after CUR: the table shows
# them (flagged) so a stray future date is visible rather than silently dropped.
# The date range does not apply -- the funnel is the years side by side -- but
# Team and Intake do, to both scopes.
FUNNEL_SQL = f"""
with {_ROWS}, {_AGG}, {_MASTER},
book as ({_BOOK_SELECT})
select
  intake_year as y,
  count(*)                                        as apps,
  count(*) filter (where act)                     as act,
  count(*) filter (where clo)                     as clos,
  count(*) filter (where act and visa_granted)    as vg,
  count(*) filter (where act and enrolled)        as enr
from f
left join (select distinct on (name) name, team from m order by name) mt on mt.name = f.name
where f.intake_year is not null and f.name is not null
  and (%(scope)s = 'all' or f.name in (select name from book))
  and (%(teams)s::text[] is null
       or coalesce(nullif(mt.team, ''), 'Unassigned') = any(%(teams)s::text[]))
group by 1 order by 1
"""

# The non-Academic courses, which the deposit figures above deliberately exclude.
# Scoped to the same book, so this is the same population seen a different way and
# the two sections cannot disagree about who counts as an introducer.
COURSE_SPLIT_SQL = f"""
with {_ROWS}, {_AGG}, {_MASTER},
book as ({_BOOK_SELECT})
select
  course_category                                                     as category,
  count(*) filter (where dep_live and in_cur)                         as act_cur,
  count(*) filter (where dep_live and scored)                         as act_life,
  count(*) filter (where daa_live and in_cur)                         as daa,
  count(*) filter (where pd_live  and in_cur)                         as pd,
  count(distinct name) filter (where dep_live or daa_live or pd_live) as n
from f0
where name in (select name from book)
group by 1
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
  (select count(*) from applications where load_id = %(apps)s and intake_year is null)    as no_year,
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


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# cycle_index as ingest writes it
CYCLES = {0: "Jan", 1: "May", 2: "Sep"}


def _month_label(key: int) -> str:
    return f"{MONTHS[key % 12]} {key // 12}"


def _window_label(lo: int, hi: int) -> str:
    if lo % 12 == 0 and hi % 12 == 11:
        return str(lo // 12) if lo // 12 == hi // 12 else f"{lo // 12}–{hi // 12}"
    if lo == hi:
        return _month_label(lo)
    return f"{_month_label(lo)} – {_month_label(hi)}"


@dataclass(frozen=True)
class Filters:
    """What the page's filter bar asks for, as the SQL takes it.

    `lo` and `hi` are an inclusive intake-month window on the line
    `year * 12 + month - 1` -- intake year and month are the only dates the
    export has (sources/context.md). The prior window is the same months moved
    back whole years, as many as it takes not to overlap: one year for anything
    up to twelve months, so a comparison is always season against season.
    `teams` and `cycles` are None when not filtering; a book built with them
    simply leaves the other teams' introducers and the other intakes' rows out.
    `teams` is what Region and Team come to together, and can be empty -- a
    team picked outside the picked regions -- which keeps nobody. `picked` and
    `regions` are the two menus as asked, for the bar to show back.
    """
    lo: int
    hi: int
    teams: tuple[str, ...] | None = None
    cycles: tuple[int, ...] | None = None
    # left out of equality, so the book cache does not hold one book twice
    picked: tuple[str, ...] = field(default=(), compare=False)
    regions: tuple[str, ...] = field(default=(), compare=False)

    @property
    def shift(self) -> int:
        return 12 * -(-(self.hi - self.lo + 1) // 12)

    @property
    def end_year(self) -> int:
        return self.hi // 12

    @property
    def whole_year(self) -> bool:
        return self.lo % 12 == 0 and self.hi == self.lo + 11

    @property
    def label(self) -> str:
        return _window_label(self.lo, self.hi)

    def prior(self) -> "Filters":
        return replace(self, lo=self.lo - self.shift, hi=self.hi - self.shift)

    def params(self, ctx: ViewContext) -> dict:
        return {
            "apps": ctx.load("applications"), "intro": ctx.load("introducers"),
            "lo": self.lo, "hi": self.hi,
            "plo": self.lo - self.shift, "phi": self.hi - self.shift,
            "teams": list(self.teams) if self.teams is not None else None,
            "cycles": list(self.cycles) if self.cycles else None,
        }


def _month_key(value: str, name: str) -> int:
    try:
        year, month = (int(part) for part in value.split("-"))
    except ValueError:
        raise ViewError(f"'{name}' must be YYYY-MM, got '{value}'") from None
    if not (1991 <= year <= 2099 and 1 <= month <= 12):
        raise ViewError(f"'{name}' is out of range: '{value}'")
    return year * 12 + month - 1


def _scope(ctx: ViewContext, params: dict) -> tuple[int, int, list[dict], Filters]:
    """CUR as always, and the filters the request asks for.

    With no `from`/`to` the window is the whole CUR year, which is the
    unfiltered dashboard exactly. Query parameters arrive as strings:
    `from`/`to` as YYYY-MM, `teams` and `regions` joined with `|` (team names
    hold commas), `cycles` as cycle indexes joined with commas.
    """
    cur, prev, hist = _years(ctx)
    lo = _month_key(params["from"], "from") if params.get("from") else cur * 12
    hi = _month_key(params["to"], "to") if params.get("to") else cur * 12 + 11
    if lo > hi:
        lo, hi = hi, lo

    picked = tuple(sorted(set(split(params.get("teams")))))
    regions = tuple(sorted(set(split(params.get("regions")))))
    known = [r["team"] for r in ctx.rows(KNOWN_TEAMS_SQL, {"intro": ctx.load("introducers")})] \
        if regions else []
    teams = narrow(list(picked), list(regions), known)

    cycles: set[int] = set()
    for part in (params.get("cycles") or "").split(","):
        if not part.strip():
            continue
        if not part.strip().isdigit() or int(part) not in CYCLES:
            raise ViewError(f"unknown intake '{part.strip()}' (have: 0=Jan, 1=May, 2=Sep)")
        cycles.add(int(part))
    # every intake selected is no filter at all; kept as a filter, it would
    # drop the rows whose month could not be read
    if cycles == set(CYCLES):
        cycles = set()

    return cur, prev, hist, Filters(lo, hi, None if teams is None else tuple(teams),
                                    tuple(sorted(cycles)) or None, picked, regions)


def _period(flt: Filters, cur: int) -> dict:
    prior = flt.prior()
    return {
        "from": f"{flt.lo // 12}-{flt.lo % 12 + 1:02d}",
        "to": f"{flt.hi // 12}-{flt.hi % 12 + 1:02d}",
        "label": flt.label,
        "prior_label": prior.label,
        "end_year": flt.end_year,
        "whole_year": flt.whole_year,
        "is_default": flt.lo == cur * 12 and flt.hi == cur * 12 + 11,
    }


def _wants_compare(params: dict) -> bool:
    return str(params.get("compare") or "").lower() in ("1", "true", "yes")


# Every view here starts from the same book, and fetching it is by far the most
# expensive thing this module does: ~7k rows and ~2.5MB, which is 2.8s across a
# link to another region. Cached on the loads it was built from, so the overview
# and all thirteen tile drill-downs share one fetch instead of paying for their
# own. Keyed on the filters as well: a filtered page and its comparison need two
# books, and the team counts the unfiltered one, so eight entries leaves room for
# a few filter changes and a rollback in flight.
_BOOK_CACHE: "OrderedDict[tuple, list[dict]]" = OrderedDict()
_BOOK_CACHE_MAX = 8


def _book(ctx: ViewContext, flt: Filters) -> list[dict]:
    key = (ctx.load("applications"), ctx.load("introducers"), flt)
    if (hit := _BOOK_CACHE.get(key)) is not None:
        _BOOK_CACHE.move_to_end(key)
        return hit

    rows = _load_book(ctx, flt)
    _BOOK_CACHE[key] = rows
    while len(_BOOK_CACHE) > _BOOK_CACHE_MAX:
        _BOOK_CACHE.popitem(last=False)
    return rows


def _load_book(ctx: ViewContext, flt: Filters) -> list[dict]:
    rows = ctx.rows(BOOK_SQL, flt.params(ctx))
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


def tile_defs(flt: Filters) -> list[dict]:
    # Cohorts count back from the year the window ends in. "cur" in the wording
    # is the window's label: a year on the default page, a range otherwise.
    cur, prev = flt.end_year, flt.end_year - 1
    now, before = flt.label, flt.prior().label
    period = f"the {now} intake year" if flt.whole_year else f"the {now} intake window"

    def cohort(year, name, definition):
        return {
            "id": f"coh{year}", "section": "active", "name": name, "definition": definition,
            "metric": "act", "head": "cur",
            "member": lambda r, y=year: r["is_active"] and r["became_y"] == y,
        }

    return [
        {"id": "active", "section": "active", "name": "Active", "metric": "act", "head": "cur",
         "definition": f"At least one active deposit in {period}.",
         "member": lambda r: r["is_active"], "book_states": True},
        cohort(cur, f"Became customer {cur}", f"Active, and first became a customer in {cur}."),
        cohort(prev, f"Became customer {prev}", f"Active, and became a customer in {prev}."),
        cohort(cur - 2, f"Became customer {cur - 2}", f"Active, and became a customer in {cur - 2}."),
        {"id": "cohOld", "section": "active", "name": f"Became customer ≤{cur - 3}",
         "metric": "act", "head": "cur",
         "definition": f"Active, and became a customer in {cur - 3} or earlier.",
         "member": lambda r: r["is_active"] and r["became_y"] is not None and r["became_y"] <= cur - 3},
        {"id": "resurrected", "section": "active", "name": "Resurrected", "metric": "act",
         "head": "cur", "invert": True,
         "definition": f"Deposits in {now}, none in {before}, but deposits before that. Win-backs that landed.",
         "member": lambda r: r["is_resurrected"]},

        {"id": "dormant", "section": "leak", "name": "Dormant", "metric": "act", "head": "life",
         "definition": (f"Paid deposits in an earlier year, none in {now}. This is the call list."
                        if flt.whole_year else
                        f"Paid deposits on record, none in {now}. This is the call list."),
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
    states = book if tile.get("book_states") else members
    metric = METRICS[tile["metric"]]
    life = sum(r[metric["life"]] for r in members) if metric["life"] else 0
    now = sum(r[metric["cur"]] for r in members) if metric["cur"] else 0
    contracts = [str(r["contract"] or "").lower() for r in members]
    return members, {
        "n": len(members), "life": life, "cur": now,
        "contract_active": contracts.count("active"),
        "contract_expired": contracts.count("expired"),
        # Reported beside every tile regardless of its metric: the deposit states
        # are a property of the members, not of what the tile happens to count.
        #
        # The Active tile is the exception, and asks for the book. Its deposit
        # figure is already every active deposit in CUR -- an introducer holding
        # one is a member by definition -- but DAA and PD are not, because a
        # partner whose only current-year money is an awaiting-approval deposit
        # never becomes a member, and that money vanished off the card. Summing
        # those two over the book makes all three numbers describe one
        # population. Cohort tiles stay member-scoped: they are statements about
        # a subset of partners, and the book figure would be the same on each.
        "daa": sum(r["daa_cur"] for r in states),
        "pd": sum(r["pd_cur"] for r in states),
    }


def _public(tile: dict, stats: dict) -> dict:
    out = {k: v for k, v in tile.items() if k not in ("member", "book_states")}
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


_TOTALS = ("act_life", "clos_life", "apps_life", "act_cur", "clos_cur", "enr_life")


def _totals(book: list[dict]) -> dict:
    return {k: sum(r[k] for r in book) for k in _TOTALS}


def _compare(ctx: ViewContext, flt: Filters, definitions: list[dict]) -> dict:
    """The same page for the prior window: same filters, months a year back.

    Keyed by the current tile ids. Cohort tiles are matched by position, so
    "Became customer 2026" is compared with "Became customer 2025" a year
    earlier -- the newest cohort against the newest cohort.
    """
    prior = flt.prior()
    book = _book(ctx, prior)
    tiles = {}
    for now, then in zip(definitions, tile_defs(prior)):
        tiles[now["id"]] = tile_stats(then, book)[1]
    return {"label": prior.label, "book_size": len(book), "totals": _totals(book), "tiles": tiles}


def overview(ctx: ViewContext, params: dict):
    cur, prev, hist, flt = _scope(ctx, params)
    book = _book(ctx, flt)
    sql = flt.params(ctx)

    # every category, Academic included: the page shows the others, but a
    # category nobody expected (Unspecified) must be visible rather than dropped
    course_split = ctx.rows(COURSE_SPLIT_SQL, sql)
    course_split.sort(key=lambda r: -r["act_cur"])

    definitions = tile_defs(flt)
    tiles = []
    for tile in definitions:
        _, stats = tile_stats(tile, book)
        tiles.append(_public(tile, stats))

    totals = _totals(book)

    # the Region and Team options, counted without either filter so every team
    # stays pickable while some are picked
    team_counts = Counter(r["team"] for r in (book if flt.teams is None
                                              else _book(ctx, replace(flt, teams=None))))

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
        "period": _period(flt, cur),
        "filters": {"teams": list(flt.picked), "regions": list(flt.regions),
                    "cycles": list(flt.cycles or ())},
        **dict(zip(("team_options", "region_options"),
                   options([{"team": t, "n": n} for t, n in sorted(team_counts.items())]))),
        "compare": _compare(ctx, flt, definitions) if _wants_compare(params) else None,
        "year_histogram": hist,
        "book_size": len(book),
        "totals": totals,
        "tiles": tiles,
        "by_stage": sorted(by_stage.values(), key=lambda s: -s["act"]),
        "cadence": sorted(cadence_list, key=lambda c: -c["act"]),
        "funnel": {
            "scope": ctx.rows(FUNNEL_SQL, {**sql, "scope": "scope"}),
            "all": ctx.rows(FUNNEL_SQL, {**sql, "scope": "all"}),
        },
        "course_split": course_split,
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
    cur, prev, _, flt = _scope(ctx, params)
    definitions = {t["id"]: t for t in tile_defs(flt)}
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

    book = _book(ctx, flt)
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
        "period": _period(flt, cur),
        "tile": _public(definition, stats),
        "group_by": group_by, "sort": sort, "dir": "desc" if descending else "asc",
        "row_limit": limit,
        "groups": groups,
    }


def members(ctx: ViewContext, params: dict):
    """Every introducer in one tile, unaggregated.

    The pane groups, sorts and expands client-side the way the single-file
    version did, so switching tab or opening a group costs no round trip. The
    largest tile is ~3.5k rows, which is well inside what one payload can carry.
    """
    tile_id = params.get("id")
    cur, prev, _, flt = _scope(ctx, params)
    definitions = {t["id"]: t for t in tile_defs(flt)}
    if tile_id not in definitions:
        raise ViewError(f"unknown tile '{tile_id}' (have: {', '.join(definitions)})")

    definition = definitions[tile_id]
    rows, stats = tile_stats(definition, _book(ctx, flt))

    by_stage: dict[str, dict] = {}
    for row in rows:
        bucket = by_stage.setdefault(row["stage"], {"stage": row["stage"], "n": 0, "act": 0, "clos": 0})
        bucket["n"] += 1
        bucket["act"] += row["act_life"]
        bucket["clos"] += row["clos_life"]

    return {
        "current_year": cur, "previous_year": prev,
        "period": _period(flt, cur),
        "tile": _public(definition, stats),
        "by_stage": sorted(by_stage.values(), key=lambda b: -b["n"]),
        "rows": [{k: r[k] for k in _ROW_FIELDS} for r in rows],
    }


VIEWS = {"overview": overview, "tile": tile, "members": members}
