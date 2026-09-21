import { useEffect, useMemo, useState } from "react";

import { useView } from "../../api/client";
import type { LeaderboardView, LogOverview } from "../../api/types";
import { n0 } from "../../format";
import { Spinner } from "../../ui/Primitives";
import { teamLabel, teamParam } from "./teams";
import { TopTable, type Dimension } from "./TopPerformers";
import { weekLabel } from "./weeks";

interface Props {
  slug: string;
  overview: LogOverview;
  dimension: Dimension | null;
  onClose: () => void;
}

/** Every row behind a top-performer table, not just the ten on the page.
 *
 *  Deliberately the same scope as the table it was opened from — the range,
 *  team and log type on screen — so the first ten rows here are the ten already
 *  shown. Reading it as "all time" instead would make the two disagree, and the
 *  lifetime column already answers that question per row. */
export function LeaderPane({ slug, overview, dimension, onClose }: Props) {
  const open = dimension !== null;
  const [search, setSearch] = useState("");

  const { data, isFetching, error } = useView<LeaderboardView>(slug, "leaderboard", {
    dimension: dimension ?? "",
    week: overview.week,
    weeks: overview.filters.weeks,
    type: overview.filters.type,
    team: teamParam(overview.filters.teams),
  }, open);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // the list is fetched once per (dimension, scope); filtering it is local
  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const needle = search.trim().toLowerCase();
    return needle ? all.filter((r) => r.name.toLowerCase().includes(needle)) : all;
  }, [data, search]);

  const types = (data?.log_types ?? overview.log_types).map((t) => t.type);

  return (
    <>
      <div className={`scrim${open ? " on" : ""}`} onClick={onClose} />
      <aside className={`pane wide${open ? " on" : ""}`} aria-hidden={!open}>
        <div className="pane-h">
          <div className="row1">
            <div>
              <h2>{data?.label ?? "Loading"}</h2>
              <p className="pdef">
                {data?.note}. {overview.filters.weeks} weeks to {weekLabel(overview.week)}
                {teamLabel(overview.filters.teams) ? ` · ${teamLabel(overview.filters.teams)}` : ""}
                {overview.filters.type ? ` · ${overview.filters.type} only` : ""}
              </p>
            </div>
            <button type="button" className="x" onClick={onClose} aria-label="Close">×</button>
          </div>
          <div className="chips">
            <span className="chip"><b>{n0(data?.total ?? 0)}</b> in range</span>
            {search ? <span className="chip"><b>{n0(rows.length)}</b> matching</span> : null}
            <input
              className="find"
              type="search"
              placeholder="Filter by name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="pane-body">
          {isFetching && !data ? <Spinner /> : null}
          {error ? <p className="empty-pane">{(error as Error).message}</p> : null}
          {data ? (
            <TopTable
              dimension={dimension ?? "introducers"}
              title={data.label}
              note={data.note}
              types={types}
              rows={rows}
              total={data.total}
            />
          ) : null}
        </div>
      </aside>
    </>
  );
}
