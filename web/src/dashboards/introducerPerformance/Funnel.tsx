import { useMemo, useState } from "react";

import type { TooltipItem } from "chart.js";

import type { FunnelRow, Overview } from "../../api/types";
import { n0, pct } from "../../format";
import { Chart, endLabels } from "../../ui/Chart";
import { Pill } from "../../ui/Primitives";

interface Row {
  y: number; apps: number; paid: number; act: number; clos: number;
  cpct: number; r1: number; r2: number; r3: number; r4: number; future: boolean;
}

const rate = (part: number, whole: number) => (whole ? (100 * part) / whole : 0);

function toRows(source: FunnelRow[], currentYear: number): Row[] {
  return source.map((r) => ({
    y: r.y, apps: r.apps, paid: r.act + r.clos, act: r.act, clos: r.clos,
    cpct: rate(r.clos, r.act + r.clos),
    r1: rate(r.act, r.apps),
    r2: rate(r.act + r.clos, r.apps),
    r3: rate(r.vg, r.act),
    r4: rate(r.enr, r.act),
    future: r.y > currentYear,
  }));
}

const COLUMNS: { key: keyof Row; label: string }[] = [
  { key: "y", label: "Year" },
  { key: "apps", label: "Applications" },
  { key: "paid", label: "Deposits paid" },
  { key: "act", label: "Active" },
  { key: "clos", label: "Closed" },
  { key: "cpct", label: "Closed %" },
  { key: "r1", label: "App → active" },
  { key: "r2", label: "App → any dep." },
  { key: "r3", label: "Dep → visa" },
  { key: "r4", label: "Dep → enrolled" },
];

