import { useState } from "react";

import type { Overview } from "../../api/types";
import { Control } from "../../ui/FilterControl";
import { DateRange } from "../../ui/DateRange";
import { RegionTeam, joinParam } from "../../ui/RegionTeam";

/** Writes the filters into the URL; a null or empty value removes the key. */
type SetParams = (changes: Record<string, string | null>) => void;

/** What is picked, read from the URL rather than from the overview: the
 *  overview lags a click by a round trip, and a second pick made in that gap
 *  would build on the stale list and drop the first. */
export interface Selection { regions: string[]; teams: string[]; cycles: number[] }

interface PartProps {
  overview: Overview; selection: Selection; set: SetParams;
  open: boolean; onToggle: () => void; onClose: () => void;
}

/** cycle_index as ingest writes it */
const CYCLES = [
  { i: 0, label: "January", hint: "Nov–Mar" },
  { i: 1, label: "May", hint: "Apr–Jul" },
  { i: 2, label: "September", hint: "Aug–Oct" },
];

/** Region, team, date range, intake, and whether to compare with the same months a
 *  year earlier.
 *
 *  The date range is an intake-period window: intake year and month are the
 *  only dates the export has. Clearing it returns to the page's own choice, the
 *  whole current intake year, rather than to no window -- every "current"
 *  figure on the page needs one. */
export function FilterBar({ overview, selection, set }: { overview: Overview; selection: Selection; set: SetParams }) {
  const [open, setOpen] = useState<"region" | "team" | "when" | "intake" | null>(null);
  const toggle = (which: "region" | "team" | "when" | "intake") =>
    setOpen((current) => (current === which ? null : which));
  const close = () => setOpen(null);

  const { period } = overview;
  const comparing = overview.compare !== null;
  const dirty = selection.regions.length > 0 || selection.teams.length > 0 || selection.cycles.length > 0 || !period.is_default || comparing;

  return (
    <div className="i360-bar">
      <RegionTeam
        regionOptions={overview.region_options} teamOptions={overview.team_options}
        regions={selection.regions} teams={selection.teams}
        onChange={(next) => set({ regions: joinParam(next.regions), teams: joinParam(next.teams) })}
        open={open === "region" || open === "team" ? open : null} onToggle={toggle} onClose={close}
      />
      <When overview={overview} selection={selection} set={set} open={open === "when"} onToggle={() => toggle("when")} onClose={close} />
      <Intake overview={overview} selection={selection} set={set} open={open === "intake"} onToggle={() => toggle("intake")} onClose={close} />

      <label className="i360-toggle">
        <input
          type="checkbox"
          checked={comparing}
          onChange={(e) => set({ compare: e.target.checked ? "1" : null })}
        />
        <span className="track"><span className="knob" /></span>
        <span className="lbl">Compare with {period.prior_label}</span>
      </label>

      {dirty ? (
        <button
          type="button"
          className="i360-clear"
          onClick={() => set({ regions: null, teams: null, from: null, to: null, cycles: null, compare: null })}
        >
          Clear all
        </button>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// date range
// --------------------------------------------------------------------------

function When({ overview, set, open, onToggle, onClose }: PartProps) {
  const { period, current_year: cur } = overview;
  const first = overview.year_histogram.find((y) => y.n > 0)?.y ?? cur;
  // the window as the calendar shows it: first day of `from` to last day of `to`
  const from = `${period.from}-01`;
  const to = lastDay(period.to);

  // `y:a:b` is the intake years a..b, whole
  const years = (label: string, a: number, b: number) => ({
    id: `y:${a}:${b}`, label, sub: a === b ? `Jan – Dec ${a}` : `Jan ${a} – Dec ${b}`,
    pressed: period.from === `${a}-01` && period.to === `${b}-12`,
  });
  const presets = [
    years("This intake year", cur, cur),
    years("Last intake year", cur - 1, cur - 1),
    years("Last 3 intake years", cur - 2, cur),
    years("All time", first, cur),
  ].filter((p, i, all) => all.findIndex((q) => q.id === p.id) === i); // a short file makes some coincide
  presets.push({ id: "custom", label: "Custom", sub: "Pick two days", pressed: !presets.some((p) => p.pressed) });

  const setMonths = (a: string, b: string) => {
    // the default window is spelled as no window, so the URL stays clean
    if (a === `${cur}-01` && b === `${cur}-12`) set({ from: null, to: null });
    else set({ from: a, to: b });
    onClose();
  };

  return (
    <DateRange
      value={period.label} isSet={!period.is_default}
      onClear={() => set({ from: null, to: null })}
      presets={presets}
      onPreset={(id) => {
        if (id === "custom") return;
        const [, a, b] = id.split(":");
        setMonths(`${a}-01`, `${b}-12`);
      }}
      from={from} to={to}
      // the export dates intakes by month, so a day stands for its whole month
      onRange={(a, b) => setMonths(a.slice(0, 7), b.slice(0, 7))}
      hint="Intakes are dated by month, so a range covers whole months."
      open={open} onToggle={onToggle} onClose={onClose}
    />
  );
}

/** "2026-02" → "2026-02-28" */
function lastDay(month: string): string {
  const [y, m] = month.split("-").map(Number) as [number, number];
  return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
}

// --------------------------------------------------------------------------
// intake
// --------------------------------------------------------------------------

function Intake({ selection, set, open, onToggle, onClose }: PartProps) {
  const chosen = selection.cycles;
  const flip = (i: number) => {
    const next = chosen.includes(i) ? chosen.filter((c) => c !== i) : [...chosen, i].sort();
    // all three is no filter at all
    set({ cycles: next.length && next.length < CYCLES.length ? next.join(",") : null });
  };
  const value = chosen.length === 0 ? "All intakes"
    : CYCLES.filter((c) => chosen.includes(c.i)).map((c) => c.label.slice(0, 3)).join(", ");

  return (
    <Control
      label="Intake" value={value} isSet={chosen.length > 0}
      onClear={() => set({ cycles: null })}
      open={open} onToggle={onToggle} onClose={onClose} width={260}
    >
      <div className="i360-list">
        <button
          type="button" className={`opt${chosen.length === 0 ? " on" : ""}`}
          onClick={() => { set({ cycles: null }); onClose(); }}
        >
          <span className="tick" aria-hidden>{chosen.length === 0 ? "✓" : ""}</span>
          <span className="nm">All intakes</span>
        </button>
        {CYCLES.map((c) => (
          <button
            key={c.i} type="button"
            className={`opt${chosen.includes(c.i) ? " on" : ""}`}
            onClick={() => flip(c.i)}
          >
            <span className="tick" aria-hidden>{chosen.includes(c.i) ? "✓" : ""}</span>
            <span className="nm">{c.label}</span>
            <span className="n">{c.hint}</span>
          </button>
        ))}
      </div>
    </Control>
  );
}
