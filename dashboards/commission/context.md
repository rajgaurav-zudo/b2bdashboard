# Commission — context

The contract terms we are paid on, per institution: base commission, tiers,
bonuses, territory and exclusions, plus every amendment since, resolved into the
terms that apply to one intake. It is an application, not a set of views: the
contracts team writes the data here (the configurator and the workbook importer)
and the calculation reads it.

This is the spec. Its sha256 is stored in `core.dashboards.context_sha`, so when a
number moves you can tell whether the spec changed or the data did.

## Source

No uploads. Contracts are entered in the configurator or imported from the
contracts workbook (`POST /api/modules/commission/import/preview`, then
`/import/{batch}/commit`). Everything lives in the `dash_commission` schema
(`migrations/001_init.sql`). Endpoints are in `router.py`, mounted at
`/api/modules/commission` behind the same auth as `/api`.

## Data model

* **Contract**: one agreement with one party (an institution, pathway provider or
  outbound agent) for a period. Header fields are columns: party, party type,
  region, status, start and end date (or rolling), currency, VAT treatment and
  rate, fee basis, academic years, intake scope, territory type. The terms are one
  JSONB document (`terms`): rules, bonuses, territory rules, exclusions, campuses,
  targets, milestones, payment and other conditions.
* **Version**: publishing freezes the whole contract into `contract_versions`
  (`snapshot_json`) with an `effective_from`. Editing a published contract edits
  the live row only and sets `has_unpublished`; nothing downstream sees it until
  the next publish.
* **Amendment**: a numbered change to a published contract, from a document:
  RATE_CHANGE, RULE_ADDITION, BONUS_INCENTIVE, SCOPE_CHANGE, INTAKE_NOTE,
  EXTENSION or SUSPENSION. It has a scope (from/until intake, a date window, or
  both) and a `changes` document. DRAFT until published; published amendments are
  never edited.
* **Audit log**: every write, with before and after, user and document reference,
  in the same transaction as the write.
* Intakes are `YYYY-MM` strings.

## resolveTerms(institution, intake)

`resolve.py`, a pure function over loaded contracts; the effective-terms screen,
the timeline and the simulator all call it.

1. Contracts for the institution are tried **latest start date first**; the first
   that yields terms wins. If none does, the reason from the latest is returned
   ("No valid contract for Sep 2026: the contract ended 31 Aug 2026").
2. The **version** is the latest whose `effective_from` is on or before the
   intake's first day (the first version when none is yet).
3. The contract must **cover** the intake: published; not EXPIRED; not INACTIVE
   from its status date; between start and end (end extended by any published
   EXTENSION; rolling has no end); inside the intake scope (every intake, listed
   intakes, or up to an intake). Status is live and needs no new version.
4. **Published amendments** are applied in order of received date then number,
   each only where its scope matches. A date window is checked against the intake
   start, or against a student date (application, offer, deposit) when the
   amendment's basis says so; without that date it is reported as conditional.
   A SUSPENSION stops resolution: no terms.
5. Every rule, bonus, territory rule and exclusion carries its **source** ("Base
   v2", "Amendment #3").

## Calculation

`calc.calculate(terms, student)`, in this order:

1. **Territory**: an EXCLUDE matching nationality, residence or country makes the
   student ineligible; with INCLUDE rules or a Not-global contract, one must match.
2. **Exclusions**: by course level (research degrees, online/distance, franchise),
   campus or student flag.
3. **Rule**: the most specific that matches: institution-specific, then campus,
   then the narrowest course-level list, then priority.
4. **Rate**: flat or percentage of the fee. A TIERED rule reads the tier for the
   pooled count at the institution. RETROACTIVE re-rates every student to the tier
   reached; MARGINAL rates each student by their own position.
5. **True-ups**: `calc.accrue` turns students joining one by one into ledger
   entries. When a retroactive tier is crossed, each earlier student gets a
   TRUE_UP entry for the difference.
6. **Bonuses**: those attached to the rule or course level. A rate uplift adds a
   percentage, a fixed bonus adds per student, a lump sum is reported separately
   when the count is reached. Progress to the next threshold is shown.
7. **VAT**: inclusive (the amount contains VAT), exclusive (added on the invoice)
   or none.
8. **Milestones** split the amount by trigger (100% on enrolment by default).

## Publishing

* A contract publishes only when the **Ready to publish?** checklist is clear
  (`validation.checklist`): the always-required fields, those required by other
  choices (e.g. a VAT rate when VAT is inclusive or exclusive; an excluded
  territory for Global with restrictions; covered institutions for a pathway
  provider or outbound agent; a per-rule check of tiers, pricing and counts) and
  warnings, which do not block.
* Version 1 is effective from the start date; later versions from today unless
  another date is given. A **backdated** later version raises a recalculation
  batch from that intake.
* An amendment publishes when its checks pass: reference, received date, document,
  a valid scope inside the contract's validity (extension excepted), a published
  base, the content its type needs, sound tiers, and no unresolved clash with
  another published amendment changing the same rule for overlapping intakes. An
  amendment whose scope starts on or before today raises a recalculation batch.
* Imported items flagged `needs_review` are a warning, not a block.

## Alerts on the contracts list

* **Ends in N days**: an active contract ending within 90 days.
* **No terms for &lt;intake&gt;**: an active contract that resolves to nothing for
  the next major intake.
* **Unpublished edits**: a published contract with draft changes.
* The needs-review count covers rules, bonuses and draft amendments.

## Import

`importer.py` reads the workbook with the standard library (`xlsx.py`), one tab
per party type and region; the invoicing tab only matches institutions.

* A **block** is the rows under one institution name, merged cells read through.
  Header fields come from the first row; one rule per course-level row.
* A rule with several value rows is TIERED (RETROACTIVE); a single "Tiered" row is
  per student. Ranges that do not parse, or that Excel turned into dates, keep the
  raw text in `tiers_raw` and are flagged.
* Course levels, countries and exclusions are matched from free text; anything
  unmatched is kept and flagged `needs_review` with a note.
* **Amendments** are inferred: bonuses tied to intakes become BONUS_INCENTIVE;
  "not accepting from May 2026" becomes a SCOPE_CHANGE excluding that country
  from that intake (with the "informed on" date as received date); "Applicable
  from Jan 2027" rows become a RATE_CHANGE targeting the base rules they replace.
  A bonus whose criteria cite intakes before its amendment starts is flagged.
* Counts default to enrolments per academic year.
* **Preview** writes only the batch and reports create / update / skip per
  contract. A contract matches an earlier import by tab, name and occurrence: a
  DRAFT is updated, a published one skipped. **Commit** creates DRAFT contracts
  and amendments, one savepoint each, and cannot run twice. Nothing is published
  by import.
