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
