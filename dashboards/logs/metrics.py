"""Log dashboard: the read model.

Definitions are documented in context.md; the three that trip people up:

  * A week runs Saturday -> Friday. `week_start` is the Saturday, decided at
    ingest so every query buckets identically.
  * The selected week defaults to the newest week in the file that has already
    begun. Not max(week): an export taken mid-week would otherwise anchor on a
    week that is two days old and read as a collapse in activity.
  * Change (Δ wk) always compares the selected week with the week immediately
    before it, whatever range the tables are showing.

Filters: `team` narrows everything, because a team's page should be a team's
page. It takes several teams at once -- the regional SRM teams are read together
as often as alone, and asking for West Africa 1 and West Africa 2 separately
gives two halves of a number nobody wants halved. `type` narrows only the tables
and the sentiment index -- the week KPIs and the week-on-week chart are *by* log
type, and filtering them to one type would leave a single bar and eleven empty
ones.

Nothing here is imported by core or by any other dashboard.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, "/srv/api")
from app.regions import narrow, options, split  # noqa: E402
from app.views import ViewContext, ViewError  # noqa: E402

DEFAULT_TABLE_WEEKS = 8      # "last 2 months", ending with the selected week
DEFAULT_CHART_WEEKS = 10
DEFAULT_TOP_N = 10
QUOTES = 3

# --------------------------------------------------------------------------
# SQL
# --------------------------------------------------------------------------

WEEKS_SQL = """
select week_start as w, count(*) as n
  from logs
 where load_id = %(load)s
 group by 1 order by 1
"""

# The filter menus list what the file holds, not what the selected week happens
# to contain: a type that vanished this week is exactly what someone wants to
# filter to.
TYPES_SQL = """
select coalesce(nullif(log_type, ''), 'Unspecified') as type, count(*) as n
  from logs
 where load_id = %(load)s
 group by 1 order by n desc, type
"""

TEAMS_SQL = """
select coalesce(nullif(managed_by_team, ''), 'Unassigned') as team, count(*) as n
  from logs
 where load_id = %(load)s
 group by 1 order by n desc, team
"""

# Sections 1 and 2: by log type, so only the team filter applies.
WEEK_TYPES_SQL = """
select coalesce(nullif(log_type, ''), 'Unspecified') as type,
       count(*) filter (where week_start = %(w)s)  as n,
       count(*) filter (where week_start = %(p)s)  as prev
  from logs
 where load_id = %(load)s
   and week_start = any(%(pair)s)
   and (%(all_teams)s or coalesce(nullif(managed_by_team, ''), 'Unassigned') = any(%(teams)s))
 group by 1
"""

SERIES_SQL = """
select week_start as w,
       coalesce(nullif(log_type, ''), 'Unspecified') as type,
       count(*) as n
  from logs
 where load_id = %(load)s
   and week_start between %(from)s and %(to)s
   and (%(all_teams)s or coalesce(nullif(managed_by_team, ''), 'Unassigned') = any(%(teams)s))
 group by 1, 2
"""

# Sections 3 and 4 read the same scoped set, which is what makes the sentiment
# index answer for the table above it rather than for the whole file.
_SCOPED = """
scoped as (
  select coalesce(nullif(log_type, ''), 'Unspecified')        as type,
         coalesce(nullif(introducer_name, ''), 'Unnamed')     as introducer,
         coalesce(nullif(managed_by_team, ''), 'Unassigned')  as team,
         coalesce(nullif(created_by, ''), 'Unattributed')     as creator,
         logged_on, note, note_score, note_hits, note_words
    from logs
   where load_id = %(load)s
     and week_start between %(from)s and %(to)s
     and (%(type)s = '' or coalesce(nullif(log_type, ''), 'Unspecified') = %(type)s)
     and (%(all_teams)s or coalesce(nullif(managed_by_team, ''), 'Unassigned') = any(%(teams)s))
)
"""

# The three top-performer tables are the same question asked of three columns.
# `raw` repeats the scoped alias against the unfiltered table, so a name's
# lifetime total can be read without a second round trip. Both are constants
# looked up by key -- nothing user-supplied is ever formatted into the SQL.
DIMENSIONS = {
    "creators": {
        "column": "creator", "label": "Created by", "note": "Who logged the contact",
        "raw": "coalesce(nullif(created_by, ''), 'Unattributed')",
    },
    "teams": {
        "column": "team", "label": "Managed by team", "note": "Which team owns the partner",
        "raw": "coalesce(nullif(managed_by_team, ''), 'Unassigned')",
    },
    "introducers": {
        "column": "introducer", "label": "Introducers", "note": "Which partners are being worked",
        "raw": "coalesce(nullif(introducer_name, ''), 'Unnamed')",
    },
}


def _leader_sql(dimension: str, limited: bool) -> str:
    """One ranked table: totals, a count per log type, and a lifetime figure.

    `per` is pivoted into a json object rather than into columns, because the
    log types are whatever the file holds -- the read model must not need
    changing when the CRM adds a type.

    `count(*) over ()` carries the number of names before the limit, so the
    table can say "10 of 2,928" without a second query for the count.
    """
    spec = DIMENSIONS[dimension]
    column, raw = spec["column"], spec["raw"]
    return f"""
