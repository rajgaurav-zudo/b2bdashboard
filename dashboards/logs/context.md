# Log dashboard — context

What this dashboard is for, and every rule the numbers on it depend on. The
figures are computed from these definitions and nowhere else; if a number looks
wrong, the disagreement is with something written down here.

Nothing in this file affects any other dashboard. It reads one platform-level
file (`introducer_logs`) into one schema (`dash_logs`), through its own
`ingest.py` and its own `metrics.py`.

## The question it answers

How much contact the team actually has with its introducers — week by week, who
is logging it, which partners are being worked, and what the notes say about how
those conversations are going.

It is an **activity** dashboard, not an outcome one. A log is a record that
someone made contact. Nothing here knows whether that contact produced an
application or a deposit; that is the introducer performance dashboard's
question, and the two are deliberately not joined.

## The file

`introducer_logs` — one row per logged interaction. Required columns, matched on
normalised headers rather than exact strings:

| Column | Used for |
| --- | --- |
| `_id` | the CRM's own log id — the natural key when present |
| `Introducers Name` | which partner the log is against |
| `Log Type` | Call · F2FVisits · Email · Meeting |
| `Call Type` | Inbound / Outbound, on calls only |
| `Log Time` | the date of the log — **required**, see below |
| `Outcome` | Connected / NoAnswer / Busy / WrongNumber — stored, not yet surfaced in the metrics |
| `Note` | free text, scored for sentiment |
| `Managed By Team` | the team that owns the partner |
| `Created By` | the person who logged it |

Only `Log Type`, `Log Time` and `Introducers Name` are required. The rest are kept
when the export has them: re-projecting an archived upload to pick a column up
later is cheap, but only if the column was stored in the first place.

**Upload the CSV, not the XLSX.** Both are accepted, and the same export in both
formats loads the same 6,977 rows — but the XLSX came through with mojibake in
135 notes (curly quotes and emoji mangled) while the CSV decoded cleanly.

## Definitions

### A week runs Saturday → Friday

`week_start` is the Saturday of the week a log falls in. It is computed once at
ingest — `(js_dow + 1) % 7` days back from the log's date — and stored, so every
query buckets identically and the index is usable. `metrics.week_start()` mirrors
the same rule in Python; the two are tested against each other.

### "Log Time" is the log's date

Parsed to a date; the time of day is discarded.

The live CRM writes **JavaScript's own `Date.toString()`**:

```
Mon Aug 24 2026 10:55:45 GMT+0000 (Coordinated Universal Time)
```

so that is tried first. The trailing `(...)` is a localised label, not an offset;
the offset is the `GMT+0000`, and it is **honoured rather than assumed** — a row
exported at `+0530` converts to the UTC day, which is what the browser version's
`getUTC*` calls did. Other timestamp formats are tried next, then bare dates,
**day-first before month-first** — the same order the introducer performance
ingest uses, so the two dashboards cannot disagree about what `03/04/2026` means.

This is not cosmetic. When the format was unrecognised, all 6,977 rows parsed as
undated, the table loaded empty, and the dashboard went dark — see *How this
failed once* below.

**A log with no readable date is skipped**, because every figure here is a week
and an undated row cannot be in one. The count of skipped rows is recorded on the
load's `stats` and shown in Data notes, so they are visibly dropped rather than
silently.

### The selected week defaults to the newest week that has already started

Not `max(week_start)`. An export pulled on a Sunday carries two days of a week
that has barely begun; anchoring on it shows a 90% collapse in activity that is
an artefact of when the file was pulled. `←` / `→` step the anchor through the
weeks the file actually holds.

The newest week in any export is almost always a **partial** week — an export
pulled on a Monday holds two days of it. The rule is deliberately the spec's, so
the anchor is still that week, but the page says so: a banner gives the week's
age and its run-rate, because otherwise the Δ against a full week reads as a
collapse that nobody caused.

*Known nuance:* that default is resolved against today's date, while the view
cache is keyed on the load. The default anchor can therefore stay one week stale
inside a long-lived process until the next upload or restart. Explicitly stepping
the week is unaffected, and an upload always re-resolves it.

### Change (Δ wk) always compares the selected week to the one before it

Regardless of what range the tables are showing. The comparison is to the
previous week *present in the file* — if a week is missing from the export
entirely it is not treated as a zero.

### Table range defaults to the last 8 weeks ending with the selected week

Roughly two months. It governs the top-performer tables and the sentiment
section; it never governs the KPI row or the week-on-week change.

### The top-performer tables

Three tables — *Created by*, *Managed by team*, *Introducers* — are the same
question asked of three columns, and are one query with the grouping column
injected from a whitelist. Each row carries:

- **a count per log type**, over the selected range. The types are whatever the
  file holds, pivoted from a `jsonb_object_agg` rather than from fixed columns,
  so the CRM adding a type needs no change here. A type a name never used is
  absent from the object and renders as `·` rather than `0`.
- **Total** — those counts added up, i.e. the range.
- **All time** — every log in the file for that name, *ignoring the range and
  both filters*. A partner who is quiet this quarter but heavily worked
  historically should not read as a stranger.
