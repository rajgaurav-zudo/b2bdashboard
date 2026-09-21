"""Introducer 360: the read model.

The dashboard is one question asked three ways -- what did this introducer put
into the pipeline, what came out of it, and how does that compare with the same
window a year ago. Everything on the page is a function of four filters:
introducer, date range, intake, and whether Compare is on.

Three things are worth knowing before reading the SQL:

  * **A stage is an event, not a status.** `Applied` is not "applications whose
    status is Applied today"; it is applications that *entered* Applied inside
    the window, read off `at_applied`. That is what makes a date range mean
    anything here, and it is why an application appears in several stages: it
    passed through them.
  * **Created = active + closed, always.** Within one stage and one window,
    `created` is every application that entered it, `active` the ones not closed
    lost, `closed` the ones that were. The two halves are a partition of the
    same count, which is what lets every percentage on the page be read against
    the number above it.
  * **"Today" is the export's newest date, not the clock's.** Presets are
    anchored on the last stage event in the file. An export taken on Sunday
    would otherwise open on a week that has not happened yet and read as a
    collapse -- the same trap the log dashboard's `pick_current_week` avoids.

Nothing here is imported by core or by any other dashboard.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, "/srv/api")
from app.views import ViewContext, ViewError  # noqa: E402

TOP_INTRODUCERS = 8          # the leaderboard under the pipeline
MENU_INTRODUCERS = 60        # what the counsellor-style picker lists at once
WISE_ROWS = 25               # rows in the introducer-wise table when nothing is selected

# --------------------------------------------------------------------------
# the pipeline
# --------------------------------------------------------------------------
#
# Eleven stages in funnel order, of two kinds.
#
# Nine are **events**: `date` is the column saying when an application entered
# the stage, and the window filters on it.
#
# Two are **states**. The CRM records a partial deposit and an initiated deferral
# as flags, not as transitions -- there is no timestamp for either -- so they
# cannot be windowed at all. They are reported as they stand in the export, and
# the card says so. Narrowing them by a date range would mean picking some other
# column's date to stand in for theirs, which is inventing a fact; leaving them
# out would drop the two states the platform already treats as first class (see
# sources/context.md). They still answer to the introducer and intake filters,
# which is where the useful question is -- "this partner's partial deposits in
# the 2026 intake" -- and Compare leaves them alone, because a state has no
# last year to be compared with.
STAGES = [
    {"id": "draft",        "name": "Draft",           "kind": "event", "date": "at_draft",        "extra": "", "group": None},
    {"id": "ready",        "name": "Ready to apply",  "kind": "event", "date": "at_ready",        "extra": "", "group": None},
    {"id": "applied",      "name": "Applied",         "kind": "event", "date": "at_applied",      "extra": "", "group": None},
    {"id": "offer",        "name": "Offer",           "kind": "event", "date": "at_offer",        "extra": "", "group": None},
    {"id": "deposit",      "name": "Deposit paid",    "kind": "event", "date": "at_deposit",      "extra": "", "group": "deposits"},
    {"id": "coe",          "name": "CoE received",    "kind": "event", "date": "at_coe",          "extra": "", "group": "deposits"},
    {"id": "visa_applied", "name": "Visa applied",    "kind": "event", "date": "at_visa_applied", "extra": "", "group": "deposits"},
    {"id": "visa_granted", "name": "Visa granted",    "kind": "event", "date": "at_visa_granted", "extra": "", "group": None},
    {"id": "enrolled",     "name": "Enrolled",        "kind": "event", "date": "at_enrolled",     "extra": "", "group": None},
    {"id": "partial",      "name": "Partial deposit", "kind": "state", "date": None,
     "extra": "deposit_partial", "group": "awaiting"},
    {"id": "deferral",     "name": "Deferral awaiting approval", "kind": "state", "date": None,
     "extra": "deposit_fully_paid and deferral_initiated and not deferral_approved",
     "group": "awaiting"},
]

EVENTS = [s for s in STAGES if s["kind"] == "event"]
EVENT_IDS = {s["id"] for s in EVENTS}

# The eight widgets. A group is the sum of its members' events, not a count of
# distinct applications: an application that paid a deposit, received a CoE and
# applied for a visa inside the window entered three stages and is counted three
# times, exactly as it would be on three separate cards. The breakdown modal is
# where that stops being an assertion and becomes visible.
GROUPS = {
    "deposits": {
        "id": "deposits", "name": "Deposits",
        "sub": "Deposit paid, CoE received and Visa applied",
    },
    "awaiting": {
        "id": "awaiting", "name": "Awaiting outcome",
        "sub": "Partial deposits and deferrals awaiting approval",
    },
}

# The order the eight cards are drawn in: a stage id, or a group id.
WIDGETS = ["draft", "ready", "applied", "offer", "deposits", "visa_granted", "enrolled", "awaiting"]

CYCLES = [(0, "Jan"), (1, "May"), (2, "Sep")]

# --------------------------------------------------------------------------
# SQL
# --------------------------------------------------------------------------

# Everything below reads from this, and only this. The filters are applied once,
# here, so no view can accidentally answer for a different population than the
# card beside it.
_BASE = """
base as (
  select *
    from applications
   where load_id = %(load)s
     and (%(all_intro)s or introducer_name = any(%(names)s))
     and (%(iy)s = 0  or intake_year  = %(iy)s)
     and (%(ic)s = -1 or cycle_index  = %(ic)s)
)
"""


def _stage_aggregates(prefix: str, window: str) -> str:
    """`created`, `active` and `closed` for every stage over one window.

    Generated rather than written out because eleven stages times three figures
    times two windows is sixty-six aggregates, and sixty-six hand-written
    `count(*) filter` clauses is sixty-six chances to paste the wrong column in.
    """
    out = []
    for stage in STAGES:
        if stage["kind"] == "state":
            if prefix:                       # a state has no previous window
                continue
            where = stage["extra"]
        else:
            where = f"{stage['date']} between %({window}f)s and %({window}t)s"
        out.append(f"count(*) filter (where {where}) as {prefix}{stage['id']}_created")
        out.append(f"count(*) filter (where {where} and not closed_lost) as {prefix}{stage['id']}_active")
        out.append(f"count(*) filter (where {where} and closed_lost) as {prefix}{stage['id']}_closed")
    return ",\n  ".join(out)


# The same population *without* the intake filter. The intake commitment panel
# compares one intake year with the one before it, so it cannot be run inside a
# base that has already narrowed to a single intake -- it would be comparing a
# year with itself and reporting zero.
_BASE_ALL_INTAKES = """
base as (
  select *
    from applications
   where load_id = %(load)s
     and (%(all_intro)s or introducer_name = any(%(names)s))
)
"""

PIPELINE_SQL = f"""
with {_BASE}
select
  {_stage_aggregates('', 'r')},
  {_stage_aggregates('p_', 'p')}
