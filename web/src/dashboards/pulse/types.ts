/** The pulse dashboard's view payloads (dashboards/pulse/metrics.py). */

export type MetricId =
  | "onboarded" | "logs" | "applied" | "offer" | "deposit" | "coe" | "visa" | "enrolled" | "closed";
export type Dim = "region" | "team" | "country" | "introducer";

export type Counts = Record<MetricId, number>;

export interface PulseMetric {
  id: MetricId;
  name: string;
  def: string;
  value: number;
  previous: number;
}

export interface ScopeOption {
  name: string;
  n: number;
  areas?: string[];
  regions?: string[];
}

export interface PulseOverview {
  range: { from: string; to: string; days: number; default: boolean };
  previous: { from: string; to: string };
  metrics: PulseMetric[];
  trend: { unit: "day" | "week" | "month"; points: ({ start: string; end: string } & Counts)[] };
  breakdown: { by: Dim; rows: ({ key: string } & Counts)[]; more: number };
  options: {
    areas: ScopeOption[];
    regions: ScopeOption[];
    teams: ScopeOption[];
    intakes: { id: number; name: string; n: number }[];
  };
  loaded: Record<string, boolean>;
  chosen: { areas: string[]; regions: string[]; teams: string[]; intakes: number[] };
}

export interface PulseRecords {
  metric: MetricId;
  name: string;
  range: { from: string; to: string };
  dim: Dim | null;
  key: string | null;
  columns: { id: string; name: string }[];
  rows: Record<string, string | number | null>[];
  total: number;
  limit: number;
}

/** What the side pane is showing: a metric, optionally narrowed to one
 *  breakdown row or one trend bucket. */
export interface Drill {
  metric: MetricId;
  from?: string;
  to?: string;
  dim?: Dim;
  key?: string;
  label: string;
}
