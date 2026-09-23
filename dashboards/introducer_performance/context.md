# Introducer performance — context

> **Paste the full CONTEXT.md spec here.** This file is the source of truth for this
> dashboard: its sha256 is stored in `core.dashboards.context_sha`, so when a number
> moves you can tell whether the spec changed or the data did. Nothing reads it at
> runtime — it is for humans and for agents working on this dashboard.

Until it is filled in, the contract the code relies on is:

- **Inputs** — introducers master (one row per partner, join key `Partner Name`) and
  applications (one row per application, 2022 onward, `Application Introducer Name`).
- **Deposits** — `active = FullyPaid AND NOT closed lost`; `closed = FullyPaid AND closed lost`.
- **Intake cycles** — Jan / May / Sep. Nov & Dec roll into the *following* January.
- **Current year** — the newest intake year holding ≥10% of the peak year, never `max(year)`.
- **Scope** — `Lifecycle Stage = Customer` OR any paid deposit at any stage.
- **Grouping dimensions** — SRM team, SRM owner, country, lifecycle stage.
- **Filters** (URL params, read by every view):
  - `from`/`to` (`YYYY-MM`) — an intake-period window replacing the current year; the
    default is the whole current year, so no params means the unfiltered page. A row with
    no intake month counts only when the window covers its whole year. Rows after `to` are
    not scored. The funnel always shows every year.
  - `teams` (`|`-joined) — SRM team; a blank team or an introducer not in the CRM is `Unassigned`.
  - `cycles` (`0,1,2` = Jan/May/Sep) — intake cycle; applies to deposits, not to book membership.
  - `compare=1` — the same filters over the window shifted back `12·⌈months/12⌉` months
    (same period last year); tiles are matched to the prior window by position.
