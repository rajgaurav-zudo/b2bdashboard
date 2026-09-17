import { useMemo } from "react";

import type { TooltipItem } from "chart.js";

import type { LogOverview } from "../../api/types";
import { n0 } from "../../format";
import { Chart } from "../../ui/Chart";
import { colourFor, weekLabel, weekTick } from "./weeks";

/** One bar per log type per week, grouped rather than stacked: the question is
 *  which kind of contact moved, and a stack makes that the hardest thing to see.
 *  The selected week is outlined so the KPI row above has an anchor in the chart. */
export function WeekOnWeek({ overview }: { overview: LogOverview }) {
  const { weeks, by_type: series, totals } = overview.series;
  const colour = colourFor(overview.log_types.map((t) => t.type));
  const selected = weeks.indexOf(overview.week);

  const config = useMemo(() => ({
    type: "bar" as const,
    data: {
      labels: weeks.map(weekTick),
      datasets: series.map((s) => ({
        label: s.type,
        data: s.counts,
        backgroundColor: colour(s.type),
        borderColor: "#17233a",
        // the selected week keeps a hairline outline; every other bar has none
        borderWidth: s.counts.map((_, i) => (i === selected ? 1.5 : 0)),
        borderSkipped: false,
        borderRadius: { topLeft: 3, topRight: 3 },
        maxBarThickness: 22,
      })),
    },
    options: {
      maintainAspectRatio: false,
      responsive: true,
      interaction: { mode: "index" as const, intersect: false },
      scales: {
        x: { grid: { display: false }, border: { display: false } },
        y: {
          grid: { color: "#e3e9f0", drawTicks: false },
          border: { display: false }, beginAtZero: true, ticks: { precision: 0 },
        },
      },
      plugins: {
        legend: {
          position: "bottom" as const,
          labels: { boxWidth: 9, boxHeight: 9, usePointStyle: true,
                    pointStyle: "rect" as const, padding: 14 },
        },
        tooltip: {
          backgroundColor: "#17233a", padding: 10, cornerRadius: 6, boxWidth: 8, boxHeight: 8,
          callbacks: {
            title: (items: TooltipItem<"bar">[]) => weekLabel(weeks[items[0]!.dataIndex]!),
            footer: (items: TooltipItem<"bar">[]) =>
              `${n0(totals[items[0]!.dataIndex] ?? 0)} logs that week`,
          },
        },
      },
    },
  }), [weeks, series, totals, selected, colour]);

  return (
    <div className="chart-card" style={{ marginTop: 18 }}>
      <h3>Logs per week by type</h3>
      <p className="cap">
        The last {weeks.length} weeks up to and including the selected one. Weeks the export does
        not hold are absent rather than plotted as zero.
      </p>
      <div className="chart-box" style={{ height: 300 }}><Chart config={config} /></div>
    </div>
  );
}