from base
"""

# Rank by everything the window produced, not by one stage: a partner whose
# week was four offers and no deposit still belongs at the top of a week's table.
_WISE_ORDER = " + ".join(
    f"count(*) filter (where {s['date']} between %(rf)s and %(rt)s)" for s in EVENTS
)

# The introducer-wise table, and the leaderboard under the pipeline: the same
# aggregates again, this time per partner. Ordered by what the window actually
# produced, so the table opens on the partners the filters are about.
WISE_SQL = f"""
with {_BASE}
select
  coalesce(nullif(introducer_name, ''), 'Not attributed') as name,
  count(*) filter (where at_entered between %(rf)s and %(rt)s) as entered,
  {_stage_aggregates('', 'r')}
from base
group by 1
order by {_WISE_ORDER} desc, name
limit %(limit)s
"""

# The anchor: the newest stage event anywhere in the file. Not the server clock
# -- see the module docstring. `first` is the oldest, where All time starts.
ANCHOR_SQL = f"""
select max(greatest({', '.join(s['date'] for s in EVENTS)})) as anchor,
       min(least({', '.join(s['date'] for s in EVENTS)}))    as first
  from applications where load_id = %(load)s
"""

# What the intake menu offers. The file's own years, and the three cycles within
# whichever year is selected, with counts -- so picking one cannot land on an
# empty page without warning.
INTAKE_SQL = """
select intake_year as y, count(*) as n
  from applications
 where load_id = %(load)s and intake_year between 1991 and 2099
 group by 1 order by 1 desc
"""

CYCLE_SQL = """
select cycle_index as i, count(*) as n
  from applications
 where load_id = %(load)s and intake_year = %(iy)s and cycle_index is not null
 group by 1 order by 1
