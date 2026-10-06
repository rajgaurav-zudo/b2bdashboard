import { useState } from "react";

import { Band } from "../../ui/Primitives";
import {
  CommissionApiError, useInstitutions, useMeta, usePublishContract, useUpdateContract,
  type Bonus, type Checklist, type Contract, type ContractDetail, type Exclusion, type Meta, type Milestone,
  type Rule, type Terms, type TerritoryRule, type Tier,
} from "./api";
import { ChecklistPanel, ErrorText, Field, LevelPicker, Review, Select, day, intakeLabel, intakeRange, label } from "./shared";

const uid = (p: string) => `${p}_${Math.random().toString(36).slice(2, 10)}`;
const num = (v: string) => (v.trim() === "" ? null : Number(v));

export const blankRule = (): Rule => ({
  id: uid("r"), name: "", course_levels: [], structure: "PER_STUDENT", pricing: "PERCENT", value: null,
  tiers: [], tier_mode: "RETROACTIVE", count_metric: "ENROLMENT", count_scope: "ACADEMIC_YEAR", fee_year_scope: "YEAR_1",
});
export const blankBonus = (): Bonus => ({
  id: uid("b"), kind: "RATE_UPLIFT", criteria_text: "", tiers: [{ min_count: null, max_count: null, value: null }],
  tier_mode: "RETROACTIVE", count_scope: "ACADEMIC_YEAR", course_levels: [],
});

/** The configurator: the whole contract edited locally, saved as one PUT, then
 *  published as a new version once the checklist is clear. */
