import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { accessToken } from "../../auth";

/** The commission module's own endpoints, mounted at /api/modules/commission.
 *  Kept apart from api/client.ts because its errors carry structure -- a
 *  refused publish returns the checklist that refused it -- and the shared
 *  client flattens every error to a string. */
const BASE = "/api/modules/commission";

export class CommissionApiError extends Error {
  constructor(message: string, readonly status: number, readonly detail: Record<string, unknown>) {
    super(message);
  }
}

async function call<T>(method: string, path: string, body?: unknown,
                       params?: Record<string, string | undefined>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(params ?? {})) if (v) url.searchParams.set(k, v);
  const headers = new Headers();
  const token = await accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    payload = JSON.stringify(body);
  }
  const res = await fetch(url, { method, headers, body: payload });
  if (!res.ok) {
    let message = res.statusText;
    let detail: Record<string, unknown> = {};
    try {
      const j = await res.json();
      if (typeof j?.detail === "string") message = j.detail;
      else if (j?.detail && typeof j.detail === "object") {
        detail = j.detail;
        if (typeof j.detail.message === "string") message = j.detail.message;
        else if (Array.isArray(j.detail)) message = j.detail.map((d: { msg?: string }) => d.msg).join("; ");
      }
    } catch { /* not JSON */ }
    throw new CommissionApiError(message, res.status, detail);
  }
  return res.json() as Promise<T>;
}

// --- types -------------------------------------------------------------------
// Terms are one JSONB document server-side; these mirror the keys the UI edits.

export type Tier = { min_count: number | null; max_count: number | null; value: number | null };

export interface Rule {
  id?: string; name?: string; course_levels?: string[]; campus?: string | null;
  institution_id?: number | null; structure?: string; pricing?: string; value?: number | null;
  tiers?: Tier[]; tiers_raw?: string; tier_mode?: string; count_metric?: string; count_scope?: string;
  count_intakes?: string[]; count_window_start?: string; count_window_end?: string;
  fee_year_scope?: string; priority?: number; clause?: string; replaces?: string;
  needs_review?: boolean; review_note?: string; source_cell?: string; source?: string;
}

export interface Bonus {
  id?: string; kind?: string; criteria_text?: string; tiers?: Tier[]; tier_mode?: string;
  count_scope?: string; count_intakes?: string[]; course_levels?: string[]; applies_to_rule_ids?: string[];
  needs_review?: boolean; review_note?: string; source_cell?: string; source?: string;
}

export interface TerritoryRule { id?: string; type: string; scope?: string; value: string; note?: string; source?: string }
export interface Exclusion {
  id?: string; type: string; course_levels?: string[]; campus?: string; note?: string;
  cap_count?: number | null; cap_scope?: string | null; source?: string;
}
export interface Milestone { trigger: string; pct: number; n_weeks?: number | null }

export interface Terms {
  rules?: Rule[]; bonuses?: Bonus[]; territory_rules?: TerritoryRule[]; exclusions?: Exclusion[];
  campuses?: string[]; milestones?: Milestone[]; payment_conditions?: unknown[];
  targets?: unknown[]; other_conditions?: unknown[];
  review_items?: { cell?: string; message: string; text?: string }[];
}

export interface IntakeScope { mode: string; intakes?: string[]; until_intake?: string; from_intake?: string }

export interface Contract {
  id: number; code: string; party_type: string | null; party_id: number | null; party_name: string | null;
  covered_institution_ids: number[] | null; covered_institutions?: { id: number; name: string }[];
  region: string | null; status: string; status_reason: string | null; status_effective_date: string | null;
  start_date: string | null; end_date: string | null; is_rolling: boolean; currency: string | null;
  vat_treatment: string | null; vat_rate: number | null; fee_basis: string | null;
  territory_type: string | null; academic_years: string[] | null; intake_scope: IntakeScope | null;
  terms: Terms; current_version: number; has_unpublished: boolean; source_tab: string | null;
  source_rows: string | null; published_by: string | null; published_at: string | null;
}

export interface Alert { kind: "expiry" | "gap" | "draft"; message: string }

export interface ContractSummary {
  id: number; code: string; party_type: string | null; party_name: string | null; region: string | null;
  status: string; status_reason: string | null; start_date: string | null; end_date: string | null;
  is_rolling: boolean; current_version: number; has_unpublished: boolean; source_tab: string | null;
  amendments: number; draft_amendments: number; days_to_expiry: number | null; needs_review: number;
  rules: number; alerts: Alert[];
}

export interface CheckItem {
  key: string; label: string; ok: boolean; because?: string | null; message?: string | null; where?: string | null;
}
export interface Checklist {
  ready: boolean; failing: number; always: CheckItem[]; choices: CheckItem[];
  warnings: { key: string; message: string; where?: string | null }[];
}

