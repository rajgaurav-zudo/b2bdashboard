import { useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { useActivateLoad, useLoads, useUpload } from "../api/client";
import type { DashboardDetail, UploadResult } from "../api/types";
import { n0, when } from "../format";
import { Section, Spinner } from "../ui/Primitives";

export function DataPage() {
  const dashboard = useOutletContext<DashboardDetail>();
  const loads = useLoads(dashboard.slug);
  const activate = useActivateLoad(dashboard.slug);

  return (
    <>
      <div className="head">
        <h1>Data</h1>
        <p>
          Every upload is kept. The newest load for each dataset is the one every figure is built
          from; the others stay queryable, so a bad export can be rolled back rather than re-imported.
        </p>
      </div>

      <Section title="Upload">
        <div className="drops">
          {dashboard.datasets.map((dataset) => (
            <Drop key={dataset.slug} slug={dashboard.slug} dataset={dataset.slug}
                  label={dataset.display_name}
                  hint={dataset.required_columns?.join(" · ") ?? ""} />
          ))}
        </div>
      </Section>

      <Section title="Current loads">
        <div className="card scroll">
          <table>
            <thead>
              <tr>
                <th>Dataset</th><th>File</th><th className="num">Rows</th>
                <th>Loaded</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.current_loads.map((load) => (
                <tr key={load.dataset}>
                  <td>{load.dataset}</td>
                  <td>{load.filename ?? <span className="dim">nothing loaded</span>}</td>
                  <td className="num">{load.row_count == null ? "--" : n0(load.row_count)}</td>
                  <td>{when(load.created_at)}</td>
                  <td>{load.load_id ? <span style={{ color: "var(--good)" }}>current</span> : "--"}</td>
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
        <div className="card scroll">
          <table>
            <thead>
              <tr>
                <th className="num">Load</th><th>Dataset</th><th>File</th>
                <th className="num">Rows</th><th>Created</th><th>Superseded</th><th>Current</th><th />
              </tr>
            </thead>
            <tbody>
              {loads.data?.map((load) => (
                <tr key={load.id}>
                  <td className="num">{load.id}</td>
                  <td>{load.dataset}</td>
                  <td>{load.filename}</td>
                  <td className="num">{n0(load.row_count)}</td>
                  <td>{when(load.created_at)}</td>
                  <td>{load.superseded_at ? when(load.superseded_at) : <span className="dim">--</span>}</td>
                  <td>{load.is_current ? <span style={{ color: "var(--good)" }}>yes</span> : <span className="dim">no</span>}</td>
                  <td>
                    {load.is_current ? null : (
                      <button type="button" className="chip" disabled={activate.isPending}
                              onClick={() => activate.mutate(load.id)}>
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
    </>
  );
}

function Drop({ slug, dataset, label, hint }: {
  slug: string; dataset: string; label: string; hint: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const upload = useUpload(slug);

  const send = (file: File | undefined) => {
    if (!file) return;
    setResult(null);
    upload.mutate({ dataset, file }, { onSuccess: setResult });
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
        <b>{label}</b>
        <span>Drop a .csv or .xlsx here, or click to choose</span>
        {hint ? <span>needs {hint}</span> : null}
        <input
          ref={input} type="file" accept=".csv,.xlsx,.xls" hidden
          onChange={(e) => { send(e.target.files?.[0]); e.target.value = ""; }}
        />
      </div>
      {upload.isPending ? <p className="status busy"><span className="spinner" /> parsing and loading…</p> : null}
      {upload.error ? <p className="status err">{(upload.error as Error).message}</p> : null}
      {result ? (
        <p className={`status ${result.status === "duplicate" ? "busy" : "ok"}`}>
          {result.summary ?? `upload ${result.status}`}
        </p>
      ) : null}
    </div>
  );
}
