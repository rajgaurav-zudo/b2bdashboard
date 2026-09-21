# 2026-09-21 — Fix verification for BUG-001 and BUG-002

- Revision: `7855f7c` plus the uncommitted fix in `api/app/ingest/reader.py` (`_sniff_separator`) and new regressions in `api/tests/test_reader.py`.
- Environment: local docker compose stack (API with Polars 1.17.1, local Postgres `db:5432`). Supabase and production were not touched.
- Data: synthetic only.

## Commands and results

| Command | Result |
| --- | --- |
| `python3 bugs/runs/2026-09-21-reader-matrix.py` | 288 cases, 0 separator failures, all record counts pass, exit 0 (before the fix: 27 failures) |
| `python3 bugs/runs/2026-09-17-reader-check.py` | 4 methods pass, including the BUG-001 reproduction |
| `python3 bugs/runs/2026-09-17-tangent-check.py` | 10 methods pass |
| `docker compose exec api pytest /srv/api/tests/test_reader.py` | 24 passed |
| `docker compose exec -T api python - < bugs/runs/2026-09-21-read-table-matrix.py` | 288 cases through `read_table`: 0 separator failures, 0 row failures; 72 header-name failures, all for the header `say "hello"` (logged as [BUG-003](../reports/BUG-003.md)); exit 0 |
| `pytest /srv/api/tests /srv/dashboards -k "ingest or reader or upload"` against the local DB | 148 passed, 163 deselected (14m58s) |

## Outcome

- [BUG-001](../reports/BUG-001.md): Cleared. The reproduction passes, the full Polars reader suite passes, and a `read_table` regression checks the two column names and the one row.
- [BUG-002](../reports/BUG-002.md): Cleared. The matrix and the `read_table` column and row checks pass for tab, `;` and `|`.
- [BUG-003](../reports/BUG-003.md): new, Open. It was also reproduced with the fix stashed, so the fix did not introduce it.
