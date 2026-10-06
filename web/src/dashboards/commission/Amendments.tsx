import { useState } from "react";

import { when } from "../../format";
import { Band, Empty, Section, Spinner } from "../../ui/Primitives";
import {
  CommissionApiError, useAmendmentPreview, useCreateAmendment, useDeleteAmendment, useMeta, usePublishAmendment,
  useUpdateAmendment, type Amendment, type AmendmentChanges, type AmendmentPreview, type ContractDetail, type Meta,
  type Resolved, type Rule,
} from "./api";
import { rateText } from "./Effective";
import { BonusEditor, Exclusions, RuleEditor, Territories, blankBonus, blankRule } from "./BaseTerms";
import { ErrorText, Field, Review, Select, day, intakeLabel, intakeRange, label, useNav } from "./shared";

const STEPS = ["Document", "Scope", "Changes", "Review"] as const;

const TYPE_HELP: Record<string, string> = {
  RATE_CHANGE: "Replaces the rates of chosen rules for the scoped intakes.",
  RULE_ADDITION: "Adds new rules alongside the base ones.",
  BONUS_INCENTIVE: "Adds a bonus or incentive.",
  SCOPE_CHANGE: "Changes territories, exclusions or campuses.",
  INTAKE_NOTE: "Records a note or target for the scoped intakes; rates are unchanged.",
  EXTENSION: "Moves the contract end date later.",
  SUSPENSION: "No commission is due for the scoped intakes.",
};

const scopeText = (a: Pick<Amendment, "scope_mode" | "from_intake" | "until_intake" | "window_start" | "window_end" | "type" | "changes">) =>
  a.type === "EXTENSION" ? `to ${day(a.changes?.new_end_date)}`
    : a.scope_mode === "DATE_WINDOW" ? `${day(a.window_start)} – ${day(a.window_end)}`
    : `${a.from_intake ? intakeLabel(a.from_intake) : "--"}${a.until_intake ? ` – ${intakeLabel(a.until_intake)}` : " onwards"}`
      + (a.scope_mode === "BOTH" ? ` · ${day(a.window_start)} – ${day(a.window_end)}` : "");

export function Amendments({ detail }: { detail: ContractDetail }) {
  const { params } = useNav();
  const a = params.get("a");
  if (a) {
    const existing = a === "new" ? null : detail.amendments.find((x) => String(x.id) === a) ?? null;
    return <Wizard key={a} detail={detail} existing={existing} />;
  }
  return <AmendmentList detail={detail} />;
}

