# Edvoy CRM Design System v1.0.0

Status: **v1.0.0: purple standardisation (P6), frozen on 1 October 2026.** This release retires the native-CRM visual layer: one Business Performance purple language for every CRM surface, Settings pages included. Independent acceptance passed; the user authorised this freeze on 1 October 2026. See `DESIGN_SYSTEM_V1_ACCEPTANCE.md` and `RELEASE_v1.0.0.md`. Authoring rules are in `CLAUDE_DESIGN_INSTRUCTIONS.md`.

## 0. Adoption block (copy into every CRM task)

> **Design authority:** `EDVOY_CRM_DESIGN_SYSTEM.md`, `css/edvoy-crm-design-tokens.css`, `css/edvoy-crm-components.css`, and `gallery/EDVOY_CRM_COMPONENT_GALLERY.html` (behaviour recipes: `gallery/edvoy-crm-gallery-recipes.js`).
>
> Inspect these before implementation. Reuse canonical components and tokens. Do not invent colours, typography, spacing systems, cards, buttons, tables or interaction patterns where a canonical pattern exists. If a new product need is not covered, propose a design-system extension explicitly rather than silently creating a project-local visual pattern.

Short form: **Use Edvoy CRM Design System v1.0; do not invent visual primitives.** The freeze gate has passed. Target Planner adoption is a separate task and has not been performed.

## 1. Principles

1. **One CRM visual language.** Reuse the canonical components. Nothing is reinvented per project.
2. **Selection changes focus; navigation changes location.** Choosing a KPI, finding, evidence card, bar, segment or option updates the view in place and never scrolls. Only explicit navigation (a link, tab, page switch or *Investigate →*) moves the user. Markup: navigation uses `aria-current`; selection uses `aria-checked`, `aria-pressed` or `aria-selected`. **Appearance is not tied to either:** both segmented appearances accept both kinds of state (P3).
3. **Overview first → details on demand → edit only when requested.**
4. **Progressive disclosure** (*Show all N*, row expansion, `<details>`) instead of permanently giant tables.
5. **Business language** in labels, empty states and errors. The words themselves belong to the consumer.
6. **Comparison rendering.** Sign (+/−) and arrow direction (↑/↓) describe the **arithmetic movement**. Colour, and whether an arrow is shown, describe **desirability**, which the consuming application classifies for each metric (higher-is-better, lower-is-better or neutral). Neutral and unchanged movement keep the sign and show no arrow. A falling lower-is-better metric is ↓ in positive green. Hidden text names the meaning (improvement, deterioration, neutral, unchanged), so colour is never the only signal.
7. **Structure ≠ semantics.** Accent and structure colours mark selection, structure and series, never good or bad.
8. **Zero, No target and Unavailable are distinct.** Zero is rendered as `0`. "No target set" and "Comparison unavailable" may share the compact `—`, but each carries its own hidden text, a visible legend or title, and (for statuses) the dashed *Status unavailable* tag.
9. **The consumer owns business meaning (P4).** Metric direction, thresholds, finding vocabulary, exception logic and Reset/Apply policy belong to the consuming application. Gallery examples show these only as examples.

## 2. Source authority (P1)

| Rank | Source | Path | Governs |
|---|---|---|---|
| 1 | Business Performance v1.3.0, **frozen baseline** | `references/Business Performance v1.3.0.html` | Default source for every reusable pattern and `[BL]` token. |
| 2 | Business Performance v1.4.0-rc2.36, release candidate | `references/Business Performance v1.4.0-rc2.36.html` | RC-only patterns (`[RC]`) are **extracted candidates** unless the brief accepts them. Accepted: Filters drawer anatomy + modal mechanics (incl. `FS(a)` fields) and the raised-white segmented appearance (P3). |
| 3 (IA only) | CRM screenshot, Settings → KPI Targets | `references/crm-kpi-targets-current.png` | Information architecture only: which controls and data a Settings page needs. No authority over visual styling or the production CRM font. |

**P6 (user decision, 1 October 2026): the CRM screenshot `references/crm-kpi-targets-current.png` is no longer a visual source.** It informs page structure only (which controls a Settings page needs). No CRM-sampled colour, size or variant remains in the system.

