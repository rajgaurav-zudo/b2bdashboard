import type { I360Cell, I360WiseRow } from "../../api/types";
import { n0 } from "../../format";

/** Introducer down the side, stage across the top.
 *
 *  One table, used twice: eight rows under the pipeline, and every row in the
 *  wide pane. They are the same query with a different limit, so they are the
 *  same component — two tables of the same numbers is two chances to disagree. */
export function WiseTable({ stages, rows, totals, totalsLabel }: {
  stages: { id: string; name: string }[];
  rows: I360WiseRow[];
  totals?: { cells: (I360Cell & { id: string })[]; total: I360Cell };
  totalsLabel?: string;
}) {
  return (
    <div className="tbl-wrap">
      <table className="i360-wise">
        <thead>
          <tr>
            <th className="txt">Introducer</th>
            <th className="num">Entered</th>
            {stages.map((stage) => <th key={stage.id} className="num">{stage.name}</th>)}
            <th className="num tot">Stages entered</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name}>
              <td className="txt">{row.name}</td>
              <td className="num dim">{n0(row.entered)}</td>
              {row.cells.map((cell) => <Cell key={cell.id} cell={cell} />)}
              <Cell cell={row.total} tot />
            </tr>
          ))}
        </tbody>
        {totals ? (
          <tfoot>
            <tr>
              <td className="txt">{totalsLabel ?? "All introducers in scope"}</td>
              <td className="num dim">--</td>
              {totals.cells.map((cell) => <Cell key={cell.id} cell={cell} />)}
              <Cell cell={totals.total} tot />
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}

/** The card, shrunk into a table cell: the entries, then the two halves under
 *  them in the same order. */
function Cell({ cell, tot }: { cell: I360Cell; tot?: boolean }) {
  return (
    <td className={`num i360-c${tot ? " tot" : ""}${cell.created ? "" : " zero"}`}>
      <b>{n0(cell.created)}</b>
      <span className="ac">{cell.created ? `${n0(cell.active)} / ${n0(cell.closed)}` : " "}</span>
    </td>
  );
}