with {_SCOPED},
per as (
  select {column} as name, type, count(*) as n from scoped group by 1, 2
),
agg as (
  select {column}                                  as name,
         count(*)                                  as n,
         max(logged_on)                            as last_log,
         coalesce(avg(coalesce(note_score, 0)), 0) as sentiment,
         count(distinct introducer)                as n_introducers,
         count(distinct creator)                   as n_creators,
         count(distinct team)                      as n_teams,
         count(distinct type)                      as n_types,
         array_agg(distinct team)                  as team_names,
         array_agg(distinct creator)               as creator_names
    from scoped group by 1
),
-- every log this name has ever carried, ignoring the range and the filters:
-- `n` answers for what is on screen, `lifetime` for the whole file
lifetime as (
  select {raw} as name, count(*) as n
    from logs where load_id = %(load)s group by 1
)
select a.name, a.n, a.last_log, a.sentiment,
       a.n_introducers, a.n_creators, a.n_teams, a.n_types,
       a.team_names, a.creator_names,
       coalesce(l.n, a.n)                                          as lifetime,
       coalesce((select jsonb_object_agg(p.type, p.n)
                   from per p where p.name = a.name), '{{}}'::jsonb) as by_type,
       count(*) over ()                                            as total_names
  from agg a
  left join lifetime l on l.name = a.name
 order by a.n desc, a.name
 {"limit %(top)s" if limited else ""}
"""


SENTIMENT_SQL = f"""
with {_SCOPED}
select count(*)                                        as n,
       count(*) filter (where note is not null)        as with_note,
       count(*) filter (where note_hits > 0)           as scored,
       count(*) filter (where note_score > 0)          as positive,
       count(*) filter (where note_score < 0)          as negative,
       count(*) filter (where note_score = 0)          as mixed,
       -- unscored notes are neutral, not missing: they count as 0 in the index
       coalesce(avg(coalesce(note_score, 0)), 0)       as index
  from scoped
"""

SENTIMENT_BY_TYPE_SQL = f"""
with {_SCOPED}
select type, count(*) as n,
       count(*) filter (where note_hits > 0) as scored,
       coalesce(avg(coalesce(note_score, 0)), 0) as index
  from scoped group by 1 order by n desc
"""

# One quote per distinct note: CRM notes repeat verbatim across partners, and
# three copies of the same sentence is not three findings. `distinct on` keeps
# the most recent occurrence of each, then the outer query ranks them.
QUOTES_SQL = f"""
with {_SCOPED},
picked as (
  select distinct on (note)
         note, note_score as score, note_hits as hits, note_words as words,
         introducer, creator, type, logged_on
    from scoped
   where note_hits > 0 and note is not null
     and (%(sign)s = 'pos') = (note_score > 0) and note_score <> 0
   order by note, logged_on desc
)
select note, score, hits, introducer, creator, type, logged_on
  from picked
 order by abs(score) desc, hits desc, words desc, logged_on desc
 limit %(limit)s
