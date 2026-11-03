# Master Sales — context

Every application in the export, narrowed by the student's business assignment,
by when each stage happened and by actual intake, shown as the pipeline Applied →
Offered → CoE → Visa applied → Visa granted → Enrolled, with Deposit beside it.

This is the spec. Its sha256 is stored in `core.dashboards.context_sha`, so when a
number moves you can tell whether the spec changed or the data did.

## Source

The platform `applications` export, projected with
`POST /api/uploads/{id}/project?dashboard=master_sales`. Every row is kept, closed
lost included: a closed-lost application still reached the stages it reached.

## Filters (the hero)

All of them apply together. Nothing picked in a menu is everything.

* **Business area** = `StudentAssignedToBusinessArea` (B2B, B2C, TBP, Accelerator).
  Unassigned is not offered in this menu; those rows still count when no area is
  picked.
* **Region** = `StudentAssignedToBusinessRegion`.
* **Team** = `CurrentlyAssignedToBusinessTeam`.
  A blank in any of the three is **Unassigned**. The three are a hierarchy (a
  region sits in one area, a team in one region): picking B2B leaves only B2B
  regions and teams in the other menus, and changing an area or region drops the
  region and team picks it no longer covers. Each menu is counted with every other
  filter applied but its own; options with nothing behind them are hidden unless
  picked.
* **Date range** reads the export's stage timestamps (`Timestamp of '…' status`).
  The export has no "Created" or "Became …" columns; the timestamps are the
  dates there are. With a range, each stage counts the applications whose date
  *for that stage* falls inside it, so "Offered, October" is offers made in
  October whatever month the application was made in. Stages are therefore
  events in the window, not a cohort, and a later stage can outnumber an earlier
  one. Presets are anchored on the export's newest stage date, not the clock.
  The default is **this week**: Monday of the anchor's week to the anchor. **All
  time** is a preset: a stage counts everything that has ever reached it.
* **Actual intake** on Actual Intake Year + Month, either quarters or a range.
  The menu lists last, this and next year ("this year" being the year of the
  export's newest date), each a full-year button above its four quarters. Any
  quarters of **one** year can be combined (`intake_q=2026-Q1|2026-Q3`); a quarter
  picked in another year starts over in that year, and the view refuses quarters
  from two years. The calendar picks a range of months instead (a day stands for
  its month, both ends included). Rows with no actual intake drop out once an
  intake is picked.
* **Course level** = `Application Course Level` in the weekly summary's groups
  (`app/reports/weekly_summary.py`), matched on letters only, any case:
  **Academic** (the default) is ALevel, ASLevel, Doctorate, Foundation,
  GCSEgradesAC, Postgraduate, PreMasters, Undergraduate; **Language** is Language
  and PresessionalEnglish. **All levels** adds the rest: a blank, `Presessional`
  (not on the report's list) and stray values. The × clears to All levels; Clear
  all goes back to Academic.
* **Applications / Unique applicants**: the same figures counted per application
  or uniquely. In unique applicants, Applied and Offered count distinct
  `Student Ref Id` (an application without one counts as its own student). From
  CoE on, and for Deposit, DAA and PD, each **sale** counts: a student's
  applications for the same actual intake (year + month) are one sale, and
  applications for different intakes are different sales. So a student who
  deposits for September 2026 and again for January 2027 is two deposits.

## Scope

Above the cards: the unique applicants (distinct students) and applications
behind the page, being the rows with any stage, deposit, part-payment or deferral
date in the range (every row under all time), under the other filters.

## Stages

`stage` is the furthest rung an application has reached, from its dates and, where
the CRM set a status without a date, its status:

| Status | Proves at least |
|---|---|
| Applied, Final Decision, Closed Won | Applied |
| Offered | Offered |
| CoE Received, Visa | CoE (`Visa` may mean the visa is being prepared) |
| Enrolled | Enrolled |

Dates are backfilled down the ladder: a later stage's date proves the earlier
ones by then (Enrolled implies the visa was granted, which implies it was applied
for, and so on). Status-only stages have no date, so they count under *all time*
but never inside a date range.

## Deposit (parallel)

Deposit is not a rung. It can be paid at Offered, CoE, Visa applied, Visa granted
or Enrolled. An application has a deposit when it has a `Deposit Fully Paid`
timestamp or its Deposit Paid Status is FullyPaid / fullyPaidWaitingForApproval.
A deposit proves an offer (it is paid against one) and nothing further. Inside a
date range only dated deposits count.

The page shows the deposit count, its share of Offered, and where those deposits
sit now: by each application's furthest stage (in students, the furthest stage
among that student's deposited applications).

Deposits split as the weekly summary's YTD sheets class them (`deposit_state`):
**closed** are closed lost; of the open ones, **DAA** (deferral awaiting
approval) have Deferred Initiated and Deferred Approved differing, and
**active** have them agreeing (both No or both Yes).

## DAA (deferrals)

A card below the ladder: deposits (paid in full) whose deferral was initiated,
dated by `Timestamp Deferral Initiated`. Inside a range, those initiated in it;
under all time, every deposit with Deferred Initiated = Yes or that date. Split
by the state now: **awaiting approval** (`deposit_state` DAA), **approved**
(Deferred Approved = Yes) and **closed** (closed lost), all but closed open.

## PD (partially paid)

A card below the ladder, dated by `Timestamp of 'DepositPaid| PartiallyPaid'
status`: part payments made in the range, or under all time every one dated or
with Deposit Paid Status PartiallyPaid now. Split by the state now: **still part
paid** (status PartiallyPaid, open), **since paid in full** (open, now a deposit)
and **closed** (closed lost). A part payment proves an offer, and its date dates
the offer if nothing earlier does.

"Today" for the date presets is the newest of every stage, deposit,
part-payment and deferral date in the export.

## Conversion

Each stage card shows its share of the previous stage. Under a date range these
are ratios of events in the window, not true conversion of one cohort.
