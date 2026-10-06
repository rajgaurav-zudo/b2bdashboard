import { useState } from "react";

import { when } from "../../format";
import { Band, Spinner } from "../../ui/Primitives";
import { Amendments } from "./Amendments";
import { Audit } from "./Audit";
import { BaseTerms } from "./BaseTerms";
import { Documents } from "./Documents";
import { Effective } from "./Effective";
import { Timeline } from "./Timeline";
import {
  useContract, useCreateContract, useDeleteContract, useMeta, useSetStatus, type Contract, type ContractDetail,
} from "./api";
import { ErrorText, Field, Select, StatusPill, day, label, useNav } from "./shared";

const TABS = [
  ["timeline", "Timeline"], ["effective", "Effective terms"], ["base", "Base terms"],
  ["amendments", "Amendments"], ["documents", "Documents"], ["audit", "Audit log"],
] as const;
type Tab = (typeof TABS)[number][0];

export function ContractPage({ id }: { id: number }) {
  const { params, go } = useNav();
  const { data, isLoading, error } = useContract(id);
  const meta = useMeta();
  const tab = (TABS.find(([k]) => k === params.get("tab"))?.[0] ?? "timeline") as Tab;

  if (isLoading) return <Spinner />;
  if (error || !data) return (
    <>
      <button type="button" className="cm-crumb" onClick={() => go({ c: null, tab: null })}>← Contracts</button>
      <ErrorText error={error ?? "Contract not found"} />
    </>
  );
  const c = data.contract;
  const today = meta.data?.today ?? new Date().toISOString().slice(0, 10);
  const days = c.end_date && !c.is_rolling
    ? Math.round((Date.parse(c.end_date) - Date.parse(today)) / 86_400_000) : null;
  const drafts = data.amendments.filter((a) => a.status === "DRAFT").length;

  return (
    <>
      <button type="button" className="cm-crumb" onClick={() => go({ c: null, tab: null, a: null, step: null, intake: null })}>
        ← Contracts
      </button>
      <div className="cm-top">
        <div className="grow">
          <h1 className="cm-h1">{c.party_name}</h1>
          <div className="chips">
            <StatusPill status={c.status} />
            <span className="chip">{c.code}</span>
            <span className="chip">{label(c.party_type)}</span>
            {c.region ? <span className="chip">{label(c.region)}</span> : null}
            <span className="chip">{day(c.start_date)} – {c.is_rolling ? "rolling" : day(c.end_date)}</span>
            <span className="chip">{c.current_version ? <>Published <b>v{c.current_version}</b></> : "Never published"}</span>
            {c.currency ? <span className="chip">{c.currency}</span> : null}
            {c.source_tab ? <span className="chip">Imported from {c.source_tab} {c.source_rows}</span> : null}
          </div>
        </div>
        <HeaderActions detail={data} />
      </div>

      <div style={{ display: "grid", gap: 8, marginTop: 14 }}>
        {c.status === "INACTIVE" ? (
          <Band tone="warn">Inactive from {day(c.status_effective_date)}{c.status_reason ? `: ${c.status_reason}` : ""}.</Band>
        ) : null}
        {days !== null && days >= 0 && days <= 90 && c.status === "ACTIVE" ? (
          <Band tone="warn">This contract ends in <b>{days} days</b> ({day(c.end_date)}). Renew it to keep terms for later intakes.</Band>
        ) : null}
        {days !== null && days < 0 ? <Band tone="warn">This contract ended on {day(c.end_date)}.</Band> : null}
        {c.has_unpublished ? (
          <Band tone="info">
            Base terms have unpublished edits. Nothing downstream sees them until you{" "}
            <button type="button" className="cm-link" onClick={() => go({ tab: "base" })}>publish a new version</button>.
          </Band>
        ) : null}
        {drafts ? (
          <Band tone="info">
            {drafts} draft amendment{drafts > 1 ? "s" : ""} not yet applied.{" "}
            <button type="button" className="cm-link" onClick={() => go({ tab: "amendments" })}>Review</button>
          </Band>
        ) : null}
        {data.recalc_batches[0] ? (
          <Band tone="info">
            Recalculation raised {when(data.recalc_batches[0].created_at)} from{" "}
            {data.recalc_batches[0].from_intake ?? "the start"}: {data.recalc_batches[0].reason}
          </Band>
        ) : null}
      </div>

      <div className="tabs" role="tablist">
        {TABS.map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k}
                  onClick={() => go({ tab: k, a: null, step: null })}>
            {l}
            {k === "amendments" && data.amendments.length ? <span className="dim"> {data.amendments.length}</span> : null}
            {k === "base" && !data.checklist.ready ? <span className="red"> •</span> : null}
          </button>
        ))}
      </div>

      {tab === "timeline" ? <Timeline id={id} /> : null}
      {tab === "effective" ? <Effective id={id} contract={c} /> : null}
      {tab === "base" ? <BaseTerms key={`${c.id}-${c.current_version}`} detail={data} /> : null}
      {tab === "amendments" ? <Amendments detail={data} /> : null}
      {tab === "documents" ? <Documents detail={data} /> : null}
      {tab === "audit" ? <Audit id={id} /> : null}
    </>
  );
}

