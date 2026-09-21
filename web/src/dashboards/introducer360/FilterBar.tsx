import { useRef, useState, type ReactNode } from "react";

import { useView } from "../../api/client";
import type { I360MenuView, I360Overview } from "../../api/types";
import { n0 } from "../../format";
import { useOutside } from "../../ui/useOutside";
import { addMonths, dayLabel, MONTHS, monthGrid, parse } from "./dates";

/** Writes the filters into the URL. Named so it cannot be confused with the
 *  `isSet` flag below, which says whether a control has a value to clear. */
type SetParams = (changes: Record<string, string | null>) => void;

/** Introducer, date range, intake, and whether to compare with last year.
 *
 *  Every control that is set carries its own ✕, and the ✕ stops the click from
 *  reaching the button underneath it -- otherwise clearing a filter opens the
 *  menu you were trying to leave. Clearing the range removes the date filter:
 *  it becomes All time, the file's first stage date to its last, rather than no
 *  window at all. Clear all still returns to the page's opening This week. */
export function FilterBar({ slug, overview, set }: {
  slug: string; overview: I360Overview; set: SetParams;
}) {
  const [open, setOpen] = useState<"who" | "when" | "intake" | null>(null);
  const toggle = (which: "who" | "when" | "intake") =>
    setOpen((current) => (current === which ? null : which));

  const { selected, range, intake } = overview;
  const dirty = selected.length > 0 || range.id !== "this_week"
    || intake.year !== null || overview.compare;

  return (
    <div className="i360-bar">
      <Who slug={slug} overview={overview} set={set}
           open={open === "who"} onToggle={() => toggle("who")} onClose={() => setOpen(null)} />
      <When overview={overview} set={set}
            open={open === "when"} onToggle={() => toggle("when")} onClose={() => setOpen(null)} />
      <Intake overview={overview} set={set}
              open={open === "intake"} onToggle={() => toggle("intake")} onClose={() => setOpen(null)} />

      <label className="i360-toggle">
        <input
          type="checkbox"
          checked={overview.compare}
          onChange={(e) => set({ compare: e.target.checked ? "1" : null })}
        />
        <span className="track"><span className="knob" /></span>
        <span className="lbl">Compare with last year</span>
      </label>

      {dirty ? (
        <button
          type="button"
          className="i360-clear"
          onClick={() => set({ introducers: null, range: null, from: null, to: null,
                               intake_year: null, intake_cycle: null, compare: null })}
        >
          Clear all
        </button>
      ) : null}
    </div>
  );
}

/** The shell every control shares: a label, a value, an optional ✕, a popover. */
function Control({ label, value, isSet, onClear, open, onToggle, onClose, width, children }: {
  label: string; value: string; isSet: boolean; onClear: () => void;
  open: boolean; onToggle: () => void; onClose: () => void;
  width?: number; children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, open, onClose);
  return (
    <div className="i360-ctl" ref={ref}>
      <button type="button" className={`face${open ? " on" : ""}`} onClick={onToggle}>
        <span className="txt">
          <span className="cap">{label}</span>
          <span className="val">{value}</span>
        </span>
        {isSet ? (
          <span
            className="x"
            role="button"
            tabIndex={0}
            aria-label={`Clear ${label.toLowerCase()}`}
            // without this the clear reopens the menu it just closed
            onClick={(e) => { e.stopPropagation(); onClear(); }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); e.preventDefault(); onClear(); }
            }}
          >
            ×
          </span>
        ) : <span className="car">▾</span>}
      </button>
      {open ? <div className="i360-pop" style={width ? { width } : undefined}>{children}</div> : null}
    </div>
  );
}

// --------------------------------------------------------------------------
// introducer
// --------------------------------------------------------------------------

function Who({ slug, overview, set, open, onToggle, onClose }: {
  slug: string; overview: I360Overview; set: SetParams;
  open: boolean; onToggle: () => void; onClose: () => void;
}) {
  const [q, setQ] = useState("");
  // there are thousands of partners, so the list is searched on the server and
  // ranked by lifetime work -- a partner who did nothing this week is exactly
  // the one someone opens this dashboard to look at
  const { data, isFetching } = useView<I360MenuView>(slug, "introducers",
    { q: q.trim(), limit: 60 }, open);

  const chosen = overview.selected;
  const flip = (name: string) => {
    const next = chosen.includes(name) ? chosen.filter((n) => n !== name) : [...chosen, name];
    set({ introducers: next.length ? next.join("|") : null });
  };

  const value = chosen.length === 0 ? "All introducers"
    : chosen.length === 1 ? chosen[0] ?? ""
    : `${chosen.length} introducers`;

  return (
    <Control
      label="Introducer" value={value} isSet={chosen.length > 0}
      onClear={() => set({ introducers: null })}
      open={open} onToggle={onToggle} onClose={onClose} width={340}
    >
      <input
        className="i360-find" type="search" autoFocus placeholder="Search partners…"
        value={q} onChange={(e) => setQ(e.target.value)}
      />
      {chosen.length ? (
        <div className="i360-chosen">
          {chosen.map((name) => (
            <button key={name} type="button" className="tag" onClick={() => flip(name)}>
              {name} <span aria-hidden>×</span>
            </button>
          ))}
        </div>
      ) : null}
      <div className="i360-list">
        {(data?.rows ?? []).map((row) => (
          <button
            key={row.name} type="button"
            className={`opt${chosen.includes(row.name) ? " on" : ""}`}
            onClick={() => flip(row.name)}
          >
            <span className="tick" aria-hidden>{chosen.includes(row.name) ? "✓" : ""}</span>
            <span className="nm">{row.name}</span>
            <span className="n">{n0(row.n)}</span>
          </button>
        ))}
        {!isFetching && (data?.rows.length ?? 0) === 0
          ? <p className="i360-none">No partner matches “{q}”.</p> : null}
      </div>
    </Control>
  );
}

