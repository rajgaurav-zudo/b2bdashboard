# Edvoy CRM Component Inventory, v1.0.0 (purple standardisation, P6)

Map: source pattern → canonical component → layer → source presence → consolidation → globalise → rationale. Frozen on 1 October 2026. **P6:** every row whose canonical was a native-CRM variant is now **RETIRED (P6)** and points to its purple Business Performance replacement.

**Source column:** **BL** = present in `references/Business Performance v1.3.0.html` (frozen baseline) · **RC** = present only in `references/Business Performance v1.4.0-rc2.36.html` (extracted candidate unless accepted) · **CRM** = `references/crm-kpi-targets-current.png` · **P5** = approved extension with no source precedent. Presence was checked by searching the decoded `__bundler/template` of each file for the pattern's identifying markup or literal.

| # | Source pattern | Canonical | Layer | Source | Consolidation | Globalise | Rationale |
|---|---|---|---|---|---|---|---|
| 1 | Header bar 60px, wordmark, nav | `.ecrm-topbar` | GLOBAL CRM | BL | — | Yes | Shell. |
| 2 | Top nav ink | `.ecrm-topnav` | GLOBAL CRM | BL | CRM `#9da3af` discarded (P6) | Yes | BL ink. Overflow scrolls (N3). |
| 3 | Left rail 64px | `.ecrm-rail` | GLOBAL CRM | BL | — | Yes | |
| 4 | Settings nav | ~~`.ecrm-settings-nav`~~ → `.ecrm-tabs` | GLOBAL CRM | CRM | — | **RETIRED (P6)** | Settings sections use BP underline tabs. |
| 5 | Sub-tabs Overall/Team/Individual | ~~`.ecrm-subtabs`~~ → `.ecrm-segmented--raised` (links, `aria-current`) | GLOBAL CRM | CRM | — | **RETIRED (P6)** | BP raised page switch. |
| 6 | Page header | `.ecrm-page-header` | GLOBAL CRM | BL | — | Yes | |
| 7 | View tabs (14.5, 3px underline) | `.ecrm-tabs` | GLOBAL CRM | BL | — | Yes | |
| 8 | `segS` filled segment | `.ecrm-segmented` | GLOBAL CRM | BL | Tracks C-05 | Yes | Canonical appearance. Not reserved for selection (P3). |
| 9 | `sfPageNav` / `appPageNav` raised segment | `.ecrm-segmented--raised` (alias `--nav`) | GLOBAL CRM | RC, accepted P3 | — | Yes | Canonical appearance. Not reserved for navigation (P3). |
| 10 | Apply | `.ecrm-btn--primary` | GLOBAL CRM | BL (hover `#5a2fc4` RC) | — | Yes | |
| 11 | Filters / Show all / Reset filters | `.ecrm-btn--secondary` | GLOBAL CRM | BL | Borders C-04 | Yes | 14px / 700. |
| 12 | Export ▾ (13 / 650) | `.ecrm-btn--menu` | GLOBAL CRM | BL | — | Yes | Restored as its own variant, not an override. |
| 13 | Cancel | `.ecrm-btn--neutral` | GLOBAL CRM | RC | — | Yes | Drawer recipe. |
| 14 | Investigate → | `.ecrm-btn--quiet` | GLOBAL CRM | BL | — | Yes | Explicit navigation. |
| 15 | Clear all / Clear | `.ecrm-btn--text` | GLOBAL CRM | BL | Underline kept for both | Yes | |
| 16 | CRM Reset (blue) | ~~`.ecrm-btn--crm-action`~~ → `.ecrm-btn--secondary` "Reset filters" | GLOBAL CRM | CRM | — | **RETIRED (P6)** | BP Reset filters treatment. |
| 17 | CRM Log Out | ~~`.ecrm-btn--destructive-text`~~ | — | CRM | — | **RETIRED (P6)** | No BP destructive pattern; destructive confirm stays a future extension. |
| 18 | Compact actions / search | `.ecrm-btn--sm`, `.ecrm-select--sm`, `.ecrm-search--sm` | GLOBAL CRM | BL (32px search) | — | Yes | |
| 19 | Drawer close × / count bubble | `.ecrm-icon-btn` / `.ecrm-count` | GLOBAL CRM | RC / BL | — | Yes | |
| 20 | Intake trigger 36px (`#cfc6ea`, hover `#f7f7fa`) | `.ecrm-select` | GLOBAL CRM | BL | — | Yes | |
| 21 | Drawer field `FS(a)` 40px | `.ecrm-select--drawer` (+ `.is-active`) | WORKFLOW | RC, accepted (drawer) | — | Yes | Unset vs active states restored. |
| 22 | CRM Select Intake / Assigned To Team, "1 added" | ~~`.ecrm-select--crm`, `__count`~~ → `.ecrm-select` (+ `.ecrm-count` if a count is needed) | GLOBAL CRM | CRM | — | **RETIRED (P6)** | BP intake select. |
| 23 | Search fields | `.ecrm-search` | GLOBAL CRM | BL | Input size → 13.5 | Yes | |
| 24 | Uppercase label / popover title | `.ecrm-label` / `.ecrm-popover__title` | GLOBAL CRM | BL | — | Yes | |
| 25 | "i" help dot (`#e7e5ee`, 9.5px) | `.ecrm-info` | GLOBAL CRM | BL | — | Yes | Tokenised. |
| 26 | `chip()` presets | `.ecrm-choice-chip` | GLOBAL CRM | BL | Radius 7 → 6 (C-07) | Yes | |
| 27 | Applied-filter pill | `.ecrm-chip` | GLOBAL CRM | BL | — | Yes | |
| 28 | Popovers / menus | `.ecrm-popover` (`--floating`) | GLOBAL CRM | BL | — | Yes | |
| 29 | In-drawer dropdown (r8, inline shadow) | `.ecrm-popover--inline` | WORKFLOW | RC | — | Yes | Consumes `--ecrm-shadow-inline`. |
| 30 | `optS` options | `.ecrm-listbox` + `.ecrm-option` | GLOBAL CRM | BL | 13 / 13.5 → 13 | Yes | Listbox holds only options. |
| 31 | Export menu items | `.ecrm-menu-item` | GLOBAL CRM | BL | — | Yes | |
| 32 | Checkbox (`#c9c4d8`) | `.ecrm-checkbox` | GLOBAL CRM | BL (`cbx()` helper RC) | — | Yes | Tokenised. |
| 33 | Tooltip / toast | `.ecrm-tooltip` / `.ecrm-toast` | GLOBAL CRM | BL | — | Yes | Toast shadow tokenised. |
| 34a | Tag tones (KT grounds/inks) | `.ecrm-tag--*` | GLOBAL CRM | BL | — | Yes (tones) | Tones are reusable. |
| 34b | KT vocabulary (Primary / Change / Concentration / Context / Data quality / Risk / Opportunity) | — | PROJECT-SPECIFIC | BL | — | **No** | BP vocabulary (P4). The gallery uses it only as example words. |
| 35 | `pill()` entity tags / At Risk | `.ecrm-tag--plain` | GLOBAL CRM | BL | — | Yes | Tokenised `#4a4f66` / `#efeef4`. |
| 36 | High volume pill | `.ecrm-tag--highlight` | ANALYTICS | BL | — | Yes (anatomy) | The "top 20%" threshold is consumer-owned. |
| 37 | Status unavailable (dashed) | `.ecrm-tag--unavailable` | GLOBAL CRM | RC | — | Yes, candidate | Needed for P2. |
| 38 | Version badge / role badge | `.ecrm-tag--status` / ~~`--role`~~ | GLOBAL CRM | BL / CRM | — | Status yes; role **RETIRED (P6)** | Role badge was CRM yellow. |
| 39 | Bordered cards | `.ecrm-panel` | GLOBAL CRM | BL | C-02 | Yes | |
| 40 | `role="note"` info callout | `.ecrm-callout` | GLOBAL CRM | BL | — | Yes | Source values restored exactly (`#f4f6fa` / `#e3e7ef` / r8 / 10 14 / icon `#5d6278` / 650). |
| 41 | `<details>` Cutoffs | `.ecrm-disclosure` | GLOBAL CRM | RC | — | Yes, candidate | |
| 42 | "No matches" | `.ecrm-empty` | GLOBAL CRM | BL | — | Yes | |
| 43 | Validation (field error, summary, warning/error callout) | `.ecrm-input[aria-invalid]`, `.ecrm-field-error`, `.ecrm-validation`, `.ecrm-callout--warning/--error` | GLOBAL CRM | P5 | — | **Approved** | Existing semantic grounds only. |
| 44 | Loading / busy | `.ecrm-busy-status` + ARIA recipe | GLOBAL CRM | P5 | — | **Approved** (minimal) | No skeleton. |
| 45 | Read-only detail | `.ecrm-detail` | WORKFLOW | P5 | — | **Approved** | |
| 46 | Missing compact value | `.ecrm-missing` + sr-only text | GLOBAL CRM | P2 | — | Yes | Distinguishes No target from Unavailable. |
| 47 | Detail table, `bgOf` / `nmS` | `.ecrm-table--analytic` | ANALYTICS | BL | — | Yes | Overall tinted, not pinned. |
| 48 | CRM KPI Targets list | ~~`.ecrm-table--crm`~~ → `.ecrm-table` | GLOBAL CRM | CRM → BL | — | **RETIRED (P6)** | One BP list table everywhere. |
| 49 | Show History link | ~~`.ecrm-crm-link`~~ → `.ecrm-btn--quiet` | GLOBAL CRM | CRM → BL | — | **RETIRED (P6)** | BP in-row action. History UI stays a future extension. |
| 50 | Sort arrows | `.ecrm-sort` on `th[aria-sort]` | GLOBAL CRM | CRM + BL | — | Yes | Truthful recipe. |
| 51 | Pagination | `.ecrm-pagination` (purple tokens) | GLOBAL CRM | CRM anatomy | Colours → BP tokens | Yes (P6) | Current page = selection tint + accent border + accent-strong ink. |
| 52 | Show all N | `.ecrm-show-more` | GLOBAL CRM | BL | — | Yes | |
| 53 | `sfStages` KPI boxes | `.ecrm-kpi`, `.ecrm-kpi-strip` | ANALYTICS | BL | — | Yes | Selected `#f7f4fe` restored. |
| 54 | Funnel conversion connectors | — | PROJECT-SPECIFIC | BL | — | **No** | Funnel-specific. |
| 55 | What changed? strip | `.ecrm-summary-strip` | ANALYTICS | BL | — | Yes | |
| 56 | Soft band | `.ecrm-control-band` | ANALYTICS | BL | `viewStyle` variants rejected | Yes | D-06 left border. |
| 57 | Key findings list | `.ecrm-findings` / `.ecrm-finding` | ANALYTICS | BL | — | Yes (anatomy, selection) | Finding rules are consumer-owned. |
| 58 | Bars `#8b6ae6` on `#f1f0f5` | `.ecrm-barlist` | ANALYTICS | BL | — | Yes | |
| 59 | Legend / footnote | `.ecrm-chart` | ANALYTICS | BL | — | Yes | |
| 60 | Exception cards (Partial Deposit…) | `.ecrm-evidence` (+ `__select`) | ANALYTICS | RC | — | Yes, candidate (anatomy) | Exception logic is consumer-owned (P4). |
| 61 | Unavailable status note | `.ecrm-status-note` | ANALYTICS | RC | — | Yes, candidate | |
| 62 | Investigation focus bar | `.ecrm-investigation` | ANALYTICS | BL | — | Yes | N2 scoped shadow. |
| 63 | O&R tabs + table | Composition of segmented + table | ANALYTICS | BL | — | Composed | No new primitive. |
| 64 | Age heat grid / bars (`AGEC`) | — | PROJECT-SPECIFIC | BL | — | **No** | Pipeline ageing. |
| 65 | Weekly alignment cards / trend table | — | PROJECT-SPECIFIC | BL | — | **No** | BP weekly model. |
| 66 | Filters drawer (anatomy + modal) | `.ecrm-drawer` + scrim + `EcrmRecipes.Drawer` | WORKFLOW | RC, accepted | — | Yes | The draft/Reset/Apply policy is consumer-owned. |
| 67 | Demo scenarios `<details>` | — | PROJECT-SPECIFIC | RC | — | **No** | Prototype utility. |
| 68 | CRM user popover | Composition of popover + menu items (BP) | GLOBAL CRM | CRM | — | Composed | Contains personal data; not reproduced. |
| 69 | CRM floating chat button | — | Out of scope | CRM | — | No | Third-party widget. |
