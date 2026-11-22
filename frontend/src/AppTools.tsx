import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ChevronDown, SlidersHorizontal, Sun } from "lucide-react";
import { ThemeControl } from "./components";
import { useEntrance, useExit } from "./useEntrance";

export default function AppTools({ compact = false }: { compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const exit = useExit();
  useEntrance(panel, open);
  const close = useCallback(
    () => exit(panel.current, () => setOpen(false)),
    [exit],
  );
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) close();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
        trigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open, close]);
  return (
    <div
      className="display-tools"
      ref={root}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) close();
      }}
    >
      <button
        ref={trigger}
        className={`display-tools-trigger ${compact ? "is-compact" : ""}`}
        aria-label="Display options"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => (open ? close() : setOpen(true))}
      >
        {compact ? <Sun size={16} /> : <SlidersHorizontal size={16} />}
        <span>Display</span>
        <ChevronDown size={13} />
      </button>
      <div className="display-tools-panel" id={id} hidden={!open} ref={panel}>
        <div className="display-theme-row">
          <span>Color theme</span>
          <ThemeControl />
        </div>
      </div>
    </div>
  );
}
