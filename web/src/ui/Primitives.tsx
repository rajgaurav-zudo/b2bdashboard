import type { ReactNode } from "react";

/** The shared kit. Every dashboard may use these; none may change them in a way
 *  that breaks another. Additions are safe, edits to existing props are not. */

export function Section({ title, note, children }: { title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <div className="sec-head">
        <h2>{title}</h2>
        {note ? <p>{note}</p> : null}
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

export function Fig({ children }: { children: ReactNode }) {
  return <span className="fig">{children}</span>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <p className="status busy">
      <span className="spinner" /> {label ?? "Loading…"}
    </p>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty card">
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
