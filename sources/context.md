# Shared definitions — context

Rules that belong to the CRM's files rather than to any one dashboard.

`sources.yaml` says what a file *is*. A dashboard's `ingest.py` says which columns
it takes. This file is the third thing: where a column's **values** carry a
meaning that every dashboard has to agree on. The intake-cycle months and the
day-first date order already work this way — two dashboards disagreeing about
what `03/04/2026` means would be a bug, not a preference. Course level, intake
period and deposit state are in the same category.

Nothing here runs. It is the spec; the code catches up when a dashboard is told
to use it. It is deliberately **not** a dashboard `context.md`, so writing it
does not move any `core.dashboards.context_sha` and cannot change a number that
is on a page today.

## The definitions, as given

These are the source of truth. Everything further down is the working detail —
which column the value comes from, how it is normalised, what each rule costs.
**The code adds no condition that is not in this table.** All three deposit
states are live-money states: paid or part-paid, and not closed lost.

| Term | Definition |
| --- | --- |
| **Active deposit** | `Application Closed Lost = No` · `Deposit Paid Status = FullyPaid`, summed over **two** deferral states: `Initiated = No` with `Approved = No`, **and** `Initiated = Yes` with `Approved = Yes` |
| **Active DAA** — deferral awaiting approval | `Deferral Initiated = Yes` · `Deferral Approved = No` · `Application Closed Lost = No` · `Deposit Paid Status = FullyPaid` |
| **Active PD** — partial deposit | `Deposit Paid Status = PartiallyPaid` · `Application Closed Lost = No` |
| **Intake period** | `Actual Intake Year` and `Actual Intake Month` — those columns, not any other date |
| **Academic** | course level in `ALevel`, `ASLevel`, `Doctorate`, `Foundation`, `GCSEgradesAC`, `Postgraduate`, `PreMasters`, `Undergraduate` |
| **Language** | course level `Language` |
| **Pre-sessional English** | course level `Presessional` or `PresessionalEnglish` |

These apply to every dashboard. Today only introducer performance reads these
columns at all; the logs dashboard touches `Deposit Paid Status` once, in a
wrong-file hint, and nowhere else.

## Applications — intake period

Intake year and month come from **`Actual Intake Year`** and **`Actual Intake
Month`**. Not the application date, not the enrolment timestamp, not a year
scraped from any other column. Where a dashboard reports "2026", it is the
actual intake year of the application.

`ingest.py` resolves both columns by those names and stores `intake_year` and
`intake_month` unchanged, and **`intake_year` is the year every figure is
reported in.** A November 2026 intake is a 2026 intake.

`ingest.py` also derives `cycle_year` — November and December rolled into the
**following** January intake, so `Actual Intake Year = 2025, Month = November`
gives `cycle_year = 2026`. It is still stored, and nothing reads it. It was the
reported year until the definition above settled it; the roll is a real
admissions fact, but it is not what the column says, and a figure that cannot be
reproduced by filtering the sheet is a figure nobody can check.

The difference is small and always in the November/December rows. On the 1 Sep
export, moving from the cycle year to the literal column took the 2026 Academic
book from **1,920 to 1,922** active deposits, DAA from **9 to 12**, and PD from
**13 to 15**. Switching back is a rename in `metrics.py`; a test sets the two
columns apart so the read model cannot relapse onto `cycle_year` unnoticed.

## Applications — course level

`Application Course Level` collapses into **three** categories. Every figure
broken down by course reports these three and not the raw column.

| Category | Course levels |
| --- | --- |
| **Language** | `Language` |
| **Pre-sessional English** | `Presessional`, `PresessionalEnglish` |
| **Academic** | `ALevel`, `ASLevel`, `Doctorate`, `Foundation`, `GCSEgradesAC`, `Postgraduate`, `PreMasters`, `Undergraduate` |

Matching is on the **normalised** value — lowercased, punctuation and whitespace
stripped — so `PresessionalEnglish`, `Pre-Sessional English` and `pre sessional
english` are one thing.

