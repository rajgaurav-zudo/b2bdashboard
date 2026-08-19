import type { Tile } from "../../api/types";
import { n0 } from "../../format";

interface Props {
  tiles: Tile[];
  section: Tile["section"];
  currentYear: number;
  selected: string | null;
  onSelect: (id: string) => void;
  extra?: (tile: Tile) => string | null;
}

function headline(tile: Tile, currentYear: number): { value: number; label: string } {
  if (tile.head === "count") return { value: tile.stats.n, label: "customer-stage introducers" };
  if (tile.head === "cur") return { value: tile.stats.cur, label: `${tile.metric_label} · ${currentYear}` };
  return { value: tile.stats.life, label: `${tile.metric_label} · lifetime` };
}

export function Tiles({ tiles, section, currentYear, selected, onSelect, extra }: Props) {
  return (
    <div className="tiles">
      {tiles.filter((t) => t.section === section).map((tile) => {
        const head = headline(tile, currentYear);
        const tone = tile.invert ? "win" : section === "active" ? "" : "leak";
        const note = extra?.(tile);
        return (
          <button
            key={tile.id}
            type="button"
            className={`tile ${tone}${selected === tile.id ? " on" : ""}`}
            onClick={() => onSelect(tile.id)}
            aria-pressed={selected === tile.id}
          >
            <div className="name">{tile.name}</div>
            <p className="big">
              {n0(head.value)}
              <span className="unit">{head.label}</span>
            </p>
            <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5 }}>
              {tile.definition}
            </p>
            {note ? <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--info)" }}>{note}</p> : null}
            <div className="foot">
              <span><b>{n0(tile.stats.n)}</b> {tile.stats.n === 1 ? "introducer" : "introducers"}</span>
              {tile.head !== "count" ? <span><b>{n0(tile.stats.cur)}</b> in {currentYear}</span> : null}
              <span>{n0(tile.stats.contract_active)} active · {n0(tile.stats.contract_expired)} expired</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
