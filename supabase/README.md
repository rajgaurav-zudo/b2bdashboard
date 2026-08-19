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
