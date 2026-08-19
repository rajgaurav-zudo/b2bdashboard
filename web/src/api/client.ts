import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { accessToken } from "../auth";
import type {
  ChangelogEntry, ChangelogRow, DashboardDetail, DashboardSummary,
  LoadRow, Overview, TileMembers, UploadResult, UploadRow,
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

export function useOverview(slug: string) {
  return useQuery({
    queryKey: ["view", slug, "overview"],
    queryFn: () => get<Overview>(`/dashboards/${slug}/views/overview`),
    retry: false,                 // 409 means "nothing uploaded yet"; retrying will not help
  });
}

export function useChangelog(slug: string) {
  return useQuery({
    queryKey: ["changelog", slug],
    queryFn: () => get<ChangelogEntry[]>(`/dashboards/${slug}/changelog`),
  });
}

export function useChangelogRows(changelogId: number | null) {
  return useQuery({
    queryKey: ["changelog-rows", changelogId],
    queryFn: () => get<ChangelogRow[]>(`/changelog/${changelogId}/rows`),
    enabled: changelogId !== null,
  });
}

export function useLoads(slug: string) {
  return useQuery({
    queryKey: ["loads", slug],
    queryFn: () => get<LoadRow[]>(`/dashboards/${slug}/loads`),
  });
}

export function useTileMembers(slug: string, tileId: string | null) {
  return useQuery({
    queryKey: ["view", slug, "members", tileId],
    queryFn: () => get<TileMembers>(
      `/dashboards/${slug}/views/members?id=${encodeURIComponent(tileId!)}`),
    enabled: tileId !== null,
    // the pane regroups and re-sorts locally, so the payload is fetched once per tile
    staleTime: 5 * 60 * 1000,
  });
}

export function useUploads(slug: string) {
  return useQuery({
    queryKey: ["uploads", slug],
    queryFn: () => get<UploadRow[]>(`/dashboards/${slug}/uploads`),
  });
}

export function useActivateLoad(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (loadId: number) => {
      const res = await fetch(`${BASE}/dashboards/${slug}/loads/${loadId}/activate`,
        { method: "POST", headers: await authHeaders() });
      if (!res.ok) throw new ApiError(await detail(res), res.status);
      return res.json() as Promise<{ load_id: number; changed: boolean; summary: string }>;
    },
    onSuccess: () => invalidate(queryClient, slug),
  });
}

function invalidate(queryClient: ReturnType<typeof useQueryClient>, slug: string) {
  // a change of current load changes every number on the page
  void queryClient.invalidateQueries({ queryKey: ["view", slug] });
  void queryClient.invalidateQueries({ queryKey: ["changelog", slug] });
  void queryClient.invalidateQueries({ queryKey: ["loads", slug] });
  void queryClient.invalidateQueries({ queryKey: ["uploads", slug] });
  void queryClient.invalidateQueries({ queryKey: ["dashboard", slug] });
}

export function useUpload(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ dataset, file }: { dataset: string; file: File }) => {
      const body = new FormData();
      body.append("file", file);
      // no Content-Type header: the browser must set the multipart boundary itself
      const res = await fetch(`${BASE}/dashboards/${slug}/datasets/${dataset}/uploads`, {
        method: "POST", body, headers: await authHeaders(),
      });
      if (!res.ok) throw new ApiError(await detail(res), res.status);
      return res.json() as Promise<UploadResult>;
    },
    onSuccess: () => invalidate(queryClient, slug),
  });
}
