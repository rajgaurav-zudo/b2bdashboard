import { useMemo, useRef, useState } from "react";

import { n0 } from "../../format";
import { useOutside } from "../../ui/useOutside";
import { teamFace } from "./teams";

/** The team filter, as a set.
 *
 *  A dropdown of checkboxes rather than a native `<select multiple>`: the
 *  native one shows three rows of a twenty-two-team list, needs ctrl-click to
 *  add a second, and drops the whole selection on a stray click. The regional
 *  SRM teams are read together as often as alone, so adding one has to be a
 *  single ordinary click. */
export function TeamPicker({ teams, selected, onChange }: {
  teams: { team: string; n: number }[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, open, () => setOpen(false));

  // the whole list is already on the page, so the search is local
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return needle ? teams.filter((t) => t.team.toLowerCase().includes(needle)) : teams;
  }, [teams, q]);

  const flip = (team: string) =>
    onChange(selected.includes(team) ? selected.filter((t) => t !== team) : [...selected, team]);

  // what the selection covers, so picking two of twenty-two says how much of
  // the file is left rather than leaving it to be guessed
  const covered = teams
    .filter((t) => selected.includes(t.team))
    .reduce((sum, t) => sum + t.n, 0);
  const all = teams.reduce((sum, t) => sum + t.n, 0);

  return (
    <div className="mselect" ref={ref}>
      <button
        type="button" className={`face${open ? " on" : ""}`}
        aria-expanded={open} onClick={() => setOpen((was) => !was)}
      >
        <span className="v">{teamFace(selected)}</span>
        <span className="car" aria-hidden>▾</span>
      </button>
      {open ? (
        <div className="mpop">
          <div className="mhead">
            <span>
              {selected.length
                ? <>{n0(covered)} of {n0(all)} logs</>
                : <>every team in the file</>}
            </span>
            {selected.length ? (
              <button type="button" onClick={() => onChange([])}>Clear</button>
            ) : null}
          </div>
          <input
            className="msearch" type="search" autoFocus placeholder="Search teams…"
            value={q} onChange={(e) => setQ(e.target.value)}
          />
          <div className="mlist">
            {/* `opt` rather than a bare label: `.filters label` is the caption
                rule above the control, and it would otherwise stack these
                three into a column and set them in faint uppercase */}
            {shown.map((team) => (
              <label key={team.team} className={`opt${selected.includes(team.team) ? " on" : ""}`}>
                <input
                  type="checkbox"
                  checked={selected.includes(team.team)}
                  onChange={() => flip(team.team)}
                />
                <span className="nm">{team.team}</span>
                <span className="n">{n0(team.n)}</span>
              </label>
            ))}
            {shown.length === 0 ? <p className="mnone">No team matches “{q}”.</p> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
