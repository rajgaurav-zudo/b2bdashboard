import { Fragment, useRef, useState } from "react";

import { n0, when } from "../../format";
import { Band, Section } from "../../ui/Primitives";
import { useImportCommit, useImportPreview, type CommitResult, type ImportBatch } from "./api";
import { ErrorText, label, useNav } from "./shared";

/** Upload the contracts workbook, see what each tab would become, untick
 *  anything that should not be written, then commit. Nothing is saved to
 *  contracts until commit. */
export function ImportPage() {
  const { go } = useNav();
  const preview = useImportPreview();
  const commit = useImportCommit();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [skip, setSkip] = useState<Set<number>>(new Set());
  const [result, setResult] = useState<CommitResult | null>(null);
  const batch = preview.data;

  const pick = (f: File | undefined) => {
    if (!f) return;
    setResult(null);
    preview.mutate(f, {
      onSuccess: (b) => setSkip(new Set(b.contracts.filter((c) => c.action === "skip").map((c) => c.index))),
    });
  };

  return (
    <>
      <button type="button" className="cm-crumb" onClick={() => go({ view: null })}>← Contracts</button>
      <div className="cm-top">
        <div className="grow">
          <h1 className="cm-h1">Import contracts workbook</h1>
          <div className="cm-sub">Each regional tab row block becomes a draft contract. Imports never publish: review each contract, then publish it.</div>
        </div>
      </div>

      <div className={`drop${over ? " over" : ""}${preview.isPending ? " busy" : ""}`} style={{ marginTop: 18 }}
           role="button" tabIndex={0}
           onClick={() => input.current?.click()}
           onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
           onDragOver={(e) => { e.preventDefault(); setOver(true); }}
           onDragLeave={() => setOver(false)}
           onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]); }}>
        <b>{preview.isPending ? "Reading workbook…" : batch ? batch.filename : "Drop the .xlsx here, or click to choose"}</b>
        <span>{batch ? `Read ${when(batch.created_at)}. Drop another file to start again.` : "Contracts summary workbook, one tab per region"}</span>
        <input ref={input} type="file" accept=".xlsx" hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      <ErrorText error={preview.error} />

      {result ? <Committed result={result} batch={batch} /> : batch ? (
        <Preview batch={batch} skip={skip} setSkip={setSkip} busy={commit.isPending}
                 onCommit={() => commit.mutate({ id: batch.id, skip: [...skip] }, { onSuccess: setResult })} />
      ) : null}
      <ErrorText error={commit.error} />
    </>
  );
}

