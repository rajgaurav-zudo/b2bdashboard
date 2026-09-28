# Commission configurator

The contracts team uses this to enter and maintain commission contracts. It also
resolves the terms that apply to a given institution and intake. The spec is in
`context.md`; this file covers how to run it and where the build differs from
the design brief (`COMMISSION_CONFIGURATOR_SPEC.md` and the `design/*.dc.html`
mockups).

* Backend: `router.py`, mounted at `/api/modules/commission`. It writes to the
  `dash_commission` schema.
* Frontend: `web/src/dashboards/commission/`, registered as the `commission`
  overview.
* Tests: `docker compose exec -e STORAGE_BACKEND=local api pytest /srv/dashboards/commission -q --import-mode=importlib -p no:cacheprovider`.

## Screens

The app navigates with search parameters, so every screen has a URL you can link
to, and `App.tsx` needed no new routes.

| URL params | Screen |
| --- | --- |
| *(none)*, plus `q`, `region`, `type`, `status`, `only=alerts\|review` | Contracts list with alert chips |
| `view=import` | Workbook import: preview, untick rows, commit |
| `c=<id>&tab=timeline` | Terms by intake, history, contract checks |
| `c=<id>&tab=effective&intake=YYYY-MM` | Resolved terms for one intake, plus a simulator |
| `c=<id>&tab=base` | Base terms configurator with the "Ready to publish?" checklist |
| `c=<id>&tab=amendments&a=<id\|new>&step=1..4` | Amendment wizard: document, scope, changes, review |
| `c=<id>&tab=documents` | Document references |
| `c=<id>&tab=audit` | Audit log with before/after for each change |

## Deviations worth knowing

* **Palette.** The screens use the codebase's tokens (`--good`, `--warn`, `--info`,
  `--purple` and the rest) and its shared classes, not the mockups' colours. They
  therefore match the other dashboards and follow dark mode. Layout and content
  follow the mockups.
* **xlsx reader.** `xlsx.py` reads the workbook with the standard library
  (zipfile + XML) rather than openpyxl, so the project needs no new dependency.
  It reads cell values, date formats and merged ranges. The merged ranges are
  what let a contract block be forward-filled the way the sheet was drawn.
* **Terms are one JSONB document.** Rules, bonuses, territory rules, exclusions,
  milestones and conditions live in `contracts.terms` rather than child tables.
  Header fields are real columns. A version snapshot stores the whole row.
* **Single-role publish.** Anyone who is signed in can publish, and when auth is
  off locally, anyone at all. There is no maker/checker split. Every publish is
  audited with the user.
* **Documents are text references.** Each amendment records a reference, a
  received date and a file name or link. There are no file uploads.
* **Phases 2 and 3 are not built.** Phase 2 would feed live counts from the
  Applications export into tier and bonus progress; for now the simulator takes
  the count as an input. Phase 3 is the commission ledger (per-student
  commission, receivables, true-ups). Recalculation batches are raised and
  shown, but nothing processes them yet.
* **EXTENSION moves the end date only.** It does not widen an `UP_TO` intake
  scope. If the contract should also cover later intakes, edit the base terms.
* **Importer defaults.** Tiered rules imported from the workbook get
  `count_metric = ENROLMENT` and `count_scope = ACADEMIC_YEAR`, because the
  sheet does not say how students are counted; check these on review. Bonuses
  take their count scope from the criteria text. A range the parser cannot
  read is kept as `tiers_raw` and flagged for review, rather than guessed. Imports always create drafts; they
  never publish.
* **The checklist reflects saved state.** The "Ready to publish?" panel comes
  from the server, so it updates on save. Publish is disabled while there are
  unsaved edits. A refused publish (409) shows the checklist that refused it.
