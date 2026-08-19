import type { Overview } from "../../api/types";
import { n0, pct, pctOf } from "../../format";

function Verdict({ bad, children }: { bad: boolean; children: string }) {
  return <span className={`verdict ${bad ? "bad" : "ok"}`}>{children}</span>;
}

/** The thresholds this dashboard was asked for, measured against the file that
 *  was actually loaded. The point is to keep the criticism visible next to the
 *  numbers it applies to, not to bury it in a document nobody opens. */
export function Critique({ overview }: { overview: Overview }) {
  const { enrolment, closures, visa_by_country } = overview.critique;
  const cadence = overview.cadence;
  const annual = [...cadence].filter((c) => c.top >= 0.55).sort((a, b) => b.top - a.top).slice(0, 5);
  const spread = [...cadence].filter((c) => c.top < 0.45).sort((a, b) => a.top - b.top).slice(0, 5);
  const name = (c: typeof cadence[number]) =>
    `${c.country} ${Math.round(100 * c.top)}% ${c.peak}`;

  return (
    <div className="card pad critique">
      <h3>
        App-to-enrolment below 10%
        <Verdict bad={enrolment.miscalibrated}>
          {enrolment.miscalibrated ? "miscalibrated" : "holds up"}
        </Verdict>
      </h3>
      <p>
        The threshold catches <span className="k">{n0(enrolment.under_10)}</span> of{" "}
        <span className="k">{n0(enrolment.base)}</span> qualifying introducers —{" "}
        <span className="k">{pct(enrolment.under_10, enrolment.base, 0)}</span> of the base.
        Org-wide enrolment conversion is <span className="k">{pctOf(enrolment.org_rate, 2)}</span> and
        the median qualifying introducer sits at <span className="k">{pctOf(enrolment.median_rate)}</span>.{" "}
        {enrolment.miscalibrated
          ? "A rule that flags most of the population describes the business; it does not isolate a problem group."
          : "On this file the rule stays selective enough to be actionable."}
      </p>
      <ul>
        <li>Below 5% catches <span className="k">{n0(enrolment.under_5)}</span>.</li>
        <li>Below 3% catches <span className="k">{n0(enrolment.under_3)}</span>.</li>
        <li>
          Better still: benchmark each introducer against the median of <b>their own market</b>, not one
          global number. Enrolment rates are set as much by destination-country visa regimes as by
          partner quality.
        </li>
      </ul>

      <h3>
        Closed deposits above 30%
        <Verdict bad={closures.miscalibrated}>
          {closures.miscalibrated ? "miscalibrated" : "holds up"}
        </Verdict>
      </h3>
      <p>
        The median introducer with 3+ active deposits closes{" "}
        <span className="k">{pctOf(closures.median_ratio)}</span> of them, so a 30% line sits almost
        exactly on the middle of the distribution and splits the base in half rather than isolating
        outliers. It currently flags <span className="k">{n0(closures.over_30)}</span> of{" "}
        <span className="k">{n0(closures.base)}</span>.
      </p>
      <ul>
        <li>Above 50% catches <span className="k">{n0(closures.over_50)}</span>.</li>
        <li>
          Above 100% catches <span className="k">{n0(closures.over_100)}</span> — introducers whose
          closed deposits <i>outnumber</i> their active ones. That last group is the real signal.
        </li>
      </ul>

      <h3>
        “Squanderer” / “resource waster” as a label
        <Verdict bad>not supported by the data</Verdict>
      </h3>
      <p>
        The label is a judgement the data cannot carry. An introducer whose students are repeatedly
        visa-refused is not wasting resources — their market is. Visa-stage losses concentrate by
        geography:{" "}
        {visa_by_country.length
          ? visa_by_country.map((v, i) => (
              <span key={v.country}>
                {i ? " · " : ""}{v.country} <span className="k">{n0(v.n)}</span>
              </span>
            ))
          : "no visa losses recorded"}
        . Read visa and closure metrics alongside country, never as a partner scorecard, and do not let
        them drive commission decisions.
      </p>

      <h3>What the deposit count cannot tell you</h3>
      <p>
        Commission value is absent from both exports, so deposit <i>count</i> stands in for revenue.
        Partners differ in commission rate and contract type, so the leaderboard here is a volume
        ranking, not a value ranking. Joining <span className="k">Org Commission</span> would reshuffle it.
      </p>

      <h3>Cadence: do not measure every market against three intakes</h3>
      <p>
        Measured across the <span className="k">{n0(cadence.length)}</span> markets with 20+ active
        deposits:{" "}
        {annual.length
          ? <>
              <b>{n0(annual.length)}</b> concentrate more than 55% of their deposits in a single
              intake — {annual.map(name).join(" · ")}.{" "}
            </>
          : "no market concentrates more than 55% of its deposits in one intake. "}
        {spread.length
          ? <>The most spread markets sit close to an even three-way split — {spread.map(name).join(" · ")}. </>
          : null}
        For a single-cycle market one missed September costs a full year, not a third of one, so the
        same dormancy rule flags its steadiest partners first. Check the <b>Country</b> grouping of any
        drill-down before acting on a call list.
      </p>
    </div>
  );
}