Not supplied for this package: other CRM screenshots and production CRM runtime. `CRM_DESIGN_REFERENCE_CONTRACT.md` and the Target Configuration contracts live in the Target Planner project and were not used as design-system sources.

## 3. Tokens

All tokens are in `css/edvoy-crm-design-tokens.css` (`--ecrm-` prefix). Provenance identifies `[BL]` or `[RC]` sources; aliases point to other tokens. Approved normalisations are recorded in the decisions log. Under P6 the CRM screenshot is not a visual-token source.

- **Font:** Figtree 400–800, the exact WOFF2 bytes from the v1.3.0 bundle (hashes in the token file header and in `CLAUDE_DESIGN_INSTRUCTIONS.md`). Tabular numerals.
- **Type scale:** 26/750 page title and KPI · 21/750 section · 20/750 drawer · 18/700 panel · 14.5 tab · 14 body · 13.5 control · 13 table · 12.5 meta · 12 helper · 11.5 caption · 11/700 uppercase label · 10.5/700 badge. **Retained source exceptions:** 15px (`--ecrm-text-emphasis` for the finding value and large delta), 10px chevron/sort glyph, 9.5px help glyph.
- **Weights:** 500 · 550 (child row name) · 600 · 650 · 700 · 750 · 800. Weight 600 is retained where the source uses it: inactive tab, raised segment item, eyebrow, text button and filter chip.
- **Spacing:** 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 40 (`--ecrm-space-1…14`). Components consume these tokens. A small set of off-scale source values is retained as documented exceptions (3, 5, 7, 9, 11, 13, 22, 30, 34px), listed in the correction report.
- **Radius:** 4 · 6 · 8 · 10 · pill, plus **retained source exceptions** 7 (raised segment), 5 (status badge), 3 (bar), 2 (legend swatch), each tokenised.
- **Elevation:** cards and panels are flat (1px border). Shadows are for floating layers (popover, tooltip, toast, drawer) and for segment states (raised and filled). **One scoped in-flow exception:** `--ecrm-shadow-investigation` on the investigation context bar (N2). There are no general card shadows.
- **Sizes:** controls 44 (drawer footer) / 40 (drawer field) / 36 (standard) / 32 (compact); icon button 40; checkbox 16; icon 14; count badge 20.
- **Layout:** header 60 · rail 64 · content max 1640 · gutter `clamp(12px, 3.2vw, 40px)` · drawer `min(480px, 100vw)`.

## 4. Consumer contract: CSS vs interaction recipes

- **The CSS owns appearance.** Every state is driven by ARIA attributes (`aria-current`, `aria-checked`, `aria-selected`, `aria-pressed`, `aria-expanded`, `aria-sort`, `aria-disabled`, `aria-invalid`, `aria-busy`) or by a documented `.is-*` class (`.is-active`, `.is-selected`, `.is-selected-col`, `.is-selected-cell`, `.is-overall`, `.is-child`).
- **Behaviour is the consumer's responsibility.** `gallery/edvoy-crm-gallery-recipes.js` (plain ES5, no dependencies) is the reference implementation: radio group, listbox, single-select press group, hierarchy disclosure, truthful sort, modal drawer and the disabled guard. Consumers may load it or implement the same contract themselves. The ARIA contract is mandatory; the file is not.
- Every `<button>` sets `type="button"` unless it submits a form. Every control has a programmatic label. Select triggers use `aria-labelledby="labelId valueId"`.

## 5. Component catalogue

**G** Global CRM · **A** Analytics · **W** Workflow · **RC** extracted candidate (rc2.36 only) · **P5** approved extension.

