# Introducer 360 — context

One introducer, end to end: every stage its applications passed through, when they
passed through it, and what became of them — against a window, an intake, and the
same window a year earlier.

This is the spec. Its sha256 is stored in `core.dashboards.context_sha`, so when a
number moves you can tell whether the spec changed or the data did.

## What it is built from

The design handed over was a **counsellor pipeline dashboard** (`README.md` and
`Counselor Pipeline Dashboard.dc.html` in the handoff bundle): a filter bar, eight
pipeline widgets on one line, two of them groups that open a breakdown, and a wide
counsellor-wise modal. The layout, the interaction model and the card anatomy are
that design. What each number *means* is this file, because the mock data behind
the prototype does not exist here and the CRM's does.

Two exports feed it, both already platform-level and both already in the archive:
`applications` and `introducers`. Nothing new had to be uploaded — the dashboard
was fed with `POST /api/uploads/{id}/project?dashboard=introducer_360`, which is
what the archive is for.

## A stage is an event, not a status

The applications export carries a timestamp for every status an application has
passed through:

| Column | Stored as |
| --- | --- |
| `Timestamp of 'Draft' status` | `at_draft` |
| `Timestamp of 'Ready to Apply' status` | `at_ready` |
| `Timestamp of 'Applied' status` | `at_applied` |
| `Timestamp of 'Offer' status` | `at_offer` |
| `Timestamp of 'Deposit Fully Paid' status` | `at_deposit` |
| `Timestamp of 'COE Received' status` | `at_coe` |
| `Timestamp of 'Visa\| Applied' status` | `at_visa_applied` |
| `Timestamp of 'Visa\| Granted' status` | `at_visa_granted` |
| `Timestamp of 'Enrolled' status` | `at_enrolled` |

Nothing on the platform was reading them. They are the whole reason this dashboard
exists as its own dashboard rather than as a tab on introducer performance: they
turn `Application Status` — a snapshot of where 227k applications sit *today* —
into a pipeline you can put a date range across.

So **Applied is not "applications whose status is Applied"**. It is applications
that entered Applied inside the window, and one application appears at several
stages because it passed through several. That is what the design's cards count,
and it is what makes the eight-card row a funnel rather than a pie.

The columns arrive as midnight — there is no time of day in the export — so they
are stored as `date`. A `timestamptz` would only invite a timezone to move a row
across a day boundary the CRM never recorded.

## Created, active, closed

Every card, every cell of the introducer-wise table, and every row of a breakdown
modal reads the same three figures over the same window:

- **created** — applications that entered this stage inside the window
- **active** — of those, `Application Closed Lost = No`
- **closed** — of those, `Application Closed Lost = Yes`

`created = active + closed`, always, by construction. Both percentages on a card
are read against the number above them, and they sum to 100.

Note what this is *not*: "active" here is not the introducer performance
dashboard's active deposit. There it means a live fully-paid deposit in the
current intake year. Here it means an application that entered a stage in the
window and has not since been closed lost. The two dashboards answer different
questions and the same word is the right word in both; when they need to be
compared, compare `Deposit paid` created against that dashboard's deposits, not
its active count.

## The eleven stages and the eight cards

Funnel order, and which card each stage is drawn on:

| # | Stage | Card |
| --- | --- | --- |
| 1 | Draft | Draft |
| 2 | Ready to apply | Ready to apply |
| 3 | Applied | Applied |
| 4 | Offer | Offer |
| 5 | Deposit paid | **Deposits** |
| 6 | CoE received | **Deposits** |
| 7 | Visa applied | **Deposits** |
| 8 | Visa granted | Visa granted |
| 9 | Enrolled | Enrolled |
| 10 | Partial deposit | **Awaiting outcome** |
| 11 | Deferral awaiting approval | **Awaiting outcome** |

Eight cards on one line, two of them groups, exactly as the design specifies. The
grouping is the design's own — *Deposits* there is Deposit + CAS + Visa Applied,
and CoE Received is this CRM's CAS.

**A group is a sum of events, not of applications.** One application that paid a
deposit, received its CoE and applied for a visa inside the same window entered
three stages and is counted three times on the Deposits card — exactly as it would
be if the three had their own cards. The breakdown modal is where that stops being
an assertion and becomes visible, which is why the group cards open one.

### The two stages that are states, and are not windowed