"""

NOTES_SQL = """
select
  (select count(*) from logs where load_id = %(load)s)                          as rows,
  (select count(*) from logs where load_id = %(load)s and note is null)         as blank_note,
  (select count(*) from logs where load_id = %(load)s and note_hits = 0
     and note is not null)                                                      as unscored_note,
  (select count(*) from logs where load_id = %(load)s
     and coalesce(introducer_name, '') = '')                                    as blank_introducer,
  (select count(*) from logs where load_id = %(load)s
     and coalesce(created_by, '') = '')                                         as blank_creator,
  (select count(*) from logs where load_id = %(load)s
     and coalesce(managed_by_team, '') = '')                                    as blank_team,
  (select count(distinct introducer_name) from logs where load_id = %(load)s)   as introducers,
  (select count(distinct created_by) from logs where load_id = %(load)s)        as creators,
  (select min(logged_on) from logs where load_id = %(load)s)                    as first_log,
  (select max(logged_on) from logs where load_id = %(load)s)                    as last_log,
  (select stats from core.loads where id = %(load)s)                            as load_stats
"""

ROWS_SQL = f"""
with {_SCOPED}
select logged_on, type, introducer, team, creator, note, note_score as score, note_hits as hits
  from scoped
 order by logged_on desc, introducer
 limit %(limit)s
