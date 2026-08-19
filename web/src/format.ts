export const n0 = (v: number | null | undefined): string =>
  v == null ? "--" : Math.round(v).toLocaleString("en-GB");

export const pct = (part: number, whole: number, digits = 1): string =>
  whole ? `${((100 * part) / whole).toFixed(digits)}%` : "--";

export const pctOf = (rate: number, digits = 1): string => `${(100 * rate).toFixed(digits)}%`;

export const when = (iso: string | null): string =>
  iso ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "--";

/** Cycle key = year*10 + index, produced by the ingest layer. */
export const cycleLabel = (key: number): string => {
  if (!key) return "--";
  const year = Math.floor(key / 10);
  const name = ["Jan", "May", "Sep"][key % 10] ?? "?";
  return `${name} ${year}`;
};