The other nine are events. These two are not: the CRM records a partial deposit
and a deferral awaiting approval as flags, not as transitions, and there is no
timestamp for either.

| Stage | Definition (`sources/context.md`) |
| --- | --- |
| Partial deposit | `Deposit Paid Status = PartiallyPaid` |
| Deferral awaiting approval | `FullyPaid` · `Deferred Initiated = Yes` · `Deferred Approved = No` |

Their `active` figure — the flag, and not closed lost — is therefore exactly the
platform's **Active PD** and **Active DAA**. On the 7 Sep export the whole book
gives 29 and 57; the same SQL against the introducer performance dashboard's own
table returns the same numbers for the same slice, which is the check that the two
dashboards have not drifted apart on a shared definition.

**They ignore the date range, and the card says so.** They are reported as they
stand in the export, "as of" its newest date. The alternative was to pick some
other column's date to stand in for theirs — pipeline entry was tried first, and
it makes the card read 0 on any window shorter than a month, which is an artefact
of the substitution rather than a fact about the business. Inventing a date is
worse than admitting there isn't one. They still answer to the introducer and
intake filters, which is where the useful question lives — *this partner's partial
deposits in the 2026 intake* — and Compare leaves them alone, because a state has
no last year to be compared with.

A group card whose members are all states is a state card: `Awaiting outcome`
carries no delta and is labelled "as of", not "this week".

For the same reason, the introducer-wise table's total column counts **stages
entered** — the nine events — and not the eleven columns beside it. A total that
added the two states would be part one window and part all time, and it would
move when the window did not. The state columns are still there, and still
answer to the introducer and intake filters; they are simply not summed into a
figure that claims to be about a week.

Everything else about deposit states follows `sources/context.md` without
deviation. Two dashboards disagreeing about what `FullyPaid` means would be a bug,
not a preference.

### Course category is stored, and nothing here filters on it

The introducer performance dashboard counts deposits **Academic-only**, and says
why: a six-week language course averaged into the same number as a three-year
degree hides both. That rule is about *deposit reporting* on that dashboard.

This one is a pipeline, and a funnel that silently dropped every language
application would misstate every stage above the deposit as well as the deposit
itself. So `course_category` is ingested by the same rule and stored on every row,
and no figure on this page filters by it. If a course split is wanted here it is a
group-by on a column that is already there, not a re-ingest.

## Filters

**Introducer** — the design's counsellor multi-select. Searchable because there
are 3,605 partners with applications, not seven counsellors: the menu lists the
largest by lifetime volume and narrows as you type. Counts in the menu are
lifetime, not windowed — a partner who did nothing this week is exactly the one
someone opens this dashboard to look at.

