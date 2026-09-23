import { Fragment, useEffect, useMemo, useState } from "react";

import { useTileMembers } from "../../api/client";
import type { IntroducerRow, Tile, TileMembers } from "../../api/types";
import { cycleLabel, n0 } from "../../format";

/* --------------------------------------------------------------------------
   The drill-down. Grouping, sorting and expansion all happen here rather than
   on the server: the member list arrives once per tile, so switching tab or
   opening a group costs nothing. The largest tile is ~3.5k rows (~75KB gzipped).
   -------------------------------------------------------------------------- */

type Tab = "team" | "country" | "srm" | "stage" | "introducer";
const TABS: [Tab, string][] = [
  ["team", "Team"], ["country", "Country"], ["srm", "SRM"],
  ["stage", "Stage"], ["introducer", "Introducer"],
];

type ColKey = "name" | "act" | "clos" | "cpct" | "last" | "cur" | "life";
interface Sort { c: ColKey; d: 1 | -1 }

interface Row {
  label: string;
  member?: IntroducerRow;      // set on leaf rows only
  n: number;
  act: number;
  clos: number;
  cur: number;
  life: number;
  last: number;
  kids?: Row[];
}

const METRIC_FIELDS: Record<Tile["metric"], { life: keyof IntroducerRow; cur: keyof IntroducerRow } | null> = {
  act: { life: "act_life", cur: "act_cur" },
  clos: { life: "clos_life", cur: "clos_cur" },
  apps: { life: "apps_life", cur: "apps_cur" },
  vrej: { life: "vrej_life", cur: "vrej_cur" },
  coe: { life: "coe_life", cur: "coe_cur" },
  none: null,
};

function leafRow(member: IntroducerRow, tile: Tile): Row {
  const fields = METRIC_FIELDS[tile.metric];
  return {
    label: member.name,
    member,
    n: 1,
    act: member.act_life,
    clos: member.clos_life,
    cur: fields ? (member[fields.cur] as number) : 0,
    life: fields ? (member[fields.life] as number) : 0,
    last: member.last_key,
  };
}

function compare(sort: Sort) {
  return (a: Row, b: Row): number => {
    if (sort.c === "name") {
      const va = a.label.toLowerCase();
      const vb = b.label.toLowerCase();
      return va < vb ? -sort.d : va > vb ? sort.d : 0;
    }
    let va: number;
    let vb: number;
    if (sort.c === "cpct") {
      // no active deposits but some closed ones sorts as the worst possible ratio
      va = a.act ? a.clos / a.act : a.clos ? 1e9 : -1;
      vb = b.act ? b.clos / b.act : b.clos ? 1e9 : -1;
    } else {
      va = a[sort.c];
      vb = b[sort.c];
    }
    if (va === vb) return a.label < b.label ? -1 : 1;
    return (va - vb) * sort.d;
  };
}

function buildRows(data: TileMembers, tab: Tab): { flat?: Row[]; groups?: Row[] } {
  if (tab === "introducer") return { flat: data.rows.map((r) => leafRow(r, data.tile)) };
  const buckets = new Map<string, Row>();
  for (const member of data.rows) {
    const key = (member[tab] || "").trim() || (tab === "stage" ? "Unknown" : "Unassigned");
    let group = buckets.get(key);
    if (!group) {
      group = { label: key, n: 0, act: 0, clos: 0, cur: 0, life: 0, last: 0, kids: [] };
      buckets.set(key, group);
    }
    const row = leafRow(member, data.tile);
    group.n += 1;
    group.act += row.act;
    group.clos += row.clos;
    group.cur += row.cur;
    group.life += row.life;
    if (row.last > group.last) group.last = row.last;
    group.kids!.push(row);
  }
  return { groups: [...buckets.values()] };
}

function ClosedPct({ act, clos }: { act: number; clos: number }) {
  if (!act && !clos) return <span className="dim">--</span>;
  if (!act) return <span className="red">no active</span>;
  const share = (100 * clos) / act;
  return <span className={share > 40 ? "red" : share > 30 ? "amber" : ""}>{share.toFixed(0)}%</span>;
}

function Caret({ column, sort }: { column: ColKey; sort: Sort }) {
  return <span className="ar">{sort.c === column ? (sort.d > 0 ? "▲" : "▼") : "▼"}</span>;
}

