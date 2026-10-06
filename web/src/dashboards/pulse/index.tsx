import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { ChartConfiguration } from "chart.js";

import { useView } from "../../api/client";
import { n0 } from "../../format";
import { Chart, chartChrome, token } from "../../ui/Chart";
import { DateRange, type RangePreset } from "../../ui/DateRange";
import { MultiSelect } from "../../ui/MultiSelect";
import { Empty, Section, Seg, Spinner } from "../../ui/Primitives";
import { dayLabel, iso, parse, rangeLabel } from "../../ui/dates";
import { RecordsPane } from "./RecordsPane";
import type { Dim, Drill, MetricId, PulseMetric, PulseOverview, ScopeOption } from "./types";

type SetParams = (changes: Record<string, string | null>) => void;

const DAY = 86_400_000;
const DIMS: { value: Dim; label: string }[] = [
  { value: "region", label: "Region" }, { value: "team", label: "Team" },
  { value: "country", label: "Country" },
  { value: "introducer", label: "Introducer" },
];
const SCOPE_KEYS = ["regions", "teams", "intakes"] as const;

/** Everything B2B did in a date range, across the three exports: who was
 *  onboarded, what activity was logged, and how many applications reached each
 *  stage. Every number opens the records behind it in the side pane.
 *
 *  Filters live in the URL, as on the other dashboards. No range is the current
 *  Edvoy week (Saturday to today), decided by the API. */
export function Pulse({ slug }: { slug: string }) {
  const [params, setParams] = useSearchParams();
  const query = {
    from: params.get("from") ?? undefined,
    to: params.get("to") ?? undefined,
    regions: params.get("regions") ?? undefined,
    teams: params.get("teams") ?? undefined,
    intakes: params.get("intakes") ?? undefined,
    by: params.get("by") ?? undefined,
  };
  const focus = (params.get("focus") ?? "applied") as MetricId;
  const [drill, setDrill] = useState<Drill | null>(null);
  const { data, isLoading, isFetching, error } = useView<PulseOverview>(slug, "overview", query);

  const set: SetParams = (changes) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  };

  if (isLoading) return <Spinner label="Reading the exports…" />;
  if (error) {
    return (
      <Empty title="Nothing to show yet">
        <p>{(error as Error).message}</p>
        <p>Load the introducers, applications and logs exports on the <b>Data</b> tab, then come back.</p>
      </Empty>
    );
  }
  if (!data) return null;

  const focused = data.metrics.find((m) => m.id === focus) ?? data.metrics[2]!;
  const scopeQuery = { ...query, by: undefined };
  const missing = Object.entries(data.loaded).filter(([, ok]) => !ok).map(([k]) => k);

  return (
    <>
      <FilterBar overview={data} set={set} />

      {missing.length ? (
        <p className="sub" style={{ margin: "0 0 12px" }}>
          Not loaded yet: {missing.join(", ")}. Their numbers read zero.
        </p>
      ) : null}

      <div className="tiles pulse-tiles" aria-busy={isFetching}>
        {data.metrics.map((m) => (
          <MetricTile
            key={m.id} metric={m} on={m.id === focused.id}
            onClick={() => {
              set({ focus: m.id === "applied" ? null : m.id });
              setDrill({ metric: m.id, label: rangeLabel(data.range.from, data.range.to) });
            }}
          />
        ))}
      </div>
      <p className="sub" style={{ margin: "6px 0 18px" }}>
        B2B only. {rangeLabel(data.range.from, data.range.to)}
        {data.range.default ? " (this Edvoy week, Saturday to today)" : ""}, against{" "}
        {rangeLabel(data.previous.from, data.previous.to)}. Click a figure for the records behind it.
        {data.chosen.intakes.length ? " The intake filter narrows the application stages only." : ""}
      </p>

      <Section
        title={`${focused.name} by ${data.trend.unit}`}
        note={<>{focused.def} Pick another figure above to chart it; click a bar for its records.</>}
      >
        <Trend overview={data} metric={focused} onPick={(p) => setDrill({
          metric: focused.id, from: p.start, to: p.end, label: rangeLabel(p.start, p.end),
        })} />
      </Section>

      <Section
        title="Breakdown"
        note={<>Every figure for the range, one row per {DIMS.find((d) => d.value === data.breakdown.by)?.label.toLowerCase()}.
          Click a number for its records. {data.breakdown.more
            ? `The top ${n0(data.breakdown.rows.length)} are shown; ${n0(data.breakdown.more)} more are smaller.` : ""}</>}
        aside={
          <Seg<Dim>
            value={data.breakdown.by}
            options={DIMS}
            onChange={(next) => set({ by: next === "region" ? null : next })}
          />
        }
      >
        <Breakdown overview={data} focus={focused.id} onPick={(metric, key) => setDrill({
          metric, dim: data.breakdown.by, key, label: key,
        })} />
      </Section>

      <footer>
        Onboarded counts Became Customer Date on the introducers master; Activity counts Log Time;
        the stages count each application's stage timestamp. Only business area B2B is counted;
        region and team are the CRM's Business* columns, and a log takes its introducer's.
      </footer>

      <RecordsPane slug={slug} scope={scopeQuery} drill={drill} onClose={() => setDrill(null)} />
    </>
  );
}

