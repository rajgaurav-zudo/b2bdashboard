import type { I360Cell, I360Overview, I360Stage, I360Widget } from "../../api/types";
import { n0 } from "../../format";

/** The eight cards, on one line.
 *
 *  Two of them are groups: they show their total and nothing else, and open a
 *  breakdown. A group is the sum of its members' events rather than a count of
 *  distinct applications -- an application that paid a deposit, received a CoE
 *  and applied for a visa inside the window entered three stages, and is
 *  counted three times exactly as it would be on three separate cards. The
 *  modal is where that stops being an assertion and becomes visible. */
export function Widgets({ overview, onOpen }: {
  overview: I360Overview; onOpen: (group: string) => void;
}) {
  return (
    <div className="i360-cards">
      {overview.widgets.map((widget) => (
        <Card key={widget.id} widget={widget} compare={overview.compare} onOpen={onOpen} />
      ))}
    </div>
  );
}

function Card({ widget, compare, onOpen }: {
  widget: I360Widget; compare: boolean; onOpen: (group: string) => void;
}) {
  const group = widget.kind === "group";
  const body = (
    <>
      <span className="nm">{widget.name}</span>
      <span className="big num">{n0(widget.created)}</span>
      {/* a state has no timestamp, so it cannot be narrowed by the window and
          the card says so rather than implying a window it does not have */}
      <span className="cap">{widget.windowed ? "entered" : "as of the export"}</span>
      <Split cell={widget} />
      {compare ? <Delta widget={widget} /> : null}
    </>
  );
  return group ? (
    <button type="button" className="i360-card grp" onClick={() => onOpen(widget.id)}>
      <span className="drill" aria-hidden>Breakdown ›</span>
      {body}
    </button>
  ) : (
    <div className="i360-card">{body}</div>
  );
}

/** Active and closed under the total, each against the number above it. The
 *  two are a partition of `created`, not two independent measures. */
export function Split({ cell }: { cell: I360Cell }) {
  return (
    <span className="i360-split">
      <span className="r">
        <span className="k">Active</span>
        <b className="num">{n0(cell.active)}</b>
        <i className="num">{cell.active_pct}%</i>
      </span>
      <span className="r">
        <span className="k">Closed</span>
        <b className="num">{n0(cell.closed)}</b>
        <i className="num">{cell.closed_pct}%</i>
      </span>
    </span>
  );
}

function Delta({ widget }: { widget: I360Widget | I360Stage }) {
  if (!("previous" in widget) || widget.previous === undefined) {
    return <span className="i360-delta none">Not compared</span>;
  }
  const delta = widget.delta;
  if (delta === null || delta === undefined) {
    return (
      <span className="i360-delta none">
        <b className="num">{n0(widget.previous.created)}</b> last year
      </span>
    );
  }
  const tone = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
  return (
    <span className={`i360-delta ${tone}`}>
      <b className="num">{delta > 0 ? "+" : ""}{delta.toFixed(1)}%</b>
      <span className="vs">vs <span className="num">{n0(widget.previous.created)}</span></span>
    </span>
  );
}