### Shell & navigation
| Component | Class | Layer | Rules |
|---|---|---|---|
| App shell | `.ecrm-shell .ecrm-topbar .ecrm-topnav .ecrm-rail .ecrm-main` | G | Header 60, rail 64 (`aria-current` item), content max 1640. The rail hides below 720px. |
| Settings composition | `.ecrm-page-header` + `.ecrm-tabs` + `.ecrm-segmented--raised` + `.ecrm-table-toolbar` + `.ecrm-table` + `.ecrm-pagination` | G | P6 replacement for the native Settings bar, sub-tabs, grey table and blue Reset. |
| Overflow policy | — | G | Shared nav rows scroll horizontally. Every item stays a focusable link. The consumer may add a "More" menu, but must never clip items with `overflow:hidden`. |
| Page header | `.ecrm-page-header` | G | Eyebrow, h1, optional status tag, one-line description. |
| Section head | `.ecrm-section-head` | G | Title and a context line. |
| Tabs | `.ecrm-tabs` | G | Underline tabs. Use links with `aria-current` for views, or `role=tab` only when real tab panels exist. |
| Segmented: filled | `.ecrm-segmented` | G [BL] | Filled accent segment. |
| Segmented: raised | `.ecrm-segmented--raised` (alias `--nav`) | G [RC, accepted P3] | Raised white segment. |

Both segmented appearances accept `aria-current`, `aria-checked`, `aria-selected` and `aria-pressed`. The context chooses the appearance. Option groups use `role=radiogroup` with the radio recipe; disabled items are skipped and expose their reason in `title`.

### Controls
| Component | Class | Layer | Rules |
|---|---|---|---|
| Primary | `.ecrm-btn--primary` | G | One per region. |
| Secondary | `.ecrm-btn--secondary` | G | Accent outline, structure ink, 14/700. |
| Menu trigger | `.ecrm-btn--secondary.ecrm-btn--menu` | G | Export ▾, 13/650. |
| Neutral | `.ecrm-btn--neutral` | G | Cancel or dismiss. |
| Quiet | `.ecrm-btn--quiet` | G | In-row action (*Investigate →*), 36px minimum. |
| Text | `.ecrm-btn--text` | G | Clear / Clear all, underlined. |
| Sizes | `--sm` (32) · default (36) · `--lg` (44) | G | |
| Disabled | `[aria-disabled=true]` + `title` reason | G | Stays focusable and never activates (disabled guard). |
| Icon button · count badge | `.ecrm-icon-btn` · `.ecrm-count` | G | The icon button needs an `aria-label`. |
| Select trigger | `.ecrm-select` + `--block` · `--sm` · `--drawer` (+ `.is-active`) | G / W | Standard 36 (BL intake). Drawer field 40 (rc2.36 `FS(a)`: unset white / control border / 500 / primary ink; active `#fbfaff` / accent border / 650 / structure ink). |
| Input · validation | `.ecrm-input[aria-invalid] .ecrm-field-error .ecrm-validation` | G P5 | Message linked by `aria-describedby`. The summary links to the fields. |
| Search | `.ecrm-search` (`--sm`) | G | Needs a visible or sr-only label. |
| Labels · help | `.ecrm-label .ecrm-field-name .ecrm-help-text .ecrm-info` | G | |
| Chips | `.ecrm-choice-chip` (aria-pressed) · `.ecrm-chip` (removable) | G | |
| Popover · listbox · menu | `.ecrm-popover` (`--floating`, `--inline`) · `.ecrm-listbox` · `.ecrm-option` · `.ecrm-menu-item` | G | The listbox contains only options. Search and footer controls sit in the surrounding popover. Checkmarks are `aria-hidden`. |
| Checkbox | `.ecrm-checkbox` | G | State comes from the parent's `aria-selected` or `aria-checked`. |
| Tooltip · toast | `.ecrm-tooltip` · `.ecrm-toast` | G | |
| Tags (tones) | `.ecrm-tag` + `--primary --info --positive --negative --warning --plain --highlight --unavailable --status` | G | The system defines tones only. Which word gets which tone is consumer vocabulary (P4). |

### Surfaces & states
Panel `.ecrm-panel` · Info callout `.ecrm-callout` [BL `role="note"`] (warning and error variants are P5, using existing grounds) · Disclosure `.ecrm-disclosure` [RC] · Empty `.ecrm-empty` · Status note `.ecrm-status-note` [RC] · Missing value `.ecrm-missing` (P2) · Busy `.ecrm-busy-status` (P5).

