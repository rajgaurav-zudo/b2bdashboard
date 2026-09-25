import { useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { useView } from "../../api/client";
import type { PipelineCell, PipelineOverview, PipelineStage } from "../../api/types";
import { n0 } from "../../format";
import { Control } from "../../ui/FilterControl";
import { MultiSelect } from "../../ui/MultiSelect";
import { RegionTeam, joinParam } from "../../ui/RegionTeam";
import { Empty, Section, Seg, Spinner } from "../../ui/Primitives";
import { dayLabel } from "../../ui/dates";

type SetParams = (changes: Record<string, string | null>) => void;
type Shape = "pipeline" | "funnel";

/** Unique students of an actual intake, each at the furthest stage any of their
 *  applications has reached, against the same intake a year earlier.
 *
 *  Filters live in the URL, as on the other dashboards, so a link carries the
 *  intake someone was looking at. */
export function Pipeline({ slug }: { slug: string }) {
  const [params, setParams] = useSearchParams();
  const query = {
    mode: params.get("mode") ?? undefined,
    year: params.get("year") ?? undefined,
    quarters: params.get("quarters") ?? undefined,
    levels: params.get("levels") ?? undefined,
    regions: params.get("regions") ?? undefined,
    teams: params.get("teams") ?? undefined,
  };
  const shape: Shape = params.get("shape") === "funnel" ? "funnel" : "pipeline";
  const { data, isLoading, error } = useView<PipelineOverview>(slug, "overview", query);

  const set: SetParams = (changes) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  };

  if (isLoading) return <Spinner label="Reading the pipeline…" />;
  if (error) {
    return (
      <Empty title="Nothing to show yet">
        <p>{(error as Error).message}</p>
        <p>Load the applications export on the <b>Data</b> tab, then come back.</p>
      </Empty>
    );
  }
  if (!data) return null;

  const { totals } = data;
  return (
    <>
      <FilterBar overview={data} set={set} />

      <div className="tiles pl-tiles">
        <Tile label="Unique applicants" now={totals.now.total} was={totals.ly_asat.total}
              foot={<>Final last year <b>{n0(totals.ly_final.total)}</b></>} />
        <Tile label="Active" now={totals.now.active ?? 0} was={null}
              foot={<>Final last year <b>{n0(totals.ly_final.active)}</b></>} />
        <Tile label="Closed lost" now={totals.now.lost ?? 0} was={null}
              foot={<>Final last year <b>{n0(totals.ly_final.lost)}</b></>} />
      </div>

      <Section
        title={shape === "pipeline" ? "Pipeline" : "Funnel"}
        note={<>
          {data.scope.label}, against {data.scope.last_year}.{" "}
          {shape === "pipeline"
            ? <>Each student is counted once, at the furthest stage any of their applications
               in scope has reached, so the rows add up to the total.</>
            : <>Cumulative: a student at Deposit is also counted at Offer and Applied, so each
               row reads against the one above.</>}
        </>}
        aside={
          <Seg<Shape>
            value={shape}
            options={[{ value: "pipeline", label: "Pipeline" }, { value: "funnel", label: "Funnel" }]}
            onChange={(next) => set({ shape: next === "pipeline" ? null : next })}
          />
        }
      >
        <StageTable overview={data} shape={shape} />
        <p className="i360-foot">
          “Today” is <b>{dayLabel(data.anchor)}</b>, the newest stage date in the loaded export.
          “Last year at this point” replays last year’s stage dates up to{" "}
          <b>{dayLabel(data.cutoff)}</b>; “final” is where last year’s students stand now.
          Closed lost has no date in the export, so the at-this-point figures have no
          active / lost split.
        </p>
      </Section>

      <footer>
        {n0(data.data.app_rows)} applications in the loaded export, every recruitment type.
        {data.data.no_intake ? <> {n0(data.data.no_intake)} have no actual intake and are not shown.</> : null}
        {data.data.no_student_ref ? <> {n0(data.data.no_student_ref)} have no Student Ref Id and count as a student each.</> : null}
      </footer>
    </>
  );
}

