# Reports — context

Files built from the data to take away, under **Data → Downloads**. Today there is
one: the weekly summary workbook (`weekly_summary.py`), which can also be written
over a Google Sheet (`sheets_sync.py`). `xlsx.py` is the standard-library writer
both use.

A report is not a dashboard. It has no schema, no ingest and no load of its own:
it reads the **latest archived upload** of each source straight from storage, so
it is only ever as fresh as the last export someone dropped on Uploads. The
Downloads page lists which files those are before anyone clicks.

## Endpoints

```
GET  /api/downloads                          the sources each report reads, and the Sheet's state
GET  /api/downloads/weekly-summary           build and download the workbook
POST /api/downloads/weekly-summary/sync      build it and write it over the Google Sheet
```

The first build after a new upload reads the full exports (a few seconds); the
parsed exports are cached by upload id until one of them changes.

## Sources

| Source | What the summary takes from it |
| --- | --- |
| `introducers` | the CRM `_id`, Partner Name, Country, BusinessTeam, BusinessRegion, SRM, Became Customer Date |
| `introducer_logs` | Log Time, Log Type, Created By, Managed By Team |
| `applications` | the deposit-state columns, course level, Actual Intake Year / Month, Application Introducer Name / Id, Introducer SRM / AMT, Institution, CurrentlyAssignedToBusinessTeam, StudentAssignedToBusinessArea / Region, Application Destination Country, Student Nationality, Application Status / Sub-Status, the timestamp of each status, Application Closure Reason |

Columns resolve the way ingest resolves them (`COLUMNS` in `weekly_summary.py`).
A missing required column fails the build with its name; a missing optional one
reads as blank. Every sheet opens with a note naming the files it was read from.

## Definitions

These follow [sources/context.md](../../../sources/context.md) except where
listed here, and each sheet's note says so.

- **Deposit states.** Paid in full (`FullyPaid` **or** `fullyPaidWaitingForApproval`)
  is an **active deposit** when the two deferral columns agree (both No or both
  Yes) and **DAA** when they do not. `PartiallyPaid` is **PD**. Closed lost is
  out of all three. The dashboards count `FullyPaid` alone.
- **Intake year** is Actual Intake Year; **quarters** are by Actual Intake Month
  (Q1 Jan–Mar … Q4 Oct–Dec). "This year" is the calendar year of the build.
- **Course level.** The eight Academic levels count everywhere. `Language` and
  `PresessionalEnglish` count only on the YTD - Language sheet. Anything else,
  blank included, counts nowhere.
- **Business area.** The B2B sheets and the deposit sheets built on `_deposits`
  count only `StudentAssignedToBusinessArea = B2B`. The YTD sheets, the funnel,
  Sametime and Closed Lost count every business area (a blank one aside).
- **Weeks** are Edvoy weeks, Saturday to Friday, in UTC. "This week" is the one
  containing today, to date; "last week" is the seven days before it, whole.
  Year to date is 1 January to today against the same span last year (29 Feb
  compares with 28 Feb).
- **Business team** names drop the CRM's `SRM` / `SRMs` / `AMT` words
  ("West Africa B2B SRMs 1" reads "West Africa B2B 1").
- **The introducer** on an application is its Application Introducer Id; an
  application with only a name gets the id from the master when exactly one
  introducer there has that name (ignoring case and spacing), and one with only
  an id gets the name. Country and Became Customer Date come from the master.
  An introducer whose id is not on the master reads **"Country missing in DB"**
  for country and "Introducer not in master file" for its onboarding year; one
  on the master with a blank country reads `(blank)`.
- **The applications export is a snapshot with no history.** "Last week's
  deposits" are those whose Deposit Fully Paid timestamp falls in last week and
  that are still paid in full today; Sametime reconstructs last year's position
  from each stage's timestamp.

## Sheets, in order

