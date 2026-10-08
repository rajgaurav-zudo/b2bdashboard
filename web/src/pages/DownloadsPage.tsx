import { useDownload, useDownloads, useSheetSync } from "../api/client";
import type { GoogleSheetSync } from "../api/types";
import { when } from "../format";
import { Band, Section, Spinner } from "../ui/Primitives";

/** An Edvoy week (Saturday to Friday) in UTC -- the clock the API builds the
 *  summary on. `back` counts weeks before the one containing today.
 *  getUTCDay(): Sunday = 0, Saturday = 6. */
function edvoyWeek(back = 0, now = new Date()): string {
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const start = new Date(today - (((now.getUTCDay() + 1) % 7) + 7 * back) * 86_400_000);
  const end = new Date(start.getTime() + 6 * 86_400_000);
  const fmt = (d: Date) =>
    d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
  return `${fmt(start)} – ${fmt(end)}`;
}

/** "Current week summary 2026-06-10-14-32-05.xlsx": year-day-month-hour-minute-second
 *  on the reader's own clock, the order the team asked for. */
function summaryName(title: string, now = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${title} ${now.getFullYear()}-${p(now.getDate())}-${p(now.getMonth() + 1)}-` +
    `${p(now.getHours())}-${p(now.getMinutes())}-${p(now.getSeconds())}.xlsx`;
}

/** The summary's button and what became of its last click. */
function SummaryButton({ label, title, blocked }: { label: string; title: string; blocked: boolean }) {
  const download = useDownload();
  return (
    <div>
      <button
        type="button"
        className="btn"
        disabled={download.isPending || blocked}
        aria-busy={download.isPending}
        onClick={() => download.mutate({
          path: "/downloads/weekly-summary", fallbackName: `${title}.xlsx`,
          name: summaryName(title),
        })}
      >
        {download.isPending ? "Building…" : label}
      </button>
      {download.isError ? <Band tone="warn">{download.error.message}</Band> : null}
      {download.isSuccess ? <p className="sub" style={{ marginTop: 8 }}>Saved {download.data}.</p> : null}
    </div>
  );
}

/** The same summary, written over one Google Sheet: same link every time,
 *  contents replaced whole. */
function SyncButton({ sheet, blocked }: { sheet: GoogleSheetSync; blocked: boolean }) {
  const sync = useSheetSync();
  return (
    <div>
      <button
        type="button"
        className="btn"
        disabled={sync.isPending || blocked}
        aria-busy={sync.isPending}
        onClick={() => sync.mutate()}
      >
        {sync.isPending ? "Syncing…" : "Sync to Google Sheet"}
      </button>
      {sync.isError ? <Band tone="warn">{sync.error.message}</Band> : null}
      <p className="sub" style={{ marginTop: 8 }}>
        {sync.isSuccess ? "Synced. " : null}
        {sheet.url ? <a href={sheet.url} target="_blank" rel="noreferrer">Open the sheet</a> : null}
        {sheet.synced_at ? ` · Last synced ${when(sheet.synced_at)}` : " · Not synced yet"}
      </p>
    </div>
  );
}

/** Files built from the data, to take away.
 *
 *  A download reads the newest good upload of each source it needs, so it is
 *  only ever as fresh as the last export someone dropped on Uploads. The table
 *  says which files those are before anyone clicks. */
export function DownloadsPage() {
  const { data, isLoading } = useDownloads();
  const sources = data?.weekly_summary.sources ?? [];
  const missing = sources.filter((s) => !s.upload_id);
  const blocked = isLoading || missing.length > 0;
  const sheet = data?.weekly_summary.google_sheet;

  return (
    <>
      <header className="top">
        <div className="top-in">
          <h1>Downloads</h1>
          <p className="sub">
            Reports built from the latest uploads, as Excel workbooks. Each is generated when you
            ask for it, so it always reflects the newest export of every file it reads.
          </p>
        </div>
      </header>

      <div className="wrap">
        <Section
          title="Weekly summary"
          note={`This week: ${edvoyWeek()} to date, against last week. ` +
            `Its Last week sheet: ${edvoyWeek(1)}, against the week before.`}
        >
          <p className="sub" style={{ margin: "0 0 14px" }}>
            Five sheets. <b>YTD - Year to Date Summary</b>: deposits, PD and DAA for this actual
            intake year against last, for the full year and each quarter, across every business
            area, then each area by business region, and by application destination country and
            student nationality, each table with its charts. <b>Onboarding</b>: introducers by Became Customer
            Date, year to date and for the week, by business region and team, SRM and country, with the week's new
            introducers listed. <b>Activity</b>: introducer logs for the week against the one
            before, by type, per SRM, business region and business team. <b>Sales &amp; Retention</b>: active deposits by
            intake year, by onboarding year, country, application destination country, business region and team, SRM, AMT
            counsellor and institution, with DAA
            and partial deposits by intake month, and the introducers resurrected and missed
            out. <b>Last week</b>: last week whole against the week before: introducers
            onboarded, activity logs, and deposits by the day they were paid in full.
          </p>

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-start" }}>
            <SummaryButton label="This week's summary" title="Current week summary" blocked={blocked} />
            {sheet?.configured ? <SyncButton sheet={sheet} blocked={blocked} /> : null}
          </div>
          <p className="sub" style={{ marginTop: 8 }}>
            The first download after a new upload reads the full exports and takes a few seconds.
            {sheet?.configured
              ? " Syncing builds the same workbook and writes it over the Google Sheet, replacing everything in it."
              : null}
          </p>
          {missing.length > 0 ? (
            <Band tone="warn">
              Upload the {missing.map((s) => s.name).join(", ")} export first: the summary reads all three.
            </Band>
          ) : null}

          {isLoading ? <Spinner /> : null}
          {sources.length > 0 ? (
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr><th>Reads</th><th>File</th><th>Uploaded</th></tr>
                </thead>
                <tbody>
                  {sources.map((s) => (
                    <tr key={s.source}>
                      <td>{s.name}</td>
                      <td>{s.filename ?? "Nothing uploaded yet"}</td>
                      <td>{when(s.uploaded_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Section>
      </div>
    </>
  );
}
