import { useEffect } from "react";

import type { I360Overview } from "../../api/types";
import { n0 } from "../../format";
import { Split } from "./Widgets";

/** What a group card is made of.
 *
 *  No fetch: the members are already on the page -- the card is their sum, and
 *  showing the same numbers from a second query would be a way for the two to
 *  disagree. The cells mirror the card exactly, so the breakdown reads as the
 *  card taken apart rather than as a different report. */
export function GroupPane({ overview, group, onClose }: {
  overview: I360Overview; group: string | null; onClose: () => void;
}) {
  const open = group !== null;
  const widget = overview.widgets.find((w) => w.id === group) ?? null;

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      <div className={`scrim${open ? " on" : ""}`} onClick={onClose} />
      <aside className={`pane${open ? " on" : ""}`} aria-hidden={!open}>
        <div className="pane-h">
          <div className="row1">
            <div>
              <h2>{widget?.name ?? "Breakdown"}</h2>
              <p className="pdef">
                {widget?.sub}. {widget?.windowed
                  ? <>Entries inside {overview.range.label.toLowerCase()}, {overview.range.from} to {overview.range.to}.</>
                  : <>As the export stands: neither of these has a timestamp, so no date range narrows them.</>}
                {" "}An application that passed through more than one of these is counted in each.
              </p>
            </div>
            <button type="button" className="x" onClick={onClose} aria-label="Close">×</button>
          </div>
          <div className="chips">
            <span className="chip"><b>{n0(widget?.created ?? 0)}</b> total</span>
            <span className="chip"><b>{n0(widget?.active ?? 0)}</b> active</span>
            <span className="chip"><b>{n0(widget?.closed ?? 0)}</b> closed</span>
            <span className="chip">{overview.scope_line}</span>
          </div>
        </div>

        <div className="pane-body">
          {widget ? (
            <div className="i360-members">
              {widget.members.map((member) => (
                <div key={member.id} className="i360-card">
                  <span className="nm">{member.name}</span>
                  <span className="big num">{n0(member.created)}</span>
                  <span className="cap">{member.kind === "event" ? "entered" : "as of the export"}</span>
                  <Split cell={member} />
                  {overview.compare && member.previous ? (
                    <span className="i360-delta none">
                      <b className="num">{n0(member.previous.created)}</b> last year
                    </span>
                  ) : null}
                </div>
              ))}
              <div className="i360-card tot">
                <span className="nm">{widget.name}, total</span>
                <span className="big num">{n0(widget.created)}</span>
                <span className="cap">the card on the page</span>
                <Split cell={widget} />
              </div>
            </div>
          ) : null}
        </div>
      </aside>
    </>
  );
}
