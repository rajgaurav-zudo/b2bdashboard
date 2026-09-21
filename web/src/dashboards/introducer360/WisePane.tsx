import { useEffect, useMemo, useState } from "react";

import { useView } from "../../api/client";
import type { I360Overview, I360WiseView } from "../../api/types";
import { n0 } from "../../format";
import { Spinner } from "../../ui/Primitives";
import { WiseTable } from "./WiseTable";

/** Every stage, per introducer, over the window on screen.
 *
 *  With partners selected it is those partners. With none, it is the ones the
 *  window actually belongs to, ranked — which is the same table the design's
 *  counsellor-wise view is, against a book with thousands of partners rather
 *  than seven counsellors. */
export function WisePane({ slug, overview, open, onClose, params }: {
  slug: string; overview: I360Overview; open: boolean; onClose: () => void;
  params: Record<string, string | undefined>;
}) {
  const [search, setSearch] = useState("");
  const { data, isFetching, error } = useView<I360WiseView>(slug, "introducer_wise", params, open);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // fetched once per scope; narrowing the list is local
  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const needle = search.trim().toLowerCase();
    return needle ? all.filter((r) => r.name.toLowerCase().includes(needle)) : all;
  }, [data, search]);

  return (
    <>
      <div className={`scrim${open ? " on" : ""}`} onClick={onClose} />
      <aside className={`pane wide${open ? " on" : ""}`} aria-hidden={!open}>
        <div className="pane-h">
          <div className="row1">
            <div>
              <h2>Introducer-wise</h2>
              <p className="pdef">
                Every stage entered inside the window, per partner. Each cell is entries
                into that stage, with the active and closed halves under it — the same
                three figures the cards carry. The last two columns are states rather than
                events: they have no timestamp, so no date range narrows them, and the
                total column counts only the stages entered inside the window.
              </p>
            </div>
            <button type="button" className="x" onClick={onClose} aria-label="Close">×</button>
          </div>
          <div className="chips">
            <span className="chip">{data?.scope_line ?? overview.scope_line}</span>
            <span className="chip"><b>{n0(rows.length)}</b> partners</span>
            {overview.selected.length === 0 && data
              ? <span className="chip">top {data.row_limit} by what the window produced</span>
              : null}
            <input
              className="find" type="search" placeholder="Filter by name…"
              value={search} onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="pane-body">
          {error ? <p className="empty-pane">{(error as Error).message}</p> : null}
          {isFetching && !data ? <Spinner label="Reading the book…" /> : null}
          {data ? (
            <WiseTable stages={data.stage_names} rows={rows} totals={data.totals} />
          ) : null}
          {data && rows.length === 0
            ? <p className="empty-pane">No partner matches “{search}”.</p> : null}
        </div>
      </aside>
    </>
  );
}
