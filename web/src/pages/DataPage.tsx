import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useActivateLoad, useDashboards, useDatasets, useLoads, useSources, useUpload, useUploads,
} from "../api/client";
import type { SourceSummary, UploadResult, UploadRow } from "../api/types";
import { n0, when } from "../format";
import { Pill, Section, Spinner } from "../ui/Primitives";

/** Where every file arrives, for every dashboard.
 *
 *  Uploads were always platform-level -- a file belongs to a *source*, is
 *  archived once, and is projected into every dashboard that declares it -- but
 *  the page for doing it sat inside one dashboard, which made a shared act look
 *  like a private one and hid what a file did next door. The dashboards keep
 *  their own way of reading the data; this is the one place it comes in. */
export function DataPage() {
  const [params, setParams] = useSearchParams();
  const only = params.get("dashboard") ?? "";
  const dashboards = useDashboards();
  const datasets = useDatasets();
  const loads = useLoads(only || undefined);
  const uploads = useUploads(only || undefined);
  const activate = useActivateLoad();
  const sources = useSources();

  const setOnly = (value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set("dashboard", value); else next.delete("dashboard");
    setParams(next, { replace: true });
  };

  // a file that never parsed has no projections and its own error; a file that
  // parsed can still have failed in one dashboard and loaded in another
  const failed = (uploads.data ?? []).filter(
    (u) => u.status === "failed" || u.projections.some((p) => p.status === "failed"),
  );
  const rows = (datasets.data ?? []).filter((d) => !only || d.dashboard === only);

  return (
    <>
      <header className="top">
        <div className="top-in">
          <h1>Uploads</h1>
          <p className="sub">
            Every file for every dashboard arrives here. A file belongs to the platform, not to
            one dashboard: it is archived once and projected into each dashboard that reads it,
            each into its own tables. Nothing is ever deleted, so a bad export can be rolled back
            rather than re-imported.
          </p>
        </div>
      </header>

      <div className="wrap">
        <Section
          title="Upload"
          note="Drop a file on the export it is. Every dashboard listed under it is rebuilt from it."
        >
          {sources.isLoading ? <Spinner /> : null}
          <div className="drops">
            {sources.data?.map((source) => <Drop key={source.slug} source={source} />)}
          </div>
        </Section>

        {failed.length > 0 ? <FailedUploads rows={failed} /> : null}

        <Section
          title="Loaded now"
          note="What each dashboard is serving, and the file behind it."
          aside={
            <DashFilter
              value={only}
              onChange={setOnly}
              options={(dashboards.data ?? []).map((d) => ({ value: d.slug, label: d.name }))}
            />
          }
        >
          {datasets.isLoading ? <Spinner /> : null}
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th className="txt">Dashboard</th><th className="txt">Table</th>
                  <th className="txt">From file</th><th className="num">Rows</th>
                  <th className="txt">Loaded</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.dashboard}.${row.dataset}`}>
                    <td className="txt">{row.dashboard_name}</td>
                    <td className="txt">
                      {row.display_name}
                      {/* only when it adds something: most tables are named
                          after the export they are built from */}
                      {row.source_name === row.display_name
                        ? null
                        : <span className="who">from {row.source_name}</span>}
                    </td>
                    <td className="txt">
                      {row.filename ?? <span className="dim">nothing loaded yet</span>}
                    </td>
                    <td className="num">{row.row_count == null ? "--" : n0(row.row_count)}</td>
                    <td className="txt">
                      {row.load_id
                        ? when(row.created_at)
                        : <span className="dim">--</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section
          title="Files received"
          note="Every file the platform has been given, and what each dashboard made of it."
        >
          {uploads.isLoading ? <Spinner /> : null}
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th className="txt">When</th><th className="txt">File</th>
                  <th className="txt">Export</th><th className="num">Rows</th>
                  <th className="txt">Went to</th>
                </tr>
              </thead>
              <tbody>
                {uploads.data?.map((row) => (
                  <tr key={row.id}>
                    <td className="txt">{when(row.started_at)}</td>
                    <td className="txt">{row.filename}</td>
                    <td className="txt">{row.source_name}</td>
                    <td className="num">{row.row_count == null ? "--" : n0(row.row_count)}</td>
                    <td className="txt">
                      {row.status === "failed" ? (
                        <span style={{ color: "var(--bad)" }}>file rejected</span>
                      ) : (
                        row.projections.map((p) => (
                          <span key={`${p.dashboard}.${p.dataset}`} style={{ marginRight: 10 }}>
                            {p.dashboard_name ?? p.dashboard}{" "}
                            <Pill kind={p.status === "ready" ? "live" : p.status === "duplicate" ? "cold" : "bad"}>
                              {p.status === "ready" ? n0(p.rows ?? 0) : p.status}
                            </Pill>
                          </span>
                        ))
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section
          title="Load history"
          note="Every load ever made, newest first. Rolling back moves the current flag; no rows are deleted."
        >
          {loads.isLoading ? <Spinner /> : null}
          {activate.error ? <p className="status err">{(activate.error as Error).message}</p> : null}
          {activate.data ? <p className="status ok">{activate.data.summary}</p> : null}
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">Load</th><th className="txt">Dashboard</th>
                  <th className="txt">Table</th><th className="txt">File</th>
                  <th className="num">Rows</th><th className="txt">Created</th>
                  <th className="txt">Superseded</th><th className="txt">Current</th><th />
                </tr>
              </thead>
              <tbody>
                {loads.data?.map((load) => (
                  <tr key={load.id}>
                    <td className="num">{load.id}</td>
                    <td className="txt">{load.dashboard_name}</td>
                    <td className="txt">{load.dataset}</td>
                    <td className="txt">{load.filename}</td>
                    <td className="num">{n0(load.row_count)}</td>
                    <td className="txt">{when(load.created_at)}</td>
                    <td className="txt">
                      {load.superseded_at ? when(load.superseded_at) : <span className="dim">--</span>}
                    </td>
                    <td className="txt">
                      {load.is_current
                        ? <span style={{ color: "var(--good)" }}>yes</span>
                        : <span className="dim">no</span>}
                    </td>
                    <td className="act">
                      {load.is_current ? null : (
                        <button
                          type="button"
                          disabled={activate.isPending}
                          onClick={() => activate.mutate({ dashboard: load.dashboard, loadId: load.id })}
                        >
                          make current
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      </div>
    </>
  );
}

/** Shared by both platform pages: narrow the tables to one dashboard without
 *  putting the pages back inside one. */
export function DashFilter({ value, onChange, options }: {
  value: string;
  onChange: (next: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      className="dash-filter"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label="Filter by dashboard"
    >
      <option value="">All dashboards</option>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

/** Failures leave no load and no changelog entry, so without this the page would
 *  show the previous file as current and give no hint that an import died. */
function FailedUploads({ rows }: { rows: UploadRow[] }) {
  return (
    <Section
      title="Failed uploads"
      note="These never became a load. The dashboards below them still serve the previous file."
    >
      <div className="tbl-wrap">
        <table>
          <thead>
            <tr>
              <th className="txt">When</th><th className="txt">File</th>
              <th className="txt">Where</th><th className="txt">Why it failed</th>
            </tr>
          </thead>
          <tbody>
            {rows.flatMap((row) => {
              const bad = row.projections.filter((p) => p.status === "failed");
              // the file itself was rejected: there is no dashboard to blame
              if (row.status === "failed") {
                return [(
                  <tr key={`u${row.id}`}>
                    <td className="txt">{when(row.started_at)}</td>
                    <td className="txt">{row.filename}</td>
                    <td className="txt"><span className="dim">the file</span></td>
                    <td className="txt note-cell" style={{ color: "var(--bad)" }}>
                      {row.error ?? "unknown"}
                    </td>
                  </tr>
                )];
              }
              return bad.map((p) => (
                <tr key={`u${row.id}.${p.dashboard}.${p.dataset}`}>
                  <td className="txt">{when(row.started_at)}</td>
                  <td className="txt">{row.filename}</td>
                  <td className="txt">{p.dashboard_name ?? p.dashboard} · {p.dataset}</td>
                  <td className="txt note-cell" style={{ color: "var(--bad)" }}>
                    {p.error ?? "unknown"}
                  </td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function Drop({ source }: { source: SourceSummary }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const upload = useUpload();

  const send = (file: File | undefined) => {
    if (!file) return;
    setResult(null);
    upload.mutate({ source: source.slug, file }, { onSuccess: setResult });
  };

  return (
    <div>
      <div
        className={`drop${over ? " over" : ""}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); send(e.dataTransfer.files[0]); }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter") input.current?.click(); }}
      >
        <b>{source.display_name}</b>
        <span>Drop a .csv or .xlsx here, or click to choose</span>
        {/* named before the drop, not after it: this is the fan-out, and it is
            the thing that makes an upload here different from an upload to a
            single dashboard */}
        <span className="req">
          feeds {source.dashboards.map((d) => d.name).join(", ") || "nothing yet"}
        </span>
        <input
          ref={input} type="file" accept=".csv,.xlsx,.xls" hidden
          onChange={(e) => { send(e.target.files?.[0]); e.target.value = ""; }}
        />
      </div>
      {upload.isPending ? <p className="status busy"><span className="spinner" /> parsing and loading…</p> : null}
      {upload.error ? <p className="status err">{(upload.error as Error).message}</p> : null}
      {result?.projections.map((p) => (
        <p key={`${p.dashboard}.${p.dataset}`}
           className={`status ${p.status === "failed" ? "err" : p.status === "duplicate" ? "busy" : "ok"}`}>
          {p.dashboard}: {p.summary ?? p.error ?? p.status}
        </p>
      ))}
    </div>
  );
}
