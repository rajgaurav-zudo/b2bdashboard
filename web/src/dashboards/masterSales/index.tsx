import { Fragment, useCallback, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useView } from "../../api/client";
import type { MasterSalesOverview } from "../../api/types";
import { n0 } from "../../format";
import { DateRange, type RangePreset } from "../../ui/DateRange";
import { Control } from "../../ui/FilterControl";
import { MultiSelect } from "../../ui/MultiSelect";
import { Empty, Section, Seg, Spinner } from "../../ui/Primitives";
import { MONTHS, dayLabel, iso, parse, rangeLabel } from "../../ui/dates";
import { useOutside } from "../../ui/useOutside";

type SetParams = (changes: Record<string, string | null>) => void;
type Unit = "applications" | "unique";

const pct = (n: number, of: number) => (of ? `${((100 * n) / of).toFixed(1)}%` : "—");

/** Every application in the export, narrowed by the student's business area,
 *  region and team, by when each stage happened and by actual intake: Applied
 *  through Enrolled as a ladder, with Deposit beside it as the parallel stage.
 *
 *  Filters live in the URL, as on the other dashboards. */
export function MasterSales({ slug }: { slug: string }) {
  const [params, setParams] = useSearchParams();
  const query = Object.fromEntries(
    ["areas", "regions", "teams", "intake_from", "intake_to", "intake_q", "from", "to", "level", "unit"]
      .map((key) => [key, params.get(key) ?? undefined]),
  );
  const { data, isLoading, error } = useView<MasterSalesOverview>(slug, "overview", query);

  const set: SetParams = (changes) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  };

  if (isLoading) return <Spinner label="Reading the applications…" />;
  if (error) {
    return (
      <Empty title="Nothing to show yet">
        <p>{(error as Error).message}</p>
        <p>Load the applications export on the <b>Data</b> tab, then come back.</p>
      </Empty>
    );
  }
  if (!data) return null;

  const { filters } = data;
  const unit = filters.unit === "unique" ? "unique applicants (sales from CoE on)" : "applications";
  const offered = data.stages.find((s) => s.id === "offered")?.n ?? 0;

  return (
    <>
      <FilterBar overview={data} set={set} />

      <Section
        title="Application pipeline"
        note={filters.from && filters.to
          ? <>Each stage counts the {unit} whose date for that stage falls between{" "}
             <b>{dayLabel(filters.from)}</b> and <b>{dayLabel(filters.to)}</b>, so the percentages
             compare events in the window rather than one group moving through.</>
          : <>All time: each stage counts every one of the {unit} that has ever reached it.</>}
        aside={
          <Seg<Unit>
            value={filters.unit}
            options={[{ value: "applications", label: "Applications" }, { value: "unique", label: "Unique applicants" }]}
            onChange={(next) => set({ unit: next === "applications" ? null : next })}
          />
        }
      >
        <p className="ms-scope">
          <b>{n0(data.scope.applicants)}</b> unique applicants · <b>{n0(data.scope.applications)}</b> applications
          <span>{filters.from && filters.to ? " with any stage, deposit or deferral date in the range" : " ever"}, under these filters</span>
        </p>
        <div className="ms-wrap">
          <div className="ms-ladder">
            {data.stages.map((stage, i) => {
              const prev = data.stages[i - 1];
              return (
                <Fragment key={stage.id}>
                  {i > 0 ? <div className="ms-arrow" aria-hidden>→</div> : null}
                  <div className="ms-card" title={stage.help}>
                    <div className="metric">{n0(stage.n)}</div>
                    <div className="nm">{stage.name}</div>
                    <div className="def">{stage.help}</div>
                    <Split rows={[["Created", stage.n], ["Active", stage.active, "act"], ["Closed", stage.closed, "cls"]]} />
                    <div className="conv">
                      {prev ? <><b>{pct(stage.n, prev.n)}</b> of {prev.name}</> : <>Start of the pipeline</>}
                    </div>
                  </div>
                </Fragment>
              );
            })}
          </div>

          <div className="ms-side">
            <DepositCard deposit={data.deposit} offered={offered} />
          </div>
        </div>
        <div className="ms-held">
          <div className="ms-card" title={data.daa.help}>
            <div className="metric">{n0(data.daa.n)}</div>
            <div className="nm">DAA · deferrals</div>
            <div className="def">Deposits whose deferral was initiated{filters.from ? " in the range" : ""}, by Timestamp Deferral Initiated.</div>
            <Split rows={[["Initiated", data.daa.n], ["Awaiting approval", data.daa.awaiting, "daa"],
                          ["Approved", data.daa.approved, "act"], ["Closed", data.daa.closed, "cls"]]} />
          </div>
          <div className="ms-card" title={data.pd.help}>
            <div className="metric">{n0(data.pd.n)}</div>
            <div className="nm">PD · part payments</div>
            <div className="def">Deposits part paid{filters.from ? " in the range" : ""}, by the PartiallyPaid timestamp.</div>
            <Split rows={[["Part paid", data.pd.n], ["Still part paid", data.pd.active, "daa"],
                          ["Since paid in full", data.pd.paid, "act"], ["Closed", data.pd.closed, "cls"]]} />
          </div>
        </div>
        <p className="i360-foot">
          “Today” for the date presets is <b>{dayLabel(data.anchor)}</b>, the newest stage date in the
          loaded export. Dates come from the export’s stage timestamps, backfilled down the ladder
          (an enrolment proves the visa, the CoE and the offer by then). Stages the CRM recorded
          without a date count under all time only. <b>Created</b> is everything that reached the
          stage; <b>active</b> are still at it and open, <b>closed</b> were closed lost at it, and the
          rest have moved on. Active and closed are the export’s state now, whatever the range.
          Deposits split as the YTD sheets do: <b>DAA</b> have a deferral awaiting approval
          (Deferred Initiated and Deferred Approved differ), <b>active</b> do not. In <b>unique
          applicants</b>, Applied and Offered count each student once; from CoE on, and for Deposit,
          DAA and PD, a student’s applications for the same actual intake are one sale, and other
          intakes are other sales.
        </p>
      </Section>

      <footer>
        {n0(data.data.app_rows)} applications from {n0(data.data.students)} students in the loaded export.
        {data.data.other_level ? <> {n0(data.data.other_level)} have a course level in neither group and count only under All levels.</> : null}
        {data.data.no_intake ? <> {n0(data.data.no_intake)} have no actual intake and drop out once an intake is picked.</> : null}
        {data.data.no_student_ref ? <> {n0(data.data.no_student_ref)} have no Student Ref Id and count as a student each.</> : null}
        {data.data.undated_deposit ? <> {n0(data.data.undated_deposit)} deposits have a paid status but no date, so they count only under all time.</> : null}
      </footer>
    </>
  );
}

