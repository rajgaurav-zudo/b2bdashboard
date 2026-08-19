# Supabase migrations

**This directory does not own the application schema.** There are two migration
systems pointed at one database, and they must never touch the same objects.

| | Owns | Applied by | Tracked in |
|---|---|---|---|
| `api/migrations/*.sql` | `core.*` — dashboards, datasets, uploads, loads, changelog | `migrate.run()` on API startup | `core.schema_migrations` (scope `core`) |
| `dashboards/<slug>/migrations/*.sql` | that dashboard's `dash_<slug>` schema | same runner, `search_path` set to the dashboard | `core.schema_migrations` (scope `<slug>`) |
| `supabase/migrations/*.sql` | platform config only — RLS policies, roles and grants, storage buckets, auth hooks | `supabase db push` | `supabase_migrations.schema_migrations` |

The app's runner is scoped per dashboard on purpose: a broken migration in one
dashboard cannot block another, and each dashboard's SQL is written with
unqualified names against its own schema. `supabase db push` is global and has
no such notion, so moving the app schema here would quietly discard that.

## What is here

| Migration | Does |
|---|---|
| `20260819172134_uploads_bucket.sql` | Private `uploads` bucket for the raw CRM exports: 200MB limit, spreadsheet mime types, and deliberately no `storage.objects` policies so only the service role can reach it. |

Not written yet, and why:

- **Auth policies.** Waiting on one decision: does the browser query PostgREST
  directly, or only ever the API? If only the API, RLS is defence in depth and
  the JWT is verified in FastAPI. If direct, RLS becomes the actual access
  control and has to be written per table before anything is exposed.
- **A least-privilege API role.** The API would otherwise connect as `postgres`.
  A dedicated owner role for `core` and `dash_*` is better, but its password
  cannot live in a committed migration, so creating it here only half-does the
  job.

## Do not run `supabase db pull`

It dumps the *entire* live schema into a new migration here — `core`, every
`dash_<slug>`, the lot. You would end up with the same tables defined in two
places, applied by two runners, in an order neither controls. If you need the
schema in one file, read `api/migrations/` and `dashboards/*/migrations/`.

## Config notes

- **`storage.file_size_limit = "50MiB"` is too small.** The applications export
  is 114MB. Raise it here *and* in the dashboard (Settings → Storage) before
  uploads move off the local filesystem, or every real import fails at the
  upload step.
- **`db.major_version = 17`** only affects a local `supabase start`, which this
  project does not use — `docker compose` runs Postgres 16. Worth aligning with
  whatever the remote project actually runs before anyone relies on the local
  Supabase stack.
- **`api.schemas = ["public", "graphql_public"]` is correct as generated.**
  `core` and `dash_*` are deliberately not exposed through PostgREST: every read
  goes through a dashboard-owned SQL view model in the API, which is what makes
  a tile number reproducible. Adding them here would create a second, unversioned
  query path around that.

## The remote project, measured

Region `ap-northeast-2` (Seoul), Postgres 17.6, reached over the transaction
pooler at `aws-0-ap-northeast-2.pooler.supabase.com:6543`. The direct host
`db.<ref>.supabase.co` resolves to IPv6 only, so the pooler is the practical
route.

The app's own migrations apply cleanly (`make migrate-remote`), and both real
exports load through the API: 17,587 introducers in 4.7s, 227,199 applications
in 25.6s. The read model returns figures **identical** to the local baseline --
current year 2026, 7,037 in the book, 2,016 active deposits in the 2026 intake.

**Region looks like the wrong choice.** Measured from this machine:

| Region | TCP connect |
|---|---|
| `ap-northeast-2` Seoul — current | 196ms |
| `ap-south-1` Mumbai | 67ms |
| `ap-southeast-1` Singapore | 47ms |

That matters because the overview takes ~7 round trips. On Supabase it runs in
2.8s against 0.5s locally, and almost all of the difference is distance, not
the database: `select 1` costs 124ms while counting all 227,199 rows costs
147ms — about 23ms of actual compute.

Two consequences:

- Deployed next to the database this cost disappears, so the number to judge is
  not the one measured from a laptop.
- A Supabase project's region **cannot be changed after creation**. Moving means
  a new project. Worth deciding before anything else is built on this one.