**Busy recipe:** the region gets `aria-busy="true"`. A separate `role="status"` line announces the start and the finish. The triggering action is `aria-disabled` until it completes. The status keeps full contrast (no dimming layer). Skeletons are a future extension.

### Tables
| Component | Class | Layer | Rules |
|---|---|---|---|
| Base table | `.ecrm-table` in `.ecrm-table-wrap` | G | Right-aligned tabular numbers. The wrapper scrolls horizontally and is focusable with a label. |
| List table | `.ecrm-table` | G | The single list table for every page, including Settings (P6). Sortable headers, `.ecrm-table__name`, quiet row actions, missing-value rendering. |
| Analytical table | `.ecrm-table--analytic` | A | Identity column: header `.ecrm-th-identity`, row headers `<th scope="row" class="ecrm-td-identity">`. Only these are sticky. Grouped header `.ecrm-th-group`. Overall `tr.is-overall` is **tinted, not vertically pinned**. Child rows `tr.is-child`. Name weights 750 / 650 / 550 (BL). |
| Hierarchy | `.ecrm-expand[aria-expanded][aria-controls][data-ecrm-name]` | A | Toggles `[hidden]` on the controlled rows and updates the label (Expand / Collapse name). Collapsing a parent collapses its descendants. |
| Sort | `th[aria-sort][data-ecrm-col] > .ecrm-sort` | G | Sorting must be truthful: parents move with their children, pinned rows stay first, missing values sort last, and the change is announced. A header without a button is non-sortable. |
| Selected column / cell | `.is-selected-col` / `td.is-selected-cell` | A | Static specimen: structure ring plus sr-only "selected" text. An interactive selectable cell must contain a `button[aria-pressed]`. Cells never get `aria-selected`. |
| Toolbar · pagination · show more | `.ecrm-table-toolbar` · `.ecrm-pagination` (`__size`) · `.ecrm-show-more` | G | Pagination (purple, P6) for record lists. *Show all N* for analytics. |

### Analytics
Delta `.ecrm-delta` (`--positive --negative --unavailable --lg`) · KPI `.ecrm-kpi` in `.ecrm-kpi-strip` (selectable = `button[aria-pressed]`; focus is drawn inset because the strip clips) · Summary strip · Control band `.ecrm-control-band` [BL Soft band] · Findings `.ecrm-findings > button.ecrm-finding[aria-pressed]` (single-select press group; the container does not clip focus) · Ranked bar list `.ecrm-barlist .ecrm-bar-row` · Chart container `.ecrm-chart` · Evidence `.ecrm-evidence[data-ecrm-selectable]` with heading `button.ecrm-evidence__select[aria-pressed]`, card `.is-selected`, and nested actions kept separate [RC] · Investigation context `.ecrm-investigation` [BL, N2 shadow].

Selection rings use `--ecrm-selection-ring` (2px inset structure colour, the BL age/evidence treatment), with the sourced accent tints kept underneath. The bar row keeps its BL 1.5px accent ring.

### Workflow
**Modal drawer** (rc2.36 anatomy and mechanics, accepted). Markup: `.ecrm-drawer-scrim[hidden]` + `.ecrm-drawer[role=dialog][aria-modal=true][aria-labelledby][hidden]`, both direct children of `<body>`. Recipe (`EcrmRecipes.Drawer`):
- On open, everything else becomes `inert` and focus moves to the title.
- Tab and Shift+Tab stay inside; Escape, the scrim and `[data-ecrm-drawer-close]` close it.
- On close, focus returns to the trigger and the drawer emits `ecrm-drawer-close` with the close reason.
- `.ecrm-drawer--specimen` is a static, non-modal picture.
- **Draft, Reset and Apply behaviour belongs to the consumer.** The gallery demo's policy is: draft until Apply, Reset sets the draft to All, Cancel and Escape discard.

**Read-only detail** `.ecrm-detail` (P5). Future extensions, not part of v1: edit-mode layouts, approval, history/revision, destructive confirmation, skeletons.

## 6. States