export interface Amendment {
  id: number; contract_id: number; number: number; type: string; status: string;
  reference: string | null; received_on: string | null; document_file: string | null;
  scope_mode: string | null; from_intake: string | null; until_intake: string | null;
  window_start: string | null; window_end: string | null; applicability_basis: string | null;
  target_rule_ids: string[] | null; supersedes_amendment_id: number | null; needs_review: boolean;
  summary: string | null; changes: AmendmentChanges; source_cell: string | null;
  created_by?: string | null; created_at?: string | null; published_by?: string | null; published_at?: string | null;
}

export interface AmendmentChanges {
  rules?: Rule[]; bonuses?: Bonus[]; remove_bonus_ids?: string[];
  add_territory_rules?: TerritoryRule[]; remove_territory_rule_ids?: string[];
  add_exclusions?: Exclusion[]; remove_exclusion_ids?: string[];
  territory_type?: string; add_campuses?: string[]; remove_campuses?: string[];
  note?: string; new_end_date?: string;
}

export interface VersionRow { version: number; effective_from: string; published_by: string | null; published_at: string }

export interface ContractDetail {
  contract: Contract; versions: VersionRow[]; amendments: Amendment[]; checklist: Checklist;
  recalc_batches: { id: number; reason: string; from_intake: string | null; created_at: string; created_by: string | null }[];
}

export interface Resolved {
  ok: boolean; reason?: string; intake?: string; version?: number; currency?: string;
  vat_treatment?: string; vat_rate?: number; fee_basis?: string;
  rules?: Rule[]; bonuses?: Bonus[]; territory_rules?: TerritoryRule[]; exclusions?: Exclusion[];
  campuses?: string[]; targets?: unknown[]; notes?: { text: string; source: string }[];
  milestones?: Milestone[]; territory_type?: string;
  applied?: { number: number; type: string; summary: string | null }[];
  conditional?: { number: number; type: string; condition: string }[];
}

export interface TimelineColumn {
  intake: string; label: string; past: boolean; current: boolean; in_default: boolean; ok: boolean;
  reason: string | null;
  summary: null | {
    rules: { name: string; rate: string; source: string }[];
    bonuses: { criteria: string | null; kind: string; source: string }[];
    excluded: { value: string; source: string }[];
    applied: { number: number; type: string; summary: string | null }[];
    version: number;
  };
}

export interface Timeline {
  columns: TimelineColumn[];
  validity: { start: string | null; end: string | null; rolling: boolean; scope: IntakeScope | null };
  versions: { version: number; effective_from: string; published_at: string; published_by: string | null }[];
  amendments: Pick<Amendment, "id" | "number" | "type" | "status" | "summary" | "scope_mode" | "from_intake"
    | "until_intake" | "window_start" | "window_end" | "needs_review" | "received_on">[];
  alerts: TimelineColumn[];
  checks: Checklist;
}

export interface SimResult {
  terms_ok: boolean;
  result: {
    eligible: boolean; blocked?: boolean; excluded?: boolean; reason: string | null; amount: number;
    currency?: string; rate?: number | null; source?: string; fee_basis?: string;
    rule?: { id: string; name: string; source: string; pricing: string; structure: string; tier_mode: string };
    breakdown?: { label: string; kind: string; source: string; rate: number | null; amount: number; detail: string }[];
    bonuses?: { id: string; kind: string; criteria: string | null; source: string; reached: boolean;
                amount: number; detail?: string; progress?: string; needs_review?: boolean }[];
    lump_sums?: { criteria: string | null; lump_sum: number; detail?: string }[];
    vat?: { treatment: string; rate: number; revenue_ex_vat: number; invoice_total: number; detail: string };
    milestones?: { trigger: string; pct: number; n_weeks?: number | null; amount: number }[];
  };
}

export interface AmendmentPreview {
  amendment: Amendment;
  intakes: { intake: string; label: string; before: Resolved; after: Resolved }[];
  checks: { key: string; label: string; ok: boolean; block: boolean; message: string | null }[];
  open_ended: boolean;
}

export interface AuditEntry {
  id: number; contract_id: number; entity: string; entity_id: string; action: string;
  before_json: unknown; after_json: unknown; user: string | null;
  document_ref: string | null; created_at: string;
}

export interface Meta {
  course_levels: string[];
  countries: { code: string; name: string; parent: string | null; aliases: string[] | null }[];
  enums: Record<string, string[]>;
  today: string;
  intakes_default: string[];
}

export interface ImportRow {
  index: number; tab: string; rows: string; party_name: string; party_type: string; region: string;
  action: "create" | "update" | "skip"; contract_id: number | null; why: string | null;
  institution: { match: "exact" | "ambiguous" | "new"; id?: number; name?: string; candidates?: { id: number; name: string }[] };
  counts: { rules: number; bonuses: number; territory_rules: number; exclusions: number; amendments: number };
  review: { cell?: string | null; message: string; text?: string | null }[];
}