function Preview({ batch, skip, setSkip, busy, onCommit }: {
  batch: ImportBatch; skip: Set<number>; setSkip: (s: Set<number>) => void; busy: boolean; onCommit: () => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const t = batch.totals;
  const toggle = (i: number) => {
    const next = new Set(skip);
    if (next.has(i)) next.delete(i); else next.add(i);
    setSkip(next);
  };
  const writing = batch.contracts.filter((c) => !skip.has(c.index)).length;

  return (
    <>
      <div className="tiles" style={{ marginTop: 18, gridTemplateColumns: "repeat(5,1fr)" }}>
        {[[t.contracts, "Contracts found"], [t.create, "New"], [t.update, "Update a draft"], [t.skip, "Skipped"], [t.review, "Items to review"]]
          .map(([n, l]) => <div key={l} className="tile"><div className="metric">{n0(Number(n))}</div><div className="metric-l">{l}</div></div>)}
      </div>

      <div style={{ display: "grid", gap: 8, marginTop: 14 }}>
        {batch.previously_committed ? <Band tone="warn">This exact file was imported before. Committing again only updates contracts that are still unpublished drafts.</Band> : null}
        {batch.unknown_tabs.length ? <Band tone="info">Tabs not read: {batch.unknown_tabs.join(", ")}.</Band> : null}
        {batch.unmatched_invoicing.length ? (
          <Band tone="warn">
            {batch.unmatched_invoicing.length} invoicing-sheet name{batch.unmatched_invoicing.length === 1 ? "" : "s"} matched no contract:{" "}
            {batch.unmatched_invoicing.slice(0, 12).map((u) => `${u.name} (${u.cell})`).join(", ")}
            {batch.unmatched_invoicing.length > 12 ? ` and ${batch.unmatched_invoicing.length - 12} more` : ""}.
          </Band>
        ) : null}
      </div>

      <Section title="What will be written" note={`${writing} of ${batch.contracts.length} will be written. Untick a row to leave it out.`}
               aside={<button type="button" className="btn" disabled={busy || !writing || batch.committed} onClick={onCommit}>
                 {busy ? "Importing…" : `Import ${writing} contract${writing === 1 ? "" : "s"}`}</button>}>
        <div className="tbl-wrap">
          <table className="cm-wrap">
            <thead><tr>
              <th /><th className="txt">Party</th><th className="txt">Tab</th><th className="txt">Action</th>
              <th className="txt">Institution</th><th>Rules</th><th>Bonuses</th><th>Territory</th><th>Exclusions</th>
              <th>Amendments</th><th className="txt">Review</th>
            </tr></thead>
            <tbody>
              {batch.contracts.map((c) => {
                const off = skip.has(c.index);
                return (
                  <Fragment key={c.index}>
                    <tr className={off ? "cm-skip" : undefined}>
                      <td className="txt">
                        <input type="checkbox" checked={!off} disabled={c.action === "skip"} onChange={() => toggle(c.index)}
                               aria-label={`Import ${c.party_name}`} />
                      </td>
                      <td className="txt"><b>{c.party_name}</b><div className="dim" style={{ fontSize: 11.5 }}>{label(c.party_type)} · {label(c.region)}</div></td>
                      <td className="txt">{c.tab} <span className="dim">{c.rows}</span></td>
                      <td className="txt">{label(c.action)}{c.why ? <div className="dim" style={{ fontSize: 11.5 }}>{c.why}</div> : null}</td>
                      <td className="txt">
                        {c.institution.match === "exact" ? <span>{c.institution.name}</span>
                          : c.institution.match === "ambiguous"
                            ? <span className="amber" title={(c.institution.candidates ?? []).map((x) => x.name).join(", ")}>
                                Ambiguous: {(c.institution.candidates ?? []).length} matches</span>
                            : <span className="dim">New institution</span>}
                      </td>
                      <td className="num">{c.counts.rules}</td>
                      <td className="num">{c.counts.bonuses}</td>
                      <td className="num">{c.counts.territory_rules}</td>
                      <td className="num">{c.counts.exclusions}</td>
                      <td className="num">{c.counts.amendments}</td>
                      <td className="txt">
                        {c.review.length ? (
                          <button type="button" className="cm-link" onClick={() => setOpen(open === c.index ? null : c.index)}>
                            <span className="cm-rev">{c.review.length} to review</span>
                          </button>
                        ) : <span className="dim">--</span>}
                      </td>
                    </tr>
                    {open === c.index ? (
                      <tr>
                        <td />
                        <td className="txt" colSpan={10}>
                          <ul className="cm-checks">
                            {c.review.map((r, i) => (
                              <li key={i} className="wn"><span className="mk">!</span>
                                <span>{r.message}{r.cell || r.text ? <span className="why">{[r.cell, r.text].filter(Boolean).join(": ")}</span> : null}</span>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>
    </>
  );
}

function Committed({ result, batch }: { result: CommitResult; batch?: ImportBatch }) {
  const { go } = useNav();
  return (
    <Section title="Imported">
      <div className="tiles" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        {[[result.created, "Created"], [result.updated, "Updated"], [result.skipped, "Skipped"], [result.failed.length, "Failed"]]
          .map(([n, l]) => <div key={l} className="tile"><div className="metric">{n0(Number(n))}</div><div className="metric-l">{l}</div></div>)}
      </div>
      {result.failed.length ? (
        <ul className="cm-checks" style={{ marginTop: 14 }}>
          {result.failed.map((f) => <li key={f.index} className="no"><span className="mk">✕</span><span>{f.party_name}<span className="why">{f.message}</span></span></li>)}
        </ul>
      ) : null}
      <p className="status ok">
        {batch ? `${batch.filename}: ` : ""}{result.contract_ids.length} contract{result.contract_ids.length === 1 ? "" : "s"} saved as drafts.
        Nothing is published until each one is reviewed.
      </p>
      <div className="cm-foot" style={{ justifyContent: "flex-start" }}>
        <button type="button" className="btn" onClick={() => go({ view: null, only: "review" })}>Contracts needing review</button>
        <button type="button" className="btn ghost" onClick={() => go({ view: null, only: null })}>All contracts</button>
      </div>
    </Section>
  );
}