1. **YTD - Academic** — deposits, PD and DAA, this intake year against last, for
   the full year and each quarter. A: headline; B: by business area; C*n*: each
   area by business region; D: by destination country; E: by student
   nationality. D and E show the 20 with the most deposits and fold the rest into
   one row. Each table has its charts.
2. **YTD - Language** — the same for the Language and Pre-sessional levels, each
   row expanding into the two.
3. **{next year} sales sheet** — the Academic sheet for next year's intake
   against this year's.
4. **Deposit funnel movement** — active deposits by the stage each stands at now
   (offered, CoE received, visa applied, visa granted, enrolled), this intake year
   against last; full year, by quarter, by business area.
5. **Sametime Last Year** — this intake year's applications as of today against
   last year's as of the same date a year ago: created at each stage (applied,
   offered, deposit, CoE, visa applied, visa granted, enrolled), still open in it,
   closed lost there, and the closed lost %; by quarter and business area.
6. **Closed Lost Deposits** — this intake year's deposits, PD and DAA: created,
   active, closed lost and closed lost % of created, for the full year and each
   quarter (four columns per period), each row expanding into the stage it was
   closed in. A headline; B by business area; C*n* by region; D destination
   country; E nationality; F introducer (the cell carries the introducer's most
   frequent business team and SRM on a second, smaller line); G institution — D
   to G top 20 by closed lost. H: the closed lost by Application Closure Reason,
   with each reason's share of the measure's closed lost, ranked within each
   measure. Closure reasons are shown as exported, near-duplicate spellings
   included.
   - **Colours**: a closed lost % under 20% is green, 20–49% amber, 50% and
     above red; the same thresholds colour the closure-reason share. Total rows
     are not coloured.
7. **B2B - Onboarding** — introducers by Became Customer Date: year to date and
   this week against the previous, by business region, team, SRM and country,
   with the week's new introducers listed.
8. **B2B - Activity Logs** — logs this week against last, by log type (face to
   face, call, meeting, email), per SRM, business region and business team.
9. **B2B - Sales and Retention** — active deposits by intake year and quarter, by
   the year the introducer was onboarded; this year's broken down by introducer
   country, destination country, business region, SRM, business team, AMT
   counsellor and institution; DAA and PD by intake month. Then, grouped by
   business team and collapsed: **resurrected** introducers (not onboarded this
   year, no active deposit for last year's intake, active deposits for this
   year's) and **missed out** ones (active deposits last year, none this year).
10. **B2B Summary Last Week** — last week whole against the week before:
    introducers onboarded, activity logs, and deposits by the day they were paid
    in full.

Totals and team rows are `SUBTOTAL` formulas over their rows, so a filtered or
collapsed table still adds up; each formula carries its computed value for
viewers that do not recalculate.

## Google Sheet sync

`POST …/sync` builds the same workbook and uploads it as a new revision of one
Drive file, which Google converts to a spreadsheet in place: the link, id and
sharing stay; the contents are replaced whole, so anything typed into the sheet
is lost. Access is a service account shared as Editor on that one sheet and
nothing else. Its key is mounted from `./secrets` (git-ignored) as
`GOOGLE_SERVICE_ACCOUNT_FILE`, and the sheet is `GOOGLE_SHEET_ID`; either unset
turns the sync off and the Downloads page hides the button. The last successful
sync time is kept in the upload directory.

## The xlsx writer

`xlsx.py` writes SpreadsheetML with the standard library: cell styles, number
formats, merged cells, row outlines (collapsed groups), frozen panes, column
widths and row heights, formulas with cached values, inline rich text (`Rich`,
for a second line in a smaller, lighter font) and native charts.

## Changing a report

- A new column goes in `COLUMNS` first; mark it required only if the report
  cannot be built without it.
- Update the sheet's note, the module docstring, the Downloads page text
  (`web/src/pages/DownloadsPage.tsx`) and this file together.
- `api/tests/test_weekly_summary.py` builds the workbook from small synthetic
  exports and reads cells back; add a case for any new table or rule.
- Re-sync the Google Sheet after a change so it matches the download.
