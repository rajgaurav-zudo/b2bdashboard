import { useState } from "react";

import { useView } from "../../api/client";
import type { I360MenuView, I360Overview } from "../../api/types";
import { n0 } from "../../format";
import { Control } from "../../ui/FilterControl";
import { MultiSelect } from "../../ui/MultiSelect";
import { RegionTeam, joinParam } from "../../ui/RegionTeam";
import { dayLabel } from "../../ui/dates";
import { DateRange } from "../../ui/DateRange";

/** Writes the filters into the URL. Named so it cannot be confused with the
 *  `isSet` flag below, which says whether a control has a value to clear. */
type SetParams = (changes: Record<string, string | null>) => void;

/** Region, team, introducer, date range, intake, and whether to compare with last year.
 *
 *  Every control that is set carries its own ✕, and the ✕ stops the click from
 *  reaching the button underneath it -- otherwise clearing a filter opens the
 *  menu you were trying to leave. Clearing the range removes the date filter:
 *  it becomes All time, the file's first stage date to its last, rather than no
 *  window at all. Clear all still returns to the page's opening This week. */
export function FilterBar({ slug, overview, set }: {
  slug: string; overview: I360Overview; set: SetParams;
}) {
  const [open, setOpen] = useState<"region" | "team" | "who" | "when" | "intake" | null>(null);
  const toggle = (which: "region" | "team" | "who" | "when" | "intake") =>
    setOpen((current) => (current === which ? null : which));

  const { selected, range, intake, filters } = overview;
  const dirty = selected.length > 0 || filters.regions.length > 0 || filters.teams.length > 0 || range.id !== "this_week"
    || intake.year !== null || overview.compare;

  return (
    <div className="i360-bar">
      <RegionTeam
        regionOptions={overview.region_options} teamOptions={overview.team_options}
        regions={filters.regions} teams={filters.teams}
        onChange={(next) => set({ regions: joinParam(next.regions), teams: joinParam(next.teams) })}
        open={open === "region" || open === "team" ? open : null} onToggle={toggle}
        onClose={() => setOpen(null)}
      />
      <Who slug={slug} overview={overview} set={set}
           open={open === "who"} onToggle={() => toggle("who")} onClose={() => setOpen(null)} />
      <When overview={overview} set={set}
            open={open === "when"} onToggle={() => toggle("when")} onClose={() => setOpen(null)} />
      <Intake overview={overview} set={set}
              open={open === "intake"} onToggle={() => toggle("intake")} onClose={() => setOpen(null)} />

      <label className="i360-toggle">
        <input
          type="checkbox"
          checked={overview.compare}
          onChange={(e) => set({ compare: e.target.checked ? "1" : null })}
        />
        <span className="track"><span className="knob" /></span>
        <span className="lbl">Compare with last year</span>
      </label>

      {dirty ? (
        <button
          type="button"
          className="i360-clear"
          onClick={() => set({ regions: null, teams: null, introducers: null, range: null, from: null, to: null,
                               intake_year: null, intake_cycle: null, compare: null })}
        >
          Clear all
        </button>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// introducer
// --------------------------------------------------------------------------

function Who({ slug, overview, set, open, onToggle, onClose }: {
  slug: string; overview: I360Overview; set: SetParams;
  open: boolean; onToggle: () => void; onClose: () => void;
}) {
  const [q, setQ] = useState("");
  // there are thousands of partners, so the list is searched on the server and
  // ranked by lifetime work -- a partner who did nothing this week is exactly
  // the one someone opens this dashboard to look at
  const { data, isFetching } = useView<I360MenuView>(slug, "introducers",
    { q: q.trim(), limit: 60 }, open);

  const chosen = overview.selected;
  return (
    <MultiSelect
      label="Introducer" all="All introducers" many={(n) => `${n} introducers`}
      chosen={chosen}
      onChange={(next) => set({ introducers: next.length ? next.join("|") : null })}
      options={data?.rows ?? []} loading={isFetching}
      query={q} onQuery={setQ} placeholder="Search partners…"
      open={open} onToggle={onToggle} onClose={onClose}
    />
  );
}

// --------------------------------------------------------------------------
// date range
// --------------------------------------------------------------------------

function When({ overview, set, open, onToggle, onClose }: {
  overview: I360Overview; set: SetParams;
  open: boolean; onToggle: () => void; onClose: () => void;
}) {
  const { range } = overview;
  return (
    <DateRange
      value={range.label} isSet={range.id !== "all_time"}
      onClear={() => set({ range: "all_time", from: null, to: null })}
      presets={range.presets.map((preset) => ({
        id: preset.id, label: preset.label, pressed: preset.id === range.id,
        sub: preset.from ? dayLabel(preset.from) : "Pick two days",
      }))}
      onPreset={(id) => {
        if (id === "custom") return;
        set({ range: id, from: null, to: null });
        onClose();
      }}
      from={range.from} to={range.to}
      onRange={(from, to) => { set({ range: "custom", from, to }); onClose(); }}
      open={open} onToggle={onToggle} onClose={onClose}
    />
  );
}

// --------------------------------------------------------------------------
// intake
// --------------------------------------------------------------------------

function Intake({ overview, set, open, onToggle, onClose }: {
  overview: I360Overview; set: SetParams;
  open: boolean; onToggle: () => void; onClose: () => void;
}) {
  const { intake } = overview;
  const cycle = intake.cycles.find((c) => c.i === intake.cycle);
  const value = intake.year === null ? "Any intake"
    : cycle ? cycle.label : String(intake.year);

  return (
    <Control
      label="Intake" value={value} isSet={intake.year !== null}
      onClear={() => set({ intake_year: null, intake_cycle: null })}
      open={open} onToggle={onToggle} onClose={onClose} width={280}
    >
      <div className="i360-list">
        <button
          type="button" className={`opt${intake.year === null ? " on" : ""}`}
          onClick={() => { set({ intake_year: null, intake_cycle: null }); onClose(); }}
        >
          <span className="tick" aria-hidden>{intake.year === null ? "✓" : ""}</span>
          <span className="nm">Any intake</span>
        </button>
        {intake.years.map((year) => (
          <button
            key={year.y} type="button"
            className={`opt${intake.year === year.y ? " on" : ""}`}
            onClick={() => set({ intake_year: String(year.y), intake_cycle: null })}
          >
            <span className="tick" aria-hidden>{intake.year === year.y ? "✓" : ""}</span>
            <span className="nm">{year.y}</span>
            <span className="n">{n0(year.n)}</span>
          </button>
        ))}
      </div>
      {intake.cycles.length ? (
        <>
          {/* the counts are here so picking a cycle cannot land on an empty page
              without having said so first */}
          <p className="i360-sub">Cycle within {intake.year}</p>
          <div className="i360-list">
            {intake.cycles.map((c) => (
              <button
                key={c.i} type="button"
                className={`opt${intake.cycle === c.i ? " on" : ""}`}
                onClick={() => {
                  set({ intake_cycle: intake.cycle === c.i ? null : String(c.i) });
                  onClose();
                }}
              >
                <span className="tick" aria-hidden>{intake.cycle === c.i ? "✓" : ""}</span>
                <span className="nm">{c.label}</span>
                <span className="n">{n0(c.n)}</span>
              </button>
            ))}
          </div>
        </>
      ) : null}
    </Control>
  );
}
