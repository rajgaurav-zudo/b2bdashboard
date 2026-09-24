import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useOverview } from "../../api/client";
import type { Overview, OverviewTotals, Tile } from "../../api/types";
import { n0, pct } from "../../format";
import { Band, Empty, Section, Seg, Spinner } from "../../ui/Primitives";
import { CourseSplit } from "./CourseSplit";
import { Critique } from "./Critique";
import { FilterBar, type Selection } from "./FilterBar";
import { Funnel } from "./Funnel";
import { Notes } from "./Notes";
import { SidePane } from "./SidePane";
import { Tiles } from "./Tiles";

/** The URL keys the server reads as filters. `compare` only changes the overview. */
const FILTER_KEYS = ["from", "to", "regions", "teams", "cycles"] as const;

export function IntroducerPerformance({ slug }: { slug: string }) {
  // in the URL rather than in state: a call list is something people send to each other
  const [params, setParams] = useSearchParams();
  const filters: Record<string, string> = {};
  for (const k of FILTER_KEYS) {
    const v = params.get(k);
    if (v) filters[k] = v;
  }
  const compare = params.get("compare") === "1";
  const selection: Selection = {
    regions: (params.get("regions") ?? "").split("|").filter(Boolean),
    teams: (params.get("teams") ?? "").split("|").filter(Boolean),
    cycles: (params.get("cycles") ?? "").split(",").filter(Boolean).map(Number),
  };
  const { data, isLoading, error } = useOverview(slug, compare ? { ...filters, compare: "1" } : filters);
  const [scope, setScope] = useState<"scope" | "all">("scope");
  const selected = params.get("tile");
  /** null or "" removes a key */
  const set = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    setParams(next, { replace: true });
  };
  const setSelected = (id: string | null) => set({ tile: id });

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
      <FilterBar overview={data} selection={selection} set={set} />

      <ScopeBand overview={data} />

      <Section
        title="Active introducers"
        note={`${n0(active.stats.n)} introducers produced ${n0(active.stats.cur)} active Academic deposits in the ${data.period.label} ${data.period.whole_year ? "intake" : "intake window"}. Cohort tiles split them by the year they became a customer. DAA and PD are shown under each tile and are not counted in the deposit figure above them.`}
      >
        <Tiles tiles={data.tiles} section="active" periodLabel={data.period.label} compare={data.compare} onOpen={setSelected} />
      </Section>

      <Section
        title="Language &amp; pre-sessional"
        note={`Every deposit figure elsewhere on this page is Academic only. Language and pre-sessional English intakes behave nothing like a degree intake, so they are reported here instead of being averaged into it.`}
      >
        <CourseSplit rows={data.course_split} periodLabel={data.period.label} />
      </Section>

      <Section title="Leaking revenue" note="Partners who paid before and don't now, plus effort that never converted.">
        <Tiles
          tiles={data.tiles} section="leak" periodLabel={data.period.label} compare={data.compare} onOpen={setSelected}
          extra={(tile) => tile.id === "dormant"
            ? `${n0(data.dormant_still_applying)} still submitting applications`
            : null}
        />
        <div className="band info" style={{ marginTop: 14 }}>
          <span className="ic">→</span>
          <div>
            <b>Where to start.</b>{" "}
            {n0(data.dormant_still_applying)} of the {n0(dormant.stats.n)} dormant introducers are{" "}
            <b>still submitting applications</b> in {data.period.label} — they have not left, they
            have stopped converting. That is a pipeline problem and far cheaper to fix than a cold
            reactivation. The other {n0(dormant.stats.n - data.dormant_still_applying)} have gone
            quiet entirely and need a relationship rebuilt. For comparison, win-backs currently
            landing: <b>{n0(resurrected.stats.n)}</b> resurrected introducers,{" "}
            {n0(resurrected.stats.cur)} deposits.
          </div>
        </div>
      </Section>

      <Section
        title="Quality"
        note="Where applications and deposits are being lost. Read alongside country — see the critique below."
      >
        <Tiles tiles={data.tiles} section="quality" periodLabel={data.period.label} compare={data.compare} onOpen={setSelected} />
      </Section>

      <Section
        title="Conversion funnel"
        note={`By intake cycle year. Nov–Dec roll into the following January.${
          data.period.is_default ? "" : " Every year is shown: the date range does not apply here."}`}
        aside={
          <Seg
            value={scope}
            onChange={setScope}
            options={[
              { value: "scope", label: "In-scope introducers" },
              { value: "all", label: "All attributed" },
            ]}
          />
        }
      >
        <InFlightBand overview={data} />
        <Funnel overview={data} scope={scope} />
        <p style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8 }}>
          Intake cycle: Nov &amp; Dec roll into the following January; Apr–Jul fold to May; Aug–Oct
          to September. <b>In-scope</b> counts only introducers in the book above; <b>all
          attributed</b> adds every named introducer, including those with applications but no
          deposits and no Customer record. Both exclude the{" "}
          {pct(data.data.blank_intro, data.data.app_rows)} of applications with no introducer name.
          {data.data.no_year
            ? ` ${n0(data.data.no_year)} applications have no usable intake year and sit outside this table.`
            : null}
        </p>
      </Section>

      <Section title="Critique of the metric definitions" note="Thresholds tested against this file, not assumed.">
        <Critique overview={data} />
      </Section>

      <Section
        title="Data notes"
        note="Everything below is measured from the files you loaded. It changes what the numbers can be used for."
      >
        <Notes overview={data} />
      </Section>

      <SidePane slug={slug} tileId={selected} filters={filters} onClose={() => setSelected(null)} />
    </>
  );
}