"""

# The picker. Counts are lifetime, not windowed: a partner who did nothing this
# week is exactly the one someone opens this dashboard to look at.
MENU_SQL = """
select coalesce(nullif(introducer_name, ''), 'Not attributed') as name,
       count(*) as n,
       count(*) filter (where deposit_fully_paid and not closed_lost) as deposits
  from applications
 where load_id = %(load)s
   and (%(q)s = '' or introducer_name ilike %(like)s)
 group by 1
 order by n desc, name
 limit %(limit)s
"""

# The 360 half: who this partner is, from the master file, and what they have
# done over their whole life rather than inside the window.
PROFILE_SQL = """
select
  coalesce(nullif(m.lifecycle_stage, ''), 'Unknown')          as stage,
  coalesce(nullif(m.latest_contract_status, ''), 'Unknown')   as contract,
  coalesce(nullif(m.country, ''), 'Unknown')                  as country,
  coalesce(nullif(m.srm_team, ''), 'Unassigned')              as team,
  coalesce(nullif(m.srm_owner, ''), 'Unassigned')             as srm,
  m.became_customer_year                                      as since
from introducers m
where m.load_id = %(intro)s and m.partner_name = %(name)s
"""

LIFETIME_SQL = f"""
with {_BASE}
select
  count(*)                                                        as apps,
  count(*) filter (where at_applied is not null)                  as applied,
  count(*) filter (where at_offer is not null)                    as offers,
  count(*) filter (where deposit_fully_paid and not closed_lost)  as deposits_live,
  count(*) filter (where at_enrolled is not null)                 as enrolled,
  count(*) filter (where closed_lost)                             as lost,
  min(at_entered)                                                 as first_seen,
  max(greatest(at_draft, at_ready, at_applied, at_offer, at_deposit,
               at_coe, at_visa_applied, at_visa_granted, at_enrolled)) as last_seen
from base
"""

# Deposits paid for the selected intake, against the same point in the intake a
# year earlier. `to_char` is not used: the comparison is on day-of-year, so a
# partial year is compared with a partial year.
COMMITMENT_SQL = f"""
with {_BASE_ALL_INTAKES}
select
  count(*) filter (where intake_year = %(iy_now)s
                     and deposit_fully_paid and not closed_lost)   as now_paid,
  count(*) filter (where intake_year = %(iy_now)s)                 as now_apps,
  count(*) filter (where intake_year = %(iy_prev)s
                     and deposit_fully_paid and not closed_lost
                     and at_deposit <= %(cut)s)                    as prev_paid_to_date,
  count(*) filter (where intake_year = %(iy_prev)s
                     and deposit_fully_paid and not closed_lost)   as prev_paid_total
from base
"""

NOTES_SQL = """
select
  (select count(*) from applications where load_id = %(load)s)                    as app_rows,
  (select count(*) from applications where load_id = %(load)s
     and at_entered is null)                                                      as no_stage_dates,
  (select count(*) from applications where load_id = %(load)s
     and introducer_name is null)                                                 as no_introducer,
  (select count(*) from applications where load_id = %(load)s
     and deposit_fully_paid and at_deposit is null)                               as paid_without_date,
  (select count(*) from applications where load_id = %(load)s and intake_year is null) as no_intake_year,
  (select count(*) from introducers where load_id = %(intro)s)                    as master_rows
