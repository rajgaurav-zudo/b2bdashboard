# Edvoy CRM Design System v1.0.0

**Status: FROZEN** — authorised by the user on 1 October 2026 after independent acceptance.

The frozen visual authority is Business Performance v1.3.0, with explicitly accepted or labelled extracted rc2.36 patterns and the approved P1–P6 decisions. One BP-purple component family covers CRM surfaces, including tables. The native CRM visual layer is retired; the CRM screenshot is an information-architecture reference only.

## Package

- Version: `VERSION`.
- Authoring and usage: `CLAUDE_DESIGN_INSTRUCTIONS.md`, `EDVOY_CRM_DESIGN_SYSTEM.md`.
- Catalogue and decisions: `EDVOY_CRM_COMPONENT_INVENTORY.md`, `EDVOY_CRM_DESIGN_SYSTEM_DECISIONS.md`.
- Tokens, components and fonts: `css/`.
- Canonical gallery and reference interaction recipes: `gallery/`.
- Root gallery entry point: `EDVOY_CRM_COMPONENT_GALLERY.html` redirects to the canonical gallery.
- Portable export: `Edvoy CRM Design System Gallery (standalone).html`.
- Acceptance evidence: `DESIGN_SYSTEM_V1_ACCEPTANCE.md`.

`RELEASE_v1.0.0_SHA256.json` records the SHA-256 digest of each frozen package file and each read-only source reference. The manifest excludes itself to avoid a circular digest. Historical RC prompts/reports are retained for provenance but are not release authority or part of the frozen distributable manifest.

## Verification

Independent acceptance passed at actual 1440×1000, 1280×1000 and 1024×1000, DPR 1, with no request interception or runtime repairs. Checks covered fonts/assets, computed semantic colours, responsive/local scrolling, sorting, hierarchy, selection, keyboard/focus, modal behaviour, busy state and accessibility basics. See the acceptance report for measurements and limitations.

Freezing updates release metadata only. CSS declarations, interaction behaviour and font bytes are preserved from the accepted package. The standalone export embeds the canonical recipe with its updated version comment. The release checksums provide a baseline for future comparisons.

## Change policy

Do not silently alter v1.0.0. Future fixes, additions and breaking changes require an appropriate patch, minor or major version, updated acceptance evidence and a new release record. The existing v1.0.0 checksum manifest must remain available as the historical baseline.

No commit, Git tag, push, publication or deployment was performed. No Business Performance or Target Planner files were changed; adoption into Target Planner remains a separate task.
