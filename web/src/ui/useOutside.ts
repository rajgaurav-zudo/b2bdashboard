import { useEffect, type RefObject } from "react";

/** Close on a click elsewhere or on Escape.
 *
 *  Shared kit: every popover on every dashboard behaves the same way, and a
 *  dropdown that only closes by clicking its own button is the thing people
 *  report as "it got stuck". */
export function useOutside(ref: RefObject<HTMLElement | null>, open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [ref, open, onClose]);
}
