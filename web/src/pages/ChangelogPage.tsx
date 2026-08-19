import { useState } from "react";
import { useOutletContext } from "react-router-dom";

import { useChangelog, useChangelogRows } from "../api/client";
import type { DashboardDetail } from "../api/types";
import { n0, when } from "../format";
import { Empty, Pill, Section, Spinner } from "../ui/Primitives";

export function ChangelogPage() {
  const dashboard = useOutletContext<DashboardDetail>();
  const { data, isLoading } = useChangelog(dashboard.slug);
  const [open, setOpen] = useState<number | null>(null);
  const rows = useChangelogRows(open);

  return (
    <>
      <div style={{ paddingTop: 30 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Changelog</h2>
        <p>
          What each upload changed, computed by comparing the new load against the one it replaced on
          the dataset's natural key. Counts are always exact; the row-level diffs below them are
          capped so one bad export cannot write millions of rows.
        </p>
      </div>

      <Section title="Uploads">
        {isLoading ? <Spinner /> : null}
        {data?.length === 0 ? <Empty title="Nothing uploaded yet" /> : null}
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th className="txt">When</th><th className="txt">Dataset</th><th className="txt">Summary</th>
                <th className="num">+</th><th className="num">~</th><th className="num">−</th>
                <th className="txt">File</th><th />
              </tr>
            </thead>
            <tbody>
              {data?.map((entry) => (
                <tr key={entry.id}>
                  <td className="txt">{when(entry.occurred_at)}</td>
                  <td className="txt">{entry.entity}</td>
                  <td className="txt" style={{ whiteSpace: "normal" }}>{entry.summary}</td>
                  <td className="num" style={{ color: "var(--good)" }}>{n0(entry.rows_added ?? 0)}</td>
                  <td className="num" style={{ color: "var(--warn)" }}>{n0(entry.rows_changed ?? 0)}</td>
                  <td className="num" style={{ color: "var(--bad)" }}>{n0(entry.rows_removed ?? 0)}</td>
                  <td className="txt">
                    {entry.filename}{" "}
                    {entry.status === "duplicate" ? <Pill>duplicate</Pill> : null}
                  </td>
                  <td className="act">
                    {entry.rows_sampled ? (
                      <button type="button"
                              onClick={() => setOpen(open === entry.id ? null : entry.id)}>
                        {open === entry.id ? "hide" : `${n0(entry.rows_sampled)} row diffs`}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {open ? (
        <Section title="Row-level diffs">
          {rows.isLoading ? <Spinner /> : null}
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr><th>Change</th><th>Key</th><th>Fields</th><th>Before → after</th></tr>
              </thead>
              <tbody>
                {rows.data?.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <Pill kind={row.change_type === "added" ? "good" : row.change_type === "removed" ? "bad" : ""}>
                        {row.change_type}
                      </Pill>
                    </td>
                    <td>{Object.values(row.natural_key).join(" · ")}</td>
                    <td>{row.changed_fields?.join(", ") ?? <span className="dim">--</span>}</td>
                    <td style={{ whiteSpace: "normal", maxWidth: 520 }}>
                      {(row.changed_fields ?? []).map((field) => (
                        <div key={field}>
                          <span className="dim">{field}:</span>{" "}
                          {String(row.before?.[field] ?? "—")} → <b>{String(row.after?.[field] ?? "—")}</b>
                        </div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      ) : null}
    </>
  );
}