function ScopeBand({ overview }: { overview: Overview }) {
  const customerStage = overview.by_stage.find((s) => s.stage === "Customer");
  const droppedByStrictFilter = overview.totals.act_life - (customerStage?.act ?? 0);
  return (
    <div className="band info" style={{ marginTop: 34 }}>
      <span className="ic">◆</span>
      <div>
        <b>Scope.</b> {n0(overview.book_size)} introducers are in scope — every partner at{" "}
        <i>Customer</i> stage, plus anyone with a paid deposit at any stage. Together they hold{" "}
        <b>{n0(overview.totals.act_life)} active</b> and <b>{n0(overview.totals.clos_life)} closed</b>{" "}
        deposits, {n0(overview.totals.act_cur)} of them active in the {overview.period.label}{" "}
        {overview.period.whole_year ? "intake" : "intake window"}.{" "}
        {overview.compare ? <CompareLine now={overview} /> : null}
        {overview.by_stage.map((s, i) => (
          <span key={s.stage}>
            {i ? " · " : ""}<b>{n0(s.n)}</b> {s.stage} ({n0(s.act)} active dep.)
          </span>
        ))}
        . A strict <i>Customer</i>-only filter would drop {n0(droppedByStrictFilter)} active
        deposits. {n0(overview.data.blank_intro)} applications (
        {pct(overview.data.blank_intro, overview.data.app_rows)}) carry no introducer name and are
        excluded from every introducer-level figure — these totals will not tie to overall revenue
        reporting.
      </div>
    </div>
  );
}

/** The scope totals against the same filters one period earlier. */
function CompareLine({ now }: { now: Overview }) {
  const before = now.compare!;
  // `invert`: a rise in lost deposits is the bad direction
  const row = (label: string, a: number, b: number, invert = false) => {
    const change = a - b;
    const good = invert ? -change : change;
    return (
      <span className={`ip-cmp ${good > 0 ? "up" : good < 0 ? "down" : "flat"}`}>
        {label} <b>{change > 0 ? "+" : ""}{n0(change)}</b> ({n0(b)} → {n0(a)})
      </span>
    );
  };
  const t = (k: keyof OverviewTotals) => [now.totals[k], before.totals[k]] as const;
  return (
    <>
      Against <b>{before.label}</b>:{" "}
      {row("active deposits in the window", ...t("act_cur"))} ·{" "}
      {row("paid then lost in the window", ...t("clos_cur"), true)}.{" "}
    </>
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
      export date. Rows dated after {overview.current_year} appear in the table below but are
      excluded from all tile scoring, so a single future-dated deposit cannot flip an introducer out
      of dormant.
    </Band>
  );
}
