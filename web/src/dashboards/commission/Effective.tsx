import { useState } from "react";

import { Band, Section, Spinner } from "../../ui/Primitives";
import { simulate, useEffective, useMeta, type Contract, type Resolved, type Rule, type SimResult } from "./api";
import { ErrorText, Field, Review, Select, Source, intakeLabel, intakeRange, label, money, tierText, useNav } from "./shared";

const FLAGS: [string, string][] = [
  ["online_distance", "Online / distance"], ["home_fee", "Home fee"], ["ruk_fee", "RUK fee"],
  ["non_fee_paying", "Non fee paying"], ["federal_aid", "Federal aid"], ["franchise_partner", "Franchise / partner"],
];
const DATE_KEYS: [string, string][] = [
  ["application_date", "Application date"], ["cas_date", "CAS date"],
  ["deposit_date", "Deposit date"], ["enrolment_date", "Enrolment date"],
];

export function rateText(r: Rule, currency?: string | null) {
  const one = (v: number | null | undefined) =>
    v == null ? "--" : r.pricing === "PERCENT" ? `${v}%` : money(v, currency);
  if (r.structure === "TIERED") {
    if (!r.tiers?.length) return r.tiers_raw ? `Tiered: ${r.tiers_raw}` : "Tiered (no tiers)";
    return r.tiers.map((t) => `${tierText(t)}: ${one(t.value)}`).join(" · ");
  }
  return one(r.value);
}

/** resolveTerms for one intake, every line tagged with where it came from,
 *  plus a one-student simulation through the calculation. */
export function Effective({ id, contract }: { id: number; contract: Contract }) {
  const { params, go } = useNav();
  const meta = useMeta();
  const intake = params.get("intake") ?? meta.data?.intakes_default.find((x) => x >= (meta.data?.today ?? "").slice(0, 7))
    ?? meta.data?.intakes_default[0] ?? null;
  const { data, isLoading, error } = useEffective(id, intake);
  const start = contract.start_date?.slice(0, 7) ?? intake ?? "2026-01";
  const choices = [...new Set([...intakeRange(start, 36), ...(intake ? [intake] : [])])].sort();

  return (
    <>
      <div className="cm-row" style={{ marginTop: 18 }}>
        <b style={{ fontSize: 13 }}>Intake</b>
        <select className="cm-in" value={intake ?? ""} onChange={(e) => go({ intake: e.target.value }, true)}>
          {choices.map((x) => <option key={x} value={x}>{intakeLabel(x)}</option>)}
        </select>
        {data?.ok ? <span className="pill live">Base v{data.version}{data.applied?.length ? ` + ${data.applied.length} amendment${data.applied.length > 1 ? "s" : ""}` : ""}</span> : null}
      </div>

      {isLoading || !intake ? <Spinner /> : error ? <ErrorText error={error} /> : !data ? null : !data.ok ? (
        <div style={{ marginTop: 16 }}><Band tone="warn">{data.reason}</Band></div>
      ) : (
        <div className="cm-split">
          <div><Terms t={data} /></div>
          <div className="cm-sticky"><Simulator id={id} intake={intake} terms={data} /></div>
        </div>
      )}
    </>
  );
}

