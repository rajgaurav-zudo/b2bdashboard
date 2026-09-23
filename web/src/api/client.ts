import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { accessToken } from "../auth";
import type {
  ChangelogEntry, ChangelogRow, DashboardDetail, DashboardSummary,
  DatasetState, LoadRow, Overview, SourceSummary, TileMembers, UploadResult, UploadRow,
} from "./types";

/** Vite proxies /api to the FastAPI service, so the app has no origin to configure. */
const BASE = "/api";

/** Every request carries the Supabase token when there is one. Read per request
 *  rather than cached: supabase-js rotates it before expiry. */
async function authHeaders(extra?: HeadersInit): Promise<Headers> {
  const headers = new Headers(extra);
  const token = await accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  }
  const res = await fetch(url, { headers: await authHeaders() });
  if (!res.ok) throw new ApiError(await detail(res), res.status);
  return res.json() as Promise<T>;
}

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : res.statusText;
  } catch {
    return res.statusText;
  }
}

export function useDashboards() {
  return useQuery({
    queryKey: ["dashboards"],
    queryFn: () => get<DashboardSummary[]>("/dashboards"),
  });
}

export function useDashboard(slug: string) {
  return useQuery({
    queryKey: ["dashboard", slug],
    queryFn: () => get<DashboardDetail>(`/dashboards/${slug}`),
  });
}

/** The introducer overview, with the page's filters. Changing a filter keeps
 *  the previous page on screen until the new one arrives. */
export function useOverview(slug: string, filters: Record<string, string | undefined> = {}) {
  return useQuery({
    queryKey: ["view", slug, "overview", filters],
    queryFn: () => get<Overview>(`/dashboards/${slug}/views/overview`, filters),
    retry: false,                 // 409 means "nothing uploaded yet"; retrying will not help
    placeholderData: keepPreviousData,
  });
}

/** Any dashboard-owned view, with its params; the params are part of the cache key. */
export function useView<T>(
  slug: string, view: string, params: Record<string, string | number | undefined>,
  enabled = true,
) {
  return useQuery({
    queryKey: ["view", slug, view, params],
    queryFn: () => get<T>(`/dashboards/${slug}/views/${view}`, params),
    enabled,
    retry: false,                 // 409 means "nothing uploaded yet"; retrying will not help
    // stepping a week should redraw, not blank the page out
    placeholderData: keepPreviousData,
  });
}

/** Every dashboard's changelog, or one dashboard's when `dashboard` is given.
 *  Uploads are platform-level, so the log of them is too. */
export function useChangelog(dashboard?: string) {
  return useQuery({
    queryKey: ["changelog", dashboard ?? "all"],
    queryFn: () => get<ChangelogEntry[]>("/changelog", { dashboard, limit: 200 }),
  });
}

export function useChangelogRows(changelogId: number | null) {
  return useQuery({
    queryKey: ["changelog-rows", changelogId],
    queryFn: () => get<ChangelogRow[]>(`/changelog/${changelogId}/rows`),
    enabled: changelogId !== null,
  });
}

export function useLoads(dashboard?: string) {
  return useQuery({
    queryKey: ["loads", dashboard ?? "all"],
    queryFn: () => get<LoadRow[]>("/loads", { dashboard, limit: 300 }),
  });
}

/** What every dashboard is serving right now, including the ones serving
 *  nothing -- which is the row worth seeing on an upload page. */
export function useDatasets() {
  return useQuery({
    queryKey: ["datasets"],
    queryFn: () => get<DatasetState[]>("/datasets"),
  });
}

export function useTileMembers(
  slug: string, tileId: string | null, filters: Record<string, string | undefined> = {},
) {
  return useQuery({
    queryKey: ["view", slug, "members", tileId, filters],
    queryFn: () => get<TileMembers>(`/dashboards/${slug}/views/members`, { id: tileId!, ...filters }),
    enabled: tileId !== null,
    // the pane regroups and re-sorts locally, so the payload is fetched once per tile
    staleTime: 5 * 60 * 1000,
  });
}

/** The files the platform accepts, and which dashboards read each one. */
export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: () => get<SourceSummary[]>("/sources"),
  });
}

export function useUploads(dashboard?: string) {
  return useQuery({
    queryKey: ["uploads", dashboard ?? "all"],
    queryFn: () => get<UploadRow[]>("/uploads", { dashboard, limit: 100 }),
  });
}

/** Rolling back is still a dashboard's own act -- the load belongs to one
 *  dashboard's tables -- so the row says which one to call. */
export function useActivateLoad() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ dashboard, loadId }: { dashboard: string; loadId: number }) => {
      const res = await fetch(`${BASE}/dashboards/${dashboard}/loads/${loadId}/activate`,
        { method: "POST", headers: await authHeaders() });
      if (!res.ok) throw new ApiError(await detail(res), res.status);
      return res.json() as Promise<{ load_id: number; changed: boolean; summary: string }>;
    },
    onSuccess: () => invalidate(queryClient),
  });
}

/** A file feeds every dashboard that declares its source, so there is no such
 *  thing as an upload that only affects the dashboard you were looking at.
 *  Everything derived from a load is dropped rather than guessing which. */
function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  for (const key of ["view", "changelog", "loads", "uploads", "datasets",
                     "dashboard", "dashboards", "sources"]) {
    void queryClient.invalidateQueries({ queryKey: [key] });
  }
}

/** Upload goes to a source, not to a dashboard: the file is archived once and
 *  projected into every dashboard that declares it. */
export function useUpload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ source, file }: { source: string; file: File }) => {
      const body = new FormData();
      body.append("file", file);
      // no Content-Type header: the browser must set the multipart boundary itself
      const res = await fetch(`${BASE}/sources/${source}/uploads`, {
        method: "POST", body, headers: await authHeaders(),
      });
      if (!res.ok) throw new ApiError(await detail(res), res.status);
      return res.json() as Promise<UploadResult>;
    },
    onSuccess: () => invalidate(queryClient),
  });
}
