import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  ChangelogEntry, ChangelogRow, DashboardDetail, DashboardSummary,
  LoadRow, Overview, TileDrilldown, UploadResult,
} from "./types";

/** Vite proxies /api to the FastAPI service, so the app has no origin to configure. */
const BASE = "/api";

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
  const res = await fetch(url);
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

export function useTile(
  slug: string,
  tileId: string | null,
  params: { group_by: string; sort: string; dir: string },
) {
  return useQuery({
    queryKey: ["view", slug, "tile", tileId, params],
    queryFn: () => get<TileDrilldown>(`/dashboards/${slug}/views/tile`, { id: tileId!, ...params }),
    enabled: tileId !== null,
    placeholderData: (previous) => previous,      // keep the table on screen while re-sorting
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

export function useActivateLoad(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (loadId: number) => {
      const res = await fetch(`${BASE}/dashboards/${slug}/loads/${loadId}/activate`, { method: "POST" });
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
  void queryClient.invalidateQueries({ queryKey: ["dashboard", slug] });
}

export function useUpload(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ dataset, file }: { dataset: string; file: File }) => {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${BASE}/dashboards/${slug}/datasets/${dataset}/uploads`, {
        method: "POST", body,
      });
      if (!res.ok) throw new ApiError(await detail(res), res.status);
      return res.json() as Promise<UploadResult>;
    },
    onSuccess: () => invalidate(queryClient, slug),
  });
}
