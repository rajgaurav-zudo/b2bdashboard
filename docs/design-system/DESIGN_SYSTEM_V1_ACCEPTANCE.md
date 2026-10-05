# Edvoy CRM Design System v1 acceptance

Final acceptance: **1 October 2026**. Reviewed package: v1.0.0 RC3, with the authorised final packaging/documentation cleanup. **FROZEN AS v1.0.0**, authorised by the user on 1 October 2026 after the ready-to-freeze recommendation. This report supersedes the earlier blocked RC2 and RC3 assessments.

The system uses the Business Performance purple visual language and components, including tables. The Global CRM native visual layer is retired. No remaining BLOCKER or MAJOR finding prevents the v1 freeze. Business Performance and Target Planner were not modified, and the system was not adopted into Target Planner.

## Accepted authority and scope

- **P1:** Business Performance v1.3.0 is the frozen baseline. rc2.36 supplies explicitly accepted patterns or labelled extracted candidates, not wholesale frozen authority.
- **P2, as amended by P6:** Figtree is authoritative from BP. Zero, No target and Unavailable remain distinct, including contextual/accessibility text where a dash is shared. The static CRM screenshot does not establish its production font.
- **P3:** Raised-white and filled-purple segmented controls are canonical appearances chosen by component/product context; neither has an absolute navigation-versus-selection mapping. Structural focus/selection semantics remain canonical.
- **P4:** Reusable anatomy and mechanics are global. Vocabulary, thresholds, metric direction, exceptions and Reset/Apply business policy belong to the consuming application.
- **P5:** Validation/error, read-only detail and minimal loading/busy are in scope. Skeleton, history/revision, approval and destructive-dialog systems are future extensions, not v1 prerequisites.
- **P6:** Standardise every CRM surface on BP components, including list and analytical tables. Retire native CRM colours, typography variants, navigation, tables, Reset and role badges. The CRM screenshot now informs information architecture only.

Native-layer retirement is **APPROVED NORMALISATION (P6)**, not a fidelity regression. Existing BP semantic colours still communicate positive, negative, neutral and informational meaning; standardisation does not turn these meanings purple.

## Final correction and scope preservation

The finaliser performed only the user-authorised cleanup following the independent RC3 audit:

1. Replaced the obsolete root [gallery entry point](EDVOY_CRM_COMPONENT_GALLERY.html) with a relative redirect and accessible fallback link to the [canonical gallery](gallery/EDVOY_CRM_COMPONENT_GALLERY.html). It no longer contains a second implementation or references missing stylesheets.
2. Reconciled source authority, version guidance, retained type/weight exceptions, table-family guidance and destructive-component scope in the [instructions](CLAUDE_DESIGN_INSTRUCTIONS.md), [system](EDVOY_CRM_DESIGN_SYSTEM.md) and [decisions](EDVOY_CRM_DESIGN_SYSTEM_DECISIONS.md).
3. Marked RC2 author reports/prompts as historical. Updated gallery/document status wording and the recipe version comment. The standalone export retains the same BP components and behaviour.
4. Updated the [RC3 report](RC3_PURPLE_STANDARDISATION.md) and this acceptance report.

Classification: **APPROVED NORMALISATION (P6)**. No CSS token or component declarations, font bytes, source references or application behaviour changed in this final cleanup. The recipe-file change is a header comment only. Verification used the resulting package without runtime repairs.

## Independent evidence and method

The earlier extraction audit fully read the six required source/system files and visually inspected all supplied references:

- [Business Performance v1.3.0](<references/Business Performance v1.3.0.html>) — frozen baseline.
- [Business Performance v1.4.0-rc2.36](<references/Business Performance v1.4.0-rc2.36.html>) — release candidate.
- [CRM screenshot](references/crm-kpi-targets-current.png) — now IA-only under P6.

BP templates were decoded for source comparisons. Screenshot samples were converted to sRGB using its embedded colour profile. The references remained unchanged through finalisation; personal source data is not reproduced here.

Final browser rerun: **actual 1440×1000, 1280×1000 and 1024×1000**, DPR 1, local Chrome 154.0.8037.58 via Playwright, opening the delivered canonical HTML directly from disk. No request interception, replacement assets, injected application behaviour, font substitution or stylesheet repairs. Axe was added only as test instrumentation after rendering. Root redirect and standalone export were also opened directly at 1024×1000.

