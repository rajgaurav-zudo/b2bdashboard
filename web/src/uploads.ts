import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useSyncExternalStore } from "react";

import { invalidate } from "./api/client";
import type { UploadResult } from "./api/types";
import { accessToken, sessionRejected } from "./auth";

/** Uploads in flight, kept outside React so they outlive the page that started
 *  them: leave the Uploads page and the request carries on, and the tray in the
 *  layout keeps showing it until it finishes.
 *
 *  XMLHttpRequest rather than fetch, because only XHR reports bytes sent. The
 *  API parses and projects the file inside the same request, so once the last
 *  byte is out there is nothing left to measure: the job moves to "processing"
 *  and the bar becomes indeterminate until the response arrives. */
export type UploadPhase = "sending" | "processing" | "done" | "failed";

export interface UploadJob {
  id: number;
  source: string;
  sourceName: string;
  filename: string;
  size: number;
  loaded: number;
  phase: UploadPhase;
  result?: UploadResult;
  error?: string;
}

// a finished upload stays in the tray this long; a failed one until dismissed
const KEEP_DONE_MS = 15_000;

let jobs: UploadJob[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function patch(id: number, change: Partial<UploadJob>) {
  jobs = jobs.map((job) => (job.id === id ? { ...job, ...change } : job));
  emit();
}

export function dismissUpload(id: number) {
  jobs = jobs.filter((job) => job.id !== id);
  emit();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function inFlight(): boolean {
  return jobs.some((job) => job.phase === "sending" || job.phase === "processing");
}

// closing or reloading the tab kills the request, so ask first
window.addEventListener("beforeunload", (event) => {
  if (inFlight()) event.preventDefault();
});

function errorText(xhr: XMLHttpRequest): string {
  try {
    const body = JSON.parse(xhr.responseText);
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    /* not JSON: fall through to the status line */
  }
  return xhr.statusText || `upload failed (${xhr.status || "network error"})`;
}

async function send(id: number, source: string, file: File, onDone: () => void) {
  const body = new FormData();
  body.append("file", file);
  const token = await accessToken();

  const xhr = new XMLHttpRequest();
  xhr.open("POST", `/api/sources/${source}/uploads`);
  // no Content-Type header: the browser must set the multipart boundary itself
  if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

  xhr.upload.onprogress = (event) => {
    if (event.lengthComputable) patch(id, { loaded: event.loaded });
  };
  xhr.upload.onload = () => patch(id, { loaded: file.size, phase: "processing" });
  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      patch(id, { phase: "done", result: JSON.parse(xhr.responseText) as UploadResult });
      onDone();
      window.setTimeout(() => dismissUpload(id), KEEP_DONE_MS);
    } else {
      if (xhr.status === 401) sessionRejected();
      patch(id, { phase: "failed", error: errorText(xhr) });
    }
  };
  xhr.onerror = () => patch(id, { phase: "failed", error: "the connection dropped before the upload finished" });
  xhr.send(body);
}

/** Every upload this tab has started and not yet cleared. */
export function useUploadJobs(): UploadJob[] {
  return useSyncExternalStore(subscribe, () => jobs);
}

/** Start an upload. Upload goes to a source, not to a dashboard: the file is
 *  archived once and projected into every dashboard that declares it. */
export function useStartUpload() {
  const queryClient = useQueryClient();
  return useCallback((source: string, sourceName: string, file: File) => {
    const id = nextId++;
    jobs = [...jobs, { id, source, sourceName, filename: file.name, size: file.size, loaded: 0, phase: "sending" }];
    emit();
    void send(id, source, file, () => invalidate(queryClient)).catch((error: unknown) =>
      patch(id, { phase: "failed", error: error instanceof Error ? error.message : String(error) }));
  }, [queryClient]);
}
