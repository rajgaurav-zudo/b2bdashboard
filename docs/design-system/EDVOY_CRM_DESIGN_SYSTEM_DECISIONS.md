# Edvoy CRM Design System v1.0.0: Decisions, exceptions and author checks

Frozen as v1.0.0 by user authorisation on 1 October 2026 following independent acceptance in `DESIGN_SYSTEM_V1_ACCEPTANCE.md`. The user-approved decisions P1–P6 (1 October 2026) are recorded in `CLAUDE_DESIGN_INSTRUCTIONS.md` and are **settled**. They are not reopened here.

## P6 — Purple standardisation (user decision, 1 October 2026)

**Decision:** standardise the whole system on the Business Performance purple language and its components (tables included). **Retire the Global CRM native layer.** This supersedes the native-fidelity parts of P2 (blue Reset, screenshot colours, native table/nav); P2's Zero / No target / Unavailable distinction remains.

| Retired | Replacement |
|---|---|
| `--ecrm-crm-*` tokens (14), `--ecrm-color-canvas`, `--ecrm-text-crm` | BL tokens (`page`, `surface-subtle`, text/border scale) |
| `.ecrm-settings-nav` | `.ecrm-tabs` (links + `aria-current`) |
| `.ecrm-subtabs` | `.ecrm-segmented--raised` (links + `aria-current`) |
| `.ecrm-btn--crm-action` (blue Reset) | `.ecrm-btn--secondary` "Reset filters" |
| `.ecrm-btn--destructive-text` | none (destructive confirm = future extension) |
| `.ecrm-select--crm`, `.ecrm-select__count` | `.ecrm-select` (+ `.ecrm-count`) |
| `.ecrm-table--crm`, `.ecrm-table-wrap--crm`, `.ecrm-crm-link` | `.ecrm-table` + `.ecrm-btn--quiet` |
| `.ecrm-tag--role` | none |
| CRM-violet pagination | `.ecrm-pagination` on BP tokens (current = `selection` / `accent-border` / `accent-strong`, 8.41:1) |

The CRM screenshot is now an information-architecture reference only. Classification of every retired item: **APPROVED NORMALISATION (P6)**.

## A. Consolidations actually applied

| ID | Consolidation | Why |
|---|---|---|
| C-01 | `#5d6278` + `#5f6479` → `--color-text-muted`. `#63687c` stays as `--color-text-meta` (RC). | Visually identical duplicates. |
| C-02 | Card borders `#e6e4ee` / `#e9e6f0` / `#e6e1f0` → `--color-border-card` | Accidental variance. |
| C-03 | Row dividers `#f1eff5` / `#f0edf5` → `--color-border-row` | Same. |
| C-04 | Accent borders `#cfc6ea` / `#d9cff5` / `#d6cdf2` → `--color-accent-border` | Same role. |
| C-05 | Segment tracks `#f1eff6` / `#f4f2f8` → `--color-surface-track`; track radius 9 → 8. | Same role. |
| C-06 | Menu hovers `#efe9fb` / `#efe9fd` → `--color-selection-hover` | Same role. |
| C-07 | **Radius.** Input and tag-Apply 7px → 8px; choice chip 7px → 6px. **Retained source exceptions (not consolidated):** 7px raised segment, 5px status badge, 3px bar, 2px legend swatch, all tokenised (`--ecrm-radius-7/5/3/2`). | Only the listed control radii were merged. |
| C-08 | Focus: body rule `#6d3fd9` vs component `style-focus` `#3a2a78` → structure `#3a2a78` | The dominant, more specific rule. |
| C-09 | **Type.** One-off sizes 16, 17 and 22px mapped to the named scale; options/inputs 13 / 13.5 / 14 → 13 or 13.5. **Retained source exceptions:** 15px (`--ecrm-text-emphasis` for finding value and large delta), 10px chevrons and sort glyph, 9.5px help glyph. Native table/sub-tab typography and the Settings root label were retired by P6. | Retained BP sizes keep their source appearance. |
| C-10 | **Weight.** 600 → 650 for options and selected states. **Retained 600** (`--ecrm-weight-600`): inactive tab, raised segment item, eyebrow, text button, filter chip. **Added 550** for hierarchy child names (BL `nmS`). The native table header was retired by P6. | Appearance is preserved; the earlier claim that 600 survives only on tabs was wrong. |
| C-11 | Duplicate KPI tint token `--selection-kpi` removed; `--surface-kpi-sel` is the single token. `--surface-field-active` aliases `--surface-child` (same `#fbfaff`, different role). | R2 duplication. |