// --------------------------------------------------------------------------
// filters
// --------------------------------------------------------------------------

type Menu = "region" | "team" | "year" | "quarter" | "level";

function FilterBar({ overview, set }: { overview: PipelineOverview; set: SetParams }) {
  const [open, setOpen] = useState<Menu | null>(null);
  const [q, setQ] = useState("");
  const toggle = (which: Menu) =>
    setOpen((current) => (current === which ? null : which));
  const close = () => setOpen(null);

  const { filters, options } = overview;
  const year = options.years.find((y) => y.value === filters.year);
  const quarterValue = filters.quarters.length === 0 ? "Whole year"
    : filters.quarters.map((n) => `Q${n}`).join(", ");
  const levels = options.levels.filter((l) => l.name.toLowerCase().includes(q.trim().toLowerCase()));
  const flipQuarter = (n: number) => {
    const next = filters.quarters.includes(n)
      ? filters.quarters.filter((x) => x !== n) : [...filters.quarters, n].sort();
    set({ quarters: next.length && next.length < 4 ? next.join("|") : null });
  };
  const dirty = filters.mode !== "calendar" || filters.quarters.length > 0 || filters.levels.length > 0
    || filters.regions.length > 0 || filters.teams.length > 0
    || new URLSearchParams(window.location.search).has("year");

  return (
    <div className="i360-bar">
      <RegionTeam
        regionOptions={options.region_options} teamOptions={options.team_options}
        regions={filters.regions} teams={filters.teams}
        onChange={(next) => set({ regions: joinParam(next.regions), teams: joinParam(next.teams) })}
        open={open === "region" || open === "team" ? open : null} onToggle={toggle} onClose={close}
      />

      <Seg<"calendar" | "academic">
        value={filters.mode}
        options={options.modes.map((m) => ({ value: m.id, label: m.label }))}
        // the year means something different in each, so it goes back to the default
        onChange={(next) => set({ mode: next === "calendar" ? null : next, year: null })}
      />

      <Control
        label={filters.mode === "calendar" ? "Calendar year" : `Academic year (${options.academic_start}–)`}
        value={year?.label ?? String(filters.year)} isSet={false} onClear={() => set({ year: null })}
        open={open === "year"} onToggle={() => toggle("year")} onClose={close} width={220}
      >
        <div className="i360-list">
          {options.years.map((y) => (
            <button
              key={y.value} type="button" className={`opt${y.value === filters.year ? " on" : ""}`}
              onClick={() => { set({ year: String(y.value) }); close(); }}
            >
              <span className="tick" aria-hidden>{y.value === filters.year ? "✓" : ""}</span>
              <span className="nm">{y.label}</span>
            </button>
          ))}
        </div>
      </Control>

      <Control
        label="Quarter" value={quarterValue} isSet={filters.quarters.length > 0}
        onClear={() => set({ quarters: null })}
        open={open === "quarter"} onToggle={() => toggle("quarter")} onClose={close} width={240}
      >
        <div className="i360-list">
          {options.quarters.map((quarter) => {
            const on = filters.quarters.includes(quarter.q);
            return (
              <button key={quarter.q} type="button" className={`opt${on ? " on" : ""}`}
                      onClick={() => flipQuarter(quarter.q)}>
                <span className="tick" aria-hidden>{on ? "✓" : ""}</span>
                <span className="nm">{quarter.label}</span>
              </button>
            );
          })}
        </div>
        <p className="i360-sub">Quarters count from the start of the chosen year. None picked is the whole year.</p>
      </Control>

      <MultiSelect
        label="Course level" all="All course levels" many={(n) => `${n} course levels`}
        chosen={filters.levels}
        onChange={(next) => set({ levels: next.length ? next.join("|") : null })}
        options={levels} query={q} onQuery={setQ} placeholder="Search course levels…"
        open={open === "level"} onToggle={() => toggle("level")} onClose={close}
      />

      {dirty ? (
        <button type="button" className="i360-clear"
                onClick={() => set({ mode: null, year: null, quarters: null, levels: null, regions: null, teams: null })}>
          Clear all
        </button>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// figures
// --------------------------------------------------------------------------

function Delta({ now, was }: { now: number; was: number | null }) {
  if (was === null) return null;
  if (!was) return <span className="pl-d flat">—</span>;
  const change = (now - was) / was;
  const dir = change > 0.0005 ? "up" : change < -0.0005 ? "down" : "flat";
  return (
    <span className={`pl-d ${dir}`}>
      {change > 0 ? "+" : ""}{(100 * change).toFixed(1)}%
    </span>
  );
}

function Tile({ label, now, was, foot }: {
  label: string; now: number; was: number | null; foot: ReactNode;
}) {
  return (
    <div className="tile">
      <div className="metric">{n0(now)}</div>
      <div className="metric-l">
        {label}
        {was !== null ? <> · last year at this point {n0(was)} <Delta now={now} was={was} /></> : null}
      </div>
      <div className="foot">{foot}</div>
    </div>
  );
}

function StageTable({ overview, shape }: { overview: PipelineOverview; shape: Shape }) {
  const first = overview.stages[0];
  const base = (period: "now" | "ly_asat" | "ly_final") => first?.[period].funnel.total ?? 0;
  const conv = (cell: PipelineCell, whole: number) =>
    whole ? `${((100 * cell.total) / whole).toFixed(1)}%` : "—";
  const pick = (stage: PipelineStage, period: "now" | "ly_asat" | "ly_final") => stage[period][shape];

  return (
    <div className="tbl-wrap">
      <table className="funnel-table pl-table">
        <thead>
          <tr>
            <th className="txt">Stage</th>
            <th className="num">Students</th>
            <th className="num">Active</th>
            <th className="num">Closed lost</th>
            {shape === "funnel" ? <th className="num">% of applied</th> : null}
            <th className="num sep">Last year at this point</th>
            <th className="num">Change</th>
            {shape === "funnel" ? <th className="num">% of applied</th> : null}
            <th className="num sep">Last year final</th>
            {shape === "funnel" ? <th className="num">% of applied</th> : null}
          </tr>
        </thead>
        <tbody>
          {overview.stages.map((stage) => {
            const now = pick(stage, "now");
            const asat = pick(stage, "ly_asat");
            const fin = pick(stage, "ly_final");
            return (
              <tr key={stage.id}>
                <td className="txt">{stage.name}</td>
                <td className="num"><b>{n0(now.total)}</b></td>
                <td className="num">{n0(now.active)}</td>
                <td className="num dim">{n0(now.lost)}</td>
                {shape === "funnel" ? <td className="num dim">{conv(now, base("now"))}</td> : null}
                <td className="num sep">{n0(asat.total)}</td>
                <td className="num"><Delta now={now.total} was={asat.total} /></td>
                {shape === "funnel" ? <td className="num dim">{conv(asat, base("ly_asat"))}</td> : null}
                <td className="num sep">{n0(fin.total)}</td>
                {shape === "funnel" ? <td className="num dim">{conv(fin, base("ly_final"))}</td> : null}
              </tr>
            );
          })}
        </tbody>
        {shape === "pipeline" ? (
          <tfoot>
            <tr>
              <td className="txt">All students</td>
              <td className="num">{n0(overview.totals.now.total)}</td>
              <td className="num">{n0(overview.totals.now.active)}</td>
              <td className="num">{n0(overview.totals.now.lost)}</td>
              <td className="num sep">{n0(overview.totals.ly_asat.total)}</td>
              <td className="num"><Delta now={overview.totals.now.total} was={overview.totals.ly_asat.total} /></td>
              <td className="num sep">{n0(overview.totals.ly_final.total)}</td>
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}
