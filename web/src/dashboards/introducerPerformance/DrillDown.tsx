import { Fragment, useState } from "react";

import { useTile } from "../../api/client";
import type { IntroducerRow, TileDrilldown } from "../../api/types";
import { cycleLabel, n0 } from "../../format";
import { Pill, Spinner } from "../../ui/Primitives";

const GROUPS: [string, string][] = [
  ["none", "Introducer"],
  ["team", "SRM team"],
  ["srm", "SRM owner"],
  ["country", "Country"],
  ["stage", "Lifecycle stage"],
];

/** Which row fields carry the tile's own metric. Sorting is done by the server,
 *  so the column header sends a field name rather than sorting in the browser. */
const METRIC_FIELDS = {
  act: ["act_cur", "act_life"],
  clos: ["clos_cur", "clos_life"],
  apps: ["apps_cur", "apps_life"],
  vrej: ["vrej_cur", "vrej_life"],
  coe: ["coe_cur", "coe_life"],
  none: [null, null],
} as const;

function columnsFor(data: TileDrilldown) {
  const [curField, lifeField] = METRIC_FIELDS[data.tile.metric];
  return [
    { key: "name", label: data.group_by === "none" ? "Introducer" : "Group", num: false },
    { key: "act_life", label: "Active dep.", num: true },
    { key: "clos_life", label: "Closed dep.", num: true },
    { key: "close_pct", label: "Closed %", num: true },
    { key: "last_key", label: "Last deposit", num: true },
    { key: curField, label: `${data.current_year} ${data.tile.metric_short}`, num: true },
    { key: lifeField, label: `Lifetime ${data.tile.metric_short}`, num: true },
  ];
}

function closeCell(row: { act_life: number; clos_life: number }) {
  if (!row.act_life && !row.clos_life) return <span className="dim">--</span>;
  if (!row.act_life) return <span style={{ color: "var(--bad)" }}>no active</span>;
  const p = (100 * row.clos_life) / row.act_life;
  const colour = p > 40 ? "var(--bad)" : p > 30 ? "var(--warn)" : undefined;
  return <span style={{ color: colour }}>{p.toFixed(0)}%</span>;
}

export function DrillDown({ slug, tileId, onClose }: {
  slug: string; tileId: string; onClose: () => void;
}) {
  const [groupBy, setGroupBy] = useState("none");
  const [sort, setSort] = useState("act_life");
  const [dir, setDir] = useState<"asc" | "desc">("desc");
  const { data, isLoading, error } = useTile(slug, tileId, { group_by: groupBy, sort, dir });

  const toggle = (key: string | null) => {
    if (key === null) return;                       // the "none" metric has no column to sort by
    if (key === sort) setDir(dir === "desc" ? "asc" : "desc");
    else { setSort(key); setDir(key === "name" ? "asc" : "desc"); }
  };

  const value = (row: IntroducerRow, field: string | null) =>
    field === null ? <span className="dim">--</span> : n0(row[field as keyof IntroducerRow] as number);

  return (
    <div className="card pane">
      <div className="pane-head">
        <div>
          <h3>{data?.tile.name ?? "…"}</h3>
          <p>{data?.tile.definition}</p>
        </div>
        <button type="button" className="pane-close" onClick={onClose} aria-label="Close">×</button>
      </div>

      <div className="pane-bar">
        <label>Group by</label>
        {GROUPS.map(([key, label]) => (
          <button key={key} type="button" className={`chip${groupBy === key ? " on" : ""}`}
                  onClick={() => setGroupBy(key)}>
            {label}
          </button>
        ))}
        {data ? (
          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--faint)" }}>
            {n0(data.tile.stats.n)} introducers · up to {n0(data.row_limit)} shown per group
          </span>
        ) : null}
      </div>

      {isLoading && !data ? <div className="pad"><Spinner /></div> : null}
      {error ? <div className="pad status err">Could not load this drill-down.</div> : null}

      {data ? (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                {columnsFor(data).map((column, i) => (
                  <th key={i} className={`${column.num ? "num" : ""}${column.key ? "" : " static"}`}
                      onClick={() => toggle(column.key)}>
                    {column.label}
                    {sort === column.key ? <span className="dir"> {dir === "desc" ? "▼" : "▲"}</span> : null}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.groups.map((group) => (
                <Fragment key={group.key}>
                  {data.group_by !== "none" ? (
                    <tr className="group">
                      <td>{group.key} <span className="dim">({n0(group.n)})</span></td>
                      <td colSpan={4} />
                      <td className="num">{n0(group.cur)}</td>
                      <td className="num">{n0(group.life)}</td>
                    </tr>
                  ) : null}
                  {group.rows.map((row) => {
                    const [curField, lifeField] = METRIC_FIELDS[data.tile.metric];
                    return (
                      <tr key={`${group.key}:${row.name}`}>
                        <td>
                          {row.name}
                          {row.stage !== "Customer" ? <> <Pill>{row.stage}</Pill></> : null}
                          {data.tile.id === "dormant" ? (
                            <> <Pill kind={row.still_applying ? "live" : ""}>
                              {row.still_applying ? "still applying" : "gone quiet"}
                            </Pill></>
                          ) : null}
                        </td>
                        <td className="num">{n0(row.act_life)}</td>
                        <td className="num">{n0(row.clos_life)}</td>
                        <td className="num">{closeCell(row)}</td>
                        <td className="num">
                          {row.last_key ? cycleLabel(row.last_key) : <span className="dim">--</span>}
                        </td>
                        <td className="num">{value(row, curField)}</td>
                        <td className="num"><b>{value(row, lifeField)}</b></td>
                      </tr>
                    );
                  })}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