// --------------------------------------------------------------------------
// filters
// --------------------------------------------------------------------------

type Menu = "region" | "team" | "intake" | "when";

/** The current Edvoy week's Saturday, `back` weeks ago, in UTC. */
function saturday(back = 0, now = Date.now()): number {
  const today = Math.floor(now / DAY) * DAY;
  return today - (((new Date(today).getUTCDay() + 1) % 7) + 7 * back) * DAY;
}

function presets(): { id: string; label: string; from: string; to: string }[] {
  const now = new Date();
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const y = now.getUTCFullYear();
  const m = now.getUTCMonth();
  return [
    { id: "week", label: "This week", from: iso(saturday(0)), to: iso(today) },
    { id: "last-week", label: "Last week", from: iso(saturday(1)), to: iso(saturday(0) - DAY) },
    { id: "30d", label: "Last 30 days", from: iso(today - 29 * DAY), to: iso(today) },
    { id: "month", label: "This month", from: iso(Date.UTC(y, m, 1)), to: iso(today) },
    { id: "last-month", label: "Last month", from: iso(Date.UTC(y, m - 1, 1)), to: iso(Date.UTC(y, m, 0)) },
    { id: "ytd", label: "Year to date", from: iso(Date.UTC(y, 0, 1)), to: iso(today) },
  ];
}

/** Options narrowed to the ones that sit under what is picked above them:
 *  regions under the picked areas, teams under the picked regions and areas. */
function narrowed(options: ScopeOption[], areas: string[], regions: string[]): ScopeOption[] {
  return options.filter((o) =>
    (!areas.length || !o.areas || o.areas.some((a) => areas.includes(a)))
    && (!regions.length || !o.regions || o.regions.some((r) => regions.includes(r))));
}

