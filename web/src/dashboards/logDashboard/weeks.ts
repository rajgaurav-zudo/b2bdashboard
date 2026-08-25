/** A week runs Saturday → Friday. The server decides which Saturday a log
 *  belongs to; everything here is presentation of that decision. */

const DAY = 86_400_000;

/** Parsed as UTC so a browser west of Greenwich cannot shift a week boundary. */
export const asDate = (iso: string): Date => new Date(`${iso}T00:00:00Z`);

const dayMonth = (d: Date) =>
  d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

/** "Sat 15 – Fri 21 Aug 2026", collapsing the month when both ends share one. */
export function weekLabel(iso: string): string {
  const from = asDate(iso);
  const to = new Date(from.getTime() + 6 * DAY);
  const year = to.toLocaleDateString("en-GB", { year: "numeric", timeZone: "UTC" });
  const sameMonth = from.getUTCMonth() === to.getUTCMonth();
  const left = sameMonth
    ? from.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", timeZone: "UTC" })
    : dayMonth(from);
  return `${left} – ${dayMonth(to)} ${year}`;
}

/** Compact form for a chart axis: "15 Aug". */
export const weekTick = (iso: string): string =>
  asDate(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

export const dayLabel = (iso: string): string =>
  asDate(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

/** Series colours, taken from the palette validated for colour-vision deficiency
 *  against the --paper surface. Assigned by the type's rank in the whole file,
 *  so a type keeps its colour as the week changes. */
const SERIES = ["#0F8A5F", "#3B6FA8", "#C08018", "#C0491F", "#5B47A0", "#5F6E68"];

export function colourFor(types: string[]): (type: string) => string {
  const index = new Map(types.map((t, i) => [t, SERIES[i % SERIES.length]!]));
  return (type: string) => index.get(type) ?? "#8C9793";
}

/** Signed, with the sign always shown: a delta of 0 reads as "0", not "—". */
export const signed = (v: number): string => (v > 0 ? `+${v.toLocaleString("en-GB")}` : v.toLocaleString("en-GB"));

export const deltaClass = (v: number): string =>
  v > 0 ? "up" : v < 0 ? "down" : "flat";

/** Which way the week moved. ▲/▼ are the same glyphs the sortable table headers
 *  use, so the page has one vocabulary for direction rather than two. A flat
 *  week gets a dash: an arrow that points nowhere is worse than no arrow. */
export const deltaArrow = (v: number): string => (v > 0 ? "▲" : v < 0 ? "▼" : "–");

/** Arrows do not survive being read aloud, so each one carries this. */
export const deltaLabel = (v: number, previous: number): string => {
  const move = v > 0 ? "up" : v < 0 ? "down" : "unchanged";
  const by = v === 0 ? "" : ` ${Math.abs(v).toLocaleString("en-GB")}`;
  return `${move}${by} against ${previous.toLocaleString("en-GB")} the week before`;
};
