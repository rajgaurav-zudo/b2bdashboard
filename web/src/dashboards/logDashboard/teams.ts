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
