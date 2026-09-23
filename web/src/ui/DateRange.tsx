import { useState, type ReactNode } from "react";

import { addMonths, dayLabel, MONTHS, monthGrid, parse } from "./dates";
import { Control } from "./FilterControl";

export interface RangePreset {
  id: string;
  label: string;
  /** the line under the label, e.g. its first day */
  sub: string;
  pressed: boolean;
}

/** The filter bars' date range: presets down the left, two months of days on
 *  the right. The first click on a day starts a custom range, the second ends
 *  it (in either order). One component so every dashboard's range looks and
 *  behaves the same; what a preset or a range means is the caller's business.
 *  Days are plain `YYYY-MM-DD` strings. */
export function DateRange({
  value, isSet, onClear, presets, onPreset, from, to, onRange, hint, open, onToggle, onClose,
}: {
  value: string; isSet: boolean; onClear: () => void;
  presets: RangePreset[];
  onPreset: (id: string) => void;
  /** the window being shown, highlighted on the calendar */
  from: string; to: string;
  onRange: (from: string, to: string) => void;
  /** a line after the calendar's own note, for what a pick means here */
  hint?: ReactNode;
  open: boolean; onToggle: () => void; onClose: () => void;
}) {
  // a half-made custom range: the first click sets it, the second completes it
  const [pending, setPending] = useState<string | null>(null);
  const [month, setMonth] = useState(() => {
    const start = new Date(parse(from));
    return { year: start.getUTCFullYear(), month: start.getUTCMonth() };
  });
  const right = addMonths(month.year, month.month, 1);

  const pick = (day: string) => {
    if (!pending) { setPending(day); return; }
    const [a, b] = pending <= day ? [pending, day] : [day, pending];
    setPending(null);
    onRange(a, b);
  };

  return (
    <Control
      label="Date range" value={value} isSet={isSet}
      onClear={() => { setPending(null); onClear(); }}
      open={open} onToggle={onToggle} onClose={() => { setPending(null); onClose(); }}
      width={620}
    >
      <div className="i360-when">
        <div className="presets">
          {presets.map((preset) => (
            <button
              key={preset.id} type="button"
              aria-pressed={preset.pressed}
              onClick={() => { setPending(null); onPreset(preset.id); }}
            >
              <b>{preset.label}</b>
              <span>{preset.sub}</span>
            </button>
          ))}
        </div>
        <div className="cal">
          <div className="cal-h">
            <button type="button" onClick={() => setMonth(addMonths(month.year, month.month, -1))}>‹</button>
            <b>{MONTHS[month.month]} {month.year}</b>
            <b>{MONTHS[right.month]} {right.year}</b>
            <button type="button" onClick={() => setMonth(addMonths(month.year, month.month, 1))}>›</button>
          </div>
          <div className="cal-pair">
            <Month {...month} from={pending ?? from} to={pending ?? to} onPick={pick} />
            <Month {...right} from={pending ?? from} to={pending ?? to} onPick={pick} />
          </div>
          <p className="cal-note">
            {pending
              ? <>Started at <b>{dayLabel(pending)}</b> — pick the other end.</>
              : <>Showing <b>{dayLabel(from)}</b> to <b>{dayLabel(to)}</b>.</>}
            {hint ? <> {hint}</> : null}
          </p>
        </div>
      </div>
    </Control>
  );
}

function Month({ year, month, from, to, onPick }: {
  year: number; month: number; from: string; to: string; onPick: (day: string) => void;
}) {
  return (
    <div className="cal-m">
      <div className="cal-dow">
        {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => <span key={i}>{d}</span>)}
      </div>
      <div className="cal-grid">
        {monthGrid(year, month).map((day, i) => day === null
          ? <span key={i} className="pad" />
          : (
            <button
              key={day} type="button"
              className={[
                "d",
                day >= from && day <= to ? "in" : "",
                day === from || day === to ? "end" : "",
              ].join(" ").trim()}
              onClick={() => onPick(day)}
            >
              {Number(day.slice(8))}
            </button>
          ))}
      </div>
    </div>
  );
}