Inspected viewport/section/modal/focus captures, computed semantic colours, actual sort order, hierarchy visibility, selection state, keyboard focus and local scrolling. Both Figtree faces loaded; a separate RC3 platform-font check confirmed custom Figtree actually renders the page title. Fonts and rendering declarations are unchanged by finalisation.

Temporary evidence: `/tmp/edvoy-ds-final-evidence/results.json`, `entrypoints.json` and viewport/section/modal/focus captures. Additional RC3 open-modal accessibility, platform-font and listbox checks are in `/tmp/edvoy-ds-rc3-evidence/extra.json`. Reproduction scripts are under `/tmp/edvoy-ds-audit/`. Screen-reader testing and full WCAG conformance certification were not performed.

## Final browser results

| Check | 1440×1000 | 1280×1000 | 1024×1000 |
|---|---|---|---|
| Failed delivered asset requests / application errors | 0 / 0 | 0 / 0 | 0 / 0 |
| Figtree Latin and Latin-ext | Loaded | Loaded | Loaded |
| Document horizontal overflow | None | None | None |
| Tested retired native colours | None | None | None |
| List and analytical sorting | Pass | Pass | Pass |
| Hierarchy disclosure and child visibility | Pass | Pass | Pass |
| Finding/evidence selection | Pass | Pass | Pass |
| Radio pointer/keyboard and roving tabindex | Pass | Pass | Pass |
| Modal entry/trap/inert/Escape/focus return | Pass | Pass | Pass |
| Busy start / repeat-action disabling / completion | Pass | Pass | Pass |
| Axe WCAG A/AA tagged violations, tested page state | 0 | 0 | 0 |

Key measurements and interaction evidence:

- Native `#0066ff`, `#7c3aed`, `#354663`, `#081f42` and `#ebecf0` do not appear in tested element text, background or checked border colours. Current pagination is `#4b2aa8` on `#f3eefe`.
- Comparison text renders at 11.5px: positive `#16794a`, negative `#bf3a2b`, neutral `#5d6278`, unavailable `#63687c`. Falling lower-is-better is green with a down arrow; neutral keeps the sign without an arrow.
- Ascending Target orders 8, 12, No target. Missing targets remain last in both directions. Qualified ascending orders parent values 647, 893, 1,397 while keeping children attached and Overall first.
- Both hierarchy controls update accessible names, expanded state and controlled-row visibility. Finding click and evidence Space activation update pressed state and selected treatment.
- Radio click updates checked state and tabindex together. End selects the last enabled option and skips the disabled option.
- Modal focus enters its title; Shift+Tab reaches the last action; Tab wraps to Close. The background ancestor is inert. Escape hides the drawer and restores focus to its trigger. The separate open-modal axe check reports zero violations; a keyboard drawer-listbox selection changes Region to Europe.
- Busy status remains outside the busy region and readable. Refresh sets `aria-busy=true` and `aria-disabled=true`; completion clears busy. The former white overlay is absent.
- At 1024, the analytical wrapper is 942px wide with 960px content. Horizontal scrolling moves 18px locally: identity x remains 41px while first metric x changes from 289.02 to 271.02px. KPI focus is visibly contained in its strip.
- Both root entry points open without failed requests, show Figtree and BP tables, and have no native component classes or document overflow. The standalone check is a smoke check, not an exhaustive export-parity certification.

Font SHA-256:

- Latin: `8330490a01c60c196eae00b823de8102275aaa5862e7b76a7af21b8745338928`
- Latin-ext: `f153aa07c1b16fbb12391c2512860c97819a0a9fd014f338b2b3f12496479d13`

## Finding closure

