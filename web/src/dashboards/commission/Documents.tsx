import { Empty, Note, Section } from "../../ui/Primitives";
import type { ContractDetail } from "./api";
import { day, label, useNav } from "./shared";

/** Documents are references (a file name or link), not uploads: the signed
 *  copies stay where they are kept today. */
export function Documents({ detail }: { detail: ContractDetail }) {
  const { go } = useNav();
  const c = detail.contract;
  const docs = [...detail.amendments].sort((a, b) => (b.received_on ?? "").localeCompare(a.received_on ?? ""));
  return (
    <>
      <Section title="Contract source">
        <div className="cm-card">
          <div className="cm-kv">
            <span>Imported from</span><span>{c.source_tab ? `${c.source_tab} ${c.source_rows ?? ""}` : "Entered here"}</span>
            <span>Validity</span><span>{day(c.start_date)} – {c.is_rolling ? "rolling" : day(c.end_date)}</span>
            <span>Published</span><span>{c.current_version ? `v${c.current_version}` : "never"}</span>
          </div>
        </div>
      </Section>
      <Section title="Amendment documents" note="Each amendment records the document it came from.">
        {!docs.length ? <Empty title="No documents"><p>Documents appear here as amendments are recorded.</p></Empty> : (
          <div className="tbl-wrap">
            <table className="cm-wrap">
              <thead><tr>
                <th className="txt">Received</th><th className="txt">Reference</th><th className="txt">Document</th>
                <th className="txt">Amendment</th><th className="txt">Status</th>
              </tr></thead>
              <tbody>
                {docs.map((a) => (
                  <tr key={a.id}>
                    <td className="txt">{day(a.received_on)}</td>
                    <td className="txt">{a.reference ?? <span className="red">missing</span>}</td>
                    <td className="txt">
                      {a.document_file?.startsWith("http")
                        ? <a href={a.document_file} target="_blank" rel="noreferrer">{a.document_file}</a>
                        : a.document_file ?? <span className="red">missing</span>}
                    </td>
                    <td className="txt">
                      <button type="button" className="cm-link" onClick={() => go({ tab: "amendments", a: a.id, step: a.status === "DRAFT" ? 1 : 4 })}>
                        #{a.number} {label(a.type)}
                      </button>
                    </td>
                    <td className="txt">{label(a.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Note title="No uploads yet">File upload is not built; record where the signed copy lives.</Note>
      </Section>
    </>
  );
}
