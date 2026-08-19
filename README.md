# B2B Dashboards

A dashboard platform for CRM exports. Upload the files, they land in Postgres, and every
upload writes a changelog saying exactly what changed since the last one. Each dashboard
is self-contained: its own schema, migrations, ingest rules and spec.

## Running it

```bash
make vm       # colima VM: 4 cpu / 8 GB / 60 GB   (once per boot)
make up       # build and start db + api
make test     # dashboard ingest tests
```

- API docs: http://localhost:8000/docs
- `make psql` for a shell, `make logs` to follow the API, `make reset` to wipe the volume.

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

## Adding a dashboard

Create `dashboards/<slug>/` with a `dashboard.yaml`, a `migrations/001_init.sql`, an
`ingest.py` and a `context.md`. It is picked up on the next API start. It gets its own
Postgres schema and its own migration scope, so it cannot affect anything already running.

See [docs/architecture.md](docs/architecture.md) for the design and the decisions behind it.

## Status

| Piece | State |
|---|---|
| Postgres schema, registry, migrations | working |
| Upload → parse → load → diff → changelog | working, 230k rows in ~7s |
| Every load retained, rollback by flag | working |
| Introducer ingest + tests | working, 14 tests |
| Metrics API (tiles, funnel, drill-down) | not started — currently computed in the browser |
| React frontend | not started |
| Auth, object storage, deployment | not started, deliberately last |

`legacy/introducer-dashboard.html` is the original single-file version. It still works
standalone and is the reference for the metric definitions until the metrics move server-side.
