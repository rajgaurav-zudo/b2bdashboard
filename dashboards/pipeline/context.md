# Pipeline — context

The whole intake, every application type: for the students of an actual intake,
how far each has got, and how that compares with the same intake a year earlier.

This is the spec. Its sha256 is stored in `core.dashboards.context_sha`, so when a
number moves you can tell whether the spec changed or the data did.

## Source

The platform `applications` export, projected with
`POST /api/uploads/{id}/project?dashboard=pipeline`. Every row is kept: direct and
indirect recruitment, every course level (a blank level is stored as
`Unspecified`). Filtering is the reader's job.

## Scope: the actual intake

A student is in scope when an application's **Actual Intake Year + Month** (after
any deferral) falls in the chosen months. The original intake is not used.

* **Calendar year**: Jan–Dec; Q1 Jan–Mar … Q4 Oct–Dec.
* **Academic year**: Aug–Jul (`ACADEMIC_START_MONTH = 8` in `metrics.py`), shown as
  "2025-2026"; Q1 Aug–Oct … Q4 May–Jul. Quarters always count from the start of the
  chosen year.
* Years run from 2022 to two years after the current year. No quarter picked is the
  whole year. There is no custom month selection.
* **Course level** is a multi-select; nothing picked is every level.

## Region and Team

The same menus as Introducer Performance, from the same place: an application's
team is its introducer's SRM team on the **introducers master** (the second
dataset, matched on Application Introducer Name = Partner Name), and the region
comes from that team (`api/app/regions.py`). An application with no introducer,
an introducer missing from the master, or one with no team there is
**Unassigned**, region **Other**. Region picks teams and Team narrows them.

Like course level, Region and Team pick *applications* before the roll-up: a
student's stage is the furthest among their applications in the picked teams. A
student with applications under two teams is counted under both, so region counts
add up to more than the total.

The export's own `Introducer SRM Team Name` column was not used. It agrees with
the master on 98.4% of applications, but the other dashboards read the master, and
the menus should put a student in the same team everywhere.

## A student, not an application

Everything is counted on Student Ref Id. A student's **super status** is the
furthest stage any of their in-scope applications has reached. An application with
no Student Ref Id counts as a student on its own.

Stages, lowest first: **Applied → Offer → Deposit → CoE → Visa granted → Enrolled**.

## How far an application got

Each stage's date comes from its `Timestamp of '…' status` column and is
**backfilled from the stages after it**: reaching Offer on 3 March means having
applied by 3 March. CoE also takes the Visa applied date. 3,834 applications in the
25 Sep 2026 export have a later-stage date and no Applied date; without the
backfill they would fall out of the funnel.

Where the CRM recorded a state without a date, the status sets a floor:

| Status | Floor |
| --- | --- |
| Applied, Final Decision, Closed Won | Applied |
| Offered | Offer |
| Deposit Paid Status FullyPaid / fullyPaidWaitingForApproval | Deposit |
| CoE Received, Visa | CoE (Visa may mean applied, not granted) |
| Enrolled | Enrolled |

## Pipeline and funnel

The same students read two ways. **Pipeline** puts each student in one stage, their
super status, so its rows sum to the total. **Funnel** is cumulative: a student at
Deposit is also counted at Offer and Applied, and "% of applied" reads each row
against the first.

**Active / closed lost**: a student is closed lost only when every in-scope
application is `Application Closed Lost = Yes`. One live application keeps them
active.

## Against last year

The same months one year earlier, read twice:

* **At this point**: last year's stage dates replayed up to the same day a year
  before "today", so a part-way intake is set against a part-way intake.
* **Final**: where last year's students stand now.

"Today" is the newest stage date in the loaded export, not the clock.

## Caveats

* Closed lost carries no date, so "at this point" has no active/lost split.
* Deferrals have no history: a student deferred out of last year's intake is not in
  last year's replay, even if they were in it at the time.
* Visa granted is backfilled from Enrolled, so an enrolled student with no visa date
  counts as having reached Visa granted.
* Deposits with a paid status but no date (22 in the 25 Sep 2026 export) count at
  Deposit in "final" but not in "at this point".
