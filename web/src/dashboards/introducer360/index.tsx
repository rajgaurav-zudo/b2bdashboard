import { useSearchParams } from "react-router-dom";

import { useView } from "../../api/client";
import type { I360Overview } from "../../api/types";
import { n0 } from "../../format";
import { Empty, Section, Spinner } from "../../ui/Primitives";
import { dayLabel } from "../../ui/dates";
import { FilterBar } from "./FilterBar";
import { GroupPane } from "./GroupPane";
import { Commitment, Notes, Profile } from "./Lower";
import { Widgets } from "./Widgets";
import { WisePane } from "./WisePane";
import { WiseTable } from "./WiseTable";

/** One introducer, end to end.
 *
 *  Every filter lives in the URL rather than in state, for the reason the log
 *  dashboard's week does: a pipeline that needs explaining is something people
 *  send to each other, and the link has to carry what they were looking at. */
export function Introducer360({ slug }: { slug: string }) {
  const [params, setParams] = useSearchParams();

  const query = {
    introducers: params.get("introducers") ?? undefined,
    regions: params.get("regions") ?? undefined,
    teams: params.get("teams") ?? undefined,
    range: params.get("range") ?? undefined,
    from: params.get("from") ?? undefined,
    to: params.get("to") ?? undefined,
    intake_year: params.get("intake_year") ?? undefined,
    intake_cycle: params.get("intake_cycle") ?? undefined,
    compare: params.get("compare") ?? undefined,
  };
  const { data, isLoading, error } = useView<I360Overview>(slug, "overview", query);

  // the two overlays. Separate keys so both are independently shareable, and
  // only one is ever on screen.
  const group = params.get("group");
  const wise = params.get("wise") !== null;

  const set = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  };

  if (isLoading) return <Spinner label="Reading the pipeline…" />;
  if (error) {
    return (
      <Empty title="Nothing to show yet">
        <p>{(error as Error).message}</p>
        <p>Load the applications export on the <b>Data</b> tab, then come back.</p>
      </Empty>
    );
  }
  if (!data) return null;

  const stages = data.stages.map((stage) => ({ id: stage.id, name: stage.name }));

  return (
    <>
      <FilterBar slug={slug} overview={data} set={set} />

      <Section
        title="Pipeline"
        note={<>
          {data.scope_line}. Each card counts applications that <b>entered</b> that stage
          inside the window, so one application appears in every stage it passed through.
          {data.compare ? <> Compared with {data.previous_range.label}.</> : null}
        </>}
        aside={
          <button type="button" className="i360-more" onClick={() => set({ wise: "1" })}>
            Introducer-wise ›
          </button>
        }
      >
        <Widgets overview={data} onOpen={(id) => set({ group: id })} />
        <p className="i360-foot">
          “Today” is <b>{dayLabel(data.anchor)}</b>, the newest stage date in the loaded
          export — not the clock. An export taken on a Sunday would otherwise open on a
          week that has not happened yet and read as a collapse.
        </p>
      </Section>

      <Section
        title="Who produced this window"
        note={<>
          {data.top.length
            ? <>The {data.top.length} partners the window belongs to, ranked by everything it
               produced rather than by one stage — a week of four offers and no deposit still
               belongs at the top.</>
            : <>Nothing entered a stage inside this window, so there is no one to rank.</>} Cells read <b>entered</b>, then <b>active / closed</b>;
          the last two columns are states, and are not narrowed by the window.
        </>}
        aside={
          <button type="button" className="i360-more" onClick={() => set({ wise: "1" })}>
            View all ›
          </button>
        }
      >
        <WiseTable stages={stages} rows={data.top} />
      </Section>

      <Section
        title="The introducer"
        note="The CRM record, and the whole of what this partner has done — neither of them narrowed by the date range above."
      >
        <Profile overview={data} />
      </Section>

      <Section
        title={`Intake commitment — ${data.commitment.intake_year}`}
        note={<>
          Deposits standing for the {data.commitment.intake_year} intake against the same
          point in the {data.commitment.intake_year - 1} one. This looks past the intake
          filter on purpose: comparing an intake with the one before it cannot be done
          inside a population already narrowed to a single intake.
        </>}
      >
        <Commitment overview={data} />
      </Section>

      <Section
        title="Data notes"
        note="Measured from the file you loaded. Each one changes what a number above can be used for."
      >
        <Notes overview={data} />
      </Section>

      <footer>
        {n0(data.data.app_rows)} applications in the loaded export.
        {" "}Stages are read from the CRM’s status timestamps; a stage is an event an
        application passed through, not the status it holds today.
      </footer>

      <GroupPane overview={data} group={group} onClose={() => set({ group: null })} />
      <WisePane slug={slug} overview={data} open={wise} params={query}
                onClose={() => set({ wise: null })} />
    </>
  );
}
