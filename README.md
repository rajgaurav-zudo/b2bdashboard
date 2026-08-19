# Introducer Performance Dashboard

`introducer-dashboard.html` — one self-contained file. Open it in a browser, load the two
CRM exports, read the report. No backend, no build step, nothing uploaded anywhere: both
files are parsed in the browser tab.

Built to the spec in `CONTEXT.md`.

## Using it

1. Open `introducer-dashboard.html` (double-click, or drag into a browser tab).
2. Box 1 — the **introducers master** (`Partner Name`, `Lifecycle Stage`, …).
3. Box 2 — the **applications** export (`Application Introducer Name`, deposit status, intake).

`.csv`, `.xls` and `.xlsx` all work. CSV is parsed by a hand-rolled streaming reader (fast,
low memory); Excel goes through SheetJS. Both files can be loaded in either order; the report
builds once both are in. Load the wrong file into the wrong box and it says so.

Chart.js and SheetJS load from CDN, so the first open needs a network connection. Everything
else is local.

## What it does

**Scope** — every partner at `Customer` stage, *plus* anyone holding a paid deposit at any
stage, including names that never made it into the master file (`Not in CRM`). A strict
Customer-only filter drops real revenue.

**Current intake year** is chosen, never assumed: the newest year holding ≥10% of the peak
year's application count. Nov/Dec roll into the following January, which otherwise invents a
barely-started future intake and zeroes every tile. Rows after `CUR` appear in the funnel
table but are excluded from all tile scoring.

**13 tiles** across Active introducers / Leaking revenue / Quality. Every tile opens a
drill-down pane — Team · Country · SRM · Stage · Introducer, groups expanding in place, every
column sortable at group level and independently inside each expanded group.

**Conversion funnel** — two charts and a sortable ten-column table, with an in-flight warning
band that quantifies the visa/enrolment gap rather than letting it read as a quality collapse.

**Critique and Data notes** — computed from the loaded file, not hard-coded. The threshold
critique re-tests both thresholds against your data and labels each *miscalibrated* or *holds
up* on the numbers it finds; the cadence paragraph measures each market's actual intake
concentration; the eight data notes carry live figures for every trap in `CONTEXT.md` §5.

## Judgement calls worth knowing

- **Funnel scope toggle.** The §7 baseline can't be satisfied by one consistent rule: the
  lifecycle table gives 2,016 active deposits for the current year across the full book, while
  the funnel row for the same year gives 1,961 — the Customer-only figure. The tiles use the
  full in-scope book. The funnel has a **In-scope / All attributed** toggle so the difference
  is visible instead of buried; the tiles and the in-scope funnel now agree.
- **Chart greens.** Semantic colours are as specified (`#1D7A5F` good, `#B7502F` bad). The two
  chart series use marginally re-stepped versions (`#0F8A5F`, `#C0491F`) because the specified
  pair fails a colourblind-separation check when stacked against each other — deutan ΔE 7.3,
  below the ΔE 8 floor. Text and UI colours are untouched.
- **Squanderers / Slackers** keep their specified names; the critique section argues against
  the naming rather than silently renaming the metric.
- **Deposit → visa/enrolled** use active deposits as the denominator and count only
  active-deposit applications in the numerator. **App → enrolment** (the bad-converters rule)
  counts every enrolled application, deposit or not.

## Verification

`CONTEXT.md` ships a regression baseline computed from the real export, which isn't in this
repo. In its place there's a synthetic pair of exports built to trip every documented trap —
curly-quote and mojibake headers, a Nov/Dec rollover into a phantom future year, blank
introducer names, blank `Became Customer Date`, duplicate partner names, a name absent from
the master file, a closed-lost-yet-enrolled contradiction — with 42 hand-computed assertions
over ingest, scope, all 13 tiles, both funnel scopes and the drill-down. All pass. A 230,000-row
/ 10.6 MB export parses in ~1.6 s and builds the whole report in ~0.3 s.

Run the real export through it and check the §7 baseline before trusting any number in a
meeting.
