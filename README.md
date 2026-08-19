# B2B Dashboards

A dashboard platform for CRM exports. Upload the files, they land in Postgres, and every
upload writes a changelog saying exactly what changed since the last one. Each dashboard
is self-contained: its own schema, migrations, ingest rules and spec.

## Running it

```bash
make vm       # colima VM: 4 cpu / 8 GB / 60 GB   (once per boot)
make up       # build and start db + api + web
make test     # dashboard tests (ingest + metrics)
```

- App: http://localhost:5173
- API docs: http://localhost:8000/docs
- `make psql` for a shell, `make logs` to follow the API, `make reset` to wipe the volume.
- `make typecheck` runs `tsc` over the frontend.

Upload a file:

```bash
curl -F "file=@introducers.csv" \
  "http://localhost:8000/api/dashboards/introducer_performance/datasets/introducers/uploads?uploaded_by=raj"
```

Re-upload the same file and it records a no-op. Re-upload a changed one and you get:

```json
{"status":"ready","rows":17600,"added":14,"removed":2,"changed_rows":31,
 "summary":"Introducers master: +14 added · 31 changed · -2 removed (17,600 rows)"}
```

Then `GET /api/dashboards/{slug}/changelog` for the feed, and
`GET /api/changelog/{id}/rows` for which records changed and which fields moved.

## Reading the numbers

Metrics are computed in Postgres and served per dashboard:

```
GET /api/dashboards/{slug}/views/overview                    tiles, funnel, critique, data notes
GET /api/dashboards/{slug}/views/tile?id=dormant&group_by=country
```

The browser receives finished numbers. Nothing is parsed or aggregated client-side, so a
230k-row applications file renders in the same time as a 139-row one — the overview query
runs in about 0.5s and a drill-down in about 0.15s.

Rolling back a bad export is a flag flip, not a re-import:

```
POST /api/dashboards/{slug}/loads/{load_id}/activate
```

The rows never left, and the switch is written to the changelog.

## Adding a dashboard

Create `dashboards/<slug>/` with a `dashboard.yaml`, a `migrations/001_init.sql`, an
`ingest.py`, a `metrics.py` and a `context.md`. It is picked up on the next API start. It
gets its own Postgres schema and its own migration scope, so it cannot affect anything
already running. For a bespoke overview, add a component to `web/src/dashboards/registry.tsx`;
without one the dashboard still gets working Data and Changelog tabs.

See [docs/architecture.md](docs/architecture.md) for the design and the decisions behind it.

## Status

| Piece | State |
|---|---|
| Postgres schema, registry, migrations | working |
| Upload → parse → load → diff → changelog | working, 230k rows in ~7s |
| Every load retained, rollback by flag | working |
| Introducer ingest + tests | working, 14 tests |
| Metrics API (tiles, funnel, drill-down) | working, 20 tests |
| React + TypeScript frontend | working |
| Auth, object storage, deployment | not started, deliberately last |

`legacy/introducer-dashboard.html` is the original single-file version, kept as the
provenance of the metric definitions. It parses both exports in the browser on every page
load, which is what the React app exists to stop doing.

## Deviations worth knowing

- **Chart series colours are not the spec's.** `#1D7A5F` / `#B7502F` fail a CVD contrast
  check as adjacent chart series (deutan ΔE 7.3, floor 8). Charts use `#0F8A5F` / `#C0491F`;
  text and UI keep the spec colours.
- **The spec's own baseline is internally inconsistent** on current-year active deposits:
  the lifecycle table gives 2,016 (full book) and the funnel row 1,961 (Customer-only).
  Tiles use the full book; the funnel carries an **In scope / All attributed** toggle so the
  difference is visible rather than hidden.
