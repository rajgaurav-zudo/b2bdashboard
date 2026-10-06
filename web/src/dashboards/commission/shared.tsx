import { useSearchParams } from "react-router-dom";
import type { ReactNode } from "react";

import { CommissionApiError, type Checklist, type Tier } from "./api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "RATE_CHANGE" -> "Rate change". Enums are shown as words everywhere. */
export const label = (v: string | null | undefined): string =>
  v ? v.charAt(0) + v.slice(1).toLowerCase().replace(/_/g, " ") : "--";

/** "2026-09" -> "Sep 2026". */
export const intakeLabel = (v: string | null | undefined): string => {
  if (!v) return "--";
  const [y, m] = v.split("-");
  return `${MONTHS[Number(m) - 1] ?? m} ${y}`;
};

export const day = (v: string | null | undefined): string =>
  v ? new Date(`${v.slice(0, 10)}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "--";

export const money = (v: number | null | undefined, currency?: string | null): string => {
  if (v == null) return "--";
  try {
    return v.toLocaleString("en-GB", { style: "currency", currency: currency || "GBP", maximumFractionDigits: 2 });
  } catch {
    return `${currency ?? ""} ${v.toFixed(2)}`;
  }
};

export const tierText = (t: Tier) =>
  `${t.min_count ?? "?"}${t.max_count == null ? "+" : `–${t.max_count}`}`;

/** Monthly intakes from `from` for `n` months, as YYYY-MM. */
export function intakeRange(from: string, n: number): string[] {
  const [y, m] = from.split("-").map(Number);
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    const k = (m ?? 1) - 1 + i;
    out.push(`${(y ?? 2026) + Math.floor(k / 12)}-${String((k % 12) + 1).padStart(2, "0")}`);
  }
  return out;
}

/** The module navigates with search params so a link carries the contract and
 *  tab someone was on, and App.tsx needs no new routes. */
export function useNav() {
  const [params, setParams] = useSearchParams();
  const go = (changes: Record<string, string | number | null>, replace = false) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, String(v));
    }
    setParams(next, { replace });
  };
  return { params, go };
}

export function Source({ source }: { source?: string | null }) {
  if (!source) return null;
  return <span className={`cm-src${source.startsWith("Amendment") ? " am" : ""}`}>{source}</span>;
}

export function Review({ on, note }: { on?: boolean | null; note?: string | null }) {
  return on ? <span className="cm-rev" title={note ?? undefined}>Needs review</span> : null;
}

export function StatusPill({ status }: { status: string }) {
  const kind = status === "ACTIVE" ? "live" : status === "DRAFT" ? "" : "cold";
  return <span className={`pill ${kind}`} style={{ marginLeft: 0 }}>{label(status)}</span>;
}

export function Field({ title, required, bad, hint, wide, children }: {
  title: string; required?: boolean; bad?: boolean; hint?: ReactNode; wide?: boolean; children: ReactNode;
}) {
  return (
    <label className={`cm-field${wide ? " wide" : ""}${bad ? " bad" : ""}`}>
      <span>{title}{required ? <span className="req">*</span> : null}</span>
      {children}
      {hint ? <small>{hint}</small> : null}
    </label>
  );
}

export function Select({ value, options, onChange, blank = "Choose…", labels }: {
  value: string | null | undefined; options: readonly string[]; onChange: (v: string | null) => void;
  blank?: string | null; labels?: (v: string) => string;
}) {
  return (
    <select value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
      {blank !== null ? <option value="">{blank}</option> : null}
      {options.map((o) => <option key={o} value={o}>{(labels ?? label)(o)}</option>)}
    </select>
  );
}

export function LevelPicker({ all, value, onChange }: {
  all: string[]; value: string[]; onChange: (v: string[]) => void;
}) {
  return (
    <div className="cm-levels">
      {all.map((l) => {
        const on = value.includes(l);
        return (
          <button key={l} type="button" aria-pressed={on}
                  onClick={() => onChange(on ? value.filter((x) => x !== l) : [...value, l])}>
            {l}
          </button>
        );
      })}
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  const blockers = error instanceof CommissionApiError ? (error.detail.blockers as { message: string }[] | undefined) : undefined;
  return (
    <div className="status err">
      {msg}
      {blockers?.length ? <ul>{blockers.map((b, i) => <li key={i}>{b.message}</li>)}</ul> : null}
    </div>
  );
}

export function ChecklistPanel({ checklist, onJump, title = "Ready to publish?" }: {
  checklist: Checklist; onJump?: (where: string) => void; title?: string;
}) {
  const failing = [...checklist.always, ...checklist.choices].filter((i) => !i.ok);
  return (
    <div className="cm-card">
      <h3>{title}</h3>
      <div className={`cm-ready ${checklist.ready ? "yes" : "no"}`}>
        {checklist.ready ? "Ready to publish" : `${failing.length} to fix before publishing`}
      </div>
      <div className="cm-checks-h">Always required</div>
      <Items items={checklist.always} onJump={onJump} />
      {checklist.choices.length ? (
        <>
          <div className="cm-checks-h">Required by your choices</div>
          <Items items={checklist.choices} onJump={onJump} />
        </>
      ) : null}
      {checklist.warnings.length ? (
        <>
          <div className="cm-checks-h">Warnings (do not block)</div>
          <ul className="cm-checks">
            {checklist.warnings.slice(0, 40).map((w) => (
              <li key={w.key} className="wn">
                <span className="mk">!</span>
                <span>{w.message}{w.where ? <span className="why">{w.where}</span> : null}</span>
              </li>
            ))}
            {checklist.warnings.length > 40 ? <li className="wn"><span className="mk" />…and {checklist.warnings.length - 40} more</li> : null}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function Items({ items, onJump }: { items: Checklist["always"]; onJump?: (where: string) => void }) {
  return (
    <ul className="cm-checks">
      {items.map((i) => (
        <li key={i.key} className={i.ok ? "ok" : "no"}>
          <span className="mk">{i.ok ? "✓" : "✕"}</span>
          <span>
            {!i.ok && i.where && onJump
              ? <button type="button" className="cm-link" onClick={() => onJump(i.where!)}>{i.label}</button>
              : i.label}
            {i.because ? <span className="why">because {i.because}</span> : null}
            {!i.ok && i.message && i.message !== `${i.label} is required` ? <span className="why">{i.message}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}
