# B2B Pulse

What happened in a date range, across all three platform exports.

| Number | Counted from | Date column |
|---|---|---|
| Onboarded | Introducers master | Became Customer Date |
| Activity | Introducer activity log | Log Time (UTC day) |
| Applied … Enrolled, Closed | Applications | `Timestamp of '<stage>' status`, `Timestamp of Application marked as Closed` |

- An application is counted once per stage whose timestamp falls in the range.
- No range picked: the current Edvoy week (Saturday to today). Deltas compare with
  the same number of days just before the range.
- Only business area **B2B** is counted: the area is fixed in `metrics.AREA`, and rows
  in any other area (or with none) never show.
- Area / region / team: `StudentAssignedToBusinessArea`, `StudentAssignedToBusinessRegion`,
  `CurrentlyAssignedToBusinessTeam` on applications; `BusinessArea/Region/Team` on the
  master. A log takes its introducer's, else the commonest among introducers managed
  by its `Managed By Team`. Blank is "Unassigned".
- Actual intake narrows the application stages only.
- Country is the introducer's, else the student's.
