import type { LogOverview, Quote } from "../../api/types";
import { n0, pct } from "../../format";
import { Band } from "../../ui/Primitives";
import { colourFor, dayLabel } from "./weeks";

/** Keyword-lexicon scoring of the Note column, over the same scoped set as the
 *  tables above — so it answers for the range, team and type on screen rather
 *  than for the whole file.
 *
 *  A note matching no lexicon term counts as neutral, not as missing. A week of
 *  terse "called, no answer" notes should not read as glowing because the three
 *  notes that did score were positive. */
export function Sentiment({ overview }: { overview: LogOverview }) {
  const s = overview.sentiment;
  const colour = colourFor(overview.log_types.map((t) => t.type));
  const index = s.index ?? 0;
  // -1..+1 mapped onto the width of the meter
  const position = `${((index + 1) / 2) * 100}%`;
  const tone = index > 0.05 ? "good" : index < -0.05 ? "bad" : "flat";

  return (
    <>
      <div className="sent">
        <div className="sent-index">
          <div className="metric" style={{ color: `var(--${tone === "flat" ? "muted" : tone})` }}>
            {index >= 0 ? "+" : ""}{index.toFixed(2)}
          </div>
          <div className="metric-l">sentiment index · −1 to +1</div>
          <div className="meter">
            <span className="zero" />
            <span className="pin" style={{ left: position }} />
          </div>
          <p className="cap">
            Mean over all {n0(s.n)} logs in range. {n0(s.scored)} matched a lexicon term
            ({pct(s.scored, s.n, 0)}); the rest count as neutral.
          </p>
        </div>

        <div className="sent-split">
          <Split label="Positive" n={s.positive} total={s.n} tone="good" />
          <Split label="Negative" n={s.negative} total={s.n} tone="bad" />
          <Split label="Mixed" n={s.mixed} total={s.n} tone="warn" />
          <Split label="No keyword" n={s.n - s.scored} total={s.n} tone="faint" />
        </div>

        <div className="sent-types">
          <h4>By log type</h4>
          <table>
            <tbody>
              {s.by_type.map((row) => (
                <tr key={row.type}>
                  <td className="txt">
                    <span className="swatch" style={{ background: colour(row.type) }} />
                    {row.type}
                  </td>
                  <td className="num dim">{n0(row.n)}</td>
                  <td className="num" style={{
                    color: row.index > 0.05 ? "var(--good)" : row.index < -0.05 ? "var(--bad)" : "var(--muted)",
                  }}>
                    {row.index >= 0 ? "+" : ""}{row.index.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="quotes">
        <Quotes title="Most positive notes" rows={s.quotes.pos} tone="good" />
        <Quotes title="Most negative notes" rows={s.quotes.neg} tone="bad" />
      </div>

      <Band tone="warn">
        <b>Read the index as a direction, not a measurement.</b> It is a keyword lexicon with no
        grammar beyond one rule: negative phrases are struck out before positives are counted, so
        “not interested” scores −1 rather than cancelling itself. It has no sarcasm and no domain
        training. <i>Pending</i> and <i>chasing</i> count negative, which is right for a follow-up
        log and wrong for a note saying a visa is pending as a matter of fact. The lexicon lives in{" "}
        <code>dashboards/logs/ingest.py</code> and is scored at ingest, so changing it means
        re-projecting the archived upload rather than asking for a fresh export.
      </Band>
    </>
  );
}

function Split({ label, n, total, tone }: { label: string; n: number; total: number; tone: string }) {
  return (
    <div className="split">
      <span className={`bar ${tone}`} style={{ width: total ? `${(100 * n) / total}%` : "0%" }} />
      <b>{n0(n)}</b>
      <span>{label}</span>
      <i>{pct(n, total, 0)}</i>
    </div>
  );
}

function Quotes({ title, rows, tone }: { title: string; rows: Quote[]; tone: "good" | "bad" }) {
  return (
    <div className={`quote-card ${tone}`}>
      <h4>{title}</h4>
      {rows.length === 0 ? (
        <p className="cap">No note in range scored on this side.</p>
      ) : rows.map((q, i) => (
        <blockquote key={`${q.logged_on}-${i}`}>
          {/* clamped to four lines in CSS; the full note is still here, and the
              drill-down pane shows it whole */}
          <p title={q.note}>“{q.note}”</p>
          <cite>
            {q.introducer} · {q.creator} · {dayLabel(q.logged_on)}
            <span className="score">{q.score >= 0 ? "+" : ""}{q.score.toFixed(2)}</span>
          </cite>
        </blockquote>
      ))}
    </div>
  );
}