// --------------------------------------------------------------------------
// date range
// --------------------------------------------------------------------------

function When({ overview, set, open, onToggle, onClose }: {
  overview: I360Overview; set: SetParams;
  open: boolean; onToggle: () => void; onClose: () => void;
}) {
  const { range } = overview;
  // a half-made custom range: the first click sets it, the second completes it
  const [pending, setPending] = useState<string | null>(null);
  const [month, setMonth] = useState(() => {
    const start = new Date(parse(range.from));
    return { year: start.getUTCFullYear(), month: start.getUTCMonth() };
  });
  const right = addMonths(month.year, month.month, 1);

  const pick = (day: string) => {
    if (!pending) { setPending(day); return; }
    const [from, to] = pending <= day ? [pending, day] : [day, pending];
    setPending(null);
    set({ range: "custom", from, to });
    onClose();
  };

  return (
    <Control
      label="Date range" value={range.label} isSet={range.id !== "all_time"}
      onClear={() => { setPending(null); set({ range: "all_time", from: null, to: null }); }}
      open={open} onToggle={onToggle} onClose={() => { setPending(null); onClose(); }}
      width={620}
    >
      <div className="i360-when">
        <div className="presets">
          {range.presets.map((preset) => (
            <button
              key={preset.id} type="button"
              aria-pressed={preset.id === range.id}
              onClick={() => {
                if (preset.id === "custom") { setPending(null); return; }
                set({ range: preset.id, from: null, to: null });
                onClose();
              }}
            >
              <b>{preset.label}</b>
              {preset.from ? <span>{dayLabel(preset.from)}</span> : <span>Pick two days</span>}
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
            <Month {...month} from={pending ?? range.from} to={pending ? pending : range.to} onPick={pick} />
            <Month {...right} from={pending ?? range.from} to={pending ? pending : range.to} onPick={pick} />
          </div>
          <p className="cal-note">
            {pending
              ? <>Started at <b>{dayLabel(pending)}</b> — pick the other end.</>
              : <>Showing <b>{dayLabel(range.from)}</b> to <b>{dayLabel(range.to)}</b>.</>}
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

// --------------------------------------------------------------------------
// intake
// --------------------------------------------------------------------------

function Intake({ overview, set, open, onToggle, onClose }: {
  overview: I360Overview; set: SetParams;
  open: boolean; onToggle: () => void; onClose: () => void;
}) {
  const { intake } = overview;
  const cycle = intake.cycles.find((c) => c.i === intake.cycle);
  const value = intake.year === null ? "Any intake"
    : cycle ? cycle.label : String(intake.year);

  return (
    <Control
      label="Intake" value={value} isSet={intake.year !== null}
      onClear={() => set({ intake_year: null, intake_cycle: null })}
      open={open} onToggle={onToggle} onClose={onClose} width={280}
    >
      <div className="i360-list">
        <button
          type="button" className={`opt${intake.year === null ? " on" : ""}`}
          onClick={() => { set({ intake_year: null, intake_cycle: null }); onClose(); }}
        >
          <span className="tick" aria-hidden>{intake.year === null ? "✓" : ""}</span>
          <span className="nm">Any intake</span>
        </button>
        {intake.years.map((year) => (
          <button
            key={year.y} type="button"
            className={`opt${intake.year === year.y ? " on" : ""}`}
            onClick={() => set({ intake_year: String(year.y), intake_cycle: null })}
          >
            <span className="tick" aria-hidden>{intake.year === year.y ? "✓" : ""}</span>
            <span className="nm">{year.y}</span>
            <span className="n">{n0(year.n)}</span>
          </button>
        ))}
      </div>
      {intake.cycles.length ? (
        <>
          {/* the counts are here so picking a cycle cannot land on an empty page
              without having said so first */}
          <p className="i360-sub">Cycle within {intake.year}</p>
          <div className="i360-list">
            {intake.cycles.map((c) => (
              <button
                key={c.i} type="button"
                className={`opt${intake.cycle === c.i ? " on" : ""}`}
                onClick={() => {
                  set({ intake_cycle: intake.cycle === c.i ? null : String(c.i) });
                  onClose();
                }}
              >
                <span className="tick" aria-hidden>{intake.cycle === c.i ? "✓" : ""}</span>
                <span className="nm">{c.label}</span>
                <span className="n">{n0(c.n)}</span>
              </button>
            ))}
          </div>
        </>
      ) : null}
    </Control>
  );
}
