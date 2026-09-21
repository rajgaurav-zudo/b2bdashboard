import { useEffect } from "react";

import { useView } from "../../api/client";
import type { LogOverview, LogRowsView } from "../../api/types";
import { n0 } from "../../format";
import { Spinner } from "../../ui/Primitives";
import { teamLabel, teamParam } from "./teams";
import { dayLabel, weekLabel } from "./weeks";

interface Props {
  slug: string;
  overview: LogOverview;
  /** null = every type in the week; a string = that type only; false = closed. */
  type: string | null | false;
  onClose: () => void;
}

/** The individual logs behind a tile. One request per (week, type) and the
 *  table is rendered as it comes back — the largest week is a few hundred rows. */
export function LogPane({ slug, overview, type, onClose }: Props) {
  const open = type !== false;
  const { data, isFetching, error } = useView<LogRowsView>(slug, "rows", {
    week: overview.week,
    only: "week",
    type: open && type ? type : overview.filters.type,
    team: teamParam(overview.filters.teams),
    limit: 500,
  }, open);

  // Escape closes, as it does on the introducer pane
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const rows = data?.rows ?? [];

  return (
    <>
      <div className={`scrim${open ? " on" : ""}`} onClick={onClose} />
      <aside className={`pane${open ? " on" : ""}`} aria-hidden={!open}>
        <div className="pane-h">
          <div className="row1">
            <div>
              <h2>{type ? `${type} logs` : "All logs"}</h2>
              <p className="pdef">
                {weekLabel(overview.week)}
                {teamLabel(overview.filters.teams) ? ` · ${teamLabel(overview.filters.teams)}` : ""}
              </p>
            </div>
            <button type="button" className="x" onClick={onClose} aria-label="Close">×</button>
          </div>
          <div className="chips">
            <span className="chip"><b>{n0(rows.length)}</b> logs</span>
            <span className="chip"><b>{n0(new Set(rows.map((r) => r.introducer)).size)}</b> introducers</span>
            <span className="chip"><b>{n0(new Set(rows.map((r) => r.creator)).size)}</b> people logging</span>
          </div>
        </div>

        <div className="pane-body">
          {isFetching && rows.length === 0 ? <Spinner /> : null}
          {error ? <p className="empty-pane">{(error as Error).message}</p> : null}
          {!isFetching && rows.length === 0 && !error
            ? <p className="empty-pane">No logs in this week.</p>
            : null}
          {rows.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th className="txt">Date</th>
                  <th className="txt">Introducer</th>
                  <th className="txt">Type</th>
                  <th className="txt">Team</th>
                  <th className="txt">Created by</th>
                  <th className="txt">Note</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={`${row.logged_on}-${i}`}>
                    <td className="txt" data-l="Date">{dayLabel(row.logged_on)}</td>
                    <td className="txt" data-l="Introducer">{row.introducer}</td>
                    <td className="txt" data-l="Type">{row.type}</td>
                    <td className="txt" data-l="Team">{row.team}</td>
                    <td className="txt" data-l="By">{row.creator}</td>
                    <td className="txt note-cell" data-l="Note">
                      {row.note ?? <span className="dim">no note</span>}
                      {row.score != null ? (
                        <span className={`score ${row.score > 0 ? "good" : row.score < 0 ? "bad" : ""}`}>
                          {row.score >= 0 ? "+" : ""}{row.score.toFixed(2)}
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      </aside>
    </>
  );
}