function HeaderActions({ detail }: { detail: ContractDetail }) {
  const c = detail.contract;
  const { go } = useNav();
  const [status, setStatus] = useState(false);
  const renew = useCreateContract();
  const del = useDeleteContract(c.id);

  const doRenew = () => {
    const start = c.end_date ? nextDay(c.end_date) : null;
    const end = start ? addYears(start, 1, -1) : null;
    const copy: Partial<Contract> = {
      party_id: c.party_id, party_type: c.party_type, covered_institution_ids: c.covered_institution_ids,
      region: c.region, start_date: start, end_date: end, is_rolling: c.is_rolling, currency: c.currency,
      vat_treatment: c.vat_treatment, vat_rate: c.vat_rate, fee_basis: c.fee_basis,
      territory_type: c.territory_type, intake_scope: { mode: "ENTIRE_YEAR" }, academic_years: null, terms: c.terms,
    };
    renew.mutate(copy, { onSuccess: (n) => go({ c: n.id, tab: "base" }) });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
      <div className="cm-row">
        {c.current_version === 0 ? (
          <button type="button" className="btn danger sm" disabled={del.isPending}
                  onClick={() => window.confirm(`Delete the draft contract ${c.code}? This cannot be undone.`)
                    && del.mutate(undefined, { onSuccess: () => go({ c: null, tab: null }) })}>
            Delete draft
          </button>
        ) : null}
        <button type="button" className="btn ghost sm" disabled={!c.current_version}
                onClick={() => setStatus((s) => !s)}>Change status</button>
        <button type="button" className="btn ghost sm" disabled={renew.isPending} onClick={doRenew}
                title="Start a new draft contract from these terms, beginning the day after this one ends">
          Renew contract
        </button>
        <button type="button" className="btn sm" disabled={!c.current_version}
                title={c.current_version ? undefined : "Publish the base terms first"}
                onClick={() => go({ tab: "amendments", a: "new", step: 1 })}>
          + Add amendment
        </button>
      </div>
      <ErrorText error={renew.error ?? del.error} />
      {status ? <StatusForm contract={c} onDone={() => setStatus(false)} /> : null}
    </div>
  );
}

function StatusForm({ contract, onDone }: { contract: Contract; onDone: () => void }) {
  const meta = useMeta();
  const set = useSetStatus(contract.id);
  const [s, setS] = useState(contract.status);
  const [reason, setReason] = useState(contract.status_reason ?? "");
  const [date, setDate] = useState(contract.status_effective_date ?? "");
  return (
    <div className="cm-card" style={{ width: 360 }}>
      <div className="cm-grid" style={{ gridTemplateColumns: "1fr" }}>
        <Field title="Status">
          <Select value={s} options={(meta.data?.enums.statuses ?? []).filter((x) => x !== "DRAFT")} onChange={(v) => setS(v ?? s)} />
        </Field>
        <Field title="Reason" required={s === "INACTIVE"}>
          <input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <Field title="Effective from" required={s === "INACTIVE"} hint="Status is live: it needs no new version.">
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
      </div>
      <ErrorText error={set.error} />
      <div className="cm-foot">
        <button type="button" className="btn ghost sm" onClick={onDone}>Cancel</button>
        <button type="button" className="btn sm" disabled={set.isPending}
                onClick={() => set.mutate({ status: s, reason: reason || undefined, effective_date: date || undefined },
                                          { onSuccess: onDone })}>
          Save status
        </button>
      </div>
    </div>
  );
}

const iso = (d: Date) => d.toISOString().slice(0, 10);
function nextDay(v: string) {
  const d = new Date(`${v.slice(0, 10)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return iso(d);
}
function addYears(v: string, years: number, days: number) {
  const d = new Date(`${v}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() + years);
  d.setUTCDate(d.getUTCDate() + days);
  return iso(d);
}
