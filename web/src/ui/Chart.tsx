import {
  BarController, BarElement, CategoryScale, Chart as ChartJS, Legend, LineController,
  LineElement, LinearScale, PointElement, Tooltip, type ChartConfiguration, type ChartType,
} from "chart.js";
import { useEffect, useRef } from "react";

ChartJS.register(
  BarController, BarElement, LineController, LineElement, PointElement,
  LinearScale, CategoryScale, Tooltip, Legend,
);

ChartJS.defaults.font.family =
  "ui-sans-serif, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
ChartJS.defaults.font.size = 11;
ChartJS.defaults.color = "#5F6E68";

/** Labels each line at its right-hand end instead of in a legend, so the eye
 *  never has to travel between a colour swatch and a line. Collisions are
 *  nudged apart and clamped inside the plot area. */
export const endLabels = {
  id: "endLabels",
  afterDatasetsDraw(chart: ChartJS) {
    const { ctx, chartArea } = chart;
    const placed: { y: number; text: string; colour: string }[] = [];
    chart.data.datasets.forEach((dataset, i) => {
      const meta = chart.getDatasetMeta(i);
      if (meta.hidden) return;
      const last = [...meta.data].reverse().find((point) => point && Number.isFinite(point.y));
      if (!last) return;
      placed.push({
        y: last.y,
        text: String(dataset.label ?? ""),
        colour: String(dataset.borderColor ?? "#15201C"),
      });
    });
    // Two series ending at the same value would print on top of each other.
    // Push apart downwards, then lift the whole column back inside the plot if
    // that pushed the last one past the bottom -- clamping instead would just
    // stack them all on the final pixel row.
    const GAP = 15;
    placed.sort((a, b) => a.y - b.y);
    for (let i = 1; i < placed.length; i += 1) {
      const previous = placed[i - 1]!;
      const current = placed[i]!;
      if (current.y - previous.y < GAP) current.y = previous.y + GAP;
    }
    const last = placed[placed.length - 1];
    const overflow = last ? last.y - chartArea.bottom : 0;
    if (overflow > 0) placed.forEach((label) => { label.y -= overflow; });
    if (placed[0] && placed[0].y < chartArea.top) {
      const lift = chartArea.top - placed[0].y;
      placed.forEach((label) => { label.y += lift; });
    }

    ctx.save();
    ctx.font = "600 11px ui-sans-serif, system-ui, sans-serif";
    ctx.textBaseline = "middle";
    placed.forEach((label) => {
      ctx.fillStyle = label.colour;
      ctx.fillText(label.text, chartArea.right + 6, label.y);
    });
    ctx.restore();
  },
};

export function Chart<T extends ChartType>({ config }: { config: ChartConfiguration<T> }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvas.current) return undefined;
    const chart = new ChartJS(canvas.current, config as ChartConfiguration);
    return () => chart.destroy();
  }, [config]);

  return (
    <div className="chart-box">
      <canvas ref={canvas} />
    </div>
  );
}
