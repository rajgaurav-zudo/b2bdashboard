# Bug list

Last updated: 2026-10-05

Confirmed bugs: **3** · Open: **0** · Ready for retest: **0** · Cleared: **3** · Reopened: **0**

| ID | Bug | Severity | Status | Cleared? | Last tested | Report |
| --- | --- | --- | --- | --- | --- | --- |
| BUG-001 | CSV delimiter detection counts commas inside quoted headers | Medium | Cleared | Yes | 2026-10-05 | [Details](reports/BUG-001.md) |
| BUG-002 | Unquoted header punctuation overrides the actual CSV delimiter | Medium | Cleared | Yes | 2026-10-05 | [Details](reports/BUG-002.md) |
| BUG-003 | Escaped quotes stay doubled in CSV header names | Low | Cleared | Yes | 2026-10-05 (helper only) | [Details](reports/BUG-003.md) |

Latest testing: [2026-10-05 Tangent pass 01](runs/2026-10-05-tangent-01.md).
All 22 isolated helper methods, all 288 separator/record-count matrix cases,
and syntax checks for 53 Python files pass at `ee9935e` (clean starting tree).
No new bugs were confirmed. BUG-003 was checked using a synthetic frame only;
full Polars and frontend checks were unavailable. Database/auth checks were not
authorized. The three Cleared statuses retain the previous full-suite evidence
below. Previous helper pass: [2026-09-21 Tangent pass 02](runs/2026-09-21-tangent-02.md).

Previous full-suite testing: [2026-09-21 fix verification](runs/2026-09-21-fix-verification.md).
The BUG-002 separator fix passes the 288-case matrix with 0 separator failures,
and the full Polars reader suite passes in the API container (24 passed), which
clears BUG-001 and BUG-002. The same matrix run through `read_table` found that
Polars keeps doubled quotes in header names (BUG-003); separators and rows were
correct in every case. BUG-003 was then fixed in `read_table` and cleared: the
matrix reports 0 header-name failures and the reader suite passes (29 passed). Previous pass: [2026-09-21 Tangent pass 01](runs/2026-09-21-tangent-01.md).

See [status definitions](README.md#status-meanings) for clearance rules. This is a
limited testing pass, not a claim of complete project coverage.
