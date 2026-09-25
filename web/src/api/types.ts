/** Shapes returned by the FastAPI service. Kept narrow on purpose: anything a
 *  component does not read does not belong here. */

export interface DatasetSummary {
  slug: string;
  display_name: string;
  table?: string;
  /** Which uploaded file feeds this table. Files are platform-level: one
   *  applications export feeds every dashboard that declares it. */
  source?: string;
  natural_key: string[];
  required_columns?: string[];
}

export interface DashboardSummary {
  slug: string;
  name: string;
  version: number;
  db_schema: string;
  context_sha: string | null;
  datasets: DatasetSummary[];
}

export interface CurrentLoad {
  dataset: string;
  load_id: number | null;
  row_count: number | null;
  created_at: string | null;
  filename: string | null;
  sha256: string | null;
  uploaded_by: string | null;
}

export interface DashboardDetail extends Omit<DashboardSummary, "db_schema"> {
  schema: string;
  /** The one-line "what is this for", from the dashboard's own manifest. */
  description: string;
  dimensions: string[];
  views: string[];
  current_loads: CurrentLoad[];
}

export interface ChangelogEntry {
  id: number;
  /** Which dashboard's diff this is: one file produces one entry per dashboard
   *  that reads it, each against that dashboard's own natural key. */
  dashboard: string;
  dashboard_name: string;
  entity: string;
  summary: string;
  rows_added: number | null;
  rows_removed: number | null;
  rows_changed: number | null;
  rows_unchanged: number | null;
  rows_sampled: number | null;
  occurred_at: string;
  load_id: number | null;
  previous_load_id: number | null;
  filename: string | null;
  status: string | null;
  uploaded_by: string | null;
  details: Record<string, unknown> | null;
}

