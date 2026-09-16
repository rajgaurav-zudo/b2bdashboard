import type { I360Overview } from "../../api/types";
import { n0, pct } from "../../format";
import { Band, Note } from "../../ui/Primitives";
import { dayLabel } from "./dates";

/** Who this partner is, from the master file, and what they have done over
 *  their whole life rather than inside the window. This is the half that makes
 *  it a 360 rather than a pipeline. */
export function Profile({ overview }: { overview: I360Overview }) {
  const { profile, lifetime, selected } = overview;
  if (selected.length === 0) {
    return (
      <Band>
        No introducer is selected, so everything below is the whole book. Pick one in
        the <b>Introducer</b> filter to see their record — the CRM profile, the lifetime
        figures and the pipeline all narrow together.
      </Band>
    );
  }
  return (
    <>
      {selected.length > 1 ? (
        <Band>
          {selected.length} introducers are selected. The lifetime figures are their
          total; the CRM profile needs exactly one partner to name.
        </Band>
      ) : null}
      <div className="i360-360">
        {profile ? (
          <div className="i360-profile">
            <Field k="Lifecycle stage" v={profile.stage} />
            <Field k="Contract" v={profile.contract} />
            <Field k="Country" v={profile.country} />
            <Field k="SRM team" v={profile.team} />
            <Field k="SRM owner" v={profile.srm} />
            <Field k="Customer since" v={profile.since ? String(profile.since) : "--"} />
          </div>
        ) : selected.length === 1 ? (
          <Band tone="warn">
            <b>{selected[0]}</b> is not in the introducers master.
            {" "}The name appears in the applications export, so the pipeline below is real;
            the CRM profile is not available until that file is loaded, or until the partner
            is created in the CRM.
          </Band>
        ) : null}

        <div className="i360-life">
          <Life k="Applications" v={lifetime.apps} />
          <Life k="Reached Applied" v={lifetime.applied} of={lifetime.apps} />
          <Life k="Reached Offer" v={lifetime.offers} of={lifetime.apps} />
          <Life k="Deposits standing" v={lifetime.deposits_live} of={lifetime.apps} />
          <Life k="Enrolled" v={lifetime.enrolled} of={lifetime.apps} />
          <Life k="Closed lost" v={lifetime.lost} of={lifetime.apps} />
        </div>
      </div>
      <p className="i360-foot">
        Lifetime, not windowed: the date range on the cards does not touch these.
        {" "}First seen <b>{dayLabel(lifetime.first_seen)}</b>, last seen{" "}
        <b>{dayLabel(lifetime.last_seen)}</b>.
      </p>
    </>
  );
}

function Field({ k, v }: { k: string; v: string }) {
  return <div className="f"><span>{k}</span><b>{v}</b></div>;
}

function Life({ k, v, of }: { k: string; v: number; of?: number }) {
  return (
    <div className="l">
      <b className="num">{n0(v)}</b>
      <span>{k}</span>
      {of !== undefined ? <i className="num">{pct(v, of, 0)}</i> : null}
    </div>
  );
}

/** Deposits paid for the selected intake against the same point in the intake a
 *  year earlier. It deliberately looks past the intake filter: comparing one
 *  intake with the one before it cannot be done inside a population already
 *  narrowed to a single intake. */
export function Commitment({ overview }: { overview: I360Overview }) {
  const c = overview.commitment;
  const delta = c.prev_paid_to_date ? (100 * (c.now_paid - c.prev_paid_to_date)) / c.prev_paid_to_date : null;
  return (
    <div className="i360-commit">
      <div className="c">
        <b className="num">{n0(c.now_paid)}</b>
        <span>deposits standing for the {c.intake_year} intake</span>
        <i>of {n0(c.now_apps)} applications · {pct(c.now_paid, c.now_apps, 1)}</i>
      </div>
      <div className="c">
        <b className="num">{n0(c.prev_paid_to_date)}</b>
        <span>{c.intake_year - 1} intake, by this day last year</span>
        <i>{n0(c.prev_paid_total)} in the end</i>
      </div>
      <div className="c">
        <b className={`num ${delta === null ? "" : delta >= 0 ? "up" : "down"}`}>
          {delta === null ? "--" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}%`}
        </b>
        <span>against the same point last year</span>
        <i>
          {c.prev_paid_total
            ? <>last year finished {pct(c.prev_paid_total - c.prev_paid_to_date, c.prev_paid_total, 0)} above this point</>
            : <>no deposits last year to compare with</>}
        </i>
      </div>
    </div>
  );
}

export function Notes({ overview }: { overview: I360Overview }) {
  const d = overview.data;
  return (
    <div className="notes-grid">
      <Note title="Rows with no stage timestamp">
        <b className="fig">{n0(d.no_stage_dates)}</b> of <b className="fig">{n0(d.app_rows)}</b>{" "}
        applications carry no stage date at all. They can never appear in a windowed
        card — this dashboard reads the <code>Timestamp of …</code> columns, and an export
        written before they existed loads cleanly and shows an empty pipeline.
      </Note>
      <Note title="Deposits with no deposit date">
        <b className="fig">{n0(d.paid_without_date)}</b> applications are fully paid but have
        no <code>Deposit Fully Paid</code> timestamp. They count in the lifetime and intake
        figures, which read the flag, and never in the Deposits card, which reads the date.
      </Note>
      <Note title="Applications no introducer owns">
        <b className="fig">{n0(d.no_introducer)}</b> rows have a blank introducer. They are
        shown as <b>Not attributed</b> rather than dropped, so the whole-book totals are the
        whole book.
      </Note>
      <Note title="The master file">
        {d.master_rows
          ? <>The CRM profile is drawn from <b className="fig">{n0(d.master_rows)}</b> partner
             records. <b className="fig">{n0(d.no_intake_year)}</b> applications carry no intake
             year and fall out of every intake filter.</>
          : <>No introducers master is loaded, so the CRM profile is unavailable. Everything
             else on this page reads the applications export and is unaffected.</>}
      </Note>
    </div>
  );
}
