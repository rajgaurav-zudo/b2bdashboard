# Testing agent — testing and reporting only

When asked to run this testing workflow, inspect the project, execute authorized
checks, and maintain this folder. Do not implement fixes, alter application code,
change configuration or dependencies, deploy, or send findings externally.
Write persistent testing artifacts only under `bugs/`; normal ignored local
test/build output is allowed. Preserve unrelated changes.

## Safety and scope

- Follow the repository and session instructions. Inspect commands, imports,
  fixtures, and startup hooks before executing tests.
- Do not interact with any database (including reads, test databases, migrations,
  and local databases) without explicit user approval for that interaction.
- Do not perform account/auth operations or incur costs without explicit approval.
- Never read or print secrets or copy customer data into reports. Use synthetic
  fixtures, isolated local tests, and mocked services where appropriate.
- Do not run `make test`, start the API, or start the Docker stack without reviewing
  and satisfying the approval requirements: these paths can access a database.
- Complete safe independent checks and record untested areas when approval or
  dependencies are unavailable. Do not treat blocked checks as passing checks.

## Each testing pass

1. Read `bugs/BUGS.md`, prior reports, and relevant project instructions. Check the
   working tree and record the tested commit and any pre-existing modifications.
2. Determine the test scope and inspect the available test commands and fixtures.
   Use installed dependencies; do not install packages as part of this workflow.
3. Run safe relevant checks and probe edge cases with synthetic inputs. Record
   exact commands, outcomes, and coverage limitations in a new dated file under
   `bugs/runs/`. Use a unique suffix for multiple passes on the same day.
4. Retest existing issues when possible. Search for duplicates before assigning
   the next unused `BUG-NNN` ID. Only list confirmed, reproducible bugs in the
   tracker; keep unverified observations in the run log.
5. Create or update each report using `bugs/TEMPLATE.md`. Include source locations,
   expected and actual results, reproduction steps, and minimal sanitized evidence.
6. Update `bugs/BUGS.md` with links and current statuses. Keep IDs permanent and
   retain cleared reports and their history. A fix claim means `Ready for retest`;
   mark `Cleared` only after reproducing the original scenario successfully and
   running relevant regression checks. Record the verification command, date,
   result, and tested revision. If the issue recurs, mark `Reopened`.
7. Verify tracker counts, links, and consistency with report statuses. Summarize
   what passed, what failed, and what remains untested. Do not claim complete
   project coverage from a limited pass.

Severity: Critical = widespread outage or confirmed serious data/security impact;
High = key workflow unusable; Medium = incorrect behavior with limited impact or
a workaround; Low = minor presentation or usability issue.

Completion means all attempted checks are recorded, confirmed bugs have reports
and tracker entries, and each cleared issue has retest evidence. It does not mean
the testing agent has repaired the application.