export function BaseTerms({ detail }: { detail: ContractDetail }) {
  const meta = useMeta();
  const [c, setC] = useState<Contract>(() => structuredClone(detail.contract));
  const [dirty, setDirty] = useState(false);
  const [effFrom, setEffFrom] = useState("");
  const [refused, setRefused] = useState<Checklist | null>(null);
  const save = useUpdateContract(c.id);
  const publish = usePublishContract(c.id);
  if (!meta.data) return null;
  const m = meta.data;
  const t = c.terms ?? {};

  const set = (patch: Partial<Contract>) => { setC({ ...c, ...patch }); setDirty(true); };
  const setT = (patch: Partial<Terms>) => set({ terms: { ...t, ...patch } });

  const doSave = () => {
    const { terms, ...rest } = c;
    const header = Object.fromEntries(Object.entries(rest).filter(([k]) => HEADER.includes(k)));
    save.mutate({ ...header, terms }, { onSuccess: (row) => { setC(structuredClone(row)); setDirty(false); setRefused(null); } });
  };
  const doPublish = () => publish.mutate(effFrom || null, {
    onSuccess: () => setRefused(null),
    onError: (e) => setRefused(e instanceof CommissionApiError ? (e.detail.checklist as Checklist) ?? null : null),
  });
  const jump = (where: string) =>
    document.getElementById(`cm-${where}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  const checklist = refused ?? detail.checklist;

  return (
    <div className="cm-split">
      <div>
        {c.current_version > 0 ? (
          <div style={{ marginTop: 0, marginBottom: 14 }}>
            <Band tone="info">
              Edits here make a new base version when published. For a change that applies from a later intake or
              comes from a document, add an amendment instead.
            </Band>
          </div>
        ) : null}

        <div className="cm-card">
          <h3><span className="n">1</span>Contract</h3>
          <div className="cm-grid">
            <Field title="Party"><input value={c.party_name ?? ""} disabled /></Field>
            <Field title="Party type" required bad={!c.party_type}>
              <Select value={c.party_type} options={m.enums.party_types ?? []} onChange={(v) => set({ party_type: v })} />
            </Field>
            <Field title="Region" required bad={!c.region}>
              <Select value={c.region} options={m.enums.regions ?? []} onChange={(v) => set({ region: v })} />
            </Field>
            <Field title="Start date" required bad={!c.start_date}>
              <input type="date" value={c.start_date ?? ""} onChange={(e) => set({ start_date: e.target.value || null })} />
            </Field>
            <Field title="End date" required={!c.is_rolling} bad={!c.is_rolling && !c.end_date}>
              <input type="date" value={c.end_date ?? ""} disabled={c.is_rolling}
                     onChange={(e) => set({ end_date: e.target.value || null })} />
            </Field>
            <Field title="Rolling">
              <label className="cm-check"><input type="checkbox" checked={c.is_rolling}
                     onChange={(e) => set({ is_rolling: e.target.checked, end_date: e.target.checked ? null : c.end_date })} />
                No end date</label>
            </Field>
            <Field title="Currency" required bad={!c.currency}>
              <input value={c.currency ?? ""} maxLength={3} placeholder="GBP"
                     onChange={(e) => set({ currency: e.target.value.toUpperCase() || null })} />
            </Field>
            <Field title="VAT treatment" required bad={!c.vat_treatment}>
              <Select value={c.vat_treatment} options={m.enums.vat ?? []} onChange={(v) => set({ vat_treatment: v })} />
            </Field>
            {c.vat_treatment && c.vat_treatment !== "NOT_APPLICABLE" ? (
              <Field title="VAT rate %" required bad={c.vat_rate == null}>
                <input type="number" value={c.vat_rate ?? ""} onChange={(e) => set({ vat_rate: num(e.target.value) })} />
              </Field>
            ) : null}
            <Field title="Fee basis" required bad={!c.fee_basis}>
              <Select value={c.fee_basis} options={m.enums.fee_basis ?? []} onChange={(v) => set({ fee_basis: v })} />
            </Field>
          </div>
          {c.party_type === "PATHWAY_PROVIDER" || c.party_type === "OUTBOUND_AGENT" ? (
            <Covered value={c.covered_institution_ids ?? []} onChange={(ids) => set({ covered_institution_ids: ids })} />
          ) : null}
        </div>

        <div className="cm-card">
          <h3><span className="n">2</span>Scope</h3>
          <div className="cm-grid">
            <Field title="Academic years" required bad={!c.academic_years?.length} hint="e.g. 2025-26, 2026-27">
              <input value={(c.academic_years ?? []).join(", ")}
                     onChange={(e) => set({ academic_years: e.target.value.split(/[,\s]+/).filter(Boolean) })} />
            </Field>
            <Field title="Intakes covered" required>
              <Select value={c.intake_scope?.mode ?? null} options={m.enums.intake_scope_modes ?? []}
                      labels={(v) => ({ ENTIRE_YEAR: "Every intake", INTAKES: "Listed intakes", UP_TO: "Up to an intake" }[v] ?? label(v))}
                      onChange={(v) => set({ intake_scope: { mode: v ?? "ENTIRE_YEAR" } })} />
            </Field>
            {c.intake_scope?.mode === "UP_TO" ? (
              <Field title="Last intake" required bad={!c.intake_scope.until_intake}>
                <IntakeSelect from={c.start_date} value={c.intake_scope.until_intake}
                              onChange={(v) => set({ intake_scope: { mode: "UP_TO", until_intake: v ?? undefined } })} />
              </Field>
            ) : null}
            {c.intake_scope?.mode === "INTAKES" ? (
              <Field title="Intakes" required bad={!c.intake_scope.intakes?.length} hint="YYYY-MM, comma separated" wide>
                <input value={(c.intake_scope.intakes ?? []).join(", ")}
                       onChange={(e) => set({ intake_scope: { mode: "INTAKES", intakes: e.target.value.split(/[,\s]+/).filter(Boolean) } })} />
              </Field>
            ) : null}
            <Field title="Territory" required bad={!c.territory_type}>
              <Select value={c.territory_type} options={m.enums.territory ?? []} onChange={(v) => set({ territory_type: v })} />
            </Field>
            <Field title="Campuses" hint="Comma separated">
              <input value={(t.campuses ?? []).join(", ")}
                     onChange={(e) => setT({ campuses: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
            </Field>
          </div>
          <Territories meta={m} value={t.territory_rules ?? []} onChange={(v) => setT({ territory_rules: v })}
                       hint={c.territory_type === "GLOBAL_WITH_RESTRICTIONS" ? "Add at least one EXCLUDE."
                         : c.territory_type === "NOT_GLOBAL" ? "Add at least one INCLUDE." : null} />
        </div>

        <div className="cm-card">
          <h3><span className="n">3</span>Commission rules</h3>
          {(t.rules ?? []).map((r, i) => (
            <RuleEditor key={r.id ?? i} meta={m} rule={r} currency={c.currency}
                        onChange={(nr) => setT({ rules: (t.rules ?? []).map((x, j) => (j === i ? nr : x)) })}
                        onRemove={() => setT({ rules: (t.rules ?? []).filter((_, j) => j !== i) })} />
          ))}
          <button type="button" className="btn ghost sm" onClick={() => setT({ rules: [...(t.rules ?? []), blankRule()] })}>+ Add rule</button>
        </div>

        <div className="cm-card">
          <h3><span className="n">4</span>Modules</h3>
          <div className="cm-checks-h">Bonuses</div>
          {(t.bonuses ?? []).map((b, i) => (
            <BonusEditor key={b.id ?? i} meta={m} bonus={b} rules={t.rules ?? []}
                         onChange={(nb) => setT({ bonuses: (t.bonuses ?? []).map((x, j) => (j === i ? nb : x)) })}
                         onRemove={() => setT({ bonuses: (t.bonuses ?? []).filter((_, j) => j !== i) })} />
          ))}
          <button type="button" className="btn ghost sm" onClick={() => setT({ bonuses: [...(t.bonuses ?? []), blankBonus()] })}>+ Add bonus</button>

          <div className="cm-checks-h">No commission for</div>
          <Exclusions meta={m} value={t.exclusions ?? []} onChange={(v) => setT({ exclusions: v })} />

          <div className="cm-checks-h" id="cm-milestones">Payment milestones</div>
          <Milestones meta={m} value={t.milestones ?? []} onChange={(v) => setT({ milestones: v })} />

          {t.review_items?.length ? (
            <>
              <div className="cm-checks-h">Imported text to review</div>
              <ul className="cm-checks">
                {t.review_items.map((r, i) => (
                  <li key={i} className="wn"><span className="mk">!</span>
                    <span>{r.message}{r.cell ? <span className="why">{r.cell}{r.text ? `: ${r.text}` : ""}</span> : null}</span></li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      </div>

      <div className="cm-sticky">
        <div className="cm-card">
          <h3>{dirty ? "Unsaved changes" : c.has_unpublished || !c.current_version ? "Saved, not published" : `Published v${c.current_version}`}</h3>
          <div className="cm-foot" style={{ marginTop: 0, justifyContent: "stretch" }}>
            <button type="button" className="btn ghost" style={{ flex: 1 }} disabled={!dirty || save.isPending} onClick={doSave}>
              {save.isPending ? "Saving…" : "Save draft"}
            </button>
            <button type="button" className="btn" style={{ flex: 1 }}
                    disabled={dirty || publish.isPending || (!c.has_unpublished && c.current_version > 0)}
                    title={dirty ? "Save first" : undefined} onClick={doPublish}>
              Publish v{c.current_version + 1}
            </button>
          </div>
          {c.current_version > 0 ? (
            <Field title="Effective from" hint="Blank means today. An earlier date raises a recalculation.">
              <input type="date" value={effFrom} onChange={(e) => setEffFrom(e.target.value)} />
            </Field>
          ) : <p className="status">Version 1 takes effect from the start date, {day(c.start_date)}.</p>}
          <ErrorText error={save.error} />
          {publish.error && !refused ? <ErrorText error={publish.error} /> : null}
          {publish.isSuccess ? <p className="status ok">Published.</p> : null}
          {dirty ? <p className="status">The checklist reflects the last save.</p> : null}
        </div>
        <ChecklistPanel checklist={checklist} onJump={jump} />
      </div>
    </div>
  );
}

const HEADER = ["party_type", "party_id", "covered_institution_ids", "region", "status_reason",
  "status_effective_date", "start_date", "end_date", "is_rolling", "currency", "vat_treatment", "vat_rate",
  "fee_basis", "territory_type", "academic_years", "intake_scope"];

function IntakeSelect({ from, value, onChange }: { from: string | null; value?: string | null; onChange: (v: string | null) => void }) {
  const opts = [...new Set([...intakeRange((from ?? new Date().toISOString()).slice(0, 7), 48), ...(value ? [value] : [])])].sort();
  return <Select value={value} options={opts} labels={intakeLabel} onChange={onChange} />;
}

function Covered({ value, onChange }: { value: number[]; onChange: (v: number[]) => void }) {
  const inst = useInstitutions();
  const [pick, setPick] = useState("");
  const name = (id: number) => inst.data?.find((i) => i.id === id)?.name ?? `#${id}`;
  return (
    <div style={{ marginTop: 12 }} id="cm-covered">
      <div className="cm-checks-h">Covered institutions<span className="red">*</span></div>
      <div className="chips" style={{ marginTop: 0 }}>
        {value.map((id) => (
          <span key={id} className="chip">{name(id)}{" "}
            <button type="button" className="cm-link" onClick={() => onChange(value.filter((x) => x !== id))}>×</button></span>
        ))}
      </div>
      <div className="cm-row" style={{ marginTop: 8 }}>
        <select className="cm-in" value={pick} onChange={(e) => setPick(e.target.value)}>
          <option value="">Add an institution…</option>
          {(inst.data ?? []).filter((i) => !value.includes(i.id)).map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </select>
        <button type="button" className="btn ghost sm" disabled={!pick}
                onClick={() => { onChange([...value, Number(pick)]); setPick(""); }}>Add</button>
      </div>
    </div>
  );
}

export function TierTable({ tiers, pricing, onChange }: { tiers: Tier[]; pricing?: string; onChange: (t: Tier[]) => void }) {
  const set = (i: number, patch: Partial<Tier>) => onChange(tiers.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  return (
    <div className="tbl-wrap" style={{ marginTop: 8 }}>
      <table>
        <thead><tr><th className="txt">From</th><th className="txt">To</th><th className="txt">{pricing === "FLAT" ? "Amount" : "Rate %"}</th><th /></tr></thead>
        <tbody>
          {tiers.map((t, i) => (
            <tr key={i}>
              <td className="txt"><input className="cm-in" type="number" style={{ width: 90 }} value={t.min_count ?? ""} onChange={(e) => set(i, { min_count: num(e.target.value) })} /></td>
              <td className="txt"><input className="cm-in" type="number" style={{ width: 90 }} placeholder="no limit" value={t.max_count ?? ""} onChange={(e) => set(i, { max_count: num(e.target.value) })} /></td>
              <td className="txt"><input className="cm-in" type="number" style={{ width: 90 }} value={t.value ?? ""} onChange={(e) => set(i, { value: num(e.target.value) })} /></td>
              <td className="act"><button type="button" onClick={() => onChange(tiers.filter((_, j) => j !== i))}>Remove</button></td>
            </tr>
          ))}
          <tr><td className="txt" colSpan={4}>
            <button type="button" className="cm-link" onClick={() => {
              const last = tiers[tiers.length - 1];
              onChange([...tiers, { min_count: last?.max_count != null ? last.max_count + 1 : null, max_count: null, value: null }]);
            }}>+ Add tier</button>
          </td></tr>
        </tbody>
      </table>
    </div>
  );
}

export function RuleEditor({ meta, rule: r, currency, onChange, onRemove }: {
  meta: Meta; rule: Rule; currency?: string | null; onChange: (r: Rule) => void; onRemove: () => void;
}) {
  const set = (patch: Partial<Rule>) => onChange({ ...r, ...patch });
  const e = meta.enums;
  return (
    <div className="cm-card" id={`cm-rule:${r.id}`} style={{ boxShadow: "none", background: "var(--paper)", marginBottom: 12 }}>
      <div className="cm-row" style={{ marginBottom: 10 }}>
        <input className="cm-in" style={{ flex: 1, fontWeight: 600 }} placeholder="Rule name, e.g. Undergraduate"
               value={r.name ?? ""} onChange={(ev) => set({ name: ev.target.value })} />
        <Review on={r.needs_review} note={r.review_note} />
        {r.needs_review ? <button type="button" className="btn ghost sm" onClick={() => set({ needs_review: false })}>Mark reviewed</button> : null}
        <button type="button" className="btn danger sm" onClick={onRemove}>Remove</button>
      </div>
      {r.review_note ? <p className="status amber" style={{ marginTop: 0 }}>{r.review_note}{r.source_cell ? ` (${r.source_cell})` : ""}</p> : null}
      <Field title="Course levels" required bad={!r.course_levels?.length}>
        <LevelPicker all={meta.course_levels} value={r.course_levels ?? []} onChange={(v) => set({ course_levels: v })} />
      </Field>
      <div className="cm-grid" style={{ marginTop: 10 }}>
        <Field title="Structure" required>
          <Select value={r.structure} blank={null} options={e.structure ?? []} onChange={(v) => set({ structure: v ?? "PER_STUDENT" })} />
        </Field>
        <Field title="Pricing" required>
          <Select value={r.pricing} blank={null} options={e.pricing ?? []} onChange={(v) => set({ pricing: v ?? "PERCENT" })} />
        </Field>
        {r.structure !== "TIERED" ? (
          <Field title={r.pricing === "FLAT" ? `Amount (${currency ?? "--"})` : "Rate %"} required bad={r.value == null}>
            <input type="number" value={r.value ?? ""} onChange={(ev) => set({ value: num(ev.target.value) })} />
          </Field>
        ) : null}
        <Field title="Campus"><input value={r.campus ?? ""} onChange={(ev) => set({ campus: ev.target.value || null })} /></Field>
        <Field title="Fee year"><Select value={r.fee_year_scope} options={e.fee_year_scope ?? []} onChange={(v) => set({ fee_year_scope: v ?? undefined })} /></Field>
        <Field title="Priority" hint="Breaks ties"><input type="number" value={r.priority ?? ""} onChange={(ev) => set({ priority: num(ev.target.value) ?? undefined })} /></Field>
      </div>
      {r.structure === "TIERED" ? (
        <>
          {r.tiers_raw ? <p className="status amber">Imported range text: “{r.tiers_raw}”. Enter the tiers below.</p> : null}
          <TierTable tiers={r.tiers ?? []} pricing={r.pricing} onChange={(v) => set({ tiers: v })} />
          <div className="cm-grid" style={{ marginTop: 10 }}>
            <Field title="Tier mode" required>
              <Select value={r.tier_mode} options={e.tier_mode ?? []} onChange={(v) => set({ tier_mode: v ?? undefined })} />
            </Field>
            <Field title="Count" required>
              <Select value={r.count_metric} options={e.count_metric ?? []} onChange={(v) => set({ count_metric: v ?? undefined })} />
            </Field>
            <Field title="Counted per" required>
              <Select value={r.count_scope} options={e.count_scope ?? []} onChange={(v) => set({ count_scope: v ?? undefined })} />
            </Field>
            {r.count_scope === "COMBINED_INTAKES" ? (
              <Field title="Combined intakes" hint="YYYY-MM, at least two">
                <input value={(r.count_intakes ?? []).join(", ")} onChange={(ev) => set({ count_intakes: ev.target.value.split(/[,\s]+/).filter(Boolean) })} />
              </Field>
            ) : null}
            {r.count_scope === "CUSTOM_WINDOW" ? (
              <>
                <Field title="Window start"><input type="date" value={r.count_window_start ?? ""} onChange={(ev) => set({ count_window_start: ev.target.value })} /></Field>
                <Field title="Window end"><input type="date" value={r.count_window_end ?? ""} onChange={(ev) => set({ count_window_end: ev.target.value })} /></Field>
              </>
            ) : null}
          </div>
          <p className="status">
            {r.tier_mode === "MARGINAL" ? "Marginal: each student is paid at the tier of their own position."
              : "Retroactive: every student is re-rated to the tier reached; earlier students get a true-up."}
          </p>
        </>
      ) : null}
    </div>
  );
}

export function BonusEditor({ meta, bonus: b, rules, onChange, onRemove }: {
  meta: Meta; bonus: Bonus; rules: Rule[]; onChange: (b: Bonus) => void; onRemove: () => void;
}) {
  const set = (patch: Partial<Bonus>) => onChange({ ...b, ...patch });
  const e = meta.enums;
  return (
    <div className="cm-card" id={`cm-bonus:${b.id}`} style={{ boxShadow: "none", background: "var(--paper)", marginBottom: 12 }}>
      <div className="cm-row" style={{ marginBottom: 10 }}>
        <input className="cm-in" style={{ flex: 1 }} placeholder="Criteria, e.g. 50+ UG students in Sep 2026"
               value={b.criteria_text ?? ""} onChange={(ev) => set({ criteria_text: ev.target.value })} />
        <Review on={b.needs_review} note={b.review_note} />
        {b.needs_review ? <button type="button" className="btn ghost sm" onClick={() => set({ needs_review: false })}>Mark reviewed</button> : null}
        <button type="button" className="btn danger sm" onClick={onRemove}>Remove</button>
      </div>
      {b.review_note ? <p className="status amber" style={{ marginTop: 0 }}>{b.review_note}</p> : null}
      <div className="cm-grid">
        <Field title="Kind"><Select value={b.kind} blank={null} options={e.bonus_kind ?? []} onChange={(v) => set({ kind: v ?? "RATE_UPLIFT" })} /></Field>
        <Field title="Tier mode"><Select value={b.tier_mode} options={e.tier_mode ?? []} onChange={(v) => set({ tier_mode: v ?? undefined })} /></Field>
        <Field title="Counted per"><Select value={b.count_scope} options={e.count_scope ?? []} onChange={(v) => set({ count_scope: v ?? undefined })} /></Field>
        {b.count_scope === "COMBINED_INTAKES" ? (
          <Field title="Combined intakes" hint="YYYY-MM, at least two">
            <input value={(b.count_intakes ?? []).join(", ")} onChange={(ev) => set({ count_intakes: ev.target.value.split(/[,\s]+/).filter(Boolean) })} />
          </Field>
        ) : null}
        <Field title="Applies to rules" wide>
          <div className="cm-levels">
            {rules.map((r) => {
              const on = (b.applies_to_rule_ids ?? []).includes(r.id ?? "");
              return (
                <button key={r.id} type="button" aria-pressed={on}
                        onClick={() => set({ applies_to_rule_ids: on ? (b.applies_to_rule_ids ?? []).filter((x) => x !== r.id)
                          : [...(b.applies_to_rule_ids ?? []), r.id ?? ""] })}>
                  {r.name || "Unnamed rule"}
                </button>
              );
            })}
          </div>
        </Field>
      </div>
      <TierTable tiers={b.tiers ?? []} pricing={b.kind === "RATE_UPLIFT" ? "PERCENT" : "FLAT"} onChange={(v) => set({ tiers: v })} />
    </div>
  );
}

export function Territories({ meta, value, onChange, hint }: {
  meta: Meta; value: TerritoryRule[]; onChange: (v: TerritoryRule[]) => void; hint?: string | null;
}) {
  const set = (i: number, p: Partial<TerritoryRule>) => onChange(value.map((x, j) => (j === i ? { ...x, ...p } : x)));
  return (
    <div style={{ marginTop: 12 }}>
      <div className="cm-checks-h">Territory rules {hint ? <span className="amber" style={{ textTransform: "none", letterSpacing: 0 }}>· {hint}</span> : null}</div>
      <datalist id="cm-countries-b">{meta.countries.map((c) => <option key={c.code} value={c.name} />)}</datalist>
      {value.map((t, i) => (
        <div key={t.id ?? i} className="cm-row">
          <Select value={t.type} blank={null} options={meta.enums.territory_rule_type ?? []} onChange={(v) => set(i, { type: v ?? "EXCLUDE" })} />
          <Select value={t.scope ?? "COUNTRY"} blank={null} options={meta.enums.territory_scope ?? []} onChange={(v) => set(i, { scope: v ?? "COUNTRY" })} />
          <input list="cm-countries-b" value={t.value} placeholder="Country" onChange={(e) => set(i, { value: e.target.value })} />
          <button type="button" className="btn ghost sm" onClick={() => onChange(value.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button type="button" className="btn ghost sm" style={{ marginTop: 8 }}
              onClick={() => onChange([...value, { id: uid("t"), type: "EXCLUDE", scope: "COUNTRY", value: "" }])}>+ Add territory</button>
    </div>
  );
}

export function Exclusions({ meta, value, onChange }: { meta: Meta; value: Exclusion[]; onChange: (v: Exclusion[]) => void }) {
  const set = (i: number, p: Partial<Exclusion>) => onChange(value.map((x, j) => (j === i ? { ...x, ...p } : x)));
  return (
    <>
      {value.map((x, i) => (
        <div key={x.id ?? i} className="cm-row">
          <Select value={x.type} blank={null} options={meta.enums.exclusion_types ?? []} onChange={(v) => set(i, { type: v ?? "CAMPUS" })} />
          {x.type === "CAMPUS" ? <input placeholder="Campus" value={x.campus ?? ""} onChange={(e) => set(i, { campus: e.target.value })} /> : null}
          <input placeholder="Note" value={x.note ?? ""} onChange={(e) => set(i, { note: e.target.value })} style={{ flex: 1 }} />
          <button type="button" className="btn ghost sm" onClick={() => onChange(value.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button type="button" className="btn ghost sm" style={{ marginTop: 8 }}
              onClick={() => onChange([...value, { id: uid("x"), type: "ONLINE_DISTANCE" }])}>+ Add exclusion</button>
    </>
  );
}

function Milestones({ meta, value, onChange }: { meta: Meta; value: Milestone[]; onChange: (v: Milestone[]) => void }) {
  const set = (i: number, p: Partial<Milestone>) => onChange(value.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const total = value.reduce((s, m) => s + (Number(m.pct) || 0), 0);
  return (
    <>
      {!value.length ? <p className="status">None set: 100% is paid on enrolment.</p> : null}
      {value.map((m, i) => (
        <div key={i} className="cm-row">
          <Select value={m.trigger} blank={null} options={meta.enums.milestone_triggers ?? []} onChange={(v) => set(i, { trigger: v ?? "ENROLLED" })} />
          <input type="number" style={{ width: 80 }} value={m.pct} onChange={(e) => set(i, { pct: Number(e.target.value) })} /> %
          {m.trigger === "N_WEEKS_ENROLLED" ? <><input type="number" style={{ width: 70 }} value={m.n_weeks ?? ""} onChange={(e) => set(i, { n_weeks: num(e.target.value) })} /> weeks</> : null}
          <button type="button" className="btn ghost sm" onClick={() => onChange(value.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      {value.length && total !== 100 ? <p className="status err">Milestones add up to {total}%, not 100%.</p> : null}
      <button type="button" className="btn ghost sm" style={{ marginTop: 8 }}
              onClick={() => onChange([...value, { trigger: "ENROLLED", pct: value.length ? 0 : 100 }])}>+ Add milestone</button>
    </>
  );
}
