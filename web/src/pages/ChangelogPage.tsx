import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useChangelog, useChangelogRows, useSources } from "../api/client";
import { n0, when } from "../format";
import { Empty, Pill, Section, Spinner } from "../ui/Primitives";
import { DashFilter } from "./DataPage";

/** What every upload changed, everywhere.
 *
 *  An upload's entry is per source: the file is diffed once against the
 *  previous upload of that source in the store, whichever dashboards read it.
 *  Rollbacks and restores, and entries from before the store, name the one
 *  dashboard they concern. */
export function ChangelogPage() {
  const [params, setParams] = useSearchParams();
  const only = params.get("source") ?? "";
  const sources = useSources();
  const { data, isLoading } = useChangelog(only || undefined);
  const [open, setOpen] = useState<number | null>(null);
  const rows = useChangelogRows(open);

  const setOnly = (value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set("source", value); else next.delete("source");
    setParams(next, { replace: true });
  };

  return (
    <>
      <header className="top">
        <div className="top-in">
          <h1>Changelog</h1>
          <p className="sub">
            What each upload changed, computed by comparing the file against the previous upload
            of the same source, row by row on its key column. Counts are always exact; the
            row-level diffs below them are capped so one bad export cannot write millions of rows.
          </p>
        </div>
      </header>

      <div className="wrap">
        <Section
          title="Uploads"
          aside={
            <DashFilter
              value={only}
              onChange={setOnly}
              all="All sources"
              options={(sources.data ?? []).map((s) => ({ value: s.slug, label: s.display_name }))}
            />
          }
        >
          {isLoading ? <Spinner /> : null}
          {data?.length === 0 ? <Empty title="Nothing uploaded yet" /> : null}
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  {/* no Table column: every summary already opens with the
                      dataset's name, and the row-diff button was being pushed
                      off the end of the table to carry the repetition */}
                  <th className="txt">When</th><th className="txt">Source</th>
                  <th className="txt">Summary</th>
                  <th className="num">+</th><th className="num">~</th><th className="num">−</th>
                  <th className="txt">File</th><th />
                </tr>
              </thead>
              <tbody>
                {data?.map((entry) => (
                  <tr key={entry.id}>
                    <td className="txt">{when(entry.occurred_at)}</td>
                    <td className="txt">
                      {entry.source_name ?? <span className="dim">--</span>}
                      {entry.dashboard_name ? <div className="dim">{entry.dashboard_name}</div> : null}
                    </td>
                    <td className="txt" style={{ whiteSpace: "normal", minWidth: 260 }}>{entry.summary}</td>
                    <td className="num" style={{ color: "var(--good)" }}>{n0(entry.rows_added ?? 0)}</td>
                    <td className="num" style={{ color: "var(--warn)" }}>{n0(entry.rows_changed ?? 0)}</td>
                    <td className="num" style={{ color: "var(--bad)" }}>{n0(entry.rows_removed ?? 0)}</td>
                    {/* export filenames are long and unsplittable, and left to
                        themselves they pushed the row-diff button off the table */}
                    <td className="txt">
                      <span className="fname" title={entry.filename ?? undefined}>
                        {entry.filename}
                      </span>{" "}
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
                      <td>{row.natural_key}</td>
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
      </div>
    </>
  );
}
