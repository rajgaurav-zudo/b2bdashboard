import { useState, type ReactNode } from "react";

import { addMonths, dayLabel, MONTHS, monthGrid, parse } from "./dates";
import { Control } from "./FilterControl";

export interface RangePreset {
  id: string;
  label: string;
  /** the line under the label, e.g. its first day */
  sub: string;
  pressed: boolean;
  /** presets sharing a group sit together under its name, two to a row */
  group?: string;
  /** the group's heading is this preset, a button across the row, in place of the plain name */
  head?: boolean;
}

/** The filter bars' date range: presets down the left, two months of days on
 *  the right. The first click on a day starts a custom range, the second ends
 *  it (in either order). One component so every dashboard's range looks and
 *  behaves the same; what a preset or a range means is the caller's business.
 *  Days are plain `YYYY-MM-DD` strings. */
export function DateRange({
  label = "Date range", value, isSet, onClear, presets, onPreset, from, to, onRange, hint, open, onToggle, onClose,
}: {
  label?: string;
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
      label={label} value={value} isSet={isSet}
      onClear={() => { setPending(null); onClear(); }}
      open={open} onToggle={onToggle} onClose={() => { setPending(null); onClose(); }}
      width={620}
    >
      <div className="i360-when">
        <div className="presets">
          {groups(presets).map(({ group, items }) => {
            const buttons = items.map((preset) => (
              <button
                key={preset.id} type="button" className={preset.head ? "head" : undefined}
                aria-pressed={preset.pressed}
                onClick={() => { setPending(null); onPreset(preset.id); }}
              >
                <b>{preset.label}</b>
                <span>{preset.sub}</span>
              </button>
            ));
            return group
              ? (
                <div key={group} className="grp">
                  {items.some((p) => p.head) ? null : <span className="gh">{group}</span>}
                  <div className="row">{buttons}</div>
                </div>
              )
              : buttons;
          })}
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

/** Consecutive presets with the same group, in order; ungrouped ones stand alone. */
function groups(presets: RangePreset[]): { group?: string; items: RangePreset[] }[] {
  const out: { group?: string; items: RangePreset[] }[] = [];
  for (const preset of presets) {
    const last = out[out.length - 1];
    if (preset.group && last?.group === preset.group) last.items.push(preset);
    else out.push({ group: preset.group, items: [preset] });
  }
  return out;
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
