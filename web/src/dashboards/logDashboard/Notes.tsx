import type { LogOverview } from "../../api/types";
import { n0, pct } from "../../format";
import { Fig, Note } from "../../ui/Primitives";
import { dayLabel, weekLabel } from "./weeks";

/** Every documented trap in the source file, counted against the loaded data
 *  rather than asserted. A number that reads as a bug is usually one of these. */
export function Notes({ overview }: { overview: LogOverview }) {
  const d = overview.data;
  const undated = d.load_stats?.undated_rows ?? null;
  const input = d.load_stats?.input_rows ?? null;

  return (
    <div className="notes-grid">
      <Note title="A week runs Saturday to Friday">
        Every figure buckets on the Saturday of the week a log falls in, decided once at ingest so
        no two queries can disagree. The file holds <Fig>{n0(overview.weeks.length)}</Fig> weeks,{" "}
        <Fig>{d.first_log ? dayLabel(d.first_log) : "--"}</Fig> to{" "}
        <Fig>{d.last_log ? dayLabel(d.last_log) : "--"}</Fig>.
      </Note>

      <Note title="Undated logs are skipped, not guessed">
        {undated === null ? (
          <>Logs whose <i>Log Time</i> cannot be read are dropped: every figure here is a week, and
            an undated row cannot be in one.</>
        ) : (
          <>
            <Fig>{n0(undated)}</Fig> of <Fig>{n0(input ?? 0)}</Fig> rows had no readable{" "}
            <i>Log Time</i> and were skipped ({pct(undated, input ?? 0, 1)}). Every figure here is a
            week, and an undated row cannot be in one. <Fig>{n0(d.rows)}</Fig> rows loaded.
          </>
        )}
      </Note>

      <Note title="The selected week is chosen, not assumed">
        The default is the newest week in the file that has <b>already started</b> — currently{" "}
        <Fig>{weekLabel(overview.current_week)}</Fig>. Taking the newest week outright would anchor
        on whatever partial week the export was pulled in, and show a collapse in activity that is
        an artefact of the export date.
      </Note>

      <Note title="Change is always week-on-week">
        Every arrow compares the selected week with the one immediately before it in the file, whatever
        range the tables below are showing. A week the export skipped is absent rather than counted
        as a zero.
      </Note>

      <Note title="Log volume is not effort">
        One person logging every email and another logging only meetings rank very differently for
        identical work. <Fig>{n0(d.creators)}</Fig> people logged against{" "}
        <Fig>{n0(d.introducers)}</Fig> introducers here. The top tables measure logging discipline
        at least as much as activity.
      </Note>

      <Note title="No outcome is attached">
        A log records that contact happened. Nothing on this page knows whether it produced an
        application or a deposit — that is the introducer performance dashboard’s question, and the
        two are deliberately not joined. A partner with 40 logs and nothing to show is a cost
        signal, not a revenue one.
      </Note>

      <Note title="Notes are often blank or wordless">
        <Fig>{n0(d.blank_note)}</Fig> logs ({pct(d.blank_note, d.rows, 0)}) carry no note at all, and
        a further <Fig>{n0(d.unscored_note)}</Fig> have a note that matches no lexicon term. Both
        count as neutral in the sentiment index, which is why it sits close to zero even in a good
        week.
      </Note>

      <Note title="Unattributed rows are named, not dropped">
        <Fig>{n0(d.blank_introducer)}</Fig> logs have no introducer, <Fig>{n0(d.blank_team)}</Fig>{" "}
        no team and <Fig>{n0(d.blank_creator)}</Fig> no creator. They appear as{" "}
        <i>Unnamed</i>, <i>Unassigned</i> and <i>Unattributed</i>: a gap in the CRM is a finding,
        not a row to lose.
      </Note>
    </div>
  );
}
