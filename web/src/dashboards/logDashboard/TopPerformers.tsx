import type { LogOverview, TopRow } from "../../api/types";
import { n0 } from "../../format";
import { colourFor, dayLabel } from "./weeks";

export type Dimension = "creators" | "teams" | "introducers";

export const DIMENSIONS: { key: Dimension; title: string; note: string }[] = [
  { key: "creators", title: "Created by", note: "Who logged the contact" },
  { key: "teams", title: "Managed by team", note: "Which team owns the partner" },
  { key: "introducers", title: "Introducers", note: "Which partners are being worked" },
];

/** Three tables over the selected range, one per grouping. Each carries a count
 *  per log type, its total for the range, and the name's lifetime total across
 *  the whole file — so a partner who is quiet this quarter but heavily worked
 *  historically does not read as a stranger.
 *
 *  These measure logging discipline at least as much as activity: one person
 *  logging every email and another logging only meetings will rank very
 *  differently for identical work. Said plainly under the section heading. */
export function TopPerformers({ overview, onViewMore }: {
  overview: LogOverview;
  onViewMore: (dimension: Dimension) => void;
}) {
  const types = overview.log_types.map((t) => t.type);
  return (
    <div className="top-stack">
      {DIMENSIONS.map(({ key, title, note }) => (
        <TopTable
          key={key}
          dimension={key}
          title={title}
          note={note}
          types={types}
          rows={overview.top[key] ?? []}
          total={overview.top_totals?.[key] ?? 0}
          onViewMore={() => onViewMore(key)}
        />
      ))}
    </div>
  );
}

export function TopTable({ dimension, title, note, types, rows, total, onViewMore }: {
  dimension: Dimension;
  title: string;
  note: string;
  types: string[];
  rows: TopRow[];
  total: number;
  onViewMore?: () => void;
}) {
  const colour = colourFor(types);
  const hidden = Math.max(total - rows.length, 0);
  const isIntroducer = dimension === "introducers";

  return (
    <div className="top-panel">
      <div className="panel-h">
        <div>
          <h3>{title}</h3>
          <p>
            {note}
            {onViewMore ? <> · showing {n0(rows.length)} of {n0(total)}</> : null}
          </p>
        </div>
        {onViewMore && hidden > 0 ? (
          <button type="button" className="more" onClick={onViewMore}>
            view more ({n0(hidden)}) →
          </button>
        ) : null}
      </div>
      <div className="tbl-wrap">
        <table className="leader">
          <thead>
            <tr>
              <th className="rk num">#</th>
              <th className="txt">Name</th>
              {types.map((type) => (
                <th key={type} className="num ty">
                  <span className="swatch" style={{ background: colour(type) }} />
                  {type}
                </th>
              ))}
              <th className="num tot">Total</th>
              <th className="num">All time</th>
              <th className="num">{isIntroducer ? "Last log" : "Introducers"}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="txt dim" colSpan={types.length + 5}>Nothing in this range.</td>
              </tr>
            ) : rows.map((row, i) => (
              <tr key={row.name}>
                <td className="rk num">{i + 1}</td>
                <td className="txt">
                  {row.name}
                  <span className="who">{subLine(row, dimension)}</span>
                </td>
                {types.map((type) => (
                  <td key={type} className={`num ty${row.by_type[type] ? "" : " zero"}`}>
                    {/* a type this name never used is a dot, not a 0: the eye
                        should land on the numbers that are there */}
                    {row.by_type[type] ? n0(row.by_type[type]) : "·"}
                  </td>
                ))}
                <td className="num tot">{n0(row.n)}</td>
                <td className="num dim" title="every log in the file, ignoring the range and filters">
                  {n0(row.lifetime)}
                </td>
                <td className="num dim">
                  {isIntroducer ? dayLabel(row.last_log) : n0(row.n_introducers)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** The line under a name: who else is involved, capped at two with the rest
 *  counted. Each table names the parties it is not already grouped by. */
function subLine(row: TopRow, dimension: Dimension): string {
  const cap = (names: string[], more: number) => names.join(", ") + (more ? ` +${more}` : "");
  if (dimension === "introducers") {
    return `${cap(row.teams, row.teams_more)} · ${cap(row.creators, row.creators_more)}`;
  }
  if (dimension === "teams") {
    return `${n0(row.n_creators)} logging · ${cap(row.creators, row.creators_more)}`;
  }
  return `${cap(row.teams, row.teams_more)}`;
}