/** Deposit sits beside the ladder. Where its deposits sit now opens on click,
 *  so the card stays the height of the stage cards. */
function DepositCard({ deposit, offered }: { deposit: MasterSalesOverview["deposit"]; offered: number }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useOutside(ref, open, close);
  return (
    <div className="ms-dep-wrap" ref={ref}>
      <div className="ms-card dep" title={deposit.help} role="button" tabIndex={0}
           aria-expanded={open} onClick={() => setOpen(!open)}
           onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(!open); } }}>
        <div className="metric">{n0(deposit.n)}</div>
        <div className="nm">{deposit.name}</div>
        <div className="def">{deposit.help}. Parallel: paid at any stage from Offered on.</div>
        <Split rows={[["Created", deposit.n], ["Active", deposit.active, "act"],
                      ["DAA", deposit.daa, "daa"], ["Closed", deposit.closed, "cls"]]} />
        <div className="conv">
          <b>{pct(deposit.n, offered)}</b> of Offered
          <span className="ms-more">Where now {open ? "▴" : "▾"}</span>
        </div>
      </div>
      {open ? (
        <div className="ms-pop" role="dialog" aria-label="Where the deposits sit now">
          <div className="ms-pop-h">Where the {n0(deposit.n)} deposits sit now</div>
          <ul className="ms-at">
            {deposit.at.map((at) => (
              <li key={at.id}><span>At {at.name}</span><b>{n0(at.n)}</b></li>
            ))}
          </ul>
          <p className="ms-pop-note">By each application’s furthest stage today.</p>
        </div>
      ) : null}
    </div>
  );
}

/** A card's total, then how many of those are in each state now: for a
 *  stage, still at it and open or closed lost. The class colours the dot. */