export interface ChangelogRow {
  id: number;
  change_type: "added" | "removed" | "changed";
  natural_key: Record<string, string>;
  changed_fields: string[] | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface LoadRow {
  id: number;
  dashboard: string;
  dashboard_name: string;
  dataset: string;
  row_count: number;
  is_current: boolean;
  created_at: string;
  superseded_at: string | null;
  filename: string;
  sha256: string;
  uploaded_by: string | null;
}

/** One row per uploaded file. The outcomes are a list because a file is
 *  uploaded once and projected into every dashboard that declares its source --
 *  and can succeed in one and fail in another. A file that never parsed carries
 *  its own `status: "failed"` and no projections at all. */
export interface UploadRow {
  id: number;
  source: string;
  source_name: string;
  filename: string;
  byte_size: number;
  row_count: number | null;
  status: "pending" | "parsing" | "loading" | "diffing" | "ready" | "failed";
  error: string | null;
  started_at: string;
  finished_at: string | null;
  uploaded_by: string | null;
  sha256: string;
  projections: Projection[];
}

/** What one dashboard did with an uploaded file. */
export interface Projection {
  dashboard: string;
  dashboard_name?: string;
  dataset: string;
  status: "ready" | "failed" | "duplicate";
  load_id?: number | null;
  rows?: number | null;
  summary?: string;
  error?: string;
}

/** An upload feeds every dashboard that declares its source, so the result is a
 *  list of outcomes rather than one. */
export interface UploadResult {
  upload_id: number;
  source: string;
  status: string;
  changed: boolean;
  rows: number;
  reused_archive: boolean;
  projections: Projection[];
}

/** One table on one dashboard, and the file currently behind it. `load_id` is
 *  null when that dashboard has never been given its file. */
export interface DatasetState {
  dashboard: string;
  dashboard_name: string;
  dataset: string;
  display_name: string;
  source: string;
  source_name: string;
  load_id: number | null;
  row_count: number | null;
  created_at: string | null;
  filename: string | null;
  uploaded_by: string | null;
}

export interface SourceSummary {
  slug: string;
  display_name: string;
  description: string | null;
  uploads: number;
  last_upload: string | null;
  dashboards: { slug: string; name: string; dataset: string; display_name: string }[];
}

/* ---------- introducer performance view models ---------- */

export interface TileStats {
  n: number;
  life: number;
  cur: number;
  contract_active: number;
  contract_expired: number;
  /** Deposit states in the current intake year, for this tile's members.
   *  `daa` is a subset of the active deposits above it; `pd` is disjoint. */
  daa: number;
  pd: number;
}

export interface Tile {
  id: string;
  section: "active" | "leak" | "quality";
  name: string;
  definition: string;
  metric: "act" | "clos" | "apps" | "vrej" | "coe" | "none";
  head: "cur" | "life" | "count";
  invert?: boolean;
  metric_label: string;
  metric_short: string;
  stats: TileStats;
}

/** One course category's deposit states. The dashboard's own deposit figures are
 *  Academic-only; this is how the other categories are reported. */
export interface CourseSplitRow {
  category: string;
  act_cur: number;
  act_life: number;
  daa: number;
  pd: number;
  n: number;
}

export interface FunnelRow {
  y: number;
  apps: number;
  act: number;
  clos: number;
  vg: number;
  enr: number;
}

export interface StageRow { stage: string; n: number; act: number; clos: number; act_cur: number }

export interface CadenceRow {
  country: string; n: number; act: number;
  jan: number; may: number; sep: number;
  sep_share: number; top: number; peak: "Jan" | "May" | "Sep";
}

export interface Critique {
  enrolment: {
    base: number; under_10: number; under_5: number; under_3: number;
    org_rate: number; median_rate: number; miscalibrated: boolean;
  };
  closures: {
    base: number; over_30: number; over_50: number; over_100: number;
    median_ratio: number; miscalibrated: boolean;
  };
  visa_by_country: { country: string; n: number; apps: number }[];
}

export interface DataNotes {
  master_rows: number;
  blank_became: number;
  used_fallback: number;
  no_contract: number;
  app_rows: number;
  blank_intro: number;
  blank_intro_deposits: number;
  no_year: number;
  contradictions: number;
  intro_stats: { input_rows?: number; blank_name_rows?: number; duplicate_names?: number } | null;
}

/** The intake-month window every "current" figure counts, and the one it is
 *  compared with: the same months, a year (or as many years as it spans) back. */
export interface Period {
  from: string;          // YYYY-MM
  to: string;            // YYYY-MM
  label: string;         // "2026", "2024–2026", "Sep 2025 – May 2026"
  prior_label: string;
  end_year: number;
  whole_year: boolean;
  is_default: boolean;
}

export interface OverviewTotals {
  act_life: number; clos_life: number; apps_life: number;
  act_cur: number; clos_cur: number; enr_life: number;
}

/** The same filters over the prior window, keyed by the current tile ids. */
export interface OverviewCompare {
  label: string;
  book_size: number;
  totals: OverviewTotals;
  tiles: Record<string, TileStats>;
}

/** A team as the filter menus list it, with the region it sits in. */
export interface TeamOption { team: string; n: number; region: string }
export interface RegionOption { region: string; n: number }

export interface Overview {
  current_year: number;
  previous_year: number;
  period: Period;
  filters: { teams: string[]; regions: string[]; cycles: number[] };
  team_options: TeamOption[];
  region_options: RegionOption[];
  compare: OverviewCompare | null;
  year_histogram: { y: number; n: number }[];
  book_size: number;
  totals: OverviewTotals;
  tiles: Tile[];
  by_stage: StageRow[];
  cadence: CadenceRow[];
  funnel: { scope: FunnelRow[]; all: FunnelRow[] };
  course_split: CourseSplitRow[];
  not_in_crm: { n: number; act: number; clos: number };
  dormant_still_applying: number;
  critique: Critique;
  data: DataNotes;
}

export interface IntroducerRow {
  name: string;
  stage: string;
  in_crm: boolean;
  in_apps: boolean;
  contract: string;
  country: string;
  team: string;
  srm: string;
  became_y: number | null;
  became_fallback: boolean;
  comm: string;
  comm_type: string;
  apps_life: number; apps_cur: number;
  act_life: number; act_cur: number;
  clos_life: number; clos_cur: number;
  enr_life: number;
  vrej_life: number; vrej_cur: number;
  coe_life: number; coe_cur: number;
  enr_rate: number;
  close_pct: number | null;
  last_key: number;
  still_applying: boolean;
  is_resurrected: boolean;
}

export interface TileMembers {
  current_year: number;
  previous_year: number;
  period: Period;
  tile: Tile;
  by_stage: { stage: string; n: number; act: number; clos: number }[];
  rows: IntroducerRow[];
}

/** Server-side grouped drill-down (`/views/tile`). The pane groups locally from
 *  `TileMembers` instead; this stays for consumers that want a capped payload. */
export interface TileDrilldown {
  current_year: number;
  previous_year: number;
  period: Period;
  tile: Tile;
  group_by: string;
  sort: string;
  dir: "asc" | "desc";
  row_limit: number;
  groups: { key: string; n: number; life: number; cur: number; rows: IntroducerRow[] }[];
}

/* ---------- log dashboard view models ---------- */

/** Every week the file holds, with its volume. Dates are ISO `YYYY-MM-DD`
 *  Saturdays: a week runs Saturday → Friday. */
export interface WeekCount {
  w: string;
  n: number;
}

export interface WeekTypeRow {
  type: string;
  n: number;
  prev: number;
  /** vs the week immediately before, whatever range the tables show */
  delta: number;
  share: number;
}

export interface LogSeries {
  type: string;
  counts: number[];
  total: number;
}

/** One row of a top-performer table. The same shape for all three groupings,
 *  so one component renders any of them. */
export interface TopRow {
  name: string;
  /** logs in the selected range */
  n: number;
  /** every log in the file for this name, ignoring range and filters */
  lifetime: number;
  /** count per log type within the range; a type the name never used is absent */
  by_type: Record<string, number>;
  last_log: string;
  sentiment: number;
  n_introducers: number;
  n_creators: number;
  n_teams: number;
  n_types: number;
  /** up to two names, with however many more there were counted separately */
  teams: string[];
  teams_more: number;
  creators: string[];
  creators_more: number;
  /** rows before the limit was applied — the same on every row */
  total_names: number;
}

/** One top-performer table in full, behind the "view more" button. */
export interface LeaderboardView {
  dimension: string;
  label: string;
  note: string;
  week: string;
  range: { from: string; to: string; weeks: number };
  filters: { type: string; teams: string[]; regions: string[] };
  log_types: { type: string; n: number }[];
  total: number;
  rows: TopRow[];
}

export interface Quote {
  note: string;
  score: number;
  hits: number;
  introducer: string;
  creator: string;
  type: string;
  logged_on: string;
}

export interface LogSentiment {
  n: number;
  with_note: number;
  /** notes that matched at least one lexicon term; the rest count as neutral */
  scored: number;
  positive: number;
  negative: number;
  mixed: number;
  index: number;
  by_type: { type: string; n: number; scored: number; index: number }[];
  quotes: { pos: Quote[]; neg: Quote[] };
}

export interface LogDataNotes {
  rows: number;
  blank_note: number;
  unscored_note: number;
  blank_introducer: number;
  blank_creator: number;
  blank_team: number;
  introducers: number;
  creators: number;
  first_log: string | null;
  last_log: string | null;
  load_stats: { input_rows?: number; undated_rows?: number } | null;
}

export interface LogOverview {
  weeks: WeekCount[];
  week: string;
  previous_week: string | null;
  current_week: string;
  is_current: boolean;
  /** the selected week has begun but not finished — its Δ compares a partial
   *  week against a complete one */
  in_progress: boolean;
  days_elapsed: number;
  has_earlier: boolean;
  has_later: boolean;
  filters: { type: string; teams: string[]; regions: string[]; weeks: number; top: number; chart_weeks: number };
  log_types: { type: string; n: number }[];
  teams: TeamOption[];
  regions: RegionOption[];
  week_kpis: {
    total: number;
    previous_total: number;
    delta: number;
    by_type: WeekTypeRow[];
  };
  series: { weeks: string[]; by_type: LogSeries[]; totals: number[] };
  range: { from: string; to: string; weeks: number; rows: number };
  top: Record<string, TopRow[]>;
  /** names each table was drawn from, before the top-N limit */
  top_totals: Record<string, number>;
  sentiment: LogSentiment;
  data: LogDataNotes;
}

export interface LogRow {
  logged_on: string;
  type: string;
  introducer: string;
  team: string;
  creator: string;
  note: string | null;
  score: number | null;
  hits: number;
}

export interface LogRowsView {
  week: string;
  from: string;
  to: string;
  filters: { type: string; teams: string[]; regions: string[] };
  rows: LogRow[];
}

/* ---------------------------------------------------------------------------
   introducer 360
   A stage is an event -- an application that entered it inside the window --
   so every cell here is a count of entries, not of applications in a status.
   --------------------------------------------------------------------------- */

export interface I360Cell {
  created: number;
  active: number;
  closed: number;
  active_pct: number;
  closed_pct: number;
}

export interface I360Stage extends I360Cell {
  id: string;
  name: string;
  group: string | null;
  /** an event is windowed by its own timestamp; a state has no timestamp and is
   *  reported as it stands in the export */
  kind: "event" | "state";
  previous?: I360Cell;
  delta?: number | null;
}

export interface I360Widget extends I360Cell {
  id: string;
  name: string;
  sub?: string;
  kind: "event" | "state" | "group";
  group: string | null;
  members: I360Stage[];
  /** false when the card cannot be narrowed by the date range, and says "as of" */
  windowed: boolean;
  previous?: I360Cell;
  delta?: number | null;
}

export interface I360Range {
  id: string;
  label: string;
  from: string;
  to: string;
}

export interface I360WiseRow {
  name: string;
  entered: number;
  cells: (I360Cell & { id: string })[];
  total: I360Cell;
}

export interface I360Overview {
  anchor: string;
  scope_line: string;
  selected: string[];
  filters: { teams: string[]; regions: string[] };
  team_options: TeamOption[];
  region_options: RegionOption[];
  compare: boolean;
  range: I360Range & { presets: { id: string; label: string; from?: string; to?: string }[] };
  previous_range: { from: string; to: string; label: string };
  intake: {
    year: number | null;
    cycle: number | null;
    years: { y: number; n: number }[];
    cycles: { i: number; label: string; n: number }[];
  };
  stages: I360Stage[];
  widgets: I360Widget[];
  groups: { id: string; name: string; sub: string }[];
  top: I360WiseRow[];
  lifetime: {
    apps: number; applied: number; offers: number; deposits_live: number;
    enrolled: number; lost: number; first_seen: string | null; last_seen: string | null;
  };
  profile: {
    stage: string; contract: string; country: string;
    team: string; srm: string; since: number | null;
  } | null;
  commitment: {
    intake_year: number;
    now_paid: number; now_apps: number;
    prev_paid_to_date: number; prev_paid_total: number;
  };
  data: {
    app_rows: number; no_stage_dates: number; no_introducer: number;
    paid_without_date: number; no_intake_year: number; master_rows: number;
  };
}

export interface I360WiseView {
  scope_line: string;
  range: I360Range;
  stage_names: { id: string; name: string }[];
  rows: I360WiseRow[];
  row_limit: number;
  totals: { cells: I360Stage[]; total: I360Cell };
}

export interface I360MenuView {
  q: string;
  limit: number;
  rows: { name: string; n: number; deposits: number }[];
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

export interface PipelineCell { total: number; active: number | null; lost: number | null }

export interface PipelinePeriod { pipeline: PipelineCell; funnel: PipelineCell }

export interface PipelineStage {
  id: string;
  name: string;
  now: PipelinePeriod;
  ly_asat: PipelinePeriod;
  ly_final: PipelinePeriod;
}

export interface PipelineOverview {
  anchor: string;
  cutoff: string;
  filters: {
    mode: "calendar" | "academic"; year: number; quarters: number[]; levels: string[];
    teams: string[]; regions: string[];
  };
  options: {
    modes: { id: "calendar" | "academic"; label: string }[];
    years: { value: number; label: string }[];
    quarters: { q: number; label: string }[];
    levels: { name: string; n: number }[];
    academic_start: string;
    team_options: TeamOption[];
    region_options: RegionOption[];
  };
  scope: { label: string; last_year: string };
  totals: { now: PipelineCell; ly_asat: PipelineCell; ly_final: PipelineCell };
  stages: PipelineStage[];
  data: { app_rows: number; no_intake: number; no_student_ref: number; no_stage: number; undated_deposit: number };
}
