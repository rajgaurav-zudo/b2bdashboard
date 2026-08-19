# Architecture

One repo, many dashboards. A dashboard owns its data, its schema, its ingest rules and
its spec. Nothing it does can reach another dashboard.

## Layout

```
compose.yml              db + api, run by colima
api/                     FastAPI service: registry, migrations, ingest, changelog
  migrations/*.sql       core schema (scope: 'core')
  app/ingest/            file reading, column resolution, the upload pipeline
dashboards/<slug>/       one self-contained dashboard
  dashboard.yaml         id, schema name, datasets, natural keys, dimensions
  context.md             the spec; its sha256 is stored on core.dashboards
  migrations/*.sql       that dashboard's tables, applied in its own schema
  ingest.py              how its export columns map onto those tables
  tests/                 its rules, asserted
legacy/                  the original single-file browser dashboard
web/                     React app (not built yet)
```

## Isolation

| Boundary | Mechanism |
|---|---|
| Data | One Postgres schema per dashboard: `dash_<slug>`. Core never holds dashboard data. |
| Schema changes | Migrations are scoped per dashboard in `core.schema_migrations (scope, version)`. A broken migration in one dashboard does not block another. |
| Ingest rules | `dashboards/<slug>/ingest.py`, imported by path. No shared parsing rules beyond the generic reader. |
| Grouping | `dimensions:` in that dashboard's manifest. |
| Spec | `context.md` per dashboard, hashed into `core.dashboards.context_sha`. |

The one deliberate coupling is the shared UI kit in `web/`. Keep it additive — that
discipline replaces the isolation separate HTML files gave for free.

## Upload pipeline

```
POST /api/dashboards/{slug}/datasets/{dataset}/uploads
  │
  ├─ sha256 → identical to the current load?  → record 'duplicate', changelog no-op, stop
  ├─ store the raw file (audit trail)          → data/uploads/<slug>/<dataset>/<sha>.csv
  ├─ read → polars, all strings, utf8-lossy    → curly quotes and mojibake normalised
  ├─ resolve columns: exact → substring → tokens; missing required → 422 with a hint
  ├─ finalize() → the dashboard's typed frame, plus a row_hash
  ├─ COPY into <schema>.<table> with a new load_id      (not yet current)
  ├─ FULL OUTER JOIN against the current load on the natural key
  │     → exact counts of added / removed / changed
  │     → up to CHANGELOG_ROW_LIMIT row-level diffs with before/after jsonb
  ├─ write core.changelog (+ core.changelog_rows)
  └─ swap: previous load stops being current, new load becomes current
```

Failure at any step rolls back the staged rows and marks the upload `failed` with the
error. The previous load stays current, so a bad export cannot leave a dashboard broken.

## Retention

Every load is kept. `core.loads.is_current` is a flag, not a deletion — so any past
snapshot stays queryable, rollback is a flag flip, and the changelog always has both
sides of a diff to point at. Growth is roughly the file size per upload.

## Changelog

`core.changelog` is one row per (upload, entity): exact counts plus a readable summary.
`core.changelog_rows` holds the row-level diffs hanging off it — `natural_key`,
`changed_fields`, and the `before`/`after` documents.

Counts are always exact. Row-level storage is capped by `CHANGELOG_ROW_LIMIT` (default
10,000) so a first load or a mangled export cannot write millions of rows; when the cap
is hit, `details.row_limit_hit` is true and `rows_sampled` says how many were kept.

## Natural keys

Diffs need a stable identity per row. `dashboard.yaml` declares it per dataset:

- **introducers** → `partner_name`, the join key the business already uses.
- **applications** → `app_uid`: the export's application id when one exists, otherwise a
  content hash plus occurrence index.

The synthesised key is stable as long as an unchanged row appears the same number of
times in each export. **If the applications export has a real application id column, the
diffs get materially better** — it is picked up automatically by header matching.

## Choices worth re-reading later

- **Postgres only, no analytical engine.** 227k rows per load is small. Revisit if a
  dashboard needs to scan tens of millions of rows per request.
- **Migrations on API startup.** Convenient in dev; in production run `make migrate` as
  a release step and drop the call from `lifespan`.
- **Sync ingest.** 230k rows takes ~7s end to end, inside one request. If uploads get
  bigger or concurrent, move `ingest()` behind a queue — the status column and changelog
  already model an async lifecycle.
- **`WATCHFILES_FORCE_POLLING`** is set because colima's virtiofs mount does not emit
  inotify events, so `--reload` misses edits without it.
