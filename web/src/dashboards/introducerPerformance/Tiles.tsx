import type { Tile } from "../../api/types";
import { n0 } from "../../format";

interface Props {
  tiles: Tile[];
  section: Tile["section"];
  currentYear: number;
  onOpen: (id: string) => void;
  extra?: (tile: Tile) => string | null;
}

/** The headline number and the line under it. `count` tiles have no deposit
 *  metric at all, so they lead with the introducer count instead. */
function headline(tile: Tile, currentYear: number): { value: number; label: string } {
  if (tile.head === "count") return { value: tile.stats.n, label: "customer-stage introducers" };
  if (tile.head === "cur") return { value: tile.stats.cur, label: `${tile.metric_label} · ${currentYear}` };
  return { value: tile.stats.life, label: `${tile.metric_label} · lifetime` };
}

export function Tiles({ tiles, section, currentYear, onOpen, extra }: Props) {
  return (
    <div className="tiles">
      {tiles.filter((tile) => tile.section === section).map((tile) => {
        const head = headline(tile, currentYear);
        const tag = extra?.(tile);
        return (
          <button
            key={tile.id}
            type="button"
            className={`tile${tile.invert ? " inv" : ""}`}
            onClick={() => onOpen(tile.id)}
          >
            <span className="drill">drill down →</span>
            <div className="metric">{n0(head.value)}</div>
            <div className="metric-l">{head.label}</div>
            <div className="name">{tile.name}</div>
            <div className="def">{tile.definition}</div>
            {tag ? <span className="tag">{tag}</span> : null}
            <div className="foot">
              <span><b>{n0(tile.stats.n)}</b> {tile.stats.n === 1 ? "introducer" : "introducers"}</span>
              {tile.head !== "count"
                ? <span><b>{n0(tile.stats.cur)}</b> in {currentYear}</span>
                : null}
              <span className="contract">
                {n0(tile.stats.contract_active)} active · {n0(tile.stats.contract_expired)} expired
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
