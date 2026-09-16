/** Dates are handled as plain `YYYY-MM-DD` strings and arithmetic is done in
 *  UTC. The API answers in the export's calendar, not the reader's timezone: a
 *  browser in Auckland must not see Monday's window start as Sunday. */

export const iso = (ms: number): string => new Date(ms).toISOString().slice(0, 10);

export const parse = (day: string): number => Date.parse(`${day}T00:00:00Z`);

const LONG = { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" } as const;
const SHORT = { day: "numeric", month: "short", timeZone: "UTC" } as const;

export const dayLabel = (day: string | null): string =>
  day ? new Date(parse(day)).toLocaleDateString("en-GB", LONG) : "--";

/** "8 – 14 Jun 2026". The year is said once, and only the ends carry it. */
export function rangeLabel(from: string, to: string): string {
  if (from === to) return dayLabel(from);
  const a = new Date(parse(from));
  const b = new Date(parse(to));
  const sameYear = a.getUTCFullYear() === b.getUTCFullYear();
  const left = sameYear
    ? a.toLocaleDateString("en-GB", a.getUTCMonth() === b.getUTCMonth() ? { day: "numeric", timeZone: "UTC" } : SHORT)
    : a.toLocaleDateString("en-GB", LONG);
  return `${left} – ${b.toLocaleDateString("en-GB", LONG)}`;
}

export const MONTHS = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];

/** One month as a grid of weeks that begin on Monday -- the same week start the
 *  read model's `this_week` uses, so the calendar and the preset agree. */
export function monthGrid(year: number, month: number): (string | null)[] {
  const lead = (new Date(Date.UTC(year, month, 1)).getUTCDay() + 6) % 7;
  const days: (string | null)[] = Array(lead).fill(null);
  const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  for (let d = 1; d <= last; d += 1) days.push(iso(Date.UTC(year, month, d)));
  while (days.length % 7) days.push(null);
  return days;
}

export const addMonths = (year: number, month: number, step: number) => {
  const next = new Date(Date.UTC(year, month + step, 1));
  return { year: next.getUTCFullYear(), month: next.getUTCMonth() };
};