- the parties it is not grouped by, capped at two names with the rest counted.

Each table shows **ten rows**, and a *view more* button opens the full list in
the side pane. That list is deliberately **the same scope as the table it came
from** — same range, same team, same log type — so its first ten rows are the
ten already on the page. Reading it as "all time" instead would make the two
disagree, and the *All time* column already answers that question per row.

### Filters

- **Team** narrows everything — a team's page should be a team's page. It holds
  a **set**, not a value: the regional SRM teams are read together as often as
  alone, and asking for `West Africa B2B SRMs 1` and `West Africa B2B SRMs 2`
  one at a time gives two halves of a number nobody wants halved. On the wire
  the names are pipe-separated (`team=A|B`) — a team name may hold a comma and
  cannot hold a pipe, and a single name still parses as a one-element list, so a
  link written before the filter took several still opens on the team it named.
  Selecting nothing is *every* team, and is a different code path from selecting
  none: `= any(array)` matches nothing when the array is empty, so "all teams"
  is a flag rather than an empty list.
- **Log type** narrows only the tables and the sentiment index. The KPI row and
  the week-on-week chart are *by* log type; filtering them to one type would
  leave a single bar and a row of empty ones.

Blank values are named rather than dropped: `Unspecified` type, `Unnamed`
introducer, `Unassigned` team, `Unattributed` creator. A gap in the CRM is a
finding, not a row to lose.

### Note sentiment

A **keyword lexicon**, not a model — the point is that anyone can read the rule
that produced a score and argue with it. Per note:

1. Count negative terms.
2. Strike the negative phrases out of the text, then count positive terms. This
   is why *"not interested"* scores −1 instead of cancelling itself against the
   *"interested"* inside it.
3. `score = (positives − negatives) / (positives + negatives)`, in −1…+1.

A note that matches nothing has `note_score = NULL` and **counts as neutral, not
as missing**: the index is the mean over every scoped log with unscored ones
contributing 0. That keeps the index honest about how much of the week was
actually expressive — a week of terse "called, no answer" notes should not read
as glowing because the three notes that did score were positive.

Quotes are the strongest-scoring notes on each side, tie-broken by number of
lexicon hits and then by length, labelled *introducer · creator · date*.

**The score is stored at ingest, not computed at read time.** Changing the
lexicon therefore means re-projecting the archived upload:

```
POST /uploads/{id}/project?dashboard=logs&force=true
```

That is the intended path — the file is already archived, so a corrected lexicon
is applied to the exact bytes that were loaded rather than to a fresh export that
has since moved on.

## Known weaknesses

Worth saying out loud before someone presents these numbers:

- **The lexicon is a blunt instrument.** It has no grammar beyond the negation
  strike-out, no sarcasm, no domain training. `pending` and `chasing` are counted
  negative, which is right for a follow-up log and wrong for a note that says a
  visa is pending as a matter of fact. Read the index as a *direction*, never as
  a measurement.
- **Log volume is not effort.** One person logging every email and another
  logging only meetings will rank very differently for identical work. The top
  tables measure logging discipline at least as much as activity.
- **No outcome is attached.** A partner with 40 logs and no applications looks
  like the most-worked account on the page. That is a real signal, but it is a
  cost signal, not a revenue one.
- **`Unnamed` introducers** are logs with no partner attached. They are counted
  in weekly totals and appear as a single row in the introducer table; they are
  not a real partner.

## Natural key

`log_uid` is the CRM's `_id` when the export carries one. A real id is the only
key that survives someone editing a note: the row then shows up in the changelog
as *changed* rather than as a removal plus an addition.

Without an `_id`, it falls back to a content hash of
(date, type, introducer, team, creator, note) plus an occurrence index. Two
genuinely identical logs on the same day stay distinct, and the key is stable
across re-uploads as long as the same row appears the same number of times.

A repeated `_id` would break the primary key, and the export is not ours to trust
on that: the first occurrence is kept and the rest are counted in the load's
`duplicate_ids`.

## How this failed once

Worth keeping, because the failure mode is quiet. The first real export used a
`Log Time` format the ingest did not recognise. Every row was dropped as undated,
the projection reported **ready with 0 rows**, that empty load became current,
and the dashboard answered every request with a 409 that said only "no dated logs
in this file". Nothing was marked failed and nothing said why.

Two changes came out of it:

- The ingest reads the format the CRM actually emits, tested against it.
- The **platform** now refuses a projection that drops every row of a non-empty
  file. It fails the projection with a readable reason and leaves the previous
  load current, so a dashboard that was working stays working. That guard is in
  `api/app/ingest/service.py` and is asserted in `api/tests/test_fan_out.py`.

## Views

- `overview` — the whole page. Params: `week`, `weeks`, `chart_weeks`, `top`,
  `type`, `team` (pipe-separated for several). Every view answers `filters.teams`
  as a list.
- `rows` — the individual logs behind a number. Params: as above, plus
  `only=week` to restrict to the selected week and `limit`.
- `leaderboard` — one top-performer table in full, for the *view more* pane.
  Params: `dimension` (`creators` · `teams` · `introducers`) plus the scope
  params above.
