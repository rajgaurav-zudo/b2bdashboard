# Bug list

Last updated: 2026-09-17

Confirmed bugs: **1** · Open: **0** · Ready for retest: **1** · Cleared: **0** · Reopened: **0**

| ID | Bug | Severity | Status | Cleared? | Last tested | Report |
| --- | --- | --- | --- | --- | --- | --- |
| BUG-001 | CSV delimiter detection counts commas inside quoted headers | Medium | Ready for retest | No | 2026-09-17 | [Details](reports/BUG-001.md) |

Latest testing: [2026-09-17 Tangent pass 01](runs/2026-09-17-tangent-01.md). Python
syntax checks passed for 35 files; 10 broader isolated helper methods passed, and
the CSV reader regression again had 3 passing methods and 1 failure confirming
BUG-001 remains Open. Frontend checks and the existing Python suite were blocked
by missing dependencies. Database and auth workflows were not exercised.

See [status definitions](README.md#status-meanings) for clearance rules. This is a
limited testing pass, not a claim of complete project coverage.