The whole 227,234-row export (1 Sep) contains exactly these eleven levels and one junk
value:

| Course level | Rows | Category |
| --- | --- | --- |
| `Postgraduate` | 162,392 | Academic |
| `Undergraduate` | 39,332 | Academic |
| `Foundation` | 15,223 | Academic |
| `Doctorate` | 4,458 | Academic |
| `Language` | 3,614 | Language |
| `PreMasters` | 1,226 | Academic |
| `PresessionalEnglish` | 972 | Pre-sessional English |
| `ALevel` | 9 | Academic |
| `Presessional` | 4 | Pre-sessional English |
| `ASLevel` | 2 | Academic |
| `GCSEgradesAC` | 1 | Academic |
| `September` | 1 | — a shifted column, not a course level |

So the list above is complete against the data. There are no blank course levels
in this export.

### Academic is matched as the residue, not as the list

The list is the definition; the **code implements it as "everything that is not
Language and not pre-sessional"**, which is the same answer for all eleven real
levels and differs only on a value nobody has defined.

The reason is what happens when the CRM adds a twelfth level. As a residue, a new
`IntegratedMasters` reports as Academic the day it appears in the export. As a
closed list it would fall out of every deposit figure silently, because deposits
are Academic-only — a load that succeeds and quietly undercounts, which is
exactly the failure mode this platform has already hit once.

The cost is the `September` row: one shifted cell, counted as Academic instead of
being flagged. One row against a silent undercount of an entire course level is
the trade being made. **Say so if the closed list is wanted instead** — it is a
one-line change in `_course_category`, and the right follow-on would be a data
note listing any level that matched nothing.

### A file with no course levels at all is Academic

Whether a blank is `Unspecified` depends on the file it came from. In an export
that carries course levels, a blank one is a gap in the CRM and is named so it
stays visible. In an export that carries **no** course levels — one from before
the column existed — every row is Academic.

Without that second rule, loading an older export would mark every row
`Unspecified`, and since deposits are Academic-only the dashboard would report
zero deposits while reporting the load as a success.

### Deposits are Academic-only

On the introducer performance dashboard, every deposit figure — the headline, the
cohort tiles, the funnel, the cadence table, and DAA and PD with them — counts
**Academic** rows only. Language and pre-sessional English are reported in their
own section, with their own deposits, DAA and PD.

Averaging a six-week language course into the same deposit number as a
three-year degree hides both: the degree intake is diluted by volume that behaves
nothing like it, and the language business is too small to ever be visible inside
it. On the 1 Sep export the whole non-Academic book is 19 deposits in 2026
against 1,922 Academic ones — about 1%, and invisible unless it is reported
separately.

**Scope is deliberately not narrowed.** An introducer who has only ever sold
language courses still enters the book on that deposit and still appears in the
course section. Only the *deposit counting* is Academic; who counts as an
introducer is unchanged.

## Applications — deposit state

`Deposit Paid Status`, `Deferred Initiated (No/Yes/All)` and `Deferred Approved
(No/Yes/All)` together produce **three separate reported states**. They are
mutually exclusive, they are never summed into one "deposits" figure, and every
one of them is a *live* state — nothing closed lost is in any of them.

| State | `Deposit Paid Status` | `Closed Lost` | `Deferral Initiated` | `Deferral Approved` |
| --- | --- | --- | --- | --- |
| **Active deposit** — no deferral | `FullyPaid` | No | **No** | **No** |
| **Active deposit** — settled deferral | `FullyPaid` | No | **Yes** | **Yes** |
| **Active DAA** | `FullyPaid` | No | **Yes** | **No** |
| **Active PD** | `PartiallyPaid` | No | — | — |

In one line: a full, live deposit is active when its deferral is **either absent
or settled**, and DAA while the decision is outstanding.

Active deposit is written as a **sum of two rows, not as a residue.** The two
phrasings agree on every row the CRM actually produces, and differ on one cell:
`Approved = Yes` with `Initiated = No`, which the sum reaches and "not awaiting
approval" would have swept in. See the open question below — it is 3 rows, none
of them a live full deposit, so it costs no figure today.

