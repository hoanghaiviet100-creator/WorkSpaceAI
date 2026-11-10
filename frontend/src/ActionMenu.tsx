import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { MoreHorizontal } from "lucide-react";

export type MenuAction = {
  label: string;
  icon?: ReactNode;
  run: () => void;
  danger?: boolean;
  disabled?: boolean;
};
export default function ActionMenu({
  label,
  actions,
}: {
  label: string;
  actions: MenuAction[];
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const trigger = useRef<HTMLButtonElement>(null),
    menu = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const rect = trigger.current!.getBoundingClientRect();
    setPosition({
      top: Math.max(
        8,
        Math.min(rect.bottom + 4, innerHeight - (actions.length * 44 + 16)),
      ),
      left: Math.max(8, Math.min(rect.right - 216, innerWidth - 224)),
    });
    menu.current
      ?.querySelector<HTMLButtonElement>("button:not(:disabled)")
      ?.focus();
    const outside = (event: PointerEvent) => {
      if (
        !menu.current?.contains(event.target as Node) &&
        !trigger.current?.contains(event.target as Node)
      )
        setOpen(false);
    };
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
      }
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const items = [
          ...(menu.current?.querySelectorAll<HTMLButtonElement>(
            "button:not(:disabled)",
          ) || []),
        ];
        const current = items.indexOf(
          document.activeElement as HTMLButtonElement,
        );
        const index =
          event.key === "Home"
            ? 0
            : event.key === "End"
              ? items.length - 1
              : (current + (event.key === "ArrowUp" ? -1 : 1) + items.length) %
                items.length;
        items[index]?.focus();
      }
      if (event.key === "Tab") setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", keyboard, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", keyboard, true);
    };
  }, [open, actions.length]);
  return (
    <>
      <button
        className="icon-button nb-menu-trigger"
        ref={trigger}
        aria-label={label}
        title={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen(!open)}
      >
        <MoreHorizontal size={18} />
      </button>
      {open &&
        createPortal(
          <div
            className="nb-action-menu"
            role="menu"
            aria-label={label}
            id={id}
            ref={menu}
            style={position}
          >
            {actions.map((action) => (
              <button
                role="menuitem"
                key={action.label}
                disabled={action.disabled}
                className={action.danger ? "is-danger" : ""}
                onClick={() => {
                  setOpen(false);
                  trigger.current?.focus();
                  action.run();
                }}
              >
                {action.icon}
                {action.label}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}
