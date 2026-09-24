import { useState } from "react";

import type { RegionOption, TeamOption } from "../api/types";
import { MultiSelect } from "./MultiSelect";

/** Region and Team, side by side, for the filter bars that share the i360 look.
 *
 *  Region picks a set of teams; Team narrows it. So the Team menu lists only
 *  the teams in the picked regions, and removing a region drops the picked
 *  teams that sat in it -- otherwise a team the menu no longer shows would keep
 *  filtering the page. The server applies the same rule, so a stale link that
 *  names a team outside its regions gets an empty page rather than a wrong one.
 *
 *  `onChange` gets both lists at once, so the caller writes them to the URL in
 *  one step. */
export function RegionTeam({
  regionOptions, teamOptions, regions, teams, onChange, open, onToggle, onClose,
}: {
  regionOptions: RegionOption[];
  teamOptions: TeamOption[];
  regions: string[];
  teams: string[];
  onChange: (next: { regions: string[]; teams: string[] }) => void;
  open: "region" | "team" | null;
  onToggle: (which: "region" | "team") => void;
  onClose: () => void;
}) {
  const [rq, setRq] = useState("");
  const [tq, setTq] = useState("");
  const regionOf = new Map(teamOptions.map((t) => [t.team, t.region]));

  const inRegions = (team: string, picked: string[]) =>
    picked.length === 0 || picked.includes(regionOf.get(team) ?? "Other");

  const rNeedle = rq.trim().toLowerCase();
  const tNeedle = tq.trim().toLowerCase();

  return (
    <>
      <MultiSelect
        label="Region" all="All regions" many={(n) => `${n} regions`}
        chosen={regions}
        onChange={(next) => onChange({ regions: next, teams: teams.filter((t) => inRegions(t, next)) })}
        options={regionOptions
          .filter((o) => o.region.toLowerCase().includes(rNeedle))
          .map((o) => ({ name: o.region, n: o.n }))}
        query={rq} onQuery={setRq} placeholder="Search regions…"
        open={open === "region"} onToggle={() => onToggle("region")} onClose={onClose}
      />
      <MultiSelect
        label="Team" all={regions.length ? "All teams in region" : "All teams"}
        many={(n) => `${n} teams`}
        chosen={teams}
        onChange={(next) => onChange({ regions, teams: next })}
        options={teamOptions
          .filter((o) => inRegions(o.team, regions) && o.team.toLowerCase().includes(tNeedle))
          .map((o) => ({ name: o.team, n: o.n }))}
        query={tq} onQuery={setTq} placeholder="Search teams…"
        open={open === "team"} onToggle={() => onToggle("team")} onClose={onClose}
      />
    </>
  );
}

/** `|`-joined for the URL, since team names are free text; empty removes the key. */
export const joinParam = (values: string[]) => (values.length ? values.join("|") : null);
