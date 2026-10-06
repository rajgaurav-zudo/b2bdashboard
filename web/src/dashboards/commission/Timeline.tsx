import { when } from "../../format";
import { Band, Section, Spinner } from "../../ui/Primitives";
import { useTimeline } from "./api";
import { ErrorText, Review, Source, day, intakeLabel, label, useNav } from "./shared";

/** "Terms by intake": what resolveTerms gives for each major intake around
 *  today, so a gap (no valid contract for Sep 2027) shows before it bites. */
export function Timeline({ id }: { id: number }) {
  const { params, go } = useNav();
  const { data, isLoading, error } = useTimeline(id);
  if (isLoading) return <Spinner />;
  if (error || !data) return <ErrorText error={error} />;

  const picked = params.get("intake");
  const col = data.columns.find((c) => c.intake === picked)
    ?? data.columns.find((c) => c.in_default && !c.past) ?? data.columns[0];
  const scope = data.validity.scope;

  return (
    <>
      <div style={{ display: "grid", gap: 8, marginTop: 16 }}>
        {data.alerts.map((a) => (
          <Band key={a.intake} tone="warn">
            <b>No terms for {a.label}.</b> {a.reason}
          </Band>
        ))}
      </div>

      <Section title="Terms by intake"
               note={<>
                 Valid {day(data.validity.start)} – {data.validity.rolling ? "rolling" : day(data.validity.end)}
                 {scope ? <> · intakes: {scope.mode === "UP_TO" ? `up to ${intakeLabel(scope.until_intake)}`
                   : scope.mode === "INTAKES" ? (scope.intakes ?? []).map(intakeLabel).join(", ") : "every intake"}</> : null}
                 . Pick an intake to see its terms.
               </>}>
        <div className="cm-tl">
          <div className="cm-tl-grid">
            {data.columns.map((c) => (
              <button key={c.intake} type="button" aria-pressed={c.intake === col?.intake}
                      className={`cm-col${c.past ? " past" : ""}${c.ok ? "" : " none"}`}
                      onClick={() => go({ intake: c.intake }, true)}>
                <div className="lbl">
                  {c.label}
                  {c.current ? <span className="pill live">now</span> : null}
                  {c.summary ? <span className="dim" style={{ marginLeft: "auto", fontSize: 11 }}>v{c.summary.version}</span> : null}
                </div>
                {c.summary ? (
                  <>
                    {c.summary.rules.slice(0, 4).map((r, i) => (
                      <div key={i} className="ln"><span>{r.name}</span><span>{r.rate}</span></div>
                    ))}
                    {c.summary.rules.length > 4 ? <div className="ln dim">+{c.summary.rules.length - 4} more rules</div> : null}
                    <div className="ln dim">
                      <span>{c.summary.bonuses.length} bonus{c.summary.bonuses.length === 1 ? "" : "es"}
                        {c.summary.applied.length ? ` · ${c.summary.applied.length} amendment${c.summary.applied.length === 1 ? "" : "s"}` : ""}</span>
                    </div>
                  </>
                ) : <div className="why">{c.reason}</div>}
              </button>
            ))}
          </div>
        </div>
      </Section>

      {col ? (
        <div className="cm-split">
          <div className="cm-card">
            <h3>
              {col.label}
              <button type="button" className="cm-link" style={{ float: "right", fontSize: 12.5, fontWeight: 500 }}
                      onClick={() => go({ tab: "effective", intake: col.intake })}>
                Full effective terms and simulator →
              </button>
            </h3>
            {!col.summary ? <p className="red">{col.reason}</p> : (
              <>
                <div className="tbl-wrap" style={{ marginTop: 0 }}>
                  <table>
                    <thead><tr><th className="txt">Rule</th><th>Rate</th><th className="txt">Source</th></tr></thead>
                    <tbody>
                      {col.summary.rules.map((r, i) => (
                        <tr key={i}><td className="txt">{r.name}</td><td className="num">{r.rate}</td><td className="txt"><Source source={r.source} /></td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {col.summary.bonuses.length ? (
                  <div className="tbl-wrap">
                    <table className="cm-wrap">
                      <thead><tr><th className="txt">Bonus</th><th className="txt">Kind</th><th className="txt">Source</th></tr></thead>
                      <tbody>
                        {col.summary.bonuses.map((b, i) => (
                          <tr key={i}><td className="txt">{b.criteria ?? "--"}</td><td className="txt">{label(b.kind)}</td>
                            <td className="txt"><Source source={b.source} /></td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                {col.summary.excluded.length ? (
                  <p className="status">Territories excluded:{" "}
                    {col.summary.excluded.map((x, i) => <span key={i}>{i ? ", " : ""}{x.value} <Source source={x.source} /></span>)}
                  </p>
                ) : null}
              </>
            )}
          </div>

          <div className="cm-sticky">
            <div className="cm-card">
              <h3>History</h3>
              <ul className="cm-checks">
                {data.versions.map((v) => (
                  <li key={`v${v.version}`} className="ok">
                    <span className="mk">v{v.version}</span>
                    <span>Base v{v.version} effective {day(v.effective_from)}
                      <span className="why">published {when(v.published_at)}{v.published_by ? ` by ${v.published_by}` : ""}</span></span>
                  </li>
                ))}
                {data.amendments.map((a) => (
                  <li key={`a${a.id}`} className={a.status === "PUBLISHED" ? "ok" : "wn"}>
                    <span className="mk">#{a.number}</span>
                    <span>
                      <button type="button" className="cm-link" onClick={() => go({ tab: "amendments", a: a.id, step: 4 })}>
                        {label(a.type)}
                      </button>{" "}
                      <span className="dim">{label(a.status)}</span> <Review on={a.needs_review} />
                      <span className="why">
                        {a.scope_mode === "DATE_WINDOW" ? `${day(a.window_start)} – ${day(a.window_end)}`
                          : `${intakeLabel(a.from_intake)}${a.until_intake ? ` – ${intakeLabel(a.until_intake)}` : " onwards"}`}
                        {a.summary ? ` · ${a.summary}` : ""}
                      </span>
                    </span>
                  </li>
                ))}
                {!data.versions.length && !data.amendments.length ? <li className="wn"><span className="mk">!</span>Nothing published yet.</li> : null}
              </ul>
            </div>
            <div className="cm-card">
              <h3>Contract checks</h3>
              <div className={`cm-ready ${data.checks.ready ? "yes" : "no"}`}>
                {data.checks.ready ? "Base terms complete" : `${data.checks.failing} required item${data.checks.failing === 1 ? "" : "s"} missing`}
              </div>
              {data.checks.warnings.length ? <p className="status">{data.checks.warnings.length} warning{data.checks.warnings.length === 1 ? "" : "s"}, mostly imported items to review.</p> : null}
              <button type="button" className="cm-link" onClick={() => go({ tab: "base" })}>Open base terms →</button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