export function SidePane({ slug, tileId, filters, onClose }: {
  slug: string; tileId: string | null;
  /** The page's filters, so the members are the ones its tiles counted. */
  filters: Record<string, string>;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("team");
  const [sort, setSort] = useState<Sort>({ c: "life", d: -1 });
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const [kidSort, setKidSort] = useState<Record<string, Sort>>({});
  const { data, isLoading, error } = useTileMembers(slug, tileId, filters);

  // a fresh tile resets everything; a tile with no metric can only sort by name
  useEffect(() => {
    if (!tileId) return;
    setOpenGroups({});
    setKidSort({});
    setTab("team");
  }, [tileId]);

  useEffect(() => {
    if (data) setSort(data.tile.metric === "none" ? { c: "name", d: 1 } : { c: "life", d: -1 });
  }, [data?.tile.id]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // the page behind the pane must not scroll with it
  useEffect(() => {
    document.body.style.overflow = tileId ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [tileId]);

  const open = tileId !== null;
  const columns = useMemo((): { k: ColKey; l: string }[] => {
    if (!data) return [];
    const label = tab === "introducer" ? "Introducer" : TABS.find((t) => t[0] === tab)![1];
    return [
      { k: "name", l: label },
      { k: "act", l: "Active dep." },
      { k: "clos", l: "Closed dep." },
      { k: "cpct", l: "Closed %" },
      { k: "last", l: "Last deposit" },
      { k: "cur", l: `${data.period.label} ${data.tile.metric_short}` },
      { k: "life", l: `Lifetime ${data.tile.metric_short}` },
    ];
  }, [data, tab]);

  const toggleSort = (column: ColKey) =>
    setSort((prev) => (prev.c === column
      ? { c: column, d: (-prev.d) as 1 | -1 }
      : { c: column, d: column === "name" ? 1 : -1 }));

  const switchTab = (next: Tab) => {
    setTab(next);
    setOpenGroups({});
    setKidSort({});
    if (sort.c === "name" && data && data.tile.metric !== "none") setSort({ c: "life", d: -1 });
  };

  return (
    <>
      <div className={`scrim${open ? " on" : ""}`} onClick={onClose} />
      <aside className={`pane${open ? " on" : ""}`} aria-hidden={!open} role="dialog" aria-label="Drill-down">
        {data ? (
          <PaneHead data={data} tab={tab} onTab={switchTab} onClose={onClose} />
        ) : (
          <div className="pane-h">
            <div className="row1">
              <h2>{isLoading ? "Loading…" : "Drill-down"}</h2>
              <button className="x" onClick={onClose} aria-label="Close">×</button>
            </div>
          </div>
        )}

        {data ? (
          <div className="msort">
            <span style={{ fontSize: 11.5, color: "var(--muted)" }}>Sort by</span>
            <select value={sort.c} onChange={(e) => setSort({ c: e.target.value as ColKey, d: sort.d })}>
              {columns.map((c) => <option key={c.k} value={c.k}>{c.l}</option>)}
            </select>
            <button type="button" onClick={() => setSort({ c: sort.c, d: (-sort.d) as 1 | -1 })}>
              {sort.d > 0 ? "↑" : "↓"}
            </button>
          </div>
        ) : null}

        <div className="pane-body">
          {error ? <p className="empty-pane">{(error as Error).message}</p> : null}
          {isLoading ? <p className="empty-pane">Loading the member list…</p> : null}
          {data ? (
            <PaneTable
              data={data} tab={tab} sort={sort} columns={columns}
              openGroups={openGroups} kidSort={kidSort}
              onSort={toggleSort}
              onToggleGroup={(key) => setOpenGroups((prev) => {
                const next = { ...prev };
                if (next[key]) delete next[key]; else next[key] = true;
                return next;
              })}
              onKidSort={(group, column) => setKidSort((prev) => {
                const current = prev[group] ?? sort;
                return {
                  ...prev,
                  [group]: current.c === column
                    ? { c: column, d: (-current.d) as 1 | -1 }
                    : { c: column, d: column === "name" ? 1 : -1 },
                };
              })}
            />
          ) : null}
        </div>
      </aside>
    </>
  );
}

function PaneHead({ data, tab, onTab, onClose }: {
  data: TileMembers; tab: Tab; onTab: (t: Tab) => void; onClose: () => void;
}) {
  const { tile } = data;
  const none = tile.metric === "none";
  return (
    <div className="pane-h">
      <div className="row1">
        <div>
          <h2>{tile.name}</h2>
          <p className="pdef">
            {tile.definition} <b>{n0(tile.stats.n)}</b>{" "}
            {tile.stats.n === 1 ? "introducer" : "introducers"} ·{" "}
            <b>{none ? "--" : `${n0(tile.stats.life)} ${tile.metric_label}`}</b> lifetime
            {none ? "" : <> · <b>{n0(tile.stats.cur)}</b> in {data.period.label}</>}.
          </p>
        </div>
        <button className="x" onClick={onClose} aria-label="Close">×</button>
      </div>

      <div className="chips">
        {data.by_stage.map((stage) => (
          <span key={stage.stage} className={`chip${stage.stage === "Customer" ? "" : " alert"}`}>
            {stage.stage} <b>{n0(stage.n)}</b>
            {stage.act || stage.clos
              ? <> · <b>{n0(stage.act)}</b> active / <b>{n0(stage.clos)}</b> closed dep.</>
              : null}
          </span>
        ))}
      </div>

      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} onClick={() => onTab(key)}>
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

function PaneTable({ data, tab, sort, columns, openGroups, kidSort, onSort, onToggleGroup, onKidSort }: {
  data: TileMembers;
  tab: Tab;
  sort: Sort;
  columns: { k: ColKey; l: string }[];
  openGroups: Record<string, boolean>;
  kidSort: Record<string, Sort>;
  onSort: (c: ColKey) => void;
  onToggleGroup: (key: string) => void;
  onKidSort: (group: string, column: ColKey) => void;
}) {
  const { flat, groups } = useMemo(() => buildRows(data, tab), [data, tab]);
  const none = data.tile.metric === "none";
  const total = { act: 0, clos: 0, cur: 0, life: 0 };
  const top = (flat ?? groups ?? []).slice().sort(compare(sort));
  for (const row of top) {
    total.act += row.act; total.clos += row.clos;
    total.cur += row.cur; total.life += row.life;
  }

  if (!top.length) {
    return <p className="empty-pane">No introducers match this tile.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          {columns.map((column) => (
            <th
              key={column.k}
              className={`sortable${sort.c === column.k ? " sorted" : ""}`}
              onClick={() => onSort(column.k)}
            >
              {column.l}<Caret column={column.k} sort={sort} />
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {top.map((row) => {
          if (flat) return <LeafRow key={row.label} row={row} tile={data.tile} year={data.period.label} />;
          const isOpen = !!openGroups[row.label];
          const ks = kidSort[row.label] ?? sort;
          return (
            <Fragment key={row.label}>
              <tr className={`grp${isOpen ? " open" : ""}`} onClick={() => onToggleGroup(row.label)}>
                <td data-l="">
                  <span className="car">▶</span> {row.label}{" "}
                  <span className="dim" style={{ fontWeight: 400 }}>({n0(row.n)})</span>
                </td>
                <Cells row={row} tile={data.tile} year={data.period.label} />
              </tr>
              {isOpen ? (
                <>
                  <tr className="kid head">
                    {columns.map((column) => (
                      <td
                        key={column.k}
                        onClick={(event) => { event.stopPropagation(); onKidSort(row.label, column.k); }}
                      >
                        {column.k === "name" ? "Introducer" : column.l}<Caret column={column.k} sort={ks} />
                      </td>
                    ))}
                  </tr>
                  {row.kids!.slice().sort(compare(ks)).map((kid) => (
                    <LeafRow key={kid.label} row={kid} tile={data.tile} year={data.period.label} />
                  ))}
                </>
              ) : null}
            </Fragment>
          );
        })}
      </tbody>
      <tfoot>
        <tr>
          <td data-l="">Total · {n0(data.tile.stats.n)} {data.tile.stats.n === 1 ? "introducer" : "introducers"}</td>
          <td className="num" data-l="Active dep.">{n0(total.act)}</td>
          <td className="num" data-l="Closed dep.">{n0(total.clos)}</td>
          <td className="num" data-l="Closed %"><ClosedPct act={total.act} clos={total.clos} /></td>
          <td />
          <td className="num" data-l={`${data.period.label} ${data.tile.metric_short}`}>
            {none ? "--" : n0(total.cur)}
          </td>
          <td className="num" data-l={`Lifetime ${data.tile.metric_short}`}>
            {none ? "--" : n0(total.life)}
          </td>
        </tr>
      </tfoot>
    </table>
  );
}

function LeafRow({ row, tile, year }: { row: Row; tile: Tile; year: string }) {
  const member = row.member!;
  const where = [member.team, member.srm, member.country]
    .filter((bit) => bit && bit !== "Unassigned" && bit !== "Unknown");
  return (
    <tr className="kid">
      <td data-l="">
        {member.name}
        {member.stage !== "Customer" ? <> <span className="flagstage">{member.stage}</span></> : null}
        {tile.id === "dormant" ? (
          member.still_applying
            ? <span className="pill live">still applying</span>
            : <span className="pill cold">gone quiet</span>
        ) : null}
        {where.length ? <span className="who">{where.join(" · ")}</span> : null}
      </td>
      <Cells row={row} tile={tile} year={year} />
    </tr>
  );
}

/** Every column after the name. Shared so group and leaf rows cannot drift. */
function Cells({ row, tile, year }: { row: Row; tile: Tile; year: string }) {
  const none = tile.metric === "none";
  return (
    <>
      <td className="num" data-l="Active dep.">{n0(row.act)}</td>
      <td className="num" data-l="Closed dep.">{n0(row.clos)}</td>
      <td className="num" data-l="Closed %"><ClosedPct act={row.act} clos={row.clos} /></td>
      <td className="num" data-l="Last deposit">
        {row.last ? cycleLabel(row.last) : <span className="dim">--</span>}
      </td>
      <td className="num" data-l={`${year} ${tile.metric_short}`}>
        {none ? <span className="dim">--</span> : n0(row.cur)}
      </td>
      <td className="num" data-l={`Lifetime ${tile.metric_short}`}>
        {none ? <span className="dim">--</span> : <b>{n0(row.life)}</b>}
      </td>
    </>
  );
}
