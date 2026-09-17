# Project commands

## `run tangent`

When the user's message is `run tangent` (ignoring capitalization and surrounding
whitespace), run the project's testing agent:

1. Spawn a sub-agent named `tangent` and tell it to follow `bugs/AGENTS.md`.
2. The agent must test and report only. It must not fix or alter application code.
3. Have it update `bugs/BUGS.md`, `bugs/reports/`, and `bugs/runs/` with verified
   results from that pass.
4. Respect all approval requirements in `bugs/AGENTS.md`, especially for database,
   account/auth, network, dependency installation, and paid operations.
5. When the agent finishes, verify the tracker and report links, then summarize the
   results for the user.

The command starts a single on-demand testing pass. It does not create a background
process or repair reported bugs.
