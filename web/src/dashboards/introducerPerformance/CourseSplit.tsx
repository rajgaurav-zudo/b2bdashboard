import type { CourseSplitRow } from "../../api/types";
import { n0 } from "../../format";

interface Props {
  rows: CourseSplitRow[];
  currentYear: number;
}

/** Every category except Academic, which the rest of the page already reports.
 *  A category nobody expected -- `Unspecified` -- renders here rather than being
 *  dropped, because a blank course level in the CRM is a finding. */
export function CourseSplit({ rows, currentYear }: Props) {
  const others = rows.filter((r) => r.category !== "Academic");
  if (others.length === 0) return null;

  return (
    <div className="course-cards">
      {others.map((row) => (
        <div className="course-card" key={row.category}>
          <div className="metric">{n0(row.act_cur)}</div>
          <div className="metric-l">deposits · {currentYear}</div>
          <div className="name">{row.category}</div>
          <div className="foot">
            <span><b>{n0(row.n)}</b> {row.n === 1 ? "introducer" : "introducers"}</span>
            <span className="contract">{n0(row.act_life)} lifetime</span>
          </div>
          <div className="foot states">
            <span><b>{n0(row.daa)}</b> DAA</span>
            <span><b>{n0(row.pd)}</b> PD</span>
          </div>
        </div>
      ))}
    </div>
  );
}
