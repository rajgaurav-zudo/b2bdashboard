/** The team filter holds a set, not a value.
 *
 *  Pipe-separated on the wire because a team name may hold a comma and cannot
 *  hold a pipe, and because a single name still parses as a one-element list —
 *  a link written before this filter took several still opens on the team it
 *  named. */

export const teamParam = (teams: string[]): string | undefined =>
  teams.length ? teams.join("|") : undefined;

/** What to call the selection in a sentence. Empty when nothing is selected, so
 *  a caller can drop the clause rather than write "· all teams". */
export const teamLabel = (teams: string[]): string =>
  teams.length === 0 ? "" : teams.length === 1 ? teams[0] ?? "" : `${teams.length} teams`;

/** The same thing on the button, where "no filter" has to say something. */
export const teamFace = (teams: string[]): string =>
  teams.length === 0 ? "All teams" : teamLabel(teams);

export const regionLabel = (regions: string[]): string =>
  regions.length === 0 ? "" : regions.length === 1 ? regions[0] ?? "" : `${regions.length} regions`;

export const regionFace = (regions: string[]): string =>
  regions.length === 0 ? "All regions" : regionLabel(regions);

/** Region and team together, for a sentence; empty when neither is set. */
export const scopeLabel = (regions: string[], teams: string[]): string =>
  [regionLabel(regions), teamLabel(teams)].filter(Boolean).join(" · ");