function AmendmentList({ detail }: { detail: ContractDetail }) {
  const { go } = useNav();
  const del = useDeleteAmendment();
  const list = [...detail.amendments].sort((x, y) => y.number - x.number);
  const published = detail.contract.current_version > 0;
  return (
    <Section title="Amendments" note="Each applies on top of the base terms for its scope. Published amendments cannot be edited; supersede them instead."
             aside={<button type="button" className="btn sm" disabled={!published}
                            title={published ? undefined : "Publish the base terms first"}
                            onClick={() => go({ a: "new", step: 1 })}>+ Add amendment</button>}>
      {!list.length ? <Empty title="No amendments"><p>Add one when a variation letter, email or addendum changes the terms.</p></Empty> : (
        <div className="tbl-wrap">
          <table className="cm-wrap">
            <thead><tr>
              <th>#</th><th className="txt">Type</th><th className="txt">Status</th><th className="txt">Scope</th>
              <th className="txt">Document</th><th className="txt">Summary</th><th />
            </tr></thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id}>
                  <td className="num">{a.number}</td>
                  <td className="txt">
                    <button type="button" className="cm-link" onClick={() => go({ a: a.id, step: a.status === "DRAFT" ? 1 : 4 })}>{label(a.type)}</button>
                  </td>
                  <td className="txt">
                    <span className={`pill ${a.status === "PUBLISHED" ? "live" : ""}`} style={{ marginLeft: 0 }}>{label(a.status)}</span>{" "}
                    <Review on={a.needs_review} />
                  </td>
                  <td className="txt">{scopeText(a)}</td>
                  <td className="txt">{a.reference ?? "--"}<div className="dim" style={{ fontSize: 11.5 }}>{day(a.received_on)}</div></td>
                  <td className="txt">{a.summary ?? <span className="dim">--</span>}</td>
                  <td className="act">
                    {a.status === "DRAFT" ? (
                      <button type="button" disabled={del.isPending}
                              onClick={() => window.confirm(`Delete draft amendment #${a.number}?`) && del.mutate(a.id)}>Delete</button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ErrorText error={del.error} />
    </Section>
  );
}

type Draft = Partial<Amendment> & { changes: AmendmentChanges };

function Wizard({ detail, existing }: { detail: ContractDetail; existing: Amendment | null }) {
  const { params, go } = useNav();
  const meta = useMeta();
  const c = detail.contract;
  const [d, setD] = useState<Draft>(() => existing ? structuredClone(existing)
    : { type: undefined, scope_mode: "INTAKE", applicability_basis: "INTAKE_START", changes: {}, target_rule_ids: [] });
  const [dirty, setDirty] = useState(false);
  const create = useCreateAmendment(c.id);
  const update = useUpdateAmendment();
  const locked = existing?.status === "PUBLISHED";
  const step = locked ? 4 : Math.min(4, Math.max(1, Number(params.get("step")) || 1));
  if (!meta.data) return <Spinner />;

  const set = (p: Partial<Draft>) => { setD({ ...d, ...p }); setDirty(true); };
  const setCh = (p: Partial<AmendmentChanges>) => set({ changes: { ...d.changes, ...p } });

  const body = (): Partial<Amendment> => ({
    type: d.type, reference: d.reference ?? null, received_on: d.received_on ?? null, document_file: d.document_file ?? null,
    summary: d.summary ?? null, scope_mode: d.scope_mode ?? null, from_intake: d.from_intake ?? null,
    until_intake: d.until_intake ?? null, window_start: d.window_start ?? null, window_end: d.window_end ?? null,
    applicability_basis: d.applicability_basis ?? null, target_rule_ids: d.target_rule_ids ?? [],
    supersedes_amendment_id: d.supersedes_amendment_id ?? null, needs_review: d.needs_review ?? false, changes: d.changes,
  });
  /** Save, then move. The first save creates the draft and puts its id in the URL. */
  const saveAndGo = (next: number) => {
    if (d.id && !dirty) return go({ step: next });
    if (d.id) {
      update.mutate({ id: d.id, data: body() }, { onSuccess: (row) => { setD(structuredClone(row) as Draft); setDirty(false); go({ step: next }); } });
    } else {
      create.mutate(body(), { onSuccess: (row) => go({ a: row.id, step: next }, true) });
    }
  };
  const busy = create.isPending || update.isPending;

  return (
    <>
      <button type="button" className="cm-crumb" style={{ marginTop: 16 }} onClick={() => go({ a: null, step: null })}>← All amendments</button>
      <h2 className="sec-h" style={{ marginTop: 6 }}>
        {existing ? `Amendment #${existing.number}` : "New amendment"}{d.type ? ` · ${label(d.type)}` : ""}
        {locked ? <span className="pill live">Published</span> : null}
      </h2>
      {!locked ? (
        <div className="cm-wiz">
          {STEPS.map((s, i) => (
            <button key={s} type="button" aria-current={step === i + 1 ? "step" : undefined}
                    disabled={!d.id && i + 1 > step} onClick={() => saveAndGo(i + 1)}>
              <b>{i + 1}</b>{s}
            </button>
          ))}
        </div>
      ) : null}

      {step === 1 ? <StepDocument meta={meta.data} d={d} set={set} /> : null}
      {step === 2 ? <StepScope meta={meta.data} d={d} set={set} detail={detail} /> : null}
      {step === 3 ? <StepChanges meta={meta.data} d={d} set={set} setCh={setCh} detail={detail} /> : null}
      {step === 4 && d.id ? <StepReview id={d.id} locked={locked} dirty={dirty} /> : null}

      <ErrorText error={create.error ?? update.error} />
      {!locked ? (
        <div className="cm-foot">
          {step > 1 ? <button type="button" className="btn ghost" disabled={busy} onClick={() => saveAndGo(step - 1)}>Back</button> : null}
          {step < 4 ? (
            <button type="button" className="btn" disabled={busy || !d.type} onClick={() => saveAndGo(step + 1)}>
              {busy ? "Saving…" : step === 3 ? "Save and review" : "Save and continue"}
            </button>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

type StepProps = { meta: Meta; d: Draft; set: (p: Partial<Draft>) => void };

function StepDocument({ meta, d, set }: StepProps) {
  return (
    <div className="cm-card">
      <h3><span className="n">1</span>What changed, and where it is written</h3>
      <div className="cm-grid">
        <Field title="Type" required bad={!d.type} hint={d.type ? TYPE_HELP[d.type] : undefined} wide>
          <Select value={d.type} options={meta.enums.amendment_types ?? []} onChange={(v) => set({ type: v ?? undefined })} />
        </Field>
        <Field title="Reference" required bad={!d.reference} hint="Letter or email subject, e.g. Variation letter 3">
          <input value={d.reference ?? ""} onChange={(e) => set({ reference: e.target.value || null })} />
        </Field>
        <Field title="Received on" required bad={!d.received_on}>
          <input type="date" value={d.received_on ?? ""} onChange={(e) => set({ received_on: e.target.value || null })} />
        </Field>
        <Field title="Document" required bad={!d.document_file} hint="File name or link where the signed copy is kept">
          <input value={d.document_file ?? ""} onChange={(e) => set({ document_file: e.target.value || null })} />
        </Field>
        <Field title="Summary" wide>
          <input value={d.summary ?? ""} placeholder="One line, shown on the timeline" onChange={(e) => set({ summary: e.target.value || null })} />
        </Field>
      </div>
      {d.needs_review ? (
        <p className="status amber">
          Flagged for review on import{d.source_cell ? ` (${d.source_cell})` : ""}.{" "}
          <button type="button" className="cm-link" onClick={() => set({ needs_review: false })}>Mark reviewed</button>
        </p>
      ) : null}
    </div>
  );
}

function StepScope({ meta, d, set, detail }: StepProps & { detail: ContractDetail }) {
  const c = detail.contract;
  const intakes = [...new Set([...intakeRange((c.start_date ?? meta.today).slice(0, 7), 48),
    ...(d.from_intake ? [d.from_intake] : []), ...(d.until_intake ? [d.until_intake] : [])])].sort();
  const mode = d.scope_mode ?? "INTAKE";
  const others = detail.amendments.filter((a) => a.status === "PUBLISHED" && a.id !== d.id);

  if (d.type === "EXTENSION") {
    return (
      <div className="cm-card">
        <h3><span className="n">2</span>Scope</h3>
        <p className="status">An extension's scope is its new end date, set on the next step.</p>
      </div>
    );
  }
  const outside: string[] = [];
  const start = c.start_date?.slice(0, 7);
  const end = c.is_rolling ? null : c.end_date?.slice(0, 7);
  for (const [l, v] of [["From intake", d.from_intake], ["Until intake", d.until_intake]] as const) {
    if (v && ((start && v < start) || (end && v > end))) outside.push(`${l} ${intakeLabel(v)}`);
  }
  for (const [l, v] of [["Window start", d.window_start], ["Window end", d.window_end]] as const) {
    if (v && ((c.start_date && v < c.start_date) || (!c.is_rolling && c.end_date && v > c.end_date))) outside.push(`${l} ${day(v)}`);
  }

  return (
    <div className="cm-card">
      <h3><span className="n">2</span>Which students it applies to</h3>
      <div className="cm-grid">
        <Field title="Scope by" required>
          <Select value={mode} blank={null} options={meta.enums.scope_modes ?? []}
                  labels={(v) => ({ INTAKE: "Intakes", DATE_WINDOW: "A date window", BOTH: "Intakes and a date window" }[v] ?? label(v))}
                  onChange={(v) => set({ scope_mode: v ?? "INTAKE" })} />
        </Field>
        {mode !== "DATE_WINDOW" ? (
          <>
            <Field title="From intake" required bad={!d.from_intake}>
              <Select value={d.from_intake} options={intakes} labels={intakeLabel} onChange={(v) => set({ from_intake: v })} />
            </Field>
            <Field title="Until intake" hint="Blank means every later intake">
              <Select value={d.until_intake} options={intakes} labels={intakeLabel} blank="Open-ended" onChange={(v) => set({ until_intake: v })} />
            </Field>
          </>
        ) : null}
        {mode !== "INTAKE" ? (
          <>
            <Field title="Window start" required bad={!d.window_start}>
              <input type="date" value={d.window_start ?? ""} onChange={(e) => set({ window_start: e.target.value || null })} />
            </Field>
            <Field title="Window end" required bad={!d.window_end}>
              <input type="date" value={d.window_end ?? ""} onChange={(e) => set({ window_end: e.target.value || null })} />
            </Field>
            <Field title="Date tested against the window" hint="Intake start needs no student dates; the others are checked per student">
              <Select value={d.applicability_basis} blank={null} options={meta.enums.applicability ?? []}
                      onChange={(v) => set({ applicability_basis: v })} />
            </Field>
          </>
        ) : null}
        {others.length ? (
          <Field title="Supersedes" hint="Set this when it replaces an earlier amendment for the same rules">
            <select value={d.supersedes_amendment_id ?? ""} onChange={(e) => set({ supersedes_amendment_id: Number(e.target.value) || null })}>
              <option value="">Nothing</option>
              {others.map((a) => <option key={a.id} value={a.id}>#{a.number} {label(a.type)} · {scopeText(a)}</option>)}
            </select>
          </Field>
        ) : null}
      </div>
      {outside.length ? (
        <p className="status err">
          Outside the contract's validity ({day(c.start_date)} – {c.is_rolling ? "rolling" : day(c.end_date)}): {outside.join(", ")}.
          Renew the contract or record an extension first.
        </p>
      ) : null}
    </div>
  );
}

function StepChanges({ meta, d, set, setCh, detail }: StepProps & { setCh: (p: Partial<AmendmentChanges>) => void; detail: ContractDetail }) {
  const c = detail.contract;
  const base = c.terms ?? {};
  const baseRules = base.rules ?? [];
  const ch = d.changes;
  const targets = d.target_rule_ids ?? [];
  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  const rulesEditor = (rules: Rule[]) => (
    <>
      {rules.map((r, i) => (
        <RuleEditor key={r.id ?? i} meta={meta} rule={r} currency={c.currency}
                    onChange={(nr) => setCh({ rules: rules.map((x, j) => (j === i ? nr : x)) })}
                    onRemove={() => setCh({ rules: rules.filter((_, j) => j !== i) })} />
      ))}
    </>
  );
  const bonusEditor = (bonuses = ch.bonuses ?? []) => (
    <>
      {bonuses.map((b, i) => (
        <BonusEditor key={b.id ?? i} meta={meta} bonus={b} rules={[...baseRules, ...(ch.rules ?? [])]}
                     onChange={(nb) => setCh({ bonuses: bonuses.map((x, j) => (j === i ? nb : x)) })}
                     onRemove={() => setCh({ bonuses: bonuses.filter((_, j) => j !== i) })} />
      ))}
      <button type="button" className="btn ghost sm" onClick={() => setCh({ bonuses: [...bonuses, blankBonus()] })}>+ Add bonus</button>
    </>
  );

  return (
    <div className="cm-card">
      <h3><span className="n">3</span>{label(d.type)}</h3>
      {!d.type ? <p className="status err">Choose a type on step 1.</p> : null}

      {d.type === "RATE_CHANGE" ? (
        <>
          <div className="cm-checks-h">Rules this replaces</div>
          <div className="cm-levels">
            {baseRules.map((r) => (
              <button key={r.id} type="button" aria-pressed={targets.includes(r.id ?? "")}
                      onClick={() => {
                        const id = r.id ?? "";
                        const on = targets.includes(id);
                        const rules = ch.rules ?? [];
                        set({
                          target_rule_ids: toggle(targets, id),
                          changes: { ...ch, rules: on ? rules.filter((x) => x.replaces !== id)
                            : [...rules, { ...structuredClone(r), id: undefined, replaces: id, source: undefined, needs_review: false }] },
                        });
                      }}>
                {r.name || "Unnamed"} · {rateText(r, c.currency)}
              </button>
            ))}
          </div>
          <p className="status">Each chosen rule is copied below. Change its rate; the base rule is replaced for the scoped intakes.</p>
          {rulesEditor(ch.rules ?? [])}
          <div className="cm-checks-h">Remove bonuses</div>
          <div className="cm-levels">
            {(base.bonuses ?? []).map((b) => (
              <button key={b.id} type="button" aria-pressed={(ch.remove_bonus_ids ?? []).includes(b.id ?? "")}
                      onClick={() => setCh({ remove_bonus_ids: toggle(ch.remove_bonus_ids ?? [], b.id ?? "") })}>
                {b.criteria_text || label(b.kind)}
              </button>
            ))}
            {!(base.bonuses ?? []).length ? <span className="dim">No base bonuses.</span> : null}
          </div>
          <div className="cm-checks-h">Add bonuses</div>
          {bonusEditor()}
        </>
      ) : null}

      {d.type === "RULE_ADDITION" ? (
        <>
          {rulesEditor(ch.rules ?? [])}
          <button type="button" className="btn ghost sm" onClick={() => setCh({ rules: [...(ch.rules ?? []), { ...blankRule(), id: undefined }] })}>+ Add rule</button>
        </>
      ) : null}

      {d.type === "BONUS_INCENTIVE" ? bonusEditor() : null}

      {d.type === "SCOPE_CHANGE" ? (
        <>
          <div className="cm-grid">
            <Field title="Territory type" hint="Blank keeps the base setting">
              <Select value={ch.territory_type} blank="Unchanged" options={meta.enums.territory ?? []}
                      onChange={(v) => setCh({ territory_type: v ?? undefined })} />
            </Field>
            <Field title="Add campuses" hint="Comma separated">
              <input value={(ch.add_campuses ?? []).join(", ")}
                     onChange={(e) => setCh({ add_campuses: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
            </Field>
          </div>
          {(base.campuses ?? []).length ? (
            <>
              <div className="cm-checks-h">Remove campuses</div>
              <div className="cm-levels">
                {(base.campuses ?? []).map((x) => (
                  <button key={x} type="button" aria-pressed={(ch.remove_campuses ?? []).includes(x)}
                          onClick={() => setCh({ remove_campuses: toggle(ch.remove_campuses ?? [], x) })}>{x}</button>
                ))}
              </div>
            </>
          ) : null}
          {(base.territory_rules ?? []).length ? (
            <>
              <div className="cm-checks-h">Remove territory rules</div>
              <div className="cm-levels">
                {(base.territory_rules ?? []).map((t) => (
                  <button key={t.id} type="button" aria-pressed={(ch.remove_territory_rule_ids ?? []).includes(t.id ?? "")}
                          onClick={() => setCh({ remove_territory_rule_ids: toggle(ch.remove_territory_rule_ids ?? [], t.id ?? "") })}>
                    {label(t.type)} {t.value}
                  </button>
                ))}
              </div>
            </>
          ) : null}
          <Territories meta={meta} value={ch.add_territory_rules ?? []} onChange={(v) => setCh({ add_territory_rules: v })} />
          {(base.exclusions ?? []).length ? (
            <>
              <div className="cm-checks-h">Remove exclusions</div>
              <div className="cm-levels">
                {(base.exclusions ?? []).map((x) => (
                  <button key={x.id} type="button" aria-pressed={(ch.remove_exclusion_ids ?? []).includes(x.id ?? "")}
                          onClick={() => setCh({ remove_exclusion_ids: toggle(ch.remove_exclusion_ids ?? [], x.id ?? "") })}>
                    {label(x.type)}{x.campus ? ` ${x.campus}` : ""}
                  </button>
                ))}
              </div>
            </>
          ) : null}
          <div className="cm-checks-h">Add exclusions</div>
          <Exclusions meta={meta} value={ch.add_exclusions ?? []} onChange={(v) => setCh({ add_exclusions: v })} />
        </>
      ) : null}

      {d.type === "INTAKE_NOTE" ? (
        <Field title="Note" required wide>
          <textarea className="cm-in" rows={4} value={ch.note ?? ""} onChange={(e) => setCh({ note: e.target.value || undefined })} />
        </Field>
      ) : null}

      {d.type === "EXTENSION" ? (
        <Field title="New end date" required bad={!ch.new_end_date}
               hint={`Currently ${c.is_rolling ? "rolling" : day(c.end_date)}. Intake scope is not widened; edit the base terms for that.`}>
          <input type="date" value={ch.new_end_date ?? ""} onChange={(e) => setCh({ new_end_date: e.target.value || undefined })} />
        </Field>
      ) : null}

      {d.type === "SUSPENSION" ? (
        <Band tone="warn">No commission is due for any student in the scoped intakes while this is published.</Band>
      ) : null}
    </div>
  );
}

function StepReview({ id, locked, dirty }: { id: number; locked: boolean; dirty: boolean }) {
  const { go } = useNav();
  const prev = useAmendmentPreview(id);
  const publish = usePublishAmendment();
  if (prev.isLoading) return <Spinner />;
  if (prev.error || !prev.data) return <ErrorText error={prev.error} />;
  const p = prev.data;
  const refused = publish.error instanceof CommissionApiError
    ? (publish.error.detail.checks as AmendmentPreview["checks"] | undefined) : undefined;
  const checks = refused ?? p.checks;
  const blocked = checks.some((x) => x.block && !x.ok);
  const a = p.amendment;

  return (
    <div className="cm-split">
      <div>
        <div className="cm-card">
          <h3>{label(a.type)} · {scopeText(a)}</h3>
          <div className="cm-kv">
            <span>Reference</span><span>{a.reference ?? "--"}</span>
            <span>Received</span><span>{day(a.received_on)}</span>
            <span>Document</span><span>{a.document_file ?? "--"}</span>
            {a.summary ? <><span>Summary</span><span>{a.summary}</span></> : null}
            {a.published_at ? <><span>Published</span><span>{when(a.published_at)}{a.published_by ? ` by ${a.published_by}` : ""}</span></> : null}
          </div>
        </div>
        {p.open_ended ? <Band tone="info">Open-ended: it applies to every intake from {intakeLabel(a.from_intake)} until superseded.</Band> : null}
        <Section title="Before and after" note="Resolved terms per intake in scope, as if this were published.">
          {!p.intakes.length ? <p className="status">No intake falls in this scope.</p> : p.intakes.map((row) => (
            <div key={row.intake} className="cm-card">
              <h3>{row.label}</h3>
              <Diff before={row.before} after={row.after} />
            </div>
          ))}
        </Section>
      </div>
      <div className="cm-sticky">
        <div className="cm-card">
          <h3>Checks</h3>
          <div className={`cm-ready ${blocked ? "no" : "yes"}`}>{blocked ? "Fix before publishing" : "Ready to publish"}</div>
          <ul className="cm-checks">
            {checks.map((x) => (
              <li key={x.key} className={x.ok ? "ok" : x.block ? "no" : "wn"}>
                <span className="mk">{x.ok ? "✓" : x.block ? "✕" : "!"}</span>
                <span>{x.label}{!x.ok && x.message ? <span className="why">{x.message}</span> : null}</span>
              </li>
            ))}
          </ul>
          {!locked ? (
            <div className="cm-foot">
              <button type="button" className="btn" disabled={blocked || dirty || publish.isPending}
                      onClick={() => publish.mutate(id, { onSuccess: () => go({ a: null, step: null }) })}>
                {publish.isPending ? "Publishing…" : "Publish amendment"}
              </button>
            </div>
          ) : null}
          {publish.error && !refused ? <ErrorText error={publish.error} /> : null}
          {!locked ? <p className="status">Publishing is final. A backdated scope raises a recalculation.</p> : null}
        </div>
      </div>
    </div>
  );
}

function Diff({ before, after }: { before: Resolved; after: Resolved }) {
  if (!before.ok && !after.ok) return <p className="status">No terms before or after: {after.reason}</p>;
  if (!after.ok) return <p className="status err">After: no commission. {after.reason}</p>;
  const b = new Map((before.rules ?? []).map((r) => [r.name ?? r.id, r]));
  const rows = (after.rules ?? []).map((r) => {
    const old = b.get(r.name ?? r.id);
    const was = old ? rateText(old, before.currency) : "--";
    const now = rateText(r, after.currency);
    return { name: r.name ?? "--", was, now, changed: was !== now, source: r.source };
  });
  const gone = (before.rules ?? []).filter((r) => !(after.rules ?? []).some((x) => (x.name ?? x.id) === (r.name ?? r.id)));
  const bonus = (x: Resolved) => (x.bonuses ?? []).map((y) => y.criteria_text || label(y.kind));
  const bb = bonus(before);
  const ab = bonus(after);
  return (
    <>
      <div className="tbl-wrap" style={{ marginTop: 0 }}>
        <table className="cm-diff">
          <thead><tr><th className="txt">Rule</th><th>Before</th><th>After</th><th className="txt">Source</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}><td className="txt">{r.name}</td><td className="num">{r.was}</td>
                <td className={`num${r.changed ? " chg" : ""}`}>{r.now}</td><td className="txt dim">{r.source}</td></tr>
            ))}
            {gone.map((r, i) => (
              <tr key={`g${i}`}><td className="txt">{r.name}</td><td className="num">{rateText(r, before.currency)}</td>
                <td className="num chg">removed</td><td /></tr>
            ))}
          </tbody>
        </table>
      </div>
      {bb.join("|") !== ab.join("|") ? (
        <p className="status">Bonuses: {bb.length ? bb.join(", ") : "none"} → <b>{ab.length ? ab.join(", ") : "none"}</b></p>
      ) : null}
      {before.territory_type !== after.territory_type || (before.territory_rules ?? []).length !== (after.territory_rules ?? []).length ? (
        <p className="status">Territory: {label(before.territory_type)} ({(before.territory_rules ?? []).length} rules) →{" "}
          <b>{label(after.territory_type)} ({(after.territory_rules ?? []).length} rules)</b></p>
      ) : null}
      {(after.notes ?? []).length > (before.notes ?? []).length ? (
        <p className="status">Notes: {(after.notes ?? []).slice((before.notes ?? []).length).map((n) => n.text).join("; ")}</p>
      ) : null}
    </>
  );
}
