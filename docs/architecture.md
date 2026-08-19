# Architecture

One repo, many dashboards. A dashboard owns its data, its schema, its ingest rules and
its spec. Nothing it does can reach another dashboard.

## Layout

```
compose.yml              db + api + web, run by colima
api/                     FastAPI service: registry, migrations, ingest, changelog, views
  migrations/*.sql       core schema (scope: 'core')
  app/ingest/            file reading, column resolution, the upload pipeline
  app/views.py           dispatch into a dashboard's own read model
dashboards/<slug>/       one self-contained dashboard
  dashboard.yaml         id, schema name, datasets, natural keys, dimensions
  context.md             the spec; its sha256 is stored on core.dashboards
  migrations/*.sql       that dashboard's tables, applied in its own schema
  ingest.py              how its export columns map onto those tables
  metrics.py             its read model: VIEWS = {name: fn}
  tests/                 its rules, asserted
legacy/                  the original single-file browser dashboard
web/                     React + TypeScript app (Vite)
  src/ui/                the shared kit -- the one deliberate coupling
  src/dashboards/<name>/ one dashboard's bespoke widgets
  src/dashboards/registry.tsx   slug -> overview component
```

## Isolation

| Boundary | Mechanism |
|---|---|
| Data | One Postgres schema per dashboard: `dash_<slug>`. Core never holds dashboard data. |
| Schema changes | Migrations are scoped per dashboard in `core.schema_migrations (scope, version)`. A broken migration in one dashboard does not block another. |
| Ingest rules | `dashboards/<slug>/ingest.py`, imported by path. No shared parsing rules beyond the generic reader. |
| Grouping | `dimensions:` in that dashboard's manifest. |
| Spec | `context.md` per dashboard, hashed into `core.dashboards.context_sha`. |
| Metrics | `dashboards/<slug>/metrics.py`, imported by path. Core resolves the current loads and sets the search_path; the SQL inside is the dashboard's own. |

The one deliberate coupling is the shared UI kit in `web/`. Keep it additive — that
discipline replaces the isolation separate HTML files gave for free.

## Read models

Metrics are SQL, computed per request against the current load, and served through one
generic endpoint:

```
GET /api/dashboards/{slug}/views/{view}?...
  │
  ├─ core: resolve the dashboard, find the current load id for every dataset
  ├─ core: set search_path to dash_<slug>, open a read-only transaction
  ├─ dashboard: metrics.VIEWS[view](ctx, params)
  └─ core: roll back, return JSON
```

Core never knows what a tile is. Adding a view to one dashboard cannot change another's,
and a dashboard with no `metrics.py` simply has no views.

Drill-downs are the exception to "the server does the arithmetic": `/views/members`
returns one tile's whole member list and the pane groups, sorts and expands it locally.
Regrouping 3.5k rows in the browser is instant and a round trip is not, and the payload
gzips to ~75KB. `/views/tile` still does the same work server-side with a row cap, for
consumers that want a bounded response.

The browser receives finished numbers. On a 227k-row applications file the overview query
takes ~0.5s and a grouped drill-down ~0.15s; the payload does not grow with the file,
because drill-downs are grouped, sorted and capped server-side.

**Definitions live in one place.** `pick_current_year`, the lifetime window, the scope
rule and the thirteen tile predicates were ported from the browser build to
`metrics.py`, and the assertions came with them — `tests/test_metrics.py` inserts
synthetic rows under a throwaway load id, runs the real SQL, and rolls back, so the dev
database is untouched and the rules are tested rather than the dictionaries.

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

`POST /api/dashboards/{slug}/loads/{load_id}/activate` performs that flip and writes a
changelog entry, so history still explains why the numbers moved. The Data tab exposes it
as **make current** on every superseded load.

`core.loads.stats` holds ingest-time counts that cannot be recovered from the loaded rows
— how many input rows were blank or collapsed as duplicates. Each dashboard decides what
goes in it via an optional `stats()` hook in its ingest module.

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
- **Sync ingest.** 227k rows takes ~5.5s end to end, inside one request. If uploads get
  bigger or concurrent, move `ingest()` behind a queue — the status column and changelog
  already model an async lifecycle.
- **`WATCHFILES_FORCE_POLLING`** is set because colima's virtiofs mount does not emit
  inotify events, so `--reload` misses edits without it. Vite needs the same treatment
  (`server.watch.usePolling`).
- **Metrics recomputed per request, not cached.** At current volumes the query is faster
  than any invalidation scheme would be worth. If a dashboard grows past a second or two,
  materialise per-load aggregates keyed on `load_id` — they are immutable once written.
- **The frontend fetches through a Vite proxy** rather than an absolute API origin, so
  the browser needs no CORS and no per-environment configuration. The API's CORS list
  exists only for running `npm run dev` outside the container.

## Auth

The browser signs in with Supabase Auth and sends the resulting JWT to the API,
which verifies it against the project's published JWKS (ES256 -- the API holds a
public key and nothing that could mint a token). PostgREST stays switched off:
`core` and `dash_*` are not in `api.schemas`, so the dashboard-owned SQL view
models remain the only way to read the data, and RLS is defence in depth rather
than the access control itself.

**Authentication is not authorization.** A Supabase project takes public
sign-ups by default, so a valid signature proves only that someone found the
sign-up form. `AUTH_ALLOWED_DOMAINS` / `AUTH_ALLOWED_EMAILS` decide who actually
gets in, and the API refuses to start with auth on and neither set -- looking
protected while admitting everyone is the worst of the three states.

Three settings hold that up together, and all three are needed:

| Where | Setting | Why |
|---|---|---|
| API | allow-list, checked per request | The only one enforced right now |
| Supabase | `enable_signup = false` | Nobody uncertain gets a token at all |
| Supabase | `enable_confirmations = true` | The allow-list trusts the `email` claim, so the address must be proven |

`config.toml` governs the local stack; the live project needs the same settings
applied in the dashboard, or with `supabase config push`.

Auth is off in local development (`AUTH_REQUIRED=false` in compose.yml) so the
stack runs without an account. The default in `config.py` is on, and the API
prints a conspicuous line at boot when it is off.