**Date range** — the design's eight presets and its two-month custom calendar,
over the stage dates. Weeks run **Monday to Sunday**, to agree with the calendar
that picks them. (The log dashboard's weeks run Saturday to Friday; that is a
property of *its* export's week definition, not a platform rule.)

**Intake** — the design's six intake presets become this data's intake years and,
within a chosen year, its three cycles (Jan · May · Sep). Intake period is
`Actual Intake Year` and `Actual Intake Month`, per `sources/context.md`: where
this dashboard says 2026, it is the actual intake year of the application. The
cycle index is derived from the month the same way it is next door — Nov–Mar Jan,
Apr–Jul May, Aug–Oct Sep — but the **year is literal**: a November 2026 intake is
a 2026 intake, and nothing here reads `cycle_year`.

**Compare** — off by default, as the design specifies. On, every card gains the
change against **the same calendar dates one year earlier**, and the previous
figures beside each metric. A stage with nothing to compare against shows no
delta rather than `+∞%`.

## "Today" is the export's newest date, not the clock's

Every preset is anchored on the **latest stage event in the loaded file**, not on
the server clock. An export taken on a Sunday would otherwise open on a week that
has barely started and read as a collapse in activity — the trap the log
dashboard's `pick_current_week` exists to avoid, arrived at again for the same
reason. The anchor is shown on the page, so the window is never mysterious.

The default range is **This week** and clearing the date filter returns to it, not
to empty. That is the design's rule and it is kept.

## The lower half

The design's lower dashboard (Due soon, Recent activity, Intake commitment, Team)
is *existing* content on the counsellor home screen; three of those four have no
counterpart in these two exports, and inventing them would put numbers on the page
that no file backs. What is there instead, in the same two-column shape:

- **This partner** — lifecycle stage, contract status, country, SRM team and
  owner, customer since, from the introducers master. Only when exactly one
  introducer is selected; that is the 360.
- **Lifetime** — applications, offers, live deposits, enrolments and closures over
  the whole book in scope, ignoring the window. What the window is a slice of.
- **Top introducers** — the partners the window actually belongs to, ranked, each
  one a click away from becoming the selection. With nothing selected this is the
  way in.
- **Intake commitment** — deposits paid for the selected intake against the same
  point in the previous intake year. Day-of-year against day-of-year, so a partial
  year is compared with a partial year.

**Due soon is not built.** Nothing in either export carries a task, an interview or
a due date. It needs a third source.

## Deviations from the handoff worth knowing

- **The visual language is the platform's, not the prototype's.** The handoff asks
  for both "recreate in the target codebase's existing environment, using its
  component library and styling approach" and high colour fidelity to a purple
  Plus Jakarta Sans design. They cannot both hold inside a platform whose visual
  language was signed off elsewhere (`web/src/index.css`), so the layout, the card
  anatomy, the interaction states and the type *scale* are the design's, and the
  palette and typeface are the platform's. Every structural rule in the handoff's
  review list is kept: eight widgets on one line with no horizontal scroll, equal
  card heights including the group cards, totals only on group cards, table cells
  mirroring the card layout, Compare off by default, per-filter clears that
  `stopPropagation`, intake starting unselected, and This week as the date
  default.
- **The prototype's open blocker does not arise.** Its stage labels were cramped
  because eight cards sat in a 1,180px content area minus a 236px sidebar. Here
  the pipeline card spans the platform's full width and the rail collapses, so the
  labels are set at their intended size rather than at 9px.
- **On a narrow screen the row folds; it never scrolls.** The rule the handoff set
  is that the pipeline does not scroll sideways, which says nothing about it being
  one line on a phone. Below 1,080px the eight cards become four and four, below
  760px two and two. Labels are never truncated, never wrapped to three lines, and
  never put behind a horizontal scrollbar — the three fixes the handoff rejected
  by name.
- **The numbers are queries, not a multiplier.** The prototype scaled one set of
  mock figures by a factor derived from the filter state. Here the filter state
  *is* the query, which is what the handoff says a real implementation should do.

The page lives in `web/src/dashboards/introducer360/`, registered by slug in
`web/src/dashboards/registry.tsx`. Every filter is held in the URL rather than in
component state, for the reason the log dashboard's week is: a pipeline that needs
explaining is something people send to each other, and the link has to carry what
they were looking at. The two overlays — a group breakdown and the introducer-wise
table — are separate URL keys, so each is shareable on its own.

## Data notes, and what they cost

Measured on the 7 Sep export (227,236 rows):

- **313 fully-paid deposits carry no `Deposit Fully Paid` timestamp** (1.3%), and
  16 rows carry the timestamp with no deposit status. Those 313 are invisible on
  the Deposit paid card at every window, and visible in the lifetime figures,
  which read the status rather than the date. Reported as a data note rather than
  patched, because dating them by anything else would be inventing a date.
- **84,520 rows have no introducer name** (37%). They are one row in every list,
  named `Not attributed`, rather than being dropped — a third of the pipeline
  going missing without explanation is worse than an ugly row.
- **An export from before the timestamp columns existed loads cleanly and shows an
  empty pipeline.** `stats.no_stage_dates` on the load records how many rows
  carried no stage date at all, and the overview refuses with a readable message
  rather than rendering eight zeroes, when *no* row has one.

## Open questions

- Should a group card count distinct applications rather than events? It is a
  one-line change; events is the reading the design's own grouping implies.
- Partial deposits and deferrals awaiting approval are not windowed at all. If the
  CRM can export a `Deposit Partially Paid` timestamp or a deferral-initiated one,
  they become ordinary event stages, the "as of" label goes away, and Compare
  starts working on them.
- Closed lost is a terminal fact, not a dated one, so "closed" within a window
  means "entered this stage in the window and is closed lost *now*" — it does not
  say the closure happened in the window. `Application Closure Reason` and a
  closure timestamp, if the export can carry one, would fix that.