"""

# --------------------------------------------------------------------------
# filters
# --------------------------------------------------------------------------

PRESETS = ["today", "yesterday", "this_week", "last_week",
           "this_month", "last_month", "this_year", "all_time", "custom"]
PRESET_LABELS = {
    "today": "Today", "yesterday": "Yesterday", "this_week": "This week",
    "last_week": "Last week", "this_month": "This month", "last_month": "Last month",
    "this_year": "This year", "all_time": "All time", "custom": "Custom",
}
DEFAULT_PRESET = "this_week"


def week_start(day: date) -> date:
    """Monday. The calendar in the design starts its weeks on Monday, and a
    range filter whose weeks disagree with the calendar that picks them is a
    bug people find by arithmetic rather than by reading."""
    return day - timedelta(days=day.weekday())


def resolve_preset(name: str, anchor: date, first: date | None = None) -> tuple[date, date]:
    """A preset's window, measured from the export's newest stage event.

    `all_time` is the date range removed: the file's first stage event to its
    last, so it is still a window -- the queries, the calendar and Compare all
    keep working -- it just holds every dated event."""
    if name == "today":
        return anchor, anchor
    if name == "yesterday":
        return anchor - timedelta(days=1), anchor - timedelta(days=1)
    if name == "this_week":
        start = week_start(anchor)
        return start, start + timedelta(days=6)
    if name == "last_week":
        start = week_start(anchor) - timedelta(days=7)
        return start, start + timedelta(days=6)
    if name == "this_month":
        start = anchor.replace(day=1)
        return start, _month_end(start)
    if name == "last_month":
        start = (anchor.replace(day=1) - timedelta(days=1)).replace(day=1)
        return start, _month_end(start)
    if name == "this_year":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    if name == "all_time":
        return (first or anchor), anchor
    raise ViewError(f"unknown date range '{name}' (have: {', '.join(PRESETS)})")


def _month_end(first: date) -> date:
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def last_year(day: date) -> date:
    """The same calendar date a year earlier. 29 February has no counterpart, so
    it falls back to the 28th rather than raising on one day in four years."""
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def _iso(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ViewError(f"{field} is not a date: '{value}'") from exc


def _range(params: dict, anchor: date, first: date | None = None) -> dict:
    """The window on screen. `from`/`to` win over `range`; a preset is resolved
    against the anchor so the label and the dates can never disagree."""
    start_raw, end_raw = params.get("from"), params.get("to")
    if start_raw and end_raw:
        start, end = _iso(start_raw, "from"), _iso(end_raw, "to")
        if end < start:
            start, end = end, start
        return {"id": "custom", "label": _range_label(start, end), "from": start, "to": end}

    preset = params.get("range") or DEFAULT_PRESET
    if preset == "custom":                       # custom with no dates yet
        preset = DEFAULT_PRESET
    start, end = resolve_preset(preset, anchor, first)
    return {"id": preset, "label": PRESET_LABELS[preset], "from": start, "to": end}


def _range_label(start: date, end: date) -> str:
    fmt = "%-d %b"
    if start == end:
        return f"{start.strftime(fmt)} {start.year}"
    if start.year == end.year:
        return f"{start.strftime(fmt)} – {end.strftime(fmt)} {end.year}"
    return f"{start.strftime(fmt)} {start.year} – {end.strftime(fmt)} {end.year}"


def _names(params: dict) -> list[str]:
    """Selected introducers. Pipe-separated, because a partner name may hold a
    comma ('Global Connect Travel, Ltd') and cannot hold a pipe."""
    raw = params.get("introducers") or ""
    return [name.strip() for name in raw.split("|") if name.strip()]


def _intake(params: dict) -> tuple[int, int]:
    year = params.get("intake_year") or ""
    cycle = params.get("intake_cycle")
    try:
        y = int(year) if year not in ("", None) else 0
        c = int(cycle) if cycle not in ("", None) else -1
    except (TypeError, ValueError) as exc:
        raise ViewError("intake_year and intake_cycle must be numbers") from exc
    if c != -1 and c not in (0, 1, 2):
        raise ViewError("intake_cycle is 0 (Jan), 1 (May) or 2 (Sep)")
    if c != -1 and not y:
        raise ViewError("an intake cycle needs an intake year")
    return y, c


def _scope(ctx: ViewContext, params: dict) -> dict:
    """Every filter, resolved once. Everything downstream reads this."""
    load = ctx.load("applications")
    row = ctx.one(ANCHOR_SQL, {"load": load}) or {}
    anchor = row.get("anchor")
    if anchor is None:
        raise ViewError(
            "no stage timestamps in the applications file -- this dashboard reads the "
            "'Timestamp of ...' columns, and the loaded export carries none of them"
        )

    names = _names(params)
    intake_year, intake_cycle = _intake(params)
    first = row.get("first")
    window = _range(params, anchor, first)
    return {
        "load": load, "anchor": anchor, "first": first, "names": names, "range": window,
        "intake_year": intake_year, "intake_cycle": intake_cycle,
        "compare": (params.get("compare") or "") in ("1", "true", "yes"),
    }


def _sql_params(scope: dict, **extra) -> dict:
    """The bind parameters `_BASE` and the aggregates need."""
    window = scope["range"]
    params = {
        "load": scope["load"],
        "all_intro": not scope["names"],
        "names": scope["names"] or [""],
        "iy": scope["intake_year"], "ic": scope["intake_cycle"],
        "rf": window["from"], "rt": window["to"],
        "pf": last_year(window["from"]), "pt": last_year(window["to"]),
    }
    params.update(extra)
    return params


def _scope_label(scope: dict) -> str:
    names = scope["names"]
    if not names:
        who = "All introducers"
    elif len(names) == 1:
        who = names[0]
    else:
        who = f"{len(names)} introducers"
    parts = [who, scope["range"]["label"]]
    if scope["intake_year"]:
        intake = str(scope["intake_year"])
        if scope["intake_cycle"] != -1:
            intake = f"{dict(CYCLES)[scope['intake_cycle']]} {intake}"
        parts.append(f"Intake: {intake}")
    return " · ".join(parts)


# --------------------------------------------------------------------------
# shaping
# --------------------------------------------------------------------------

def _cell(created: int, active: int, closed: int) -> dict:
    return {
        "created": created, "active": active, "closed": closed,
        "active_pct": round(100 * active / created) if created else 0,
        "closed_pct": round(100 * closed / created) if created else 0,
    }


def _stage_rows(row: dict, compare: bool) -> list[dict]:
    out = []
    for stage in STAGES:
        cell = _cell(row[f"{stage['id']}_created"], row[f"{stage['id']}_active"],
                     row[f"{stage['id']}_closed"])
        cell.update(id=stage["id"], name=stage["name"], group=stage["group"],
                    kind=stage["kind"])
        if compare and stage["kind"] == "event":
            cell["previous"] = _cell(row[f"p_{stage['id']}_created"],
                                     row[f"p_{stage['id']}_active"],
                                     row[f"p_{stage['id']}_closed"])
            cell["delta"] = _delta(cell["created"], cell["previous"]["created"])
        out.append(cell)
    return out


def _delta(now: int, before: int) -> float | None:
    """Percentage change against last year. None rather than infinity when there
    was nothing to compare with -- a card that says '+∞%' says nothing."""
    if not before:
        return None
    return round(100 * (now - before) / before, 1)


def _widgets(stages: list[dict], compare: bool) -> list[dict]:
    by_id = {s["id"]: s for s in stages}
    cards = []
    for widget in WIDGETS:
        if widget in by_id:
            card = dict(by_id[widget])
            card["members"] = []
            card["windowed"] = card["kind"] == "event"
            cards.append(card)
            continue

        group = GROUPS[widget]
        members = [dict(by_id[s["id"]]) for s in STAGES if s["group"] == widget]
        card = _cell(*(sum(m[k] for m in members) for k in ("created", "active", "closed")))
        card.update(id=group["id"], name=group["name"], sub=group["sub"],
                    kind="group", group=None, members=members,
                    # a group whose members are all states is itself a state, and
                    # the card has to say "as of" rather than name a window
                    windowed=any(m["kind"] == "event" for m in members))
        comparable = [m for m in members if "previous" in m]
        if compare and comparable:
            previous = _cell(*(sum(m["previous"][k] for m in comparable)
                               for k in ("created", "active", "closed")))
            card["previous"] = previous
            # a group whose members are all states has nothing to compare, and a
            # mixed group would be comparing part of itself with all of itself
            card["delta"] = (_delta(sum(m["created"] for m in comparable),
                                    previous["created"])
                             if len(comparable) == len(members) else None)
        cards.append(card)
    return cards


def _wise_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        cells = [dict(_cell(row[f"{s['id']}_created"], row[f"{s['id']}_active"],
                            row[f"{s['id']}_closed"]), id=s["id"]) for s in STAGES]
        out.append({"name": row["name"], "entered": row["entered"], "cells": cells,
                    "total": _event_total(cells)})
    return out


def _event_total(cells: list[dict]) -> dict:
    """The row total counts stages entered inside the window, and nothing else.

    The two states are reported as they stand in the export rather than over the
    window, so adding them to a windowed total would produce a number that is
    part one week and part all time -- and it would move when the window did not.
    """
    events = [c for c in cells if c["id"] in EVENT_IDS]
    return _cell(*(sum(c[k] for c in events) for k in ("created", "active", "closed")))


# --------------------------------------------------------------------------
# views
# --------------------------------------------------------------------------

def overview(ctx: ViewContext, params: dict):
    scope = _scope(ctx, params)
    sql = _sql_params(scope)

    row = ctx.one(PIPELINE_SQL, sql) or {}
    stages = _stage_rows(row, scope["compare"])
    widgets = _widgets(stages, scope["compare"])

    years = ctx.rows(INTAKE_SQL, {"load": scope["load"]})
    cycles = []
    if scope["intake_year"]:
        counts = {r["i"]: r["n"] for r in ctx.rows(
            CYCLE_SQL, {"load": scope["load"], "iy": scope["intake_year"]})}
        cycles = [{"i": i, "label": f"{label} {scope['intake_year']}", "n": counts.get(i, 0)}
                  for i, label in CYCLES]

    # the leaderboard: who produced the window. Doubles as the way in -- with no
    # introducer selected this is the only list on the page that names one.
    top = _wise_rows(ctx.rows(WISE_SQL, _sql_params(scope, limit=TOP_INTRODUCERS)))

    lifetime = ctx.one(LIFETIME_SQL, sql) or {}
    # The master file is what makes this a 360 rather than a pipeline, but the
    # pipeline is readable without it: a null load id matches no rows, so an
    # unloaded master costs the profile card and nothing else.
    master = ctx.loads.get("introducers")
    profile = (ctx.one(PROFILE_SQL, {"intro": master, "name": scope["names"][0]})
               if len(scope["names"]) == 1 else None)

    intake_now = scope["intake_year"] or max((r["y"] for r in years), default=scope["anchor"].year)
    commitment = ctx.one(COMMITMENT_SQL, _sql_params(
        scope, iy_now=intake_now, iy_prev=intake_now - 1, cut=last_year(scope["anchor"]))) or {}
    commitment["intake_year"] = intake_now

    notes = ctx.one(NOTES_SQL, {"load": scope["load"], "intro": master}) or {}

    window = scope["range"]
    return {
        "anchor": scope["anchor"],
        "scope_line": _scope_label(scope),
        "selected": scope["names"],
        "compare": scope["compare"],
        "range": {**window, "presets": [
            {"id": p, "label": PRESET_LABELS[p],
             **(dict(zip(("from", "to"), resolve_preset(p, scope["anchor"], scope["first"]))) if p != "custom" else {})}
            for p in PRESETS
        ]},
        "previous_range": {
            "from": last_year(window["from"]), "to": last_year(window["to"]),
            "label": _range_label(last_year(window["from"]), last_year(window["to"])),
        },
        "intake": {"year": scope["intake_year"] or None,
                   "cycle": None if scope["intake_cycle"] == -1 else scope["intake_cycle"],
                   "years": years, "cycles": cycles},
        "stages": stages,
        "widgets": widgets,
        "groups": list(GROUPS.values()),
        "top": top,
        "lifetime": lifetime,
        "profile": profile,
        "commitment": commitment,
        "data": notes,
    }


def introducers(ctx: ViewContext, params: dict):
    """The picker's list. Searchable, because there are 3,605 of them."""
    query = (params.get("q") or "").strip()
    limit = max(1, min(int(params.get("limit") or MENU_INTRODUCERS), 200))
    rows = ctx.rows(MENU_SQL, {
        "load": ctx.load("applications"),
        "q": query, "like": f"%{query}%", "limit": limit,
    })
    return {"q": query, "limit": limit, "rows": rows}


def introducer_wise(ctx: ViewContext, params: dict):
    """The wide modal: every stage, per introducer, over the same window.

    With introducers selected it is those introducers. With none, it is the
    partners the window actually belongs to, ranked -- which is the same table
    the design's counsellor-wise view is, against a book that has three thousand
    partners rather than seven counsellors.
    """
    scope = _scope(ctx, params)
    limit = len(scope["names"]) or max(1, min(int(params.get("limit") or WISE_ROWS), 200))
    rows = _wise_rows(ctx.rows(WISE_SQL, _sql_params(scope, limit=limit)))

    totals = ctx.one(PIPELINE_SQL, _sql_params(scope)) or {}
    all_stages = _stage_rows(totals, False)
    return {
        "scope_line": _scope_label(scope),
        "range": scope["range"],
        "stage_names": [{"id": s["id"], "name": s["name"]} for s in STAGES],
        "rows": rows,
        "row_limit": limit,
        "totals": {"cells": all_stages, "total": _event_total(all_stages)},
    }


VIEWS = {"overview": overview, "introducers": introducers, "introducer_wise": introducer_wise}