export interface ImportBatch {
  id: number; filename: string; sha256: string; committed: boolean; created_by: string | null;
  created_at: string; previously_committed: boolean; contracts: ImportRow[];
  totals: { contracts: number; review: number; create: number; update: number; skip: number };
  unknown_tabs: string[]; unmatched_invoicing: { name: string; cell: string }[];
}

export interface CommitResult {
  created: number; updated: number; skipped: number; contract_ids: number[];
  failed: { index: number; party_name: string; message: string }[];
}

// --- hooks -------------------------------------------------------------------

export function useMeta() {
  return useQuery({ queryKey: ["commission", "meta"], queryFn: () => call<Meta>("GET", "/meta"), staleTime: Infinity });
}

export function useInstitutions() {
  return useQuery({
    queryKey: ["commission", "institutions"],
    queryFn: () => call<{ id: number; name: string; country: string | null; region: string | null }[]>("GET", "/institutions"),
  });
}

export function useContracts() {
  return useQuery({ queryKey: ["commission", "contracts"], queryFn: () => call<ContractSummary[]>("GET", "/contracts") });
}

export function useContract(id: number) {
  return useQuery({ queryKey: ["commission", "contract", id], queryFn: () => call<ContractDetail>("GET", `/contracts/${id}`) });
}

export function useTimeline(id: number) {
  return useQuery({ queryKey: ["commission", "timeline", id], queryFn: () => call<Timeline>("GET", `/contracts/${id}/timeline`) });
}

export function useEffective(id: number, intake: string | null) {
  return useQuery({
    queryKey: ["commission", "effective", id, intake],
    queryFn: () => call<Resolved>("GET", `/contracts/${id}/effective`, undefined, { intake: intake ?? undefined }),
    enabled: !!intake,
  });
}

export function useAudit(id: number, entity?: string, action?: string) {
  return useQuery({
    queryKey: ["commission", "audit", id, entity, action],
    queryFn: () => call<AuditEntry[]>("GET", `/contracts/${id}/audit`, undefined, { entity, action }),
  });
}

export function useAmendmentPreview(id: number | null) {
  return useQuery({
    queryKey: ["commission", "amendment-preview", id],
    queryFn: () => call<AmendmentPreview>("GET", `/amendments/${id}/preview`),
    enabled: id !== null,
  });
}

export function useImportBatch(id: number | null) {
  return useQuery({
    queryKey: ["commission", "import", id],
    queryFn: () => call<ImportBatch>("GET", `/import/${id}`),
    enabled: id !== null,
  });
}

export const simulate = (id: number, body: Record<string, unknown>) => call<SimResult>("POST", `/contracts/${id}/simulate`, body);

/** Every write changes what several screens show (list alerts, timeline,
 *  checklist, audit), so each one drops the whole module's cache. */
function useWrite<A, R>(fn: (arg: A) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["commission"] }),
  });
}

export const useCreateContract = () => useWrite((data: Partial<Contract>) => call<Contract>("POST", "/contracts", data));
export const useUpdateContract = (id: number) =>
  useWrite((data: Partial<Contract>) => call<Contract>("PUT", `/contracts/${id}`, data));
export const useDeleteContract = (id: number) => useWrite(() => call<{ deleted: number }>("DELETE", `/contracts/${id}`));
export const usePublishContract = (id: number) =>
  useWrite((effective_from: string | null) => call<Contract>("POST", `/contracts/${id}/publish`, { effective_from }));
export const useSetStatus = (id: number) =>
  useWrite((b: { status: string; reason?: string; effective_date?: string }) => call<Contract>("POST", `/contracts/${id}/status`, b));

export const useCreateAmendment = (contractId: number) =>
  useWrite((data: Partial<Amendment>) => call<Amendment>("POST", `/contracts/${contractId}/amendments`, data));
export const useUpdateAmendment = () =>
  useWrite(({ id, data }: { id: number; data: Partial<Amendment> }) => call<Amendment>("PUT", `/amendments/${id}`, data));
export const useDeleteAmendment = () => useWrite((id: number) => call<{ deleted: number }>("DELETE", `/amendments/${id}`));
export const usePublishAmendment = () => useWrite((id: number) => call<Amendment>("POST", `/amendments/${id}/publish`));

export const useImportPreview = () =>
  useWrite((file: File) => {
    const body = new FormData();
    body.append("file", file);
    return call<ImportBatch>("POST", "/import/preview", body);
  });
export const useImportCommit = () =>
  useWrite(({ id, skip }: { id: number; skip: number[] }) => call<CommitResult>("POST", `/import/${id}/commit`, { skip }));
