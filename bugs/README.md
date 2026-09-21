# Testing and bug tracking

This folder is only for testing records and bug status. Application fixes are outside
the testing agent's scope.

- [Bug list](BUGS.md): current status of every confirmed issue.
- [Testing agent instructions](AGENTS.md): scope and workflow for each testing pass.
- [Report template](TEMPLATE.md): reproduction and verification details.
- `reports/`: one report per bug, named `BUG-001-short-description.md`.
- `runs/`: dated testing logs, including passing checks and coverage limitations.

To request another testing pass, type:

```text
run tangent
```

The project-level `AGENTS.md` maps that command to the testing workflow in this
folder.

The agent runs when requested; these files do not install a background process or
schedule automatic testing. Each pass updates the existing tracker rather than
creating a second list. A reported fix is only cleared after a successful retest.

## Status meanings

| Status | Cleared? | Meaning |
| --- | --- | --- |
| Open | No | Reproduced and awaiting a fix. |
| Ready for retest | No | A fix has been reported but not verified. |
| Cleared | Yes | The original reproduction and relevant regression checks pass; evidence is linked. |
| Reopened | No | The issue reproduced again after a claimed or verified fix. |

An unavailable dependency or a test requiring approval is a testing limitation,
not a confirmed product bug. Record it in the run log. If an existing bug cannot
be retested, retain its status and explain why in its report.
