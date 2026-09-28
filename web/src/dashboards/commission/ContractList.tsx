import { useMemo, useState } from "react";

import { n0 } from "../../format";
import { Empty, Section, Spinner } from "../../ui/Primitives";
import { useContracts, useCreateContract, useInstitutions, useMeta, type ContractSummary } from "./api";
import { ErrorText, Field, Select, StatusPill, day, label, useNav } from "./shared";

export function ContractList() {
  const { params, go } = useNav();
  const { data, isLoading, error } = useContracts();
  const [creating, setCreating] = useState(false);
  const q = params.get("q") ?? "";
  const region = params.get("region");
  const type = params.get("type");
  const status = params.get("status");
  const only = params.get("only");

  const rows = useMemo(() => (data ?? []).filter((c) =>
    (!q || `${c.party_name} ${c.code} ${c.source_tab ?? ""}`.toLowerCase().includes(q.toLowerCase()))
    && (!region || c.region === region) && (!type || c.party_type === type) && (!status || c.status === status)
    && (only !== "alerts" || c.alerts.length > 0) && (only !== "review" || c.needs_review > 0),
  ), [data, q, region, type, status, only]);

  const count = (f: (c: ContractSummary) => boolean) => (data ?? []).filter(f).length;
  const opts = (key: keyof ContractSummary) =>
    [...new Set((data ?? []).map((c) => c[key]).filter(Boolean) as string[])].sort();

  return (
    <>
      <div className="cm-top">
        <div className="grow">
          <h1 className="cm-h1">Commission contracts</h1>
          <div className="cm-sub">The terms we are paid on, per institution, with every amendment since.</div>
        </div>
        <button type="button" className="btn ghost" onClick={() => go({ view: "import" })}>Import workbook</button>
        <button type="button" className="btn" onClick={() => setCreating(true)}>+ New contract</button>
      </div>

      {creating ? <NewContract onClose={() => setCreating(false)} /> : null}

      {isLoading ? <Spinner /> : error ? <ErrorText error={error} /> : !data?.length ? (
        <Empty title="No contracts yet">
          <p>Add one with <b>New contract</b>, or import the contracts workbook.</p>
        </Empty>
      ) : (
        <>
          <div className="tiles" style={{ marginTop: 18, gridTemplateColumns: "repeat(4,1fr)" }}>
            <Tile n={data.length} l="Contracts" on={!only} onClick={() => go({ only: null })} />
            <Tile n={count((c) => c.status === "ACTIVE")} l="Active" on={status === "ACTIVE"}
                  onClick={() => go({ status: status === "ACTIVE" ? null : "ACTIVE" })} />
            <Tile n={count((c) => c.alerts.length > 0)} l="With alerts" on={only === "alerts"}
                  onClick={() => go({ only: only === "alerts" ? null : "alerts" })} />
            <Tile n={count((c) => c.needs_review > 0)} l="Need review" on={only === "review"}
                  onClick={() => go({ only: only === "review" ? null : "review" })} />
          </div>

          <Section title="Contracts" note={`${n0(rows.length)} of ${n0(data.length)} shown`}
                   aside={
                     <div className="cm-row">
                       <input className="cm-in" placeholder="Search party or code" value={q}
                              onChange={(e) => go({ q: e.target.value }, true)} />
                       <Select value={region} options={opts("region")} blank="All regions" onChange={(v) => go({ region: v })} />
                       <Select value={type} options={opts("party_type")} blank="All party types" onChange={(v) => go({ type: v })} />
                       <Select value={status} options={opts("status")} blank="All statuses" onChange={(v) => go({ status: v })} />
                     </div>
                   }>
            <div className="tbl-wrap">
              <table className="cm-wrap">
                <thead>
                  <tr>
                    <th className="txt">Party</th><th className="txt">Type</th><th className="txt">Region</th>
                    <th className="txt">Status</th><th className="txt">Validity</th><th>Version</th>
                    <th>Rules</th><th>Amendments</th><th className="txt">Alerts</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 500).map((c) => (
                    <tr key={c.id}>
                      <td className="txt">
                        <button type="button" className="cm-link" onClick={() => go({ c: c.id, tab: null })}>
                          <b>{c.party_name ?? "Unnamed"}</b>
                        </button>
                        <div className="dim" style={{ fontSize: 11.5 }}>{c.code}</div>
                      </td>
                      <td className="txt">{label(c.party_type)}</td>
                      <td className="txt">{label(c.region)}</td>
                      <td className="txt"><StatusPill status={c.status} /></td>
                      <td className="txt">{day(c.start_date)} – {c.is_rolling ? "rolling" : day(c.end_date)}</td>
                      <td className="num">{c.current_version ? `v${c.current_version}` : <span className="dim">none</span>}</td>
                      <td className="num">{c.rules}</td>
                      <td className="num">{c.amendments}{c.draft_amendments ? <span className="dim"> ({c.draft_amendments} draft)</span> : null}</td>
                      <td className="txt">
                        <div className="chips" style={{ margin: 0 }}>
                          {c.alerts.map((a, i) => (
                            <span key={i} className={`chip${a.kind === "draft" ? "" : " alert"}`}>{a.message}</span>
                          ))}
                          {c.needs_review ? <span className="cm-rev">{c.needs_review} to review</span> : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {rows.length > 500 ? <p className="status">Showing the first 500; narrow the search to see the rest.</p> : null}
          </Section>
        </>
      )}
    </>
  );
}

function Tile({ n, l, on, onClick }: { n: number; l: string; on: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`tile${on ? " inv" : ""}`} onClick={onClick} style={{ textAlign: "left", font: "inherit" }}>
      <div className="metric">{n0(n)}</div>
      <div className="metric-l">{l}</div>
    </button>
  );
}

function NewContract({ onClose }: { onClose: () => void }) {
  const { go } = useNav();
  const meta = useMeta();
  const inst = useInstitutions();
  const create = useCreateContract();
  const [f, setF] = useState<{ party_id: number | null; party_name: string; party_type: string | null;
                               region: string | null; start_date: string }>({
    party_id: null, party_name: "", party_type: "UNIVERSITY", region: null, start_date: "",
  });
  const enums = meta.data?.enums ?? {};

  const submit = () => create.mutate(
    { party_id: f.party_id, party_name: f.party_name || null, party_type: f.party_type, region: f.region,
      start_date: f.start_date || null } as never,
    { onSuccess: (c) => go({ c: c.id, tab: "base" }) },
  );

  return (
    <div className="cm-card" style={{ marginTop: 18 }}>
      <h3>New contract</h3>
      <div className="cm-grid">
        <Field title="Existing institution">
          <select value={f.party_id ?? ""} onChange={(e) => setF({ ...f, party_id: Number(e.target.value) || null })}>
            <option value="">New party…</option>
            {(inst.data ?? []).map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
          </select>
        </Field>
        {f.party_id ? null : (
          <Field title="New party name" required>
            <input value={f.party_name} onChange={(e) => setF({ ...f, party_name: e.target.value })} />
          </Field>
        )}
        <Field title="Party type" required>
          <Select value={f.party_type} options={enums.party_types ?? []} onChange={(v) => setF({ ...f, party_type: v })} />
        </Field>
        <Field title="Region">
          <Select value={f.region} options={enums.regions ?? []} onChange={(v) => setF({ ...f, region: v })} />
        </Field>
        <Field title="Start date">
          <input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />
        </Field>
      </div>
      <ErrorText error={create.error} />
      <div className="cm-foot">
        <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
        <button type="button" className="btn" disabled={create.isPending || (!f.party_id && !f.party_name.trim())}
                onClick={submit}>Create draft</button>
      </div>
    </div>
  );
}
