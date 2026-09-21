import type { LogOverview } from "../../api/types";
import { n0 } from "../../format";
import { Pill } from "../../ui/Primitives";
import { TeamPicker } from "./TeamPicker";
import { weekLabel } from "./weeks";

interface Props {
  overview: LogOverview;
  onStep: (direction: -1 | 1) => void;
  onJumpToCurrent: () => void;
  onFilter: (key: "type" | "team" | "weeks", value: string) => void;
}

const RANGES = [
  { value: "4", label: "4 weeks" },
  { value: "8", label: "8 weeks (2 months)" },
  { value: "13", label: "13 weeks (a quarter)" },
  { value: "26", label: "26 weeks" },
  { value: "52", label: "52 weeks" },
];

/** Week stepper and the three filters, above everything they govern.
 *  `←`/`→` move one week through the weeks the file actually holds — a week the
 *  export skipped is not stepped onto and is not treated as a zero. */
export function WeekBar({ overview, onStep, onJumpToCurrent, onFilter }: Props) {
  const { filters } = overview;
  // where this week sits in the file, so stepping has a sense of distance
  const position = overview.weeks.findIndex((w) => w.w === overview.week) + 1;
  return (
    <div className="weekbar">
      <div className="stepper">
        <button type="button" className="step" onClick={() => onStep(-1)}
                disabled={!overview.has_earlier} aria-label="Previous week"
                title="Previous week">←</button>
        <div className="wk">
          <b>{weekLabel(overview.week)}</b>
          <span>
            {n0(overview.week_kpis.total)} logs · week {n0(position)} of {n0(overview.weeks.length)}
            {overview.in_progress ? <Pill kind="live">in progress</Pill> : null}
          </span>
        </div>
        <button type="button" className="step" onClick={() => onStep(1)}
                disabled={!overview.has_later} aria-label="Next week"
                title="Next week">→</button>
        {/* always rendered, disabled when there is nowhere newer to go: showing
            and hiding it made the whole bar reflow as you stepped weeks */}
        <button
          type="button"
          className="latest"
          onClick={onJumpToCurrent}
          disabled={overview.is_current}
          title={overview.is_current
            ? `Already on the latest week in the file (${weekLabel(overview.current_week)})`
            : `Jump to the latest week in the file (${weekLabel(overview.current_week)})`}
        >
          Latest<span className="g" aria-hidden="true">⇥</span>
        </button>
      </div>

      <div className="filters">
        {/* a set rather than a value: the regional SRM teams are read together
            as often as alone. Not a <label>, because a button is not labelable
            and the caption would point at nothing. */}
        <div className="fld">
          <span className="cap">Team</span>
          <TeamPicker
            teams={overview.teams}
            selected={filters.teams}
            onChange={(next) => onFilter("team", next.join("|"))}
          />
        </div>
        <label>
          Log type
          <select value={filters.type} onChange={(e) => onFilter("type", e.target.value)}>
            <option value="">All types</option>
            {overview.log_types.map((t) => (
              <option key={t.type} value={t.type}>{t.type} ({n0(t.n)})</option>
            ))}
          </select>
        </label>
        <label>
          Table range
          <select value={String(filters.weeks)} onChange={(e) => onFilter("weeks", e.target.value)}>
            {RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </label>
      </div>
    </div>
  );
}
