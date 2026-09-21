# Bug list

Last updated: 2026-09-17

Confirmed bugs: **1** · Open: **0** · Ready for retest: **1** · Cleared: **0** · Reopened: **0**

| ID | Bug | Severity | Status | Cleared? | Last tested | Report |
| --- | --- | --- | --- | --- | --- | --- |
| BUG-001 | CSV delimiter detection counts commas inside quoted headers | Medium | Ready for retest | No | 2026-09-17 | [Details](reports/BUG-001.md) |

Latest testing: [2026-09-17 Tangent pass 02](runs/2026-09-17-tangent-02.md). Python
syntax checks passed for 35 files; 10 broader isolated helper methods and all 4
standalone CSV reader methods passed at `f409ee7`. BUG-001 remains Ready for
retest because the complete Polars `read_table` suite could not be independently
run without its missing dependencies. Frontend checks were blocked for the same
reason. Database and auth workflows were not exercised.

See [status definitions](README.md#status-meanings) for clearance rules. This is a
limited testing pass, not a claim of complete project coverage.