| Earlier finding | Final disposition |
|---|---|
| B1 — Assets/instructions | Closed: working relative assets, exact BP fonts and meaningful instructions. |
| M1 / R1 — Authority/provenance | Closed under P1–P6: baseline and RC scope explicit, native screenshot IA-only, business semantics consumer-owned, approved/future scope reconciled. |
| M2 — Source fidelity | Source-backed BP callout, KPI tint, tag, drawer field and investigation treatments retained. Native-fidelity requirements superseded by P6. |
| M3 / R2 — Tokens/gallery forks | Canonical variants and token use improved in RC3; 160 component spacing-token references, no undefined canonical variables. Duplicate compact-button attributes and old native examples removed. |
| M4 / R3 — Comparison semantics | Closed: correct computed colours, movement/desirability distinction and contextual missing-value text. |
| M5 / R4 — Hierarchy/selection/sort/focus | Closed: working state recipes, truthful sorting, scoped sticky identity and visible focus. |
| M6 / R5 — Modal/ARIA/keyboard | Closed: working modal, field names, valid static-cell specimen, state-synchronised keyboard recipes. |
| M7 / R6 — Contrast/busy | Closed: active inverse contrast and readable busy status; no axe contrast violations in tested states. Retired native-subtab correction is moot under P6. |
| N1 / R7 — Type/radius | Closed: retained BP exceptions documented; removed native type/weight exceptions no longer presented as canonical. |
| N2 / R7 — Elevation | Closed: investigation context is explicitly a source-backed in-flow exception, not permission for general card shadows. |
| N3 — 1024px composition | Closed: fitting specimen, readable bar end content and local table scrolling. |
| RC3-1 — Obsolete root gallery | Closed: root entry point routes to the canonical gallery, with no stale native implementation. |
| RC3-2 — Contradictory P6 docs | Closed: active authority and retained-pattern guidance consistently reflect P6. |

## Coverage of the 20 acceptance areas

| # | Area | Final assessment |
|---|---|---|
| 1 | Tokens against references | BP extraction plus recorded normalisations; no undefined canonical token references. |
| 2 | Typography | Exact BP Figtree assets load; scale and retained BP exceptions documented. |
| 3 | Colours and semantics | BP purple authority; semantic colours preserved; native palette retired. |
| 4 | Spacing | Canonical spacing consumed; source-specific exceptions remain scoped. |
| 5 | Radius/border/shadow | Flat source-backed panels and documented radius/elevation exceptions. |
| 6 | Buttons | BP canonical variants, compact sizes and source-backed state styling; native Reset retired. |
| 7 | Inputs/selects/search/filter | Labelled controls and reusable states; working drawer field recipe. |
| 8 | Tabs/segmented | Raised and filled approved appearances; context chooses semantics; radio keyboard verified. |
| 9 | Cards/panels | Source-backed restrained surfaces and restored callout. |
| 10 | Tables/hierarchy | BP base and analytical family, working sorting/disclosure, correctly scoped sticky identity. |
| 11 | Status/validation | Approved error/read-only/busy scope; missing values distinguishable. |
| 12 | Selection/focus | Working finding/evidence selection, structural focus and unclipped KPI ring. |
| 13 | Comparison meaning | Correct positive/negative/neutral rendering; consumer determines desirability. |
| 14 | Analytical components | Source-backed reusable anatomy with application rules excluded. |
| 15 | Responsive | Requested actual viewports pass; tables scroll locally. |
| 16 | Accessibility basics | Representative keyboard/modal checks and axe pass in tested states; no certification claim. |
| 17 | Application-specific globalisation | Business vocabulary, direction, thresholds and policies remain consumer-owned. |
| 18 | Duplication | One canonical BP family; root entry point no longer forks it. Standalone is a distributable export. |
| 19 | Canonical gallery use | Delivered assets and component/state recipes work without substitution. |
| 20 | New-project completeness | Sufficient basic primitives and recipes for the approved v1 scope; excluded workflows remain extensions. |

**EXPECTED BEHAVIOUR:** BP base and analytical table compositions, pagination versus progressive disclosure, both segmented appearances, and informational/semantic tones remain distinct where their roles differ. Overall is tinted rather than vertically pinned. These are not unresolved defects.

**PRODUCT DECISION NEEDED:** none for this freeze. Future product workflows or new primitives require their own extension review; they do not block v1.

The user subsequently authorised the local package freeze. Release metadata and SHA-256 hashes are recorded in `RELEASE_v1.0.0.md` and `RELEASE_v1.0.0_SHA256.json`. No commit, Git tag, publication, deployment or adoption into another project was performed.

FROZEN AS v1.0.0
