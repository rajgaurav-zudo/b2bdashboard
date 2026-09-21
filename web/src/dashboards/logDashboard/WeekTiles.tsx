import type { LogOverview } from "../../api/types";
import { n0, pctOf } from "../../format";
import { colourFor, deltaArrow, deltaClass, deltaLabel, signed, weekLabel } from "./weeks";

interface Props {
  overview: LogOverview;
  onOpen: (type: string | null) => void;
}

/** The selected week: a total, then one tile per log type. Every tile carries
 *  the change against the week immediately before it — never against the
 *  average, and never against whatever range the tables happen to show. */
export function WeekTiles({ overview, onOpen }: Props) {
  const { by_type: types, total, previous_total: previous, delta } = overview.week_kpis;
  const colour = colourFor(overview.log_types.map((t) => t.type));
  const previousLabel = overview.previous_week
    ? `vs ${weekLabel(overview.previous_week).replace(/ \d{4}$/, "")}`
    : "no earlier week in the file";

  return (
    <div className="tiles">
      <button type="button" className="tile" onClick={() => onOpen(null)}>
        <span className="drill">see the logs →</span>
        <div className="metric">{n0(total)}</div>
        <div className="metric-l">logs this week</div>
        <div className="name">All log types</div>
        <div className="def">
          Every interaction logged between Saturday and Friday of the selected week.
        </div>
        <div className="foot">
          <span className={`d ${deltaClass(delta)}`} title={deltaLabel(delta, previous)}>
            <b>{signed(delta)}</b><span className="dir" aria-hidden="true">{deltaArrow(delta)}</span> wk
          </span>
          <span className="contract">{previousLabel} ({n0(previous)})</span>
        </div>
      </button>

      {types.map((row) => (
        <button key={row.type} type="button" className="tile" onClick={() => onOpen(row.type)}>
          <span className="drill">see the logs →</span>
          <div className="metric" style={{ color: colour(row.type) }}>{n0(row.n)}</div>
          <div className="metric-l">logs this week</div>
          <div className="name">{row.type}</div>
          <div className="def">{pctOf(row.share, 0)} of the week’s logs.</div>
          <div className="foot">
            <span className={`d ${deltaClass(row.delta)}`} title={deltaLabel(row.delta, row.prev)}>
              <b>{signed(row.delta)}</b><span className="dir" aria-hidden="true">{deltaArrow(row.delta)}</span> wk
            </span>
            <span className="contract">{n0(row.prev)} the week before</span>
          </div>
        </button>
      ))}
    </div>
  );
}
