import { useRef, type ReactNode } from "react";

import { useOutside } from "./useOutside";

/** The shell every control shares: a label, a value, an optional ✕, a popover. */
export function Control({ label, value, isSet, onClear, open, onToggle, onClose, width, children }: {
  label: string; value: string; isSet: boolean; onClear: () => void;
  open: boolean; onToggle: () => void; onClose: () => void;
  width?: number; children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, open, onClose);
  return (
    <div className="i360-ctl" ref={ref}>
      <button type="button" className={`face${open ? " on" : ""}`} onClick={onToggle}>
        <span className="txt">
          <span className="cap">{label}</span>
          <span className="val">{value}</span>
        </span>
        {isSet ? (
          <span
            className="x"
            role="button"
            tabIndex={0}
            aria-label={`Clear ${label.toLowerCase()}`}
            // without this the clear reopens the menu it just closed
            onClick={(e) => { e.stopPropagation(); onClear(); }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); e.preventDefault(); onClear(); }
            }}
          >
            ×
          </span>
        ) : <span className="car">▾</span>}
      </button>
      {open ? <div className="i360-pop" style={width ? { width } : undefined}>{children}</div> : null}
    </div>
  );
}
