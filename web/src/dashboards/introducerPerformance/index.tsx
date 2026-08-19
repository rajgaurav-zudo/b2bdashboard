import { useSearchParams } from "react-router-dom";

import { useOverview } from "../../api/client";
import type { Overview, Tile } from "../../api/types";
import { n0, pct } from "../../format";
import { Band, Empty, Section, Spinner } from "../../ui/Primitives";
import { Critique } from "./Critique";
import { DrillDown } from "./DrillDown";
import { Funnel } from "./Funnel";
import { Notes } from "./Notes";
import { Tiles } from "./Tiles";

export function IntroducerPerformance({ slug }: { slug: string }) {
  const { data, isLoading, error } = useOverview(slug);
  // in the URL rather than in state: a call list is something people send to each other
  const [params, setParams] = useSearchParams();
  const selected = params.get("tile");
  const setSelected = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id === null || id === selected) next.delete("tile");
    else next.set("tile", id);
    setParams(next, { replace: true });
  };

  if (isLoading) return <Spinner label="Building the read model…" />;
  if (error) {
    return (
      <Empty title="Nothing to show yet">
        <p>{(error as Error).message}</p>
        <p>Load both exports on the <b>Data</b> tab, then come back.</p>
      </Empty>
    );
  }
  if (!data) return null;

  const byId = Object.fromEntries(data.tiles.map((t) => [t.id, t])) as Record<string, Tile>;
  const dormant = byId.dormant!;
  const resurrected = byId.resurrected!;
  const active = byId.active!;

  return (
    <>
      <div className="head">
        <h1>Which introducers used to pay us, and stopped</h1>
        <p>
          Every figure below is a deposit count for the {data.current_year} intake year or earlier.
          Start with <b>Dormant</b> — that is the call list.
        </p>
      </div>

      <ScopeBand overview={data} />
      <InFlightBand overview={data} />

      <Section
        title="Active"
        note={`${n0(active.stats.n)} introducers produced ${n0(active.stats.cur)} active deposits in the ${data.current_year} intake. Cohort tiles split them by the year they became a customer.`}
      >
        <Tiles tiles={data.tiles} section="active" currentYear={data.current_year}
               selected={selected} onSelect={setSelected} />
      </Section>

      <Band icon="→">
        <b>Where to start.</b>{" "}
        {n0(data.dormant_still_applying)} of the {n0(dormant.stats.n)} dormant introducers are{" "}
        <b>still submitting applications</b> in {data.current_year} — they have not left, they have
        stopped converting. That is a pipeline problem and far cheaper to fix than a cold
        reactivation. The other {n0(dormant.stats.n - data.dormant_still_applying)} have gone quiet
        entirely and need a relationship rebuilt. For comparison, win-backs currently landing:{" "}
        <b>{n0(resurrected.stats.n)}</b> resurrected introducers, {n0(resurrected.stats.cur)} deposits.
      </Band>

      <Section title="Leakage" note="Revenue that used to arrive, or never did.">
        <Tiles
          tiles={data.tiles} section="leak" currentYear={data.current_year}
          selected={selected} onSelect={setSelected}
          extra={(tile) => tile.id === "dormant"
            ? `${n0(data.dormant_still_applying)} still submitting applications`
            : null}
        />
      </Section>

      <Section title="Quality" note="Read these alongside country. See the critique below.">
        <Tiles tiles={data.tiles} section="quality" currentYear={data.current_year}
               selected={selected} onSelect={setSelected} />
      </Section>

      {selected ? (
        <DrillDown slug={slug} tileId={selected} onClose={() => setSelected(null)} />
      ) : null}

      <Section
        title="Conversion funnel by intake year"
        note={
          <>
            Intake cycle: Nov &amp; Dec roll into the following January; Apr–Jul fold to May; Aug–Oct
            to September. Both scopes exclude the{" "}
            {pct(data.data.blank_intro, data.data.app_rows)} of applications with no introducer name.
            {data.data.no_year
              ? ` ${n0(data.data.no_year)} applications have no usable intake year and sit outside this table.`
              : null}
          </>
        }
      >
        <Funnel overview={data} />
      </Section>

      <Section title="What these thresholds actually measure">
        <Critique overview={data} />
      </Section>

      <Section title="Data notes">
        <Notes overview={data} />
      </Section>
    </>
  );
}

function ScopeBand({ overview }: { overview: Overview }) {
  const customerStage = overview.by_stage.find((s) => s.stage === "Customer");
  const droppedByStrictFilter = overview.totals.act_life - (customerStage?.act ?? 0);
  return (
    <Band>
      <b>Scope.</b> {n0(overview.book_size)} introducers are in scope — every partner at{" "}
      <i>Customer</i> stage, plus anyone with a paid deposit at any stage. Together they hold{" "}
      <b>{n0(overview.totals.act_life)} active</b> and <b>{n0(overview.totals.clos_life)} closed</b>{" "}
      deposits, {n0(overview.totals.act_cur)} of them active in the {overview.current_year} intake.{" "}
      {overview.by_stage.map((s, i) => (
        <span key={s.stage}>
          {i ? " · " : ""}<b>{n0(s.n)}</b> {s.stage} ({n0(s.act)} active dep.)
        </span>
      ))}
      . A strict <i>Customer</i>-only filter would drop {n0(droppedByStrictFilter)} active deposits.{" "}
      {n0(overview.data.blank_intro)} applications (
      {pct(overview.data.blank_intro, overview.data.app_rows)}) carry no introducer name and are
      excluded from every introducer-level figure — these totals will not tie to overall revenue
      reporting.
    </Band>
  );
}

function InFlightBand({ overview }: { overview: Overview }) {
  const current = overview.funnel.scope.find((r) => r.y === overview.current_year);
  const previous = overview.funnel.scope.find((r) => r.y === overview.previous_year);
  return (
    <Band tone="warn">
      <b>The {overview.current_year} intake is still in flight.</b>{" "}
      {current && previous ? (
        <>
          Visa and enrolment ratios are only meaningful for closed intakes: {overview.current_year}{" "}
          shows <b>{pct(current.enr, current.act)}</b> deposit→enrolled against{" "}
          <b>{pct(previous.enr, previous.act)}</b> for {overview.previous_year}, and{" "}
          <b>{pct(current.vg, current.act)}</b> vs <b>{pct(previous.vg, previous.act)}</b> for visas.
          That gap is students not having reached those stages yet — not a collapse in quality.{" "}
        </>
      ) : null}
      Treat every {overview.current_year} figure as a <b>floor</b>: deposits keep landing after the
      export date. Rows dated after {overview.current_year} appear in the funnel table but are
      excluded from all tile scoring, so a single future-dated deposit cannot flip an introducer out
      of dormant.
    </Band>
  );
}
