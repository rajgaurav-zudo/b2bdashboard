import type { OverviewCompare, Tile, TileStats } from "../../api/types";
import { n0 } from "../../format";

interface Props {
  tiles: Tile[];
  section: Tile["section"];
  /** The intake window every "current" figure covers: "2026", "Sep 2025 – May 2026". */
  periodLabel: string;
  /** The same filters over the prior window, when Compare is on. */
  compare?: OverviewCompare | null;
  onOpen: (id: string) => void;
  extra?: (tile: Tile) => string | null;
}

/** The headline number and the line under it. `count` tiles have no deposit
 *  metric at all, so they lead with the introducer count instead. */
function headline(tile: Tile, periodLabel: string): { key: keyof TileStats; label: string } {
  if (tile.head === "count") return { key: "n", label: "customer-stage introducers" };
  if (tile.head === "cur") return { key: "cur", label: `${tile.metric_label} · ${periodLabel}` };
  return { key: "life", label: `${tile.metric_label} · lifetime` };
}

/** The headline against the prior window. Leak and quality tiles count
 *  problems, so there a rise is the bad direction and the colour flips. */
function Delta({ now, before, invert, label }: { now: number; before: number; invert: boolean; label: string }) {
  const change = now - before;
  const good = invert ? -change : change;
  const tone = good > 0 ? "up" : good < 0 ? "down" : "flat";
  const move = change > 0 ? "up" : change < 0 ? "down" : "unchanged";
  return (
    <span className={`d ${tone}`} title={`${move} against ${n0(before)} in ${label}`}>
      <b>{change > 0 ? "+" : ""}{n0(change)}</b>
      <span className="dir" aria-hidden="true">{change > 0 ? "▲" : change < 0 ? "▼" : "–"}</span>
      {" "}vs {label} ({n0(before)})
    </span>
  );
}

export function Tiles({ tiles, section, periodLabel, compare, onOpen, extra }: Props) {
  return (
    <div className="tiles">
      {tiles.filter((tile) => tile.section === section).map((tile) => {
        const head = headline(tile, periodLabel);
        const before = compare?.tiles[tile.id];
        const tag = extra?.(tile);
        return (
          <button
            key={tile.id}
            type="button"
            className={`tile${tile.invert ? " inv" : ""}`}
            onClick={() => onOpen(tile.id)}
          >
            <span className="drill">drill down →</span>
            <div className="metric">{n0(tile.stats[head.key])}</div>
            <div className="metric-l">{head.label}</div>
            <div className="name">{tile.name}</div>
            <div className="def">{tile.definition}</div>
            {tag ? <span className="tag">{tag}</span> : null}
            {compare && before ? (
              <div className="foot">
                <Delta now={tile.stats[head.key]} before={before[head.key]} invert={tile.section !== "active"} label={compare.label} />
              </div>
            ) : null}
            <div className="foot">
              <span><b>{n0(tile.stats.n)}</b> {tile.stats.n === 1 ? "introducer" : "introducers"}</span>
              {tile.head !== "count"
                ? <span><b>{n0(tile.stats.cur)}</b> in {periodLabel}</span>
                : null}
              <span className="contract">
                {n0(tile.stats.contract_active)} active · {n0(tile.stats.contract_expired)} expired
              </span>
            </div>
            <div className="foot states">
              <span title={`Deferral awaiting approval — deposit paid, deferral initiated, not yet approved, in ${periodLabel}. Not counted in the deposits above.`}>
                <b>{n0(tile.stats.daa)}</b> DAA
              </span>
              <span title={`Partial deposits — part paid, not closed lost, in ${periodLabel}. Never counted in the deposits above.`}>
                <b>{n0(tile.stats.pd)}</b> PD
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
