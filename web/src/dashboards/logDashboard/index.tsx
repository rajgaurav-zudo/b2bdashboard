import { useSearchParams } from "react-router-dom";

import { useView } from "../../api/client";
import type { LogOverview } from "../../api/types";
import { n0, pct } from "../../format";
import { Band, Empty, Section, Spinner } from "../../ui/Primitives";
import { LeaderPane } from "./LeaderPane";
import { LogPane } from "./LogPane";
import { Notes } from "./Notes";
import { Sentiment } from "./Sentiment";
import { scopeLabel } from "./teams";
import { TopPerformers, type Dimension } from "./TopPerformers";
import { WeekBar } from "./WeekBar";
import { WeekOnWeek } from "./WeekOnWeek";
import { WeekTiles } from "./WeekTiles";
import { weekLabel } from "./weeks";

/** The week, the filters and the range live in the URL rather than in state: a
 *  week that needs explaining is something people send to each other. */
export function LogDashboard({ slug }: { slug: string }) {
  const [params, setParams] = useSearchParams();
  // the drill-down is in the URL too, for the same reason the week is: a list
  // of "who did we actually call" is something people send to each other.
  // "all" = every type in the week; a type name = that type; absent = closed.
  const open = params.get("open");
  const pane = open === null ? false : open === "all" ? null : open;
  // "view more" on a top-performer table. Separate from `open` so both are
  // independently shareable; only one is ever on screen.
  const more = params.get("more") as Dimension | null;

  const query = {
    week: params.get("week") ?? undefined,
    region: params.get("region") ?? undefined,
    team: params.get("team") ?? undefined,
    type: params.get("type") ?? undefined,
    weeks: params.get("weeks") ?? undefined,
  };
  const { data, isLoading, error } = useView<LogOverview>(slug, "overview", query);

  const set = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  };

  if (isLoading) return <Spinner label="Reading the activity log…" />;
  if (error) {
    return (
      <Empty title="Nothing to show yet">
        <p>{(error as Error).message}</p>
        <p>Load the activity log on the <b>Data</b> tab, then come back.</p>
      </Empty>
    );
  }
  if (!data) return null;

  const step = (direction: -1 | 1) => {
    const weeks = data.weeks.map((w) => w.w);
    const next = weeks[weeks.indexOf(data.week) + direction];
    if (next) set({ week: next });
  };

  return (
    <>
      <WeekBar
        overview={data}
        onStep={step}
        onJumpToCurrent={() => set({ week: null })}
        onFilter={(changes) => set(changes)}
      />

      <Section
        title="Selected week by log type"
        note={<>
          {weekLabel(data.week)} — {n0(data.week_kpis.total)} logs.
          {" "}The arrow on each tile is the change against the week immediately before, whichever
          range the tables below show.
        </>}
      >
        {data.in_progress ? <PartialWeek overview={data} /> : null}
        <WeekTiles overview={data} onOpen={(type) => set({ open: type ?? "all" })} />
      </Section>

      <Section
        title="Week on week by log type"
        note={`The last ${data.series.weeks.length} weeks. The selected week is outlined.`}
      >
        <WeekOnWeek overview={data} />
      </Section>

      <Section
        title="Top performers"
        note={<>
          {data.filters.weeks} weeks to {weekLabel(data.week)} — {n0(data.range.rows)} logs
          {data.filters.type ? <> · {data.filters.type} only</> : null}
          {scopeLabel(data.filters.regions, data.filters.teams)
            ? <> · {scopeLabel(data.filters.regions, data.filters.teams)}</> : null}.
          {" "}These rank logging as much as activity; see the notes below.
        </>}
      >
        <TopPerformers overview={data} onViewMore={(d) => set({ more: d, open: null })} />
      </Section>

      <Section
        title="Note sentiment"
        note={<>
          Keyword scoring of the Note column over the same {n0(data.range.rows)} logs as the tables
          above, so it follows the week, range, team and type on screen.
          {" "}{pct(data.sentiment.scored, data.sentiment.n, 0)} of them matched a term.
        </>}
      >
        <Sentiment overview={data} />
      </Section>

      <Section
        title="Data notes"
        note="Everything below is measured from the file you loaded. It changes what the numbers can be used for."
      >
        <Notes overview={data} />
      </Section>

      <LogPane slug={slug} overview={data} type={more ? false : pane}
               onClose={() => set({ open: null })} />
      <LeaderPane slug={slug} overview={data} dimension={more}
                  onClose={() => set({ more: null })} />
    </>
  );
}

/** The newest week in an export is almost always a partial one. The change
 *  against a complete week then reads as a collapse, which is an artefact of the
 *  export date rather than anything the team did. */
function PartialWeek({ overview }: { overview: LogOverview }) {
  const { days_elapsed: days, week_kpis: week } = overview;
  const pace = Math.round((week.total / days) * 7);
  return (
    <Band tone="warn">
      <b>This week is still running.</b> It is {days} {days === 1 ? "day" : "days"} old, and the
      change is measured against a full seven-day week — which is why it reads as{" "}
      <b>{week.delta.toLocaleString("en-GB")}</b>. At the current rate it is on for about{" "}
      <b>{pace.toLocaleString("en-GB")}</b> logs against {week.previous_total.toLocaleString("en-GB")}{" "}
      last week. Step back one week with ← for the last complete comparison.
    </Band>
  );
}