function Split({ rows }: { rows: [label: string, n: number, cls?: "act" | "daa" | "cls"][] }) {
  return (
    <ul className="ms-split">
      {rows.map(([label, n, cls]) => <li key={label} className={cls}><span>{label}</span><b>{n0(n)}</b></li>)}
    </ul>
  );
}

// --------------------------------------------------------------------------
// filters
// --------------------------------------------------------------------------

type Menu = "area" | "region" | "team" | "when" | "intake" | "level";

/** Presets anchored on the export's newest stage date, not the clock. */
function presets(anchor: string): { id: string; label: string; from: string; to: string }[] {
  const a = new Date(parse(anchor));
  const y = a.getUTCFullYear();
  const m = a.getUTCMonth();
  const day = (yy: number, mm: number, dd: number) => iso(Date.UTC(yy, mm, dd));
  const back = (days: number) => iso(parse(anchor) - (days - 1) * 86_400_000);
  const monday = iso(parse(anchor) - ((a.getUTCDay() + 6) % 7) * 86_400_000);
  return [
    { id: "this_week", label: "This week", from: monday, to: anchor },
    { id: "this_month", label: "This month", from: day(y, m, 1), to: anchor },
    { id: "last_month", label: "Last month", from: day(y, m - 1, 1), to: day(y, m, 0) },
    { id: "last_30", label: "Last 30 days", from: back(30), to: anchor },
    { id: "last_90", label: "Last 90 days", from: back(90), to: anchor },
    { id: "this_year", label: "This year", from: day(y, 0, 1), to: anchor },
    { id: "last_year", label: "Last year", from: day(y - 1, 0, 1), to: day(y - 1, 11, 31) },
  ];
}