"""

# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

def week_start(day: date) -> date:
    """The Saturday on or before `day`. Mirrors ingest._week_start exactly.

    python's weekday() is 0=Monday..6=Sunday; the rule is written against
    JavaScript's 0=Sunday..6=Saturday, so it is converted rather than re-derived.
    """
    js_dow = (day.weekday() + 1) % 7
    return day - timedelta(days=(js_dow + 1) % 7)


def pick_current_week(weeks: list[date], today: date | None = None) -> date | None:
    """Newest week in the file that has already started -- NOT max(week).

    An export taken on a Sunday carries two days of a week that has barely
    begun. Anchoring on it shows a 90% drop in activity that is an artefact of
    when the file was pulled, not of what the team did.
    """
    if not weeks:
        return None
    this_week = week_start(today or date.today())
    started = [w for w in weeks if w <= this_week]
    return started[-1] if started else weeks[0]


def _int(params: dict, key: str, default: int, low: int, high: int) -> int:
    raw = params.get(key)
    if raw in (None, ""):
        return default
    try:
        return max(low, min(int(raw), high))
    except (TypeError, ValueError) as exc:
        raise ViewError(f"'{key}' must be a number, got '{raw}'") from exc


def _capped(values: list[str] | None, keep: int = 2) -> tuple[list[str], int]:
    """Two names and a count of the rest -- the introducer sub-line."""
    names = sorted(v for v in (values or []) if v)
    return names[:keep], max(len(names) - keep, 0)


def _leaderboard(ctx: ViewContext, scoped: dict, dimension: str,
                 limit: int | None) -> tuple[list[dict], int]:
    """One ranked table and how many names it was drawn from.

    `limit=None` is the whole list -- what the "view more" pane asks for. The
    largest is one row per introducer in the file, which is well inside what a
    single payload can carry.
    """
    params = dict(scoped)
    if limit is not None:
        params["top"] = limit
    rows = ctx.rows(_leader_sql(dimension, limited=limit is not None), params)
    for row in rows:
        row["teams"], row["teams_more"] = _capped(row.pop("team_names"))
        row["creators"], row["creators_more"] = _capped(row.pop("creator_names"))
    return rows, (rows[0]["total_names"] if rows else 0)


def _scope(ctx: ViewContext, params: dict) -> dict:
    """Resolve the week anchor, the table range and the filters, once.

    Every view here shares it, so the tables, the chart and the sentiment index
    can never disagree about which rows they are describing.
    """
    load = ctx.load("logs")
    today = date.today()
    counted = ctx.rows(WEEKS_SQL, {"load": load})
    weeks = [r["w"] for r in counted]
    if not weeks:
        raise ViewError("no dated logs in this file")

    current = pick_current_week(weeks)
    chosen = params.get("week")
    if chosen:
        try:
            anchor = date.fromisoformat(chosen)
        except ValueError as exc:
            raise ViewError(f"'week' must be a YYYY-MM-DD date, got '{chosen}'") from exc
        anchor = week_start(anchor)
        if anchor not in weeks:
            raise ViewError(f"no logs in the week beginning {anchor.isoformat()}")
    else:
        anchor = current

    index = weeks.index(anchor)
    previous = weeks[index - 1] if index else None
    span = _int(params, "weeks", DEFAULT_TABLE_WEEKS, 1, 260)
    start = weeks[max(index - span + 1, 0)]

    scope = {
        "load": load, "weeks": weeks, "counted": counted, "anchor": anchor, "today": today, "previous": previous,
        "current": current, "index": index, "span": span, "start": start,
        "type": (params.get("type") or "").strip(),
        "teams": _teams(params),
        "regions": sorted(set(split(params.get("region")))),
    }
    # Region and Team come to one list of teams, or None for every team; an
    # empty list -- a team picked outside the picked regions -- matches nothing
    known = [r["team"] for r in ctx.rows(TEAMS_SQL, {"load": load})] if scope["regions"] else []
    scope["effective"] = narrow(scope["teams"], scope["regions"], known)
    return scope


def _teams(params: dict) -> list[str]:
    """The selected teams. Pipe-separated rather than comma-separated, because a
    team name may hold a comma and cannot hold a pipe -- and a single name still
    parses as a one-element list, so links written before this took several
    still open on the team they named."""
    raw = params.get("team") or ""
    return [name.strip() for name in raw.split("|") if name.strip()]


def _scoped_params(scope: dict) -> dict:
    return {"load": scope["load"], "from": scope["start"], "to": scope["anchor"],
            "type": scope["type"], **_team_params(scope)}


def _team_params(scope: dict) -> dict:
    """`= any(array)` matches nothing when the array is empty, so "every team" is
    a flag rather than an empty list -- and the list is never empty, because an
    empty array has no type for the planner to compare against."""
    return {"all_teams": scope["effective"] is None, "teams": scope["effective"] or [""]}


# --------------------------------------------------------------------------
# views
# --------------------------------------------------------------------------

def overview(ctx: ViewContext, params: dict):
    scope = _scope(ctx, params)
    load, anchor, previous = scope["load"], scope["anchor"], scope["previous"]
    scoped = _scoped_params(scope)
    top_n = _int(params, "top", DEFAULT_TOP_N, 1, 100)
    chart_weeks = _int(params, "chart_weeks", DEFAULT_CHART_WEEKS, 2, 104)

    # --- 1. selected week by log type ------------------------------------
    by_type = ctx.rows(WEEK_TYPES_SQL, {
        "load": load, "w": anchor, "p": previous,
        "pair": [d for d in (anchor, previous) if d], **_team_params(scope),
    })
    week_total = sum(r["n"] for r in by_type)
    prev_total = sum(r["prev"] for r in by_type)
    for row in by_type:
        row["delta"] = row["n"] - row["prev"]
        row["share"] = (row["n"] / week_total) if week_total else 0.0
    by_type.sort(key=lambda r: (-r["n"], r["type"]))

    # --- 2. week on week --------------------------------------------------
    chart_from = scope["weeks"][max(scope["index"] - chart_weeks + 1, 0)]
    grid = ctx.rows(SERIES_SQL, {"load": load, "from": chart_from, "to": anchor,
                                 **_team_params(scope)})
    chart_range = [w for w in scope["weeks"] if chart_from <= w <= anchor]
    counts: dict[str, dict[date, int]] = {}
    for row in grid:
        counts.setdefault(row["type"], {})[row["w"]] = row["n"]
    series = sorted(
        ({"type": t, "counts": [by_week.get(w, 0) for w in chart_range],
          "total": sum(by_week.values())} for t, by_week in counts.items()),
        key=lambda s: (-s["total"], s["type"]),
    )

    # --- 3. top performers ------------------------------------------------
    top: dict[str, list[dict]] = {}
    totals: dict[str, int] = {}
    for dimension in DIMENSIONS:
        top[dimension], totals[dimension] = _leaderboard(ctx, scoped, dimension, top_n)

    # --- 4. note sentiment ------------------------------------------------
    sentiment = ctx.one(SENTIMENT_SQL, scoped) or {}
    sentiment["by_type"] = ctx.rows(SENTIMENT_BY_TYPE_SQL, scoped)
    sentiment["quotes"] = {
        sign: ctx.rows(QUOTES_SQL, {**scoped, "sign": sign, "limit": QUOTES})
        for sign in ("pos", "neg")
    }

    scoped_rows = sentiment.get("n", 0)
    return {
        "weeks": scope["counted"],
        "week": anchor,
        "previous_week": previous,
        "current_week": scope["current"],
        "is_current": anchor == scope["current"],
        # A week that has not finished is being compared with one that has. The
        # rule is the spec's -- the newest week that has begun -- but a Monday
        # export makes a two-day week look like a collapse, so say so rather
        # than letting the Δ speak for itself.
        "in_progress": anchor <= scope["today"] <= anchor + timedelta(days=6),
        "days_elapsed": max(1, min((scope["today"] - anchor).days + 1, 7)),
        "has_earlier": scope["index"] > 0,
        "has_later": scope["index"] < len(scope["weeks"]) - 1,
        "filters": {"type": scope["type"], "teams": scope["teams"], "regions": scope["regions"],
                    "weeks": scope["span"], "top": top_n, "chart_weeks": chart_weeks},
        "log_types": ctx.rows(TYPES_SQL, {"load": load}),
        **dict(zip(("teams", "regions"), options(ctx.rows(TEAMS_SQL, {"load": load})))),
        "week_kpis": {"total": week_total, "previous_total": prev_total,
                      "delta": week_total - prev_total, "by_type": by_type},
        "series": {"weeks": chart_range, "by_type": series,
                   "totals": [sum(s["counts"][i] for s in series) for i in range(len(chart_range))]},
        "range": {"from": scope["start"], "to": anchor, "weeks": scope["span"], "rows": scoped_rows},
        "top": top,
        # how many names each table was drawn from, so it can say "10 of 2,928"
        # and the "view more" pane knows what it is opening
        "top_totals": totals,
        "sentiment": sentiment,
        "data": ctx.one(NOTES_SQL, {"load": load}) or {},
    }


def rows(ctx: ViewContext, params: dict):
    """The individual logs behind a number, newest first.

    Same scope resolution as the overview, plus an optional single-week
    restriction so a KPI tile can drill into just its own week.
    """
    scope = _scope(ctx, params)
    scoped = _scoped_params(scope)
    if (params.get("only") or "") == "week":
        scoped["from"] = scope["anchor"]
    limit = _int(params, "limit", 200, 1, 2000)
    return {
        "week": scope["anchor"],
        "from": scoped["from"], "to": scoped["to"],
        "filters": {"type": scope["type"], "teams": scope["teams"], "regions": scope["regions"]},
        "rows": ctx.rows(ROWS_SQL, {**scoped, "limit": limit}),
    }


def leaderboard(ctx: ViewContext, params: dict):
    """One top-performer table in full, for the "view more" pane.

    Same scope as the table it was opened from -- the range, team and log type
    on screen -- so the first ten rows of this list are the ten already shown.
    Reading it as a different scope would make the two disagree.
    """
    dimension = params.get("dimension") or ""
    if dimension not in DIMENSIONS:
        raise ViewError(
            f"unknown dimension '{dimension}' (have: {', '.join(DIMENSIONS)})"
        )
    scope = _scope(ctx, params)
    found, total = _leaderboard(ctx, _scoped_params(scope), dimension, limit=None)
    return {
        "dimension": dimension,
        "label": DIMENSIONS[dimension]["label"],
        "note": DIMENSIONS[dimension]["note"],
        "week": scope["anchor"],
        "range": {"from": scope["start"], "to": scope["anchor"], "weeks": scope["span"]},
        "filters": {"type": scope["type"], "teams": scope["teams"], "regions": scope["regions"]},
        "log_types": ctx.rows(TYPES_SQL, {"load": scope["load"]}),
        "total": total,
        "rows": found,
    }


VIEWS = {"overview": overview, "rows": rows, "leaderboard": leaderboard}
