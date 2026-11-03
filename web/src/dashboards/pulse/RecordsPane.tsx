import { useEffect, useMemo, useState } from "react";

import { useView } from "../../api/client";
import { n0 } from "../../format";
import type { Drill, PulseRecords } from "./types";

const DIM_NAMES: Record<string, string> = {
  region: "Region", team: "Team", country: "Country", introducer: "Introducer",
};

/** The records behind a figure: the same scope as the page, narrowed to one
 *  metric and, when the click came from a bar or a breakdown row, to that
 *  bucket or row. Search and the CSV download work on what was fetched. */
export function RecordsPane({ slug, scope, drill, onClose }: {
  slug: string;
  scope: Record<string, string | undefined>;
  drill: Drill | null;
  onClose: () => void;
}) {
  const [find, setFind] = useState("");
  useEffect(() => setFind(""), [drill]);
  const params = drill ? {
    ...scope,
    metric: drill.metric,
    from: drill.from ?? scope.from,
    to: drill.to ?? scope.to,
    dim: drill.dim,
    key: drill.key,
  } : {};
  const { data, isLoading, error } = useView<PulseRecords>(slug, "records", params, drill !== null);
  const open = drill !== null;

  const shown = useMemo(() => {
    const needle = find.trim().toLowerCase();
    if (!data || !needle) return data?.rows ?? [];
    return data.rows.filter((r) => Object.values(r).some((v) => v !== null && String(v).toLowerCase().includes(needle)));
  }, [data, find]);

  const download = () => {
    if (!data) return;
    const cell = (v: unknown) => {
      const s = v === null || v === undefined ? "" : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [
      data.columns.map((c) => cell(c.name)).join(","),
      ...shown.map((r) => data.columns.map((c) => cell(r[c.id])).join(",")),
    ];
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${data.name} ${data.range.from} to ${data.range.to}${data.key ? ` ${data.key}` : ""}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className={`scrim${open ? " on" : ""}`} onClick={onClose} />
      <aside className={`pane wide${open ? " on" : ""}`} aria-hidden={!open} role="dialog" aria-label="Records">
        <div className="pane-h">
          <div className="row1">
            <div>
              <h2>{data ? data.name : drill ? "Loading…" : "Records"}{drill ? ` · ${drill.label}` : ""}</h2>
              {data ? (
                <p className="pdef">
                  <b>{n0(data.total)}</b> {data.total === 1 ? "record" : "records"}
                  {data.dim ? <> where {DIM_NAMES[data.dim]?.toLowerCase()} is <b>{data.key}</b></> : null}
                  {data.total > data.rows.length ? <>, the newest {n0(data.rows.length)} shown</> : null}.
                  B2B only, with the same region, team and intake filters as the page.
                </p>
              ) : null}
            </div>
            <button className="x" onClick={onClose} aria-label="Close">×</button>
          </div>
          {data ? (
            <div style={{ display: "flex", gap: 10, alignItems: "center", margin: "12px 0" }}>
              <input
                className="find" type="search" value={find} placeholder="Search these records…"
                onChange={(e) => setFind(e.target.value)} style={{ flex: 1 }}
              />
              <button type="button" className="btn" onClick={download} disabled={!shown.length}>
                Download CSV
              </button>
            </div>
          ) : null}
        </div>

        <div className="pane-body">
          {error ? <p className="empty-pane">{(error as Error).message}</p> : null}
          {isLoading ? <p className="empty-pane">Loading the records…</p> : null}
          {data && !shown.length ? <p className="empty-pane">No records match.</p> : null}
          {data && shown.length ? (
            <div className="tbl-wrap">
              <table className="pulse-records">
                <thead>
                  <tr>{data.columns.map((c) => <th key={c.id} className="txt">{c.name}</th>)}</tr>
                </thead>
                <tbody>
                  {shown.map((r, i) => (
                    <tr key={i}>
                      {data.columns.map((c) => (
                        <td key={c.id} className={c.id === "note" ? "pulse-note" : "txt"}>{r[c.id] ?? ""}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </aside>
    </>
  );
}