function FilterBar({ overview, set }: { overview: MasterSalesOverview; set: SetParams }) {
  const [open, setOpen] = useState<Menu | null>(null);
  const [q, setQ] = useState("");
  const toggle = (which: Menu) => {
    setQ("");
    setOpen((current) => (current === which ? null : which));
  };
  const close = () => setOpen(null);

  const { filters, options } = overview;
  const join = (next: (string | number)[]) => (next.length ? next.join("|") : null);
  const match = (name: string) => name.toLowerCase().includes(q.trim().toLowerCase());
  // options with nothing behind them under the other filters are hidden, unless picked
  const shown = (list: { name: string; n: number }[], chosen: string[]) =>
    list.filter((o) => (o.n > 0 || chosen.includes(o.name)) && match(o.name));

  // Area -> region -> team is a hierarchy: a parent's change drops the picks
  // below it that it no longer covers.
  const { tree } = options;
  const pickAreas = (areas: string[]) => {
    const keep = (row: { area: string }) => areas.length === 0 || areas.includes(row.area);
    const regions = filters.regions.filter((r) => tree.some((t) => t.region === r && keep(t)));
    const teams = filters.teams.filter((m) => tree.some((t) => t.team === m && keep(t)
      && (regions.length === 0 || regions.includes(t.region))));
    set({ areas: join(areas), regions: join(regions), teams: join(teams) });
  };
  const pickRegions = (regions: string[]) => {
    const teams = filters.teams.filter((m) => tree.some((t) => t.team === m
      && (regions.length === 0 || regions.includes(t.region))));
    set({ regions: join(regions), teams: join(teams) });
  };

  const ranges = presets(overview.anchor);
  const isRange = Boolean(filters.from && filters.to);
  const rangePresets: RangePreset[] = [
    ...ranges.map((r) => ({
      id: r.id, label: r.label, sub: rangeLabel(r.from, r.to),
      pressed: isRange && r.from === filters.from && r.to === filters.to,
    })),
    { id: "all", label: "All time", sub: "Ever reached", pressed: !isRange },
  ];
  const named = ranges.find((r) => r.from === filters.from && r.to === filters.to);
  const whenValue = !isRange ? "All time"
    : named ? named.label : rangeLabel(filters.from ?? "", filters.to ?? "");

  const dirty = !filters.default_range || filters.level !== "academic" || Boolean(filters.intake_from)
    || filters.intake_q.length > 0
    || filters.areas.length > 0 || filters.regions.length > 0 || filters.teams.length > 0;

  return (
    <div className="i360-bar">
      <MultiSelect
        label="Business area" all="All business areas" many={(n) => `${n} business areas`}
        chosen={filters.areas} onChange={pickAreas}
        options={shown(options.areas, filters.areas)} query={q} onQuery={setQ}
        placeholder="Search business areas…"
        open={open === "area"} onToggle={() => toggle("area")} onClose={close}
      />
      <MultiSelect
        label="Region" all="All regions" many={(n) => `${n} regions`}
        chosen={filters.regions} onChange={pickRegions}
        options={shown(options.regions, filters.regions)} query={q} onQuery={setQ}
        placeholder="Search regions…"
        open={open === "region"} onToggle={() => toggle("region")} onClose={close}
      />
      <MultiSelect
        label="Team" all="All teams" many={(n) => `${n} teams`}
        chosen={filters.teams} onChange={(next) => set({ teams: join(next) })}
        options={shown(options.teams, filters.teams)} query={q} onQuery={setQ}
        placeholder="Search teams…"
        open={open === "team"} onToggle={() => toggle("team")} onClose={close}
      />

      <DateRange
        // any range, the default week included, clears to all time; Clear all
        // still goes back to this week
        value={whenValue} isSet={isRange}
        onClear={() => set({ from: "all", to: null })}
        presets={rangePresets}
        onPreset={(id) => {
          const r = ranges.find((p) => p.id === id);
          // this week is the default, spelled as no range so the URL stays clean
          set(id === "this_week" ? { from: null, to: null }
            : r ? { from: r.from, to: r.to } : { from: "all", to: null });
          close();
        }}
        from={filters.from ?? ranges[0]?.from ?? overview.anchor}
        to={filters.to ?? overview.anchor}
        onRange={(from, to) => { set({ from, to }); close(); }}
        hint={<>Each stage is counted by its own date.</>}
        open={open === "when"} onToggle={() => toggle("when")} onClose={close}
      />

      <Intake overview={overview} set={set}
              open={open === "intake"} onToggle={() => toggle("intake")} onClose={close} />

      <Level value={filters.level} set={set}
             open={open === "level"} onToggle={() => toggle("level")} onClose={close} />

      {dirty ? (
        <button type="button" className="i360-clear"
                onClick={() => set({ areas: null, regions: null, teams: null, intake_from: null, intake_to: null, intake_q: null, from: null, to: null, level: null })}>
          Clear all
        </button>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// actual intake
// --------------------------------------------------------------------------

const QUARTERS = [[1, 3, "Jan – Mar"], [4, 6, "Apr – Jun"], [7, 9, "Jul – Sep"], [10, 12, "Oct – Dec"]] as const;

const ym = (year: number, month: number) => `${year}-${String(month).padStart(2, "0")}`;

/** "2026-02" -> "2026-02-28" */
const lastDay = (month: string) => {
  const [y, m] = month.split("-").map(Number) as [number, number];
  return iso(Date.UTC(y, m, 0));
};

/** "2026-01".."2026-03" -> "Q1 2026", else "Sep 2026 – Feb 2027" */
function intakeLabel(from: string, to: string): string {
  const [fy, fm] = from.split("-").map(Number) as [number, number];
  const [ty, tm] = to.split("-").map(Number) as [number, number];
  if (fy === ty && fm === 1 && tm === 12) return String(fy);
  const q = QUARTERS.findIndex(([a, b]) => a === fm && b === tm);
  if (fy === ty && q >= 0) return `Q${q + 1} ${fy}`;
  const name = (y: number, m: number) => `${MONTHS[m - 1]?.slice(0, 3)} ${y}`;
  return from === to ? name(fy, fm) : `${name(fy, fm)} – ${name(ty, tm)}`;
}

/** "2026-Q1", "2026-Q3" -> "Q1 + Q3 2026"; all four -> "2026" */
function quartersLabel(picks: string[]): string {
  const year = picks[0]?.slice(0, 4) ?? "";
  if (picks.length === 4) return year;
  return `${picks.map((p) => p.slice(5)).join(" + ")} ${year}`;
}

/** Actual intake: whole years or quarters of one year down the left, any
 *  quarters of a year together but never across years, or a custom range of
 *  months on the calendar. Quarters toggle, so the menu stays open; picking
 *  in another year starts over in that year. Intakes are dated by month, so a
 *  day picked on the calendar stands for its month. */
function Intake({ overview, set, open, onToggle, onClose }: {
  overview: MasterSalesOverview; set: SetParams; open: boolean; onToggle: () => void; onClose: () => void;
}) {
  const { intake_from: from, intake_to: to, intake_q: picked } = overview.filters;
  const cur = Number(overview.anchor.slice(0, 4));
  const presets: RangePreset[] = [
    { id: "all", label: "All intakes", sub: "No intake filter", pressed: !from && picked.length === 0 },
  ];
  const yearOf = (year: number) => [1, 2, 3, 4].map((q) => `${year}-Q${q}`);
  for (const [year, name] of [[cur - 1, "Last year"], [cur, "This year"], [cur + 1, "Next year"]] as const) {
    const group = `${name} · ${year}`;
    presets.push({ id: `year:${year}`, label: group, sub: "Full year · Jan – Dec", group, head: true,
                   pressed: yearOf(year).every((q) => picked.includes(q)) });
    QUARTERS.forEach(([, , sub], i) => presets.push({
      id: `${year}-Q${i + 1}`, label: `Q${i + 1}`, sub, group, pressed: picked.includes(`${year}-Q${i + 1}`),
    }));
  }
  const setQuarters = (next: string[]) =>
    set({ intake_q: next.length ? [...next].sort().join("|") : null, intake_from: null, intake_to: null });

  const onPreset = (id: string) => {
    if (id === "all") { set({ intake_q: null, intake_from: null, intake_to: null }); onClose(); return; }
    if (id.startsWith("year:")) {
      const all = yearOf(Number(id.slice(5)));
      setQuarters(all.every((q) => picked.includes(q)) ? [] : all);
      return;
    }
    // quarters of one year only: a quarter in another year starts over there
    const same = picked.filter((q) => q.slice(0, 4) === id.slice(0, 4));
    setQuarters(same.includes(id) ? same.filter((q) => q !== id) : [...same, id]);
  };

  const value = picked.length ? quartersLabel(picked) : from && to ? intakeLabel(from, to) : "All intakes";
  const year = Number(picked[0]?.slice(0, 4) ?? cur);
  const qs = picked.map((p) => Number(p.slice(6)));
  return (
    <DateRange
      label="Actual intake"
      value={value} isSet={Boolean(from) || picked.length > 0}
      onClear={() => set({ intake_q: null, intake_from: null, intake_to: null })}
      presets={presets}
      onPreset={onPreset}
      from={from ? `${from}-01` : picked.length ? `${ym(year, QUARTERS[Math.min(...qs) - 1]![0])}-01` : `${cur}-01-01`}
      to={to ? lastDay(to) : picked.length ? lastDay(ym(year, QUARTERS[Math.max(...qs) - 1]![1])) : `${cur}-12-31`}
      onRange={(a, b) => { set({ intake_from: a.slice(0, 7), intake_to: b.slice(0, 7), intake_q: null }); onClose(); }}
      hint="Quarters can be combined within one year. A range on the calendar covers whole months."
      open={open} onToggle={onToggle} onClose={onClose}
    />
  );
}

const LEVELS: { id: MasterSalesOverview["filters"]["level"]; label: string; sub: string }[] = [
  { id: "academic", label: "Academic", sub: "Postgraduate, Undergraduate, Foundation, Doctorate, Pre-Masters, A/AS level, GCSE" },
  { id: "language", label: "Language", sub: "Language and Pre-sessional English" },
  { id: "all", label: "All levels", sub: "Every course level, blanks included" },
];

/** Application Course Level in the weekly summary's groups. Academic is the
 *  default and spelled as no param; the × clears to all levels. */
function Level({ value, set, open, onToggle, onClose }: {
  value: MasterSalesOverview["filters"]["level"]; set: SetParams;
  open: boolean; onToggle: () => void; onClose: () => void;
}) {
  const pick = (id: string) => { set({ level: id === "academic" ? null : id }); onClose(); };
  return (
    <Control
      label="Course level" value={LEVELS.find((l) => l.id === value)?.label ?? value}
      isSet={value !== "all"} onClear={() => set({ level: "all" })}
      open={open} onToggle={onToggle} onClose={onClose} width={300}
    >
      <div className="i360-list">
        {LEVELS.map((l) => (
          <button key={l.id} type="button" className={`opt ms-lvl${l.id === value ? " on" : ""}`}
                  onClick={() => pick(l.id)}>
            <span className="tick" aria-hidden>{l.id === value ? "✓" : ""}</span>
            <span className="nm">{l.label}<small>{l.sub}</small></span>
          </button>
        ))}
      </div>
    </Control>
  );
}
