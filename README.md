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
227k-row applications file renders in the same time as a 139-row one — the overview query
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
without one the dashboard is still fed, and still appears on Uploads and Changelog.

Uploading and the changelog are platform pages, not dashboard ones. A file belongs to a
source and fans out, so there is one place to drop it (`/uploads`) and one log of what each
upload did to each dashboard (`/changelog`); both can be narrowed to a single dashboard.

Each dataset names the **source** that feeds it. If the file is one the platform already
accepts, point at it and the dashboard is fed from the archive without anyone re-uploading:

```
POST /api/uploads/{id}/project?dashboard=<slug>
```

If the file is new, declare it in `sources/sources.yaml` first — `identified_by` is what
refuses the wrong export before a single row is stored.

See [docs/architecture.md](docs/architecture.md) for the design and the decisions behind it.

## Status

| Piece | State |
|---|---|
| Postgres schema, registry, migrations | working |
| Upload → parse → load → diff → changelog | working, 227k rows in ~5.5s |
| Every load retained, rollback by flag | working |
| File reading + column resolution | working, 13 tests |
| Introducer ingest + tests | working, 14 tests |
| Metrics API (tiles, funnel, drill-down) | working, 20 tests |
| Drill-down side pane (group / sort / expand) | working, client-side from `/views/members` |
| React + TypeScript frontend | working |
| Hosting, object storage | undecided; the repo runs locally only |

`legacy/introducer-dashboard.html` is the original single-file version, kept as the
provenance of both the metric definitions and the visual design. It parses both exports in
the browser on every page load, which is what the React app exists to stop doing; the
stylesheet and the drill-down pane are ports of it, not reinterpretations.

## Exports that need handling

- **Lone-CR line endings.** Excel for Mac and some CRM exporters end each record with `\r`
  rather than `\n`. Polars breaks rows on `\n` only, so the whole file arrives as a single
  header row: the 227k-row, 114MB applications export parsed as a 2,907-column header and
  exhausted memory before a row was read. `read_table` normalises `\r\n` and `\r` to `\n`
  before parsing, and every load is checked against an independent record count.
- **Interrupted imports.** A crash mid-import cannot mark its own upload failed, so the row
  sat at `parsing` forever while the dashboard quietly served the previous file. Startup
  fails anything left in flight, and the Uploads page lists failed uploads with the reason.

## Deviations worth knowing

- **Chart series colours are not the spec's.** `#1D7A5F` / `#B7502F` fail a CVD contrast
  check as adjacent chart series (deutan ΔE 7.3, floor 8). Charts use `#0F8A5F` / `#C0491F`;
  text and UI keep the spec colours.
- **The spec's own baseline is internally inconsistent** on current-year active deposits:
  the lifecycle table gives 2,016 (full book) and the funnel row 1,961 (Customer-only).
  Tiles use the full book; the funnel carries an **In scope / All attributed** toggle so the
  difference is visible rather than hidden.
- **Two of Introducer 360's eleven stages carry no date, and say so.** A stage there is an
  event — an application that *entered* it, read off the CRM's `Timestamp of '<status>'`
  columns — which is what makes a date range mean anything. Partial deposits and deferrals
  awaiting approval are recorded as flags with no transition, so they are reported "as of"
  the export instead of being narrowed by the window, they carry no year-on-year delta, and
  the introducer-wise total column counts only the nine stages that are events. Borrowing
  another column's date for them was tried and made the card read 0 on any short window.
- **Introducer 360 keeps the handoff's layout, not its palette.** The eight-card line, the
  card anatomy, the group breakdown and the counsellor-wise modal are the design's; the
  colours, type and components are this codebase's, because a second visual language inside
  the same left menu costs more than it buys.