function Terms({ t }: { t: Resolved }) {
  const cur = t.currency;
  const excluded = (t.territory_rules ?? []).filter((x) => x.type === "EXCLUDE");
  const included = (t.territory_rules ?? []).filter((x) => x.type === "INCLUDE");
  return (
    <>
      <div className="cm-card">
        <dl className="cm-kv">
          <dt>Currency</dt><dd>{t.currency ?? "--"}</dd>
          <dt>Fee basis</dt><dd>{label(t.fee_basis)}</dd>
          <dt>VAT</dt><dd>{label(t.vat_treatment)}{t.vat_rate ? ` at ${t.vat_rate}%` : ""}</dd>
          <dt>Territory</dt><dd>{label(t.territory_type)}</dd>
          {t.campuses?.length ? <><dt>Campuses</dt><dd>{t.campuses.join(", ")}</dd></> : null}
          {t.applied?.length ? <><dt>Amendments applied</dt><dd>{t.applied.map((a) => `#${a.number} ${label(a.type)}`).join(", ")}</dd></> : null}
        </dl>
      </div>
      {t.conditional?.length ? (
        <div style={{ marginTop: 12 }}>
          <Band tone="info">
            Depends on the student's dates:{" "}
            {t.conditional.map((c) => `#${c.number} ${label(c.type)} (${c.condition})`).join("; ")}. Add dates in the simulator to check.
          </Band>
        </div>
      ) : null}

      <Section title="Commission rules">
        <div className="tbl-wrap" style={{ marginTop: 0 }}>
          <table className="cm-wrap">
            <thead><tr><th className="txt">Rule</th><th className="txt">Course levels</th><th className="txt">Rate</th>
              <th className="txt">Counted</th><th className="txt">Source</th></tr></thead>
            <tbody>
              {(t.rules ?? []).map((r) => (
                <tr key={r.id}>
                  <td className="txt"><b>{r.name}</b>{r.campus ? <div className="dim">{r.campus}</div> : null} <Review on={r.needs_review} note={r.review_note} /></td>
                  <td className="txt">{(r.course_levels ?? []).join(", ")}</td>
                  <td className="txt">{rateText(r, cur)}{r.structure === "TIERED" ? <div className="dim">{label(r.tier_mode)}</div> : null}</td>
                  <td className="txt">{r.structure === "TIERED" ? `${label(r.count_metric)} per ${label(r.count_scope).toLowerCase()}` : "--"}</td>
                  <td className="txt"><Source source={r.source} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {t.bonuses?.length ? (
        <Section title="Bonuses">
          <div className="tbl-wrap" style={{ marginTop: 0 }}>
            <table className="cm-wrap">
              <thead><tr><th className="txt">Criteria</th><th className="txt">Kind</th><th className="txt">Tiers</th><th className="txt">Source</th></tr></thead>
              <tbody>
                {t.bonuses.map((b) => (
                  <tr key={b.id}>
                    <td className="txt">{b.criteria_text ?? "--"} <Review on={b.needs_review} note={b.review_note} /></td>
                    <td className="txt">{label(b.kind)}</td>
                    <td className="txt">{(b.tiers ?? []).map((x) => `${tierText(x)}: ${b.kind === "RATE_UPLIFT" ? `+${x.value}%` : money(x.value, cur)}`).join(" · ")}</td>
                    <td className="txt"><Source source={b.source} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      ) : null}

      <Section title="No commission for">
        <div className="tbl-wrap" style={{ marginTop: 0 }}>
          <table className="cm-wrap">
            <thead><tr><th className="txt">What</th><th className="txt">Detail</th><th className="txt">Source</th></tr></thead>
            <tbody>
              {excluded.map((x) => (
                <tr key={x.id}><td className="txt">Territory ({label(x.scope ?? "COUNTRY").toLowerCase()})</td><td className="txt">{x.value}</td><td className="txt"><Source source={x.source} /></td></tr>
              ))}
              {(t.exclusions ?? []).map((x) => (
                <tr key={x.id}>
                  <td className="txt">{label(x.type)}</td>
                  <td className="txt">{[x.campus, (x.course_levels ?? []).join(", "), x.note, x.cap_count != null ? `cap ${x.cap_count}` : null].filter(Boolean).join(" · ") || "--"}</td>
                  <td className="txt"><Source source={x.source} /></td>
                </tr>
              ))}
              {!excluded.length && !t.exclusions?.length ? <tr><td className="txt dim" colSpan={3}>Nothing excluded.</td></tr> : null}
            </tbody>
          </table>
        </div>
        {included.length ? <p className="status">Only these territories: {included.map((x) => x.value).join(", ")}</p> : null}
      </Section>

      {t.notes?.length ? (
        <Section title="Notes">
          <ul className="cm-checks">
            {t.notes.map((n, i) => <li key={i} className="ok"><span className="mk">·</span><span>{n.text} <Source source={n.source} /></span></li>)}
          </ul>
        </Section>
      ) : null}
    </>
  );
}

function Simulator({ id, intake, terms }: { id: number; intake: string; terms: Resolved }) {
  const meta = useMeta();
  const levels = [...new Set((terms.rules ?? []).flatMap((r) => r.course_levels ?? []))];
  const [s, setS] = useState({
    course_level: levels[0] ?? "", nationality: "", residence: "", campus: "", fee: "15000", count: "1",
    position: "", bonus_count: "", flags: [] as string[], dates: {} as Record<string, string>,
  });
  const [res, setRes] = useState<SimResult | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const cur = terms.currency;

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      setRes(await simulate(id, {
        intake, course_level: s.course_level || null, nationality: s.nationality || null,
        residence: s.residence || null, campus: s.campus || null, fee: Number(s.fee) || 0,
        count: Number(s.count) || 1, position: s.position ? Number(s.position) : null,
        bonus_count: s.bonus_count ? Number(s.bonus_count) : null, flags: s.flags,
        dates: Object.fromEntries(Object.entries(s.dates).filter(([, v]) => v)),
      }));
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
  const r = res?.result;

  return (
    <div className="cm-card">
      <h3>Simulate a student</h3>
      <div className="cm-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <Field title="Course level" wide>
          <Select value={s.course_level} options={meta.data?.course_levels ?? levels}
                  labels={(v) => v} onChange={(v) => setS({ ...s, course_level: v ?? "" })} />
        </Field>
        <Field title="Nationality">
          <input list="cm-countries" value={s.nationality} onChange={(e) => setS({ ...s, nationality: e.target.value })} />
        </Field>
        <Field title="Residence">
          <input list="cm-countries" value={s.residence} onChange={(e) => setS({ ...s, residence: e.target.value })} />
        </Field>
        <Field title="Campus">
          {terms.campuses?.length ? (
            <Select value={s.campus} options={terms.campuses} labels={(v) => v} blank="Any" onChange={(v) => setS({ ...s, campus: v ?? "" })} />
          ) : <input value={s.campus} onChange={(e) => setS({ ...s, campus: e.target.value })} />}
        </Field>
        <Field title={`Tuition fee (${cur ?? "--"})`}>
          <input type="number" min={0} value={s.fee} onChange={(e) => setS({ ...s, fee: e.target.value })} />
        </Field>
        <Field title="Students counted" hint="Pooled count at the institution">
          <input type="number" min={1} value={s.count} onChange={(e) => setS({ ...s, count: e.target.value })} />
        </Field>
        <Field title="This student's position" hint="For marginal tiers">
          <input type="number" min={1} value={s.position} onChange={(e) => setS({ ...s, position: e.target.value })} />
        </Field>
        <Field title="Bonus count" hint="Defaults to students counted">
          <input type="number" min={0} value={s.bonus_count} onChange={(e) => setS({ ...s, bonus_count: e.target.value })} />
        </Field>
      </div>
      <datalist id="cm-countries">
        {(meta.data?.countries ?? []).map((c) => <option key={c.code} value={c.name} />)}
      </datalist>
      <div className="cm-checks-h">Flags</div>
      <div className="cm-row">
        {FLAGS.map(([k, l]) => (
          <label key={k} className="cm-check">
            <input type="checkbox" checked={s.flags.includes(k)}
                   onChange={(e) => setS({ ...s, flags: e.target.checked ? [...s.flags, k] : s.flags.filter((f) => f !== k) })} />
            {l}
          </label>
        ))}
      </div>
      {terms.conditional?.length ? (
        <>
          <div className="cm-checks-h">Student dates</div>
          <div className="cm-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            {DATE_KEYS.map(([k, l]) => (
              <Field key={k} title={l}>
                <input type="date" value={s.dates[k] ?? ""} onChange={(e) => setS({ ...s, dates: { ...s.dates, [k]: e.target.value } })} />
              </Field>
            ))}
          </div>
        </>
      ) : null}
      <div className="cm-foot">
        <button type="button" className="btn" disabled={busy} onClick={run}>{busy ? "Calculating…" : "Calculate"}</button>
      </div>
      <ErrorText error={err} />

      {r ? (
        <div style={{ marginTop: 14, borderTop: "1px solid var(--line-soft)", paddingTop: 14 }}>
          {!r.eligible ? (
            <>
              <div className="cm-total red">No commission</div>
              <p className="status err">{r.reason}</p>
              {r.source ? <Source source={r.source} /> : null}
            </>
          ) : (
            <>
              <div className="cm-total">{money(r.amount, r.currency)}</div>
              <div className="cm-sub">{r.rule?.name}{r.rate != null ? ` · ${r.rate}% in total` : ""} · {label(r.fee_basis)} fee</div>
              <ul className="cm-checks" style={{ marginTop: 10 }}>
                {r.breakdown?.map((b, i) => (
                  <li key={i} className="ok"><span className="mk">=</span>
                    <span>{money(b.amount, r.currency)} {b.label} <Source source={b.source} /><span className="why">{b.detail}</span></span></li>
                ))}
                {r.bonuses?.map((b) => (
                  <li key={b.id} className={b.reached ? "ok" : "wn"}><span className="mk">{b.reached ? "+" : "…"}</span>
                    <span>
                      {b.reached ? money(b.amount, r.currency) : "Not reached"} {b.criteria ?? label(b.kind)} <Source source={b.source} />
                      <Review on={b.needs_review} />
                      <span className="why">{[b.detail, b.progress ? `progress ${b.progress}` : null].filter(Boolean).join(" · ")}</span>
                    </span></li>
                ))}
              </ul>
              {r.lump_sums?.length ? <p className="status">Lump sums, paid separately: {r.lump_sums.map((l) => money(l.lump_sum, r.currency)).join(", ")}</p> : null}
              {r.vat ? (
                <dl className="cm-kv" style={{ marginTop: 10 }}>
                  <dt>VAT</dt><dd>{r.vat.detail}</dd>
                  <dt>Revenue ex VAT</dt><dd>{money(r.vat.revenue_ex_vat, r.currency)}</dd>
                  <dt>Invoice total</dt><dd>{money(r.vat.invoice_total, r.currency)}</dd>
                </dl>
              ) : null}
              {r.milestones?.length ? (
                <>
                  <div className="cm-checks-h">Paid on</div>
                  <ul className="cm-checks">
                    {r.milestones.map((m, i) => (
                      <li key={i} className="ok"><span className="mk">{m.pct}%</span>
                        <span>{money(m.amount, r.currency)} on {label(m.trigger).toLowerCase()}{m.n_weeks ? ` (${m.n_weeks} weeks)` : ""}</span></li>
                    ))}
                  </ul>
                </>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
