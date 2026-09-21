import { n0 } from "../format";
import { Control } from "./FilterControl";

/** The filter bars' pick-several control: a search box, the picks as removable
 *  tags, then a ticked list with a count per option. One component so every
 *  dashboard's multi-select looks and behaves the same.
 *
 *  The search is controlled: a caller with thousands of options searches on the
 *  server and passes back what matched; a short list is filtered locally. */
export function MultiSelect({
  label, all, many, chosen, onChange, options, query, onQuery, loading = false,
  placeholder, open, onToggle, onClose,
}: {
  label: string;
  /** the value shown when nothing is picked, e.g. "All teams" */
  all: string;
  /** the value for several picks, e.g. (n) => `${n} teams` */
  many: (n: number) => string;
  chosen: string[];
  onChange: (next: string[]) => void;
  options: { name: string; n: number }[];
  query: string;
  onQuery: (q: string) => void;
  loading?: boolean;
  placeholder: string;
  open: boolean; onToggle: () => void; onClose: () => void;
}) {
  const flip = (name: string) =>
    onChange(chosen.includes(name) ? chosen.filter((n) => n !== name) : [...chosen, name]);

  const value = chosen.length === 0 ? all
    : chosen.length === 1 ? chosen[0] ?? ""
    : many(chosen.length);

  return (
    <Control
      label={label} value={value} isSet={chosen.length > 0}
      onClear={() => onChange([])}
      open={open} onToggle={onToggle} onClose={onClose} width={340}
    >
      <input
        className="i360-find" type="search" autoFocus placeholder={placeholder}
        value={query} onChange={(e) => onQuery(e.target.value)}
      />
      {chosen.length ? (
        <div className="i360-chosen">
          {chosen.map((name) => (
            <button key={name} type="button" className="tag" onClick={() => flip(name)}>
              {name} <span aria-hidden>×</span>
            </button>
          ))}
        </div>
      ) : null}
      <div className="i360-list">
        {options.map((row) => (
          <button
            key={row.name} type="button"
            className={`opt${chosen.includes(row.name) ? " on" : ""}`}
            onClick={() => flip(row.name)}
          >
            <span className="tick" aria-hidden>{chosen.includes(row.name) ? "✓" : ""}</span>
            <span className="nm">{row.name}</span>
            <span className="n">{n0(row.n)}</span>
          </button>
        ))}
        {!loading && options.length === 0
          ? <p className="i360-none">No {label.toLowerCase()} matches “{query}”.</p> : null}
      </div>
    </Control>
  );
}