| State | Treatment |
|---|---|
| Hover | `surface-hover`; table and finding rows use `surface-row-hover`; KPI and select use `surface-kpi-hover`; accent outline uses `accent-hover-tint`; menus use `selection-hover`. |
| Focus | 2px structure outline, 2px offset (inset −2px inside the KPI strip; offset 0 plus accent border on inputs). |
| Selected | Option: `selection` tint, `accent-strong` ink, 650. Filled segment: accent fill with white ink. Raised segment: white with raised shadow. KPI: `surface-kpi-sel` with accent underline. Finding, evidence and cell: structure ring (plus `surface-kpi-sel` tint on finding and evidence). |
| Current (navigation) | Underline or segment appearance plus `aria-current`. |
| Disabled | `text-disabled` on `surface-disabled` / `border-disabled`, `aria-disabled`, reason in `title`. |
| Invalid | Negative border, message, summary (P5). |
| Busy | `aria-busy`, status line, disabled duplicate action (P5). |
| Zero / No target / Unavailable | `0` / `—` with sr-only "No target set" / `—` with sr-only "Comparison unavailable" or the dashed tag. |

## 7. Responsive baseline

Target widths are 1440, 1280 and 1024. Rows of controls wrap. Wide tables scroll inside their wrapper with the identity column frozen. Nav rows scroll horizontally. The bar-list end column wraps its badge and delta. Below 720px the rail hides and findings and bar rows stack. Text is never shrunk below the scale. The gallery's frame-width buttons only set `max-width`; real media queries follow the browser viewport.

## 8. Accessibility baseline

Visible focus on every interactive element. Programmatic labels everywhere. State in ARIA. Meaning never by colour alone. Keyboard recipes for radio groups, listboxes and the modal. Disabled controls are inert to activation. Enabled text uses the verified contrast treatments; current independent checks are recorded in `DESIGN_SYSTEM_V1_ACCEPTANCE.md`. **No WCAG conformance is claimed.** Screen-reader testing has not been done.

## 9. Do / Don't

- **Do** use tokens. **Don't** write hex values in project CSS.
- **Do** let the consumer classify desirability. **Don't** colour neutral or structural movement green or red by default.
- **Do** keep cards flat. **Don't** add card shadows or gradients. The control band's left border (D-06) and the investigation shadow (N2) are the only recorded exceptions.
- **Don't** reintroduce native CRM colours (blue `#0066ff`, violet `#7c3aed`, CRM greys) or native variants. P6 retired them.
- **Do** pick either segmented appearance to suit the context. **Don't** treat appearance as a substitute for the right ARIA state.
- **Don't** auto-scroll on selection. **Don't** fork buttons, tables or cards per project.

## 10. Governance

1. Identify the unmet need.
2. Check the existing components and variants.
3. Document the semantic need.
4. Propose an extension built from existing tokens and principles.
5. Review it against the CRM and existing projects.
6. Make it global only if it is broadly reusable.
7. Otherwise keep it project-specific, prefixed and documented in that project.
8. For any global change, update the gallery, inventory and decisions log.

Projects may extend the system but must not silently override it. **Versioning:** patch for fixes that don't change the API; minor for additive tokens, components or variants; major for renames, removals or changed semantics. This pass renamed tokens (`surface-neutral-finding` → `surface-neutral-tag`; `selection-kpi` removed as a duplicate) and changed the identity-cell classes. These changes were made during the pre-freeze RC cycle. RC3 (P6) made a **major-scope** change before freeze: removed `--ecrm-crm-*`, `--ecrm-color-canvas`, `--ecrm-text-crm`, `.ecrm-settings-nav`, `.ecrm-subtabs`, `.ecrm-btn--crm-action`, `.ecrm-btn--destructive-text`, `.ecrm-select--crm`, `.ecrm-select__count`, `.ecrm-table--crm`, `.ecrm-table-wrap--crm`, `.ecrm-crm-link`, `.ecrm-tag--role`.

## 11. Target Planner adoption (not in this pass)

When separately authorised, Target Planner must consume these tokens, reuse the canonical BP-purple components and shell, add a component only for a genuine unmet need (documented first) and never fork components for cosmetic reasons. Its product contract stays authoritative for business semantics.