A deposit whose deferral is still waiting on a decision is real money that is not
yet a seat in any intake, and a partial deposit is a commitment that has not
cleared. Rolling either into the headline overstates the intake; hiding both
loses money the team is actually holding. Three numbers, each honest about what
it is.

`closed = FullyPaid AND closed lost` is unchanged and stays out of all three.

### An approved deferral is a settled deferral, and stays in the headline

This is the rule that decides how big DAA is, so it is worth being explicit.
`Deferral Initiated = Yes` on its own is **not** DAA — it is the entire deferral
population, and almost all of it has already been decided. Of the active deposits
carrying an initiated deferral, **2,117 of 2,174 are also `Deferred Approved =
Yes`** (1 Sep export).

| Rule | Active deposits affected |
| --- | --- |
| `Initiated = Yes` (initiated only) | 2,174 |
| `Initiated = Yes AND Approved = Yes` — settled, **counted as active** | 2,117 |
| `Initiated = Yes AND Approved = No` — **DAA** | **57** |

An approved deferral has a decision and an intake; it is not awaiting anything,
and the student is still coming. Counting it as active is what keeps DAA at the
57 genuinely-undecided rows rather than a number thirty-eight times larger with a label
that is false for 97% of it.

On the 2026 Academic book that is **383 approved deferrals inside the 1,922
headline**, against **12 DAA** beside it.

### Both deferral columns are read, not just the first

`Deferred Approved` is the second half of the DAA test, not decoration. Reading
`Deferred Initiated` alone would move 12.5% of every deposit figure behind the
"awaiting approval" label. Removing only the undecided rows moves the headline by
well under a percent — the large number was never awaiting approval.

### The Active tile reports the book; cohort tiles report their members

DAA and PD sit beside every tile. On the **cohort and leak tiles** they are
summed over that tile's **members**, because those tiles are statements about a
subset of partners — Dormant's PD is Dormant's PD.

The **Active tile is scoped to the whole book instead**, and this is deliberate.
Its deposit figure is already the complete current-year number: an introducer
holding an active deposit is an Active member *by definition*, so nothing is
missing from it. DAA and PD are not, because membership requires a **paid**
deposit — a partner whose only 2026 money is awaiting approval never becomes a
member, and that money used to fall off the card entirely. On the 1 Sep export
that hid 5 of the 12 DAA and 2 of the 15 PD.

So the Active tile's three figures now describe one population, and they tie
exactly to the Academic row of the course split. Under member scoping they did
not, and the two sections of the page disagreed.

### Open questions — flagging, not deciding

1. **Two small statuses have no category.** `fullyPaidWaitingForApproval` (21
   rows) and `DepositRejected` (21). Neither is full, partial nor deferred. They
   are excluded from all three states — the `deposit_fully_paid` test is an exact
   match on `fullypaid`, so the waiting-for-approval rows have never counted.
   Note these are a *deposit* approval, unrelated to the *deferral* approval
   above; the similar names are the CRM's, not ours.
2. **PD ignores deferral entirely**, as defined. A `PartiallyPaid` row with a
   deferral initiated is PD, not DAA, because DAA is defined on `FullyPaid`. 91
   rows are in that overlap. Say so if they should be reported separately.
3. **One deferral cell is reported by nothing.** `Deferral Approved = Yes` with
   `Deferral Initiated = No` is in neither half of the active-deposit sum, and
   DAA needs an initiation it does not have. The export holds **3 such rows, 0
   of them live and fully paid**, so no figure moves. It is a CRM
   contradiction — approved without ever being asked for — and leaving it
   unreported keeps it visible rather than folding it into the headline. Worth a
   data note if the count ever leaves zero.
4. **Approved deferrals are not separately visible.** They fold into the active
   deposit count, which is the definition, but it means the 383 approved
   deferrals in the 2026 Academic headline cannot be read off the page. A fourth
   figure is a small change if it turns out to be wanted.
