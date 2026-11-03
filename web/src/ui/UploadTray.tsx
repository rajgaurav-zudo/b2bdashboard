import { useLocation } from "react-router-dom";

import { dismissUpload, useUploadJobs, type UploadJob } from "../uploads";

function size(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** One upload: a bar while it runs, then what each dashboard made of the file. */
export function UploadProgress({ job, showSource = false }: { job: UploadJob; showSource?: boolean }) {
  const pct = job.size ? Math.min(100, Math.round((job.loaded / job.size) * 100)) : 0;
  const running = job.phase === "sending" || job.phase === "processing";

  let label: string;
  if (job.phase === "sending") label = `Uploading ${pct}% · ${size(job.loaded)} of ${size(job.size)}`;
  else if (job.phase === "processing") label = "Uploaded · parsing and loading into the dashboards…";
  else if (job.phase === "done") label = job.result?.changed === false ? "Done · same file as before" : "Done";
  else label = job.error ?? "Failed";

  return (
    <div className={`upl ${job.phase}`}>
      <div className="upl-head">
        <span className="upl-name" title={job.filename}>
          {showSource ? <b>{job.sourceName} · </b> : null}{job.filename}
        </span>
        {running ? null : (
          <button type="button" className="upl-x" onClick={() => dismissUpload(job.id)}
                  aria-label={`Dismiss ${job.filename}`} title="Dismiss">×</button>
        )}
      </div>
      <div className={`upl-bar${job.phase === "processing" ? " indet" : ""}`}
           role="progressbar" aria-label={`Upload of ${job.filename}`}
           aria-valuemin={0} aria-valuemax={100}
           aria-valuenow={job.phase === "processing" ? undefined : job.phase === "sending" ? pct : 100}>
        <i style={{ width: job.phase === "sending" ? `${pct}%` : "100%" }} />
      </div>
      <p className="upl-lbl">{label}</p>
      {job.result?.projections.map((p) => (
        <p key={`${p.dashboard}.${p.dataset}`}
           className={`status ${p.status === "failed" ? "err" : p.status === "duplicate" ? "busy" : "ok"}`}>
          {p.dashboard}: {p.summary ?? p.error ?? p.status}
        </p>
      ))}
    </div>
  );
}

/** Uploads stay on screen wherever you go until they finish. The Uploads page
 *  shows the same jobs under each drop zone, so the tray steps aside there. */
export function UploadTray() {
  const jobs = useUploadJobs();
  const { pathname } = useLocation();
  if (!jobs.length || pathname === "/uploads") return null;
  return (
    <aside className="upl-tray" aria-live="polite" aria-label="Uploads">
      {jobs.map((job) => <UploadProgress key={job.id} job={job} showSource />)}
    </aside>
  );
}
