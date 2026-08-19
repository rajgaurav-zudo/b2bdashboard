import type { ReactNode } from "react";

/** The shared kit. Every dashboard may use these; none may change them in a way
 *  that breaks another. Additions are safe, edits to existing props are not. */

export function Section({ title, note, aside, children }: {
  title: string; note?: ReactNode; aside?: ReactNode; children: ReactNode;
}) {
  return (
    <section>
      <div className="sec-h">
        <h2>{title}</h2>
        {note ? <p>{note}</p> : null}
        {aside ? <span style={{ marginLeft: "auto" }}>{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

export function Band({ tone = "info", icon, children }: {
  tone?: "info" | "warn"; icon?: string; children: ReactNode;
}) {
  return (
    <div className={`band ${tone}`}>
      <span className="ic">{icon ?? (tone === "warn" ? "▲" : "◆")}</span>
      <div>{children}</div>
    </div>
  );
}

export function Pill({ kind = "", children }: { kind?: string; children: ReactNode }) {
  return <span className={`pill ${kind}`}>{children}</span>;
}

/** A number inside prose. Mono and tabular so figures line up down a column. */
export function Fig({ children }: { children: ReactNode }) {
  return <span className="fig">{children}</span>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <p className="state">
      <span className="spin" /> {label ?? "Loading…"}
    </p>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      {children}
    </div>
  );
}

export function Note({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="note">
      <b>{title}</b>
      <span>{children}</span>
    </div>
  );
}

/** Segmented control. Matches the funnel scope switch in the original. */
export function Seg<T extends string>({ value, options, onChange }: {
  value: T; options: { value: T; label: string }[]; onChange: (next: T) => void;
}) {
  return (
    <span className="seg">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </span>
  );
}