## B. Deliberately separate patterns

- **Filled vs raised segmented appearance.** Both are canonical. The context chooses; neither maps to navigation or selection (P3).
- **Floating popover vs inline (in-drawer) dropdown elevation.**
- **Pagination (record lists) vs *Show all N* (analytics).** Both use BP tokens.
- **BP base list table vs analytical table composition.** One BP table family; analytics adds grouped headers, hierarchy and selection. The native CRM table is retired.
- **Accent fill vs structure ink and ring.**
- **Zero vs No target vs Unavailable** (P2).
- **Static specimens vs working recipes.** The drawer specimen is a picture; the modal is the working recipe.

## C. Recorded decisions and exceptions

| ID | Item | Status in v1.0.0 (P6) |
|---|---|---|
| D-00 | Source authority | **Settled (P1).** BL is the frozen baseline. RC-only patterns are tagged `[RC]` and labelled candidates unless accepted (drawer anatomy and mechanics, `FS(a)`, raised segment). |
| D-01 | Native blue Reset | **Retired (P6).** Reset uses `.ecrm-btn--secondary`. |
| D-02 | CRM violet vs BP accent | **Resolved (P6):** BP accent `#6d3fd9` only. |
| D-03 | CRM font and top-nav ink | Figtree is authoritative (P2). The production CRM font is not established by the screenshot. The top nav uses BL ink. |
| D-04 | Destructive confirmation | **Future extension (P5).** Native text-only destructive styling was retired by P6; no destructive component is included. Not a v1 prerequisite. |
| D-05 | Page ground | **Resolved (P6):** BP `page` `#fff`; canvas token removed. |
| D-06 | Soft-band left accent border | Retained source exception for `.ecrm-control-band` only. The other `viewStyle` variants are rejected. |
| D-07 | Blue highlight `#2f56a8` vs structure ring | Settled under P3: selection rings use structure `#3a2a78`; the blue highlight is kept for *High volume* and the investigation label. Business Performance is read-only, so nothing there is migrated. |
| D-08 | Info callout | **Restored to BL** `role="note"` values. |
| D-09 | Validation / error | **Approved extension (P5).** Uses existing grounds only. The warning and error callout borders equal their grounds; no new border literal. |
| D-10 | Edit mode, approval, history, destructive dialog, skeleton | Read-only detail and minimal busy are **approved (P5)**. The rest are **future extensions**, not dependencies of this freeze. |
| D-11 | Missing targets | **Settled (P2, kept under P6).** `—` with sr-only "No target set" plus a visible legend; zero is shown as `0`; Unavailable has its own text. |
| N2 | Investigation shadow `0 4px 14px rgba(30,50,90,.08)` | Retained BL source exception, tokenised `--ecrm-shadow-investigation`, scoped to `.ecrm-investigation`. It is an in-flow element, not a floating overlay; no general card shadows. |
| M7 | Inactive sub-tab ink | **Moot (P6):** native sub-tabs retired; raised segmented items use BL ink. |

## D. Rejected or removed

Every native-CRM variant and colour (P6); a blue primary button; filled destructive buttons; gradients; card shadows; the `viewStyle` variants "Underline tabs", "Outlined card" and "Bold band"; skeleton loaders; the `AGEC` palette as a global scale; the `#0052cc` Reset hover; the 60%-white busy overlay; the earlier `#f3dfb3`, `#f1c7c1` and `#fafbfb` literals (no source).

## E. Author checks (not independent acceptance)

Historical RC2 author checks are in `RC2_CORRECTION_REPORT.md` §4. RC3 author checks are in `RC3_PURPLE_STANDARDISATION.md`; current independent results are in `DESIGN_SYSTEM_V1_ACCEPTANCE.md`. Historical author-check summary:

- Author browser harness at 1440×1000, 1280×1000 and 1024×1000 (iframe viewports, unmodified gallery): **all scripted checks passed**.
- Screen-reader testing: **NOT TESTED**.
- axe-core: **NOT TESTED** (not available to the author). The harness ran its own contrast and ARIA-validity scan instead.
- Production CRM runtime and font: **NOT TESTED** (cannot be established from one screenshot).
