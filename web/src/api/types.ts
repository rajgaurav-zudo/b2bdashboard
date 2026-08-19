/** Shapes returned by the FastAPI service. Kept narrow on purpose: anything a
 *  component does not read does not belong here. */

export interface DatasetSummary {
  slug: string;
  display_name: string;
  table?: string;
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
  dimensions: string[];
  views: string[];
  current_loads: CurrentLoad[];
}

export interface ChangelogEntry {
  id: number;
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
  dataset: string;
  row_count: number;
  is_current: boolean;
  created_at: string;
  superseded_at: string | null;
  filename: string;
  sha256: string;
  uploaded_by: string | null;
}

export interface UploadRow {
  id: number;
  dataset: string;
  filename: string;
  byte_size: number;
  row_count: number | null;
  status: "pending" | "parsing" | "loading" | "diffing" | "ready" | "failed" | "duplicate";
  error: string | null;
  started_at: string;
  finished_at: string | null;
  uploaded_by: string | null;
}

export interface UploadResult {
  upload_id: number;
  status: string;
  changed: boolean;
  load_id?: number;
  summary?: string;
  counts?: Record<string, number>;
}

/* ---------- introducer performance view models ---------- */

export interface TileStats {
  n: number;
  life: number;
  cur: number;
  contract_active: number;
  contract_expired: number;
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

export interface Overview {
  current_year: number;
  previous_year: number;
  year_histogram: { y: number; n: number }[];
  book_size: number;
  totals: {
    act_life: number; clos_life: number; apps_life: number;
    act_cur: number; clos_cur: number; enr_life: number;
  };
  tiles: Tile[];
  by_stage: StageRow[];
  cadence: CadenceRow[];
  funnel: { scope: FunnelRow[]; all: FunnelRow[] };
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

export interface TileDrilldown {
  current_year: number;
  previous_year: number;
  tile: Tile;
  group_by: string;
  sort: string;
  dir: "asc" | "desc";
  row_limit: number;
  groups: { key: string; n: number; life: number; cur: number; rows: IntroducerRow[] }[];
}