function FilterBar({ overview, set }: { overview: PulseOverview; set: SetParams }) {
  const [open, setOpen] = useState<Menu | null>(null);
  const [q, setQ] = useState("");
  const toggle = (which: Menu) => { setQ(""); setOpen((current) => (current === which ? null : which)); };
  const close = () => { setQ(""); setOpen(null); };

  const { chosen, options, range } = overview;
  const match = (name: string) => name.toLowerCase().includes(q.trim().toLowerCase());
  const join = (xs: string[]) => (xs.length ? xs.join("|") : null);
  const list = presets();
  const isDefault = range.default;
  const intakeName = new Map(options.intakes.map((i) => [i.id, i.name]));
  const intakeId = new Map(options.intakes.map((i) => [i.name, i.id]));
  const chosenIntakes = chosen.intakes.map((id) => intakeName.get(id) ?? String(id));

  const rangePresets: RangePreset[] = list.map((p) => ({
    id: p.id, label: p.label, sub: rangeLabel(p.from, p.to),
    pressed: p.from === range.from && p.to === range.to,
  }));
  const dirty = !isDefault || SCOPE_KEYS.some((k) => chosen[k].length > 0);

  return (
    <div className="i360-bar">
      <DateRange
        value={rangeLabel(range.from, range.to)} isSet={!isDefault}
        onClear={() => set({ from: null, to: null })}
        presets={rangePresets}
        onPreset={(id) => {
          const p = list.find((x) => x.id === id)!;
          set(id === "week" ? { from: null, to: null } : { from: p.from, to: p.to });
          close();
        }}
        from={range.from} to={range.to}
        onRange={(from, to) => { set({ from, to }); close(); }}
        hint={<>Counts the events dated inside the range: Became Customer Date, Log Time and the
          application stage timestamps.</>}
        open={open === "when"} onToggle={() => toggle("when")} onClose={close}
      />

      <MultiSelect
        label="Business region" all="All regions" many={(n) => `${n} regions`}
        chosen={chosen.regions}
        onChange={(next) => set({ regions: join(next) })}
        options={narrowed(options.regions, chosen.areas, []).filter((o) => match(o.name))}
        query={q} onQuery={setQ} placeholder="Search regions…"
        open={open === "region"} onToggle={() => toggle("region")} onClose={close}
      />
      <MultiSelect
        label="Business team" all="All teams" many={(n) => `${n} teams`}
        chosen={chosen.teams}
        onChange={(next) => set({ teams: join(next) })}
        options={narrowed(options.teams, chosen.areas, chosen.regions).filter((o) => match(o.name))}
        query={q} onQuery={setQ} placeholder="Search teams…"
        open={open === "team"} onToggle={() => toggle("team")} onClose={close}
      />
      <MultiSelect
        label="Actual intake" all="All intakes" many={(n) => `${n} intakes`}
        chosen={chosenIntakes}
        onChange={(next) => set({
          intakes: join(next.map((name) => String(intakeId.get(name) ?? name))),
        })}
        options={options.intakes.filter((o) => match(o.name))} query={q} onQuery={setQ}
        placeholder="Search intakes, e.g. Sep 2026…"
        open={open === "intake"} onToggle={() => toggle("intake")} onClose={close}
      />

      {dirty ? (
        <button type="button" className="i360-clear"
                onClick={() => set({ from: null, to: null, regions: null, teams: null, intakes: null })}>
          Clear all
        </button>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// figures
// --------------------------------------------------------------------------

function Delta({ now, was }: { now: number; was: number }) {
  if (!was) return <span className="pl-d flat">{now ? "new" : "—"}</span>;
  const change = (now - was) / was;
  const dir = change > 0.0005 ? "up" : change < -0.0005 ? "down" : "flat";
  return <span className={`pl-d ${dir}`}>{change > 0 ? "+" : ""}{(100 * change).toFixed(1)}%</span>;
}

function MetricTile({ metric, on, onClick }: { metric: PulseMetric; on: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`tile pulse-tile${on ? " inv" : ""}`} onClick={onClick} title={metric.def}>
      <span className="drill" aria-hidden>Records →</span>
      <div className="metric">{n0(metric.value)}</div>
      <div className="metric-l">{metric.name}</div>
      <div className="foot">was {n0(metric.previous)} <Delta now={metric.value} was={metric.previous} /></div>
    </button>
  );
}

function Trend({ overview, metric, onPick }: {
  overview: PulseOverview; metric: PulseMetric;
  onPick: (point: PulseOverview["trend"]["points"][number]) => void;
}) {
  const { points, unit } = overview.trend;
  const config = useMemo<ChartConfiguration<"bar">>(() => {
    const chrome = chartChrome();
    const label = (start: string) => {
      const d = new Date(parse(start));
      return unit === "month"
        ? d.toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" })
        : d.toLocaleDateString("en-GB", { weekday: unit === "day" ? "short" : undefined, day: "numeric", month: "short", timeZone: "UTC" });
    };
    return {
      type: "bar",
      data: {
        labels: points.map((p) => label(p.start)),
        datasets: [{
          label: metric.name,
          data: points.map((p) => p[metric.id]),
          backgroundColor: token("color-accent") || "#3b6cf6",
          borderRadius: 3,
          maxBarThickness: 48,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (_event, elements) => {
          const point = elements[0] ? points[elements[0].index] : undefined;
          if (point) onPick(point);
        },
        onHover: (event, elements) => {
          const target = event.native?.target as HTMLElement | undefined;
          if (target) target.style.cursor = elements.length ? "pointer" : "default";
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: chrome.tooltip,
            callbacks: {
              title: (items) => {
                const p = points[items[0]?.dataIndex ?? 0];
                return p ? (p.start === p.end ? dayLabel(p.start) : rangeLabel(p.start, p.end)) : "";
              },
            },
          },
        },
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: true, grid: { color: chrome.grid }, ticks: { precision: 0 } },
        },
      },
    };
    // onPick changes every render; the chart only needs rebuilding for new data
  }, [points, unit, metric.id, metric.name]);

  return <div style={{ height: 260 }}><Chart config={config} /></div>;
}

function Breakdown({ overview, focus, onPick }: {
  overview: PulseOverview; focus: MetricId; onPick: (metric: MetricId, key: string) => void;
}) {
  const { rows } = overview.breakdown;
  const top = Math.max(1, ...rows.map((r) => r[focus]));
  if (!rows.length) return <p className="sub">Nothing happened in this range for the picked scope.</p>;
  return (
    <div className="tbl-wrap">
      <table className="pulse-table">
        <thead>
          <tr>
            <th className="txt">{DIMS.find((d) => d.value === overview.breakdown.by)?.label}</th>
            {overview.metrics.map((m) => (
              <th key={m.id} className={`num${m.id === focus ? " on" : ""}`}>{m.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td className="txt">
                <span className="pulse-bar" style={{ width: `${(100 * row[focus]) / top}%` }} aria-hidden />
                <span className="pulse-key">{row.key}</span>
              </td>
              {overview.metrics.map((m) => (
                <td key={m.id} className={`num${m.id === focus ? " on" : ""}`}>
                  {row[m.id] ? (
                    <button type="button" className="pulse-n" onClick={() => onPick(m.id, row.key)}>
                      {n0(row[m.id])}
                    </button>
                  ) : <span className="pulse-zero">·</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td className="txt"><b>Total</b></td>
            {overview.metrics.map((m) => (
              <td key={m.id} className={`num${m.id === focus ? " on" : ""}`}><b>{n0(m.value)}</b></td>
            ))}
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