export function Funnel({ overview }: { overview: Overview }) {
  const [scope, setScope] = useState<"scope" | "all">("scope");
  const [sort, setSort] = useState<keyof Row>("y");
  const [dir, setDir] = useState<1 | -1>(1);

  const rows = useMemo(
    () => toRows(overview.funnel[scope], overview.current_year),
    [overview, scope],
  );

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => (a[sort] as number) - (b[sort] as number) || a.y - b.y);
    return dir === 1 ? copy : copy.reverse();
  }, [rows, sort, dir]);

  const totals = rows.reduce(
    (acc, r) => ({ apps: acc.apps + r.apps, act: acc.act + r.act, clos: acc.clos + r.clos }),
    { apps: 0, act: 0, clos: 0 },
  );

  // Future intakes stay in the table but out of the charts: a barely-started
  // year reads as a rate collapse rather than as the artefact it is.
  const peak = Math.max(0, ...rows.map((r) => r.apps));
  const shown = useMemo(
    () => [...rows].sort((a, b) => a.y - b.y)
      .filter((r) => r.y <= overview.current_year && r.apps >= 0.01 * peak),
    [rows, overview.current_year, peak],
  );
  const labels = shown.map((r) => String(r.y));

  const volume = useMemo(() => ({
    type: "bar" as const,
    data: {
      labels,
      datasets: [
        { label: "Active deposits", data: shown.map((r) => r.act), backgroundColor: "#0F8A5F",
          borderColor: "#FFFFFF", borderWidth: { top: 2 }, borderSkipped: false, maxBarThickness: 46 },
        { label: "Closed lost", data: shown.map((r) => r.clos), backgroundColor: "#C0491F",
          borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: "bottom" as const, maxBarThickness: 46 },
      ],
    },
    options: {
      maintainAspectRatio: false, responsive: true,
      interaction: { mode: "index" as const, intersect: false },
      scales: {
        x: { stacked: true, grid: { display: false }, border: { display: false } },
        y: { stacked: true, grid: { color: "rgba(21,32,28,.07)", drawTicks: false },
             border: { display: false }, ticks: { precision: 0 } },
      },
      plugins: {
        legend: { position: "bottom" as const,
                  labels: { boxWidth: 9, boxHeight: 9, usePointStyle: true, pointStyle: "rect" as const, padding: 14 } },
        tooltip: {
          backgroundColor: "#15201C", padding: 10, cornerRadius: 6, boxWidth: 8, boxHeight: 8,
          callbacks: {
            footer: (items: TooltipItem<"bar">[]) => {
              const r = shown[items[0]!.dataIndex]!;
              return `paid ${n0(r.paid)} of ${n0(r.apps)} applications (${r.r2.toFixed(2)}%)`;
            },
          },
        },
      },
    },
  }), [labels, shown]);

  const rates = useMemo(() => {
    const series = (label: string, key: keyof Row, colour: string, dash: number[] = []) => ({
      label, data: shown.map((r) => Number((r[key] as number).toFixed(2))),
      borderColor: colour, backgroundColor: colour, borderWidth: 2, borderDash: dash,
      pointRadius: 4, pointHoverRadius: 6, pointBorderColor: "#FFFFFF", pointBorderWidth: 2, tension: 0.25,
    });
    return {
      type: "line" as const,
      data: {
        labels,
        datasets: [
          series("Dep → enrolled", "r4", "#3B6FA8"),
          series("Dep → visa", "r3", "#C08018"),
          series("App → any dep.", "r2", "#0F8A5F"),
          series("App → active", "r1", "#C0491F", [5, 4]),
        ],
      },
      options: {
        maintainAspectRatio: false, responsive: true,
        layout: { padding: { right: 96 } },
        interaction: { mode: "index" as const, intersect: false },
        scales: {
          x: { grid: { display: false }, border: { display: false } },
          y: { grid: { color: "rgba(21,32,28,.07)", drawTicks: false }, border: { display: false },
               beginAtZero: true, ticks: { callback: (v: string | number) => `${v}%` } },
        },
        plugins: {
          legend: { display: false },
          tooltip: { backgroundColor: "#15201C", padding: 10, cornerRadius: 6, boxWidth: 8, boxHeight: 8,
                     callbacks: { label: (c: TooltipItem<"line">) =>
                       `${c.dataset.label}: ${(c.parsed.y ?? 0).toFixed(2)}%` } },
        },
      },
      plugins: [endLabels],
    };
  }, [labels, shown]);

  const header = (key: keyof Row, label: string) => (
    <th key={key} className="num" onClick={() => {
      if (key === sort) setDir(dir === 1 ? -1 : 1);
      else { setSort(key); setDir(key === "y" ? 1 : -1); }
    }}>
      {label}{sort === key ? <span className="dir"> {dir === 1 ? "▲" : "▼"}</span> : null}
    </th>
  );

  return (
    <>
      <div className="pane-bar card" style={{ borderRadius: "var(--radius)", marginBottom: 12 }}>
        <label>Scope</label>
        <button type="button" className={`chip${scope === "scope" ? " on" : ""}`}
                onClick={() => setScope("scope")}>In scope</button>
        <button type="button" className={`chip${scope === "all" ? " on" : ""}`}
                onClick={() => setScope("all")}>All attributed</button>
        <span style={{ fontSize: 12, color: "var(--faint)" }}>
          “In scope” is the book the tiles score. “All attributed” adds every named introducer,
          including those who never reached Customer stage and never paid a deposit.
        </span>
      </div>

      <div className="card scroll">
        <table>
          <thead><tr>{COLUMNS.map((c) => header(c.key, c.label))}</tr></thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.y} style={r.future ? { opacity: 0.6 } : undefined}>
                <td className="num">
                  <b>{r.y}</b>{" "}
                  {r.future ? <Pill kind="future">future intake</Pill>
                    : r.y === overview.current_year ? <Pill kind="live">in flight</Pill> : null}
                </td>
                <td className="num">{n0(r.apps)}</td>
                <td className="num">{n0(r.paid)}</td>
                <td className="num">{n0(r.act)}</td>
                <td className="num">{n0(r.clos)}</td>
                <td className="num">{r.cpct.toFixed(1)}%</td>
                <td className="num">{r.r1.toFixed(2)}%</td>
                <td className="num">{r.r2.toFixed(2)}%</td>
                <td className="num">{r.r3.toFixed(1)}%</td>
                <td className="num">{r.r4.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="total">
              <td>All years</td>
              <td className="num">{n0(totals.apps)}</td>
              <td className="num">{n0(totals.act + totals.clos)}</td>
              <td className="num">{n0(totals.act)}</td>
              <td className="num">{n0(totals.clos)}</td>
              <td className="num">{pct(totals.clos, totals.act + totals.clos)}</td>
              <td className="num">{pct(totals.act, totals.apps, 2)}</td>
              <td className="num">{pct(totals.act + totals.clos, totals.apps, 2)}</td>
              <td /><td />
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="charts" style={{ marginTop: 12 }}>
        <div className="card pad"><Chart config={volume} /></div>
        <div className="card pad"><Chart config={rates} /></div>
      </div>
    </>
  );
}
