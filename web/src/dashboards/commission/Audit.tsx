import { Fragment, useState } from "react";

import { when } from "../../format";
import { Empty, Section, Spinner } from "../../ui/Primitives";
import { useAudit, type AuditEntry } from "./api";
import { ErrorText, Select, label } from "./shared";

const NOISE = new Set(["updated_at", "created_at"]);

/** Top-level keys whose value differs, so a row shows what changed rather
 *  than two full JSON documents. */
function changed(e: AuditEntry): string[] {
  const b = (e.before_json ?? {}) as Record<string, unknown>;
  const a = (e.after_json ?? {}) as Record<string, unknown>;
  return [...new Set([...Object.keys(b), ...Object.keys(a)])]
    .filter((k) => !NOISE.has(k) && JSON.stringify(b[k]) !== JSON.stringify(a[k]));
}

export function Audit({ id }: { id: number }) {
  const { data, isLoading, error } = useAudit(id);
  const [entity, setEntity] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  if (isLoading) return <Spinner />;
  if (error || !data) return <ErrorText error={error} />;

  const uniq = (f: (e: AuditEntry) => string) => [...new Set(data.map(f))].sort();
  const rows = data.filter((e) => (!entity || e.entity === entity) && (!action || e.action === action));

  return (
    <Section title="Audit log" note={`${rows.length} of ${data.length} entries, newest first`}
             aside={
               <div className="cm-row">
                 <Select value={entity} options={uniq((e) => e.entity)} blank="All records" onChange={setEntity} />
                 <Select value={action} options={uniq((e) => e.action)} blank="All actions" onChange={setAction} />
               </div>
             }>
      {!rows.length ? <Empty title="Nothing logged" /> : (
        <div className="tbl-wrap">
          <table className="cm-wrap">
            <thead><tr>
              <th className="txt">When</th><th className="txt">Who</th><th className="txt">Record</th>
              <th className="txt">Action</th><th className="txt">Changed</th><th className="txt">Document</th><th />
            </tr></thead>
            <tbody>
              {rows.map((e) => {
                const keys = changed(e);
                const isOpen = open === e.id;
                return (
                  <Fragment key={e.id}>
                    <tr>
                      <td className="txt">{when(e.created_at)}</td>
                      <td className="txt">{e.user ?? <span className="dim">system</span>}</td>
                      <td className="txt">{label(e.entity)} <span className="dim">{e.entity_id}</span></td>
                      <td className="txt">{label(e.action)}</td>
                      <td className="txt">{keys.slice(0, 6).join(", ")}{keys.length > 6 ? ` +${keys.length - 6}` : ""}</td>
                      <td className="txt">{e.document_ref ?? ""}</td>
                      <td className="act">
                        {e.before_json != null || e.after_json != null
                          ? <button type="button" onClick={() => setOpen(isOpen ? null : e.id)}>{isOpen ? "Hide" : "Details"}</button> : null}
                      </td>
                    </tr>
                    {isOpen ? (
                      <tr>
                        <td className="txt" colSpan={7}>
                          <Detail e={e} keys={keys} />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function Detail({ e, keys }: { e: AuditEntry; keys: string[] }) {
  const pick = (o: unknown) => {
    if (o == null) return null;
    if (!keys.length || e.before_json == null || e.after_json == null) return o;
    const src = o as Record<string, unknown>;
    return Object.fromEntries(keys.map((k) => [k, src[k]]));
  };
  return (
    <div className="cm-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <div><div className="cm-checks-h">Before</div><pre className="cm-pre">{e.before_json == null ? "--" : JSON.stringify(pick(e.before_json), null, 2)}</pre></div>
      <div><div className="cm-checks-h">After</div><pre className="cm-pre">{e.after_json == null ? "--" : JSON.stringify(pick(e.after_json), null, 2)}</pre></div>
    </div>
  );
}
