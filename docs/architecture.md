# Architecture

One repo, many dashboards. A dashboard owns its data, its schema, its ingest rules and
its spec. Nothing it does can reach another dashboard.

## Layout

```
compose.yml              db + api + web, run by colima
sources/sources.yaml     the files the platform accepts, independent of any dashboard
sources/context.md       shared value definitions: course levels, deposit states, intake period
api/                     FastAPI service: registry, migrations, ingest, changelog, views
  migrations/*.sql       core schema (scope: 'core')
  app/ingest/            file reading, column resolution, the upload pipeline
  app/views.py           dispatch into a dashboard's own read model
dashboards/<slug>/       one self-contained dashboard
  dashboard.yaml         id, schema name, datasets, their sources, natural keys, dimensions
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

## Sources

A file belongs to the CRM, not to whichever dashboard happens to read it. So an
upload names a **source** — a kind of export, declared once in `sources.yaml` —
and every dashboard whose manifest declares that source is fed from it:

```
POST /api/sources/applications/uploads
  │
  ├─ read once, into one polars frame
  ├─ identify: does the header match what this source is?  → 422 with what it looks like instead
  ├─ archive once, keyed on the content hash
  └─ for each dashboard declaring `source: applications`
        └─ its own ingest.py → its own tables → its own load → its own changelog
```

The 114MB applications export is uploaded once and stored once however many
dashboards read it. Each takes different columns and may transform them
differently; none can see another's rows.

**Projections are rows, not a status on the upload.** One upload now has N
outcomes, and the point of the design is that they are independent: a dashboard
whose `ingest.py` raises, or whose migrations have not run, records `failed` on
its own `core.projections` row and keeps serving its previous load, while every
other dashboard's projection commits normally. `api/tests/test_fan_out.py`
asserts exactly that, by breaking one dashboard and checking the others.

**A dashboard added later reads what already arrived.** `POST
/api/uploads/{id}/project?dashboard=<slug>` rebuilds one dashboard's tables from
an archived file — which is what the archive is for, and why the platform can
grow a dashboard without anyone hunting for last week's export. The same
endpoint with `force=true` re-applies a corrected `ingest.py` to the exact bytes
that were loaded, rather than to a fresh export that has since moved on.

## Isolation

| Boundary | Mechanism |
|---|---|
| Data | One Postgres schema per dashboard: `dash_<slug>`. Core never holds dashboard data. |
| Ingest failure | One `core.projections` row per (upload, dataset). A failure is recorded there and rolled back there; other dashboards' projections are separate transactions. |
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

Read models are cached on the load ids they were built from, not on a clock. An
upload creates a new load, which is a new key, so the previous answer becomes
unreachable rather than stale; rolling back returns to the earlier load's key and
its cached answer, which is the same value it computed before. This matters once
the database is not local: fetching one dashboard's book is ~2.5MB and costs
~2.8s across a link to another region, and it was being refetched for the
overview and for each of the thirteen tiles separately. The dashboard caches the
book itself as well, so all of them share one fetch.

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
POST /api/sources/{source}/uploads
  │
  ├─ read → polars, all strings, utf8-lossy    → curly quotes and mojibake normalised
  ├─ identify against the source's headers      → wrong file, 422, nothing stored
  ├─ sha256 → this exact file already archived? → reuse the row, do not store it twice
  ├─ record core.uploads first, so a failure has somewhere to be recorded
  ├─ store the raw file, gzipped (audit trail) → sources/<source>/<sha>.csv.gz
  │
  └─ for each dashboard reading this source, separately:
     ├─ resolve columns: exact → substring → tokens; missing required → the projection fails
     ├─ finalize() → the dashboard's typed frame, plus a row_hash
     ├─ COPY into <schema>.<table> with a new load_id      (not yet current)
     ├─ FULL OUTER JOIN against the current load on the natural key
     │     → exact counts of added / removed / changed
     │     → up to CHANGELOG_ROW_LIMIT row-level diffs with before/after jsonb
     ├─ write core.changelog (+ core.changelog_rows)
     └─ swap: previous load stops being current, new load becomes current
```

Failure inside a projection rolls back that dashboard's staged rows and marks its
`core.projections` row `failed` with the error. Its previous load stays current, and
the other dashboards reading the same file are untouched — so a bad export, or a bad
mapping in one dashboard, cannot leave anything broken.

Re-uploading a file already held is not an error. The dedupe is per dashboard, not per
file, so uploading the same export after adding a dashboard feeds the new one and
reports `duplicate` for the ones that already had it.

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

Natural keys are per dashboard-dataset, not per source: two dashboards reading the same
applications file may identify a row differently, and neither's diffs are the other's.

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

## Connections

Behind Supabase's transaction pooler a connection can be closed by the pooler
without the client being told. The pool would then hand that half-open socket to
the next request, which failed as `OperationalError: consuming input failed: SSL
SYSCALL error: EOF detected` — a 500 on whatever endpoint happened to draw it,
which is why it looked random and why it hit uploads that had already parsed
their file.

`check=ConnectionPool.check_connection` costs one round trip on checkout and
discards the corpse instead. `max_lifetime` and TCP keepalives recycle
connections before anything upstream does it silently; neither replaces the
check, because `min_size` connections are exempt from `max_idle` and those are
exactly the ones that go stale overnight. `api/tests/test_db_pool.py` reproduces
the half-open state directly and asserts both halves.

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

## Storage

The parsed rows go to Postgres; the original export is kept separately so a load
can be explained or replayed. `api/app/storage.py` has two backends behind one
interface -- the filesystem for development, a private Supabase bucket for
anything that outlives a container -- and `STORAGE_BACKEND=supabase` fails at
startup rather than silently falling back, because a deployment that thinks it
is archiving to object storage while writing to a disposable disk loses the
archive without any error.

Keys are the sha256 prefix of the content, so re-uploading the same file writes
the same object instead of a second copy.

**Supabase objects are gzipped; local ones are not.** Supabase enforces a
per-object ceiling at the project level, separate from the bucket's own
`file_size_limit` and, on the free plan, not raisable: 50MB, measured. The
applications export is 114MB, so every upload of it failed at the archive step
with `EntityTooLarge` — and, because the archive ran before the upload row was
written, failed with no record of the attempt anywhere. Gzipped the export is
21MB. Local storage keeps writing plain files, where `head` is worth more than
compression.

Formats that are already compressed do not shrink: a 48MB `.xlsx` stays 48MB, so
a workbook past 50MB still cannot be archived on this plan. That case now returns
413 with the reason and the workaround (export the same data as `.csv`) rather
than a 500 and a stack trace.

**The stored object is the file as it arrived.** For the applications export
that is all 50 source columns, including the student names, nationalities and
reference numbers the ingest layer drops -- the loaded table keeps 18. So the
database holds no student PII but the archive does. The bucket is private with
no `storage.objects` policies, reachable only with the service role key, and how
long these are retained is a decision that has not been made yet.
