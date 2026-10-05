# Edvoy CRM Design System — Authoring Instructions

Reconstructed from the approved brief dated 1 October 2026. This is not a
byte-for-byte recovery of a previously lost file; it is the governing
instruction set for v1.0.0, including the P6 purple standardisation.

The current authority is P1–P6 below and `EDVOY_CRM_DESIGN_SYSTEM.md`.
`CLAUDE_DESIGN_SYSTEM_RC2_CORRECTION_PROMPT.txt` is historical; P6 supersedes
its native-CRM fidelity requirements.
`DESIGN_SYSTEM_V1_ACCEPTANCE.md` is the independent audit and is never edited by the author.

## Consumer contract

- CSS (`css/`) owns appearance; state is expressed by ARIA attributes or documented `.is-*` classes.
- Behaviour recipes live in `gallery/edvoy-crm-gallery-recipes.js`. The ARIA contract is mandatory; using that file is optional.
- Business meaning (metric direction, thresholds, vocabulary, exception logic, Reset/Apply policy) belongs to the consuming application (P4).
- Token provenance identifies `[BL]` or `[RC]` sources and aliases; approved normalisations are recorded in the decisions log. The CRM screenshot is not a visual-token source under P6.

## Source authority (P1)

| Rank | Source | Path | Governs |
|------|--------|------|---------|
| 1 | Business Performance v1.3.0 | `references/Business Performance v1.3.0.html` | Frozen baseline. All reusable patterns default to this. |
| 2 | Business Performance v1.4.0-rc2.36 | `references/Business Performance v1.4.0-rc2.36.html` | Newer reusable patterns only when explicitly accepted or labelled candidate/extracted. The entire RC is not frozen authority. |
| 3 (IA only after P6) | CRM KPI Targets screenshot | `references/crm-kpi-targets-current.png` | Information architecture only: which controls and data a Settings page needs. No authority over colours, typography or component appearance. |

Font authority: Figtree, extracted from BP v1.3.0 frozen baseline.
- `css/fonts/figtree-latin.woff2` SHA256: `8330490a01c60c196eae00b823de8102275aaa5862e7b76a7af21b8745338928`
- `css/fonts/figtree-latin-ext.woff2` SHA256: `f153aa07c1b16fbb12391c2512860c97819a0a9fd014f338b2b3f12496479d13`

A static CRM screenshot cannot independently establish the production CRM font.

## Purple standardisation (P6, user decision 1 October 2026)

- One visual language: Business Performance purple. The Global CRM native layer is **retired**: no `--ecrm-crm-*` tokens, no blue Reset, no CRM violet, no native Settings nav/sub-tabs/grey table/role badge.
- Settings and list pages compose BP components: page header, `.ecrm-tabs`, `.ecrm-segmented--raised`, toolbar, `.ecrm-table`, `.ecrm-pagination`.
- The CRM screenshot is an information-architecture reference only. Version: **v1.0.0**, frozen on 1 October 2026.

## Typography and semantic fidelity (P2) — native visual requirements superseded by P6

- ~~Preserve the native blue Reset~~ (retired by P6).
- Figtree is the design-system typography authority from BP.
- No target, Unavailable and Zero are distinct states.
- Document accessibility contrast deviations from source values with measured before/after contrast.

## Segmented controls (P3)

- Keep raised-white (`--nav`) and filled-purple (default) canonical variants.
- Product/component context chooses the approved variant.
- Do not claim a universal navigation-versus-selection appearance mapping.
- Use existing canonical structure/focus semantic for focus and selection treatment.

## Global versus application semantics (P4)

- Globalise reusable component anatomy and interaction mechanics.
- BP vocabulary, thresholds, metric direction, exception logic and Reset/Apply business semantics belong to the consumer.
- Gallery examples are examples, not mandated product rules.
- Drawer anatomy/modal mechanics can be global; a demo's draft/reset behaviour must be labelled as that demo's policy.

## Minimum v1 form/status scope (P5)

- Validation/error and read-only-detail patterns are APPROVED extensions.
- Minimal reusable loading/busy treatment: existing typography and tokens, visible status, aria-busy/live, disabled duplicate action.
- Skeleton, history/revision, approval and destructive-dialog systems remain future extensions.

## Resolution classifications

For every fidelity difference, use exactly one classification:
- **RESTORE SOURCE** — return to the confirmed source value
- **APPROVED NORMALISATION** — cite P1–P6 or a recorded consolidation
- **PROJECT-SPECIFIC / NOT GLOBAL** — belongs to the consumer, not the design system

## Governance

1. The independent auditor owns the final freeze recommendation.
2. Do not rewrite or self-approve `DESIGN_SYSTEM_V1_ACCEPTANCE.md`.
3. Do not modify anything under `references/`.
4. Gallery examples use synthetic data only.
5. No new theme, font, brand palette, gradient, card treatment, framework, skeleton, history/revision, approval workflow or destructive dialog system.
6. Version: v1.0.0, frozen by user authorisation on 1 October 2026. Acceptance is recorded in `DESIGN_SYSTEM_V1_ACCEPTANCE.md`; release hashes are in `RELEASE_v1.0.0_SHA256.json`.
7. Preserve this frozen baseline. Subsequent changes require an appropriate new semantic version, updated evidence and a release record.
