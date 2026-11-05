import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  X,
  FileText,
  ArrowUpRight,
  Check,
  AlertTriangle,
  LoaderCircle,
  Sun,
  Moon,
  Monitor,
} from "lucide-react";
import { type Evidence, type EvidenceKey } from "./data";
export const EvidenceContext = createContext<Record<string, Evidence>>({});
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Citation({
  id,
  onOpen,
}: {
  id: EvidenceKey;
  onOpen: (id: EvidenceKey) => void;
}) {
  const entry = useContext(EvidenceContext)[id];
  if (!entry)
    return <span className="unavailable-source">Source unavailable</span>;
  return (
    <button className="citation" onClick={() => onOpen(id)}>
      <FileText size={13} />
      <span>
        {entry.file}
        <span className="locator">{entry.locator}</span>
      </span>
      <ArrowUpRight size={12} />
    </button>
  );
}
export function Notice({
  children,
  tone = "warning",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <div className={`notice ${tone}`}>
      <AlertTriangle size={16} />
      <div>{children}</div>
    </div>
  );
}
export function Status({ status }: { status: string }) {
  return (
    <span
      className={`source-status ${status === "Unreadable" ? "danger" : status === "Processed" ? "good" : ""}`}
    >
      {status === "Processed" ? (
        <Check size={12} />
      ) : status === "Processing" ? (
        <LoaderCircle size={12} />
      ) : (
        <AlertTriangle size={12} />
      )}{" "}
      {status}
    </span>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
  className = "",
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    const el = ref.current;
    el?.focus();
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handle = (e: KeyboardEvent) => {
      if (
        e.key === "Escape" &&
        !e.defaultPrevented &&
        !document.querySelector("select:open")
      ) {
        e.preventDefault();
        closeRef.current();
      }
      if (e.key === "Tab" && el) {
        const nodes = Array.from(
          el.querySelectorAll<HTMLElement>(
            'button,input,select,textarea,iframe,a[href],[tabindex="0"]',
          ),
        ).filter(
          (n) => !n.hasAttribute("disabled") && n.getClientRects().length,
        );
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (
          e.shiftKey &&
          (document.activeElement === first || document.activeElement === el)
        ) {
          e.preventDefault();
          last?.focus();
        } else if (
          !e.shiftKey &&
          (document.activeElement === last || document.activeElement === el)
        ) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handle);
    return () => {
      document.removeEventListener("keydown", handle);
      document.body.style.overflow = old;
      before?.focus();
    };
  }, []);
  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={`modal ${wide ? "wide" : ""} ${className}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={ref}
      >
        <header>
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={19} />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}
export type Theme = "light" | "dark" | "system";
export function ThemeControl() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem("wai-theme") as Theme) || "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (
        event.key === "wai-theme" &&
        ["light", "dark", "system"].includes(event.newValue || "")
      ) {
        setTheme(event.newValue as Theme);
      }
    };
    addEventListener("storage", onStorage);
    return () => removeEventListener("storage", onStorage);
  }, []);
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        theme === "system" ? (media.matches ? "dark" : "light") : theme;
      document.documentElement.style.colorScheme =
        document.documentElement.dataset.theme!;
    };
    apply();
    localStorage.setItem("wai-theme", theme);
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  return (
    <div className="theme-control" role="group" aria-label="Color theme">
      {(
        [
          { id: "light", icon: Sun },
          { id: "dark", icon: Moon },
          { id: "system", icon: Monitor },
        ] as const
      ).map(({ id, icon: Icon }) => (
        <button
          key={id}
          className={theme === id ? "selected" : ""}
          aria-label={`${id[0].toUpperCase() + id.slice(1)} theme`}
          aria-pressed={theme === id}
          title={`${id[0].toUpperCase() + id.slice(1)} theme`}
          onClick={() => setTheme(id)}
        >
          <Icon size={15} />
        </button>
      ))}
    </div>
  );
}
export function Brand({ onClick }: { onClick: () => void }) {
  return (
    <button className="brand" onClick={onClick} aria-label="WorkspaceAI home">
      <svg
        width="27"
        height="27"
        viewBox="0 0 28 28"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M3 5.5h8l3 3 3-3h8v17h-8l-3 2-3-2H3v-17Z"
          stroke="currentColor"
          strokeWidth="1.7"
        />
        <path
          d="M14 9v14M7 10h3M7 14h3M18 10h3M18 14h3"
          stroke="currentColor"
          strokeWidth="1.7"
        />
      </svg>
      <span>
        Workspace<span className="brand-ai">AI</span>
      </span>
    </button>
  );
}

export function usePanelFocus(
  open: boolean,
  selector: string,
  maxWidth: number,
  close: () => void,
) {
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    if (!open || !matchMedia(`(max-width: ${maxWidth}px)`).matches) return;
    const panel = document.querySelector<HTMLElement>(selector);
    if (!panel) return;
    const previous = document.activeElement as HTMLElement;
    const controls = () =>
      Array.from(
        panel.querySelectorAll<HTMLElement>(
          "button,input,select,textarea,summary,[tabindex]",
        ),
      ).filter(
        (el) =>
          !el.hasAttribute("disabled") &&
          el.tabIndex >= 0 &&
          el.getClientRects().length > 0,
      );
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    controls()[0]?.focus();
    const handle = (event: KeyboardEvent) => {
      if (document.querySelector(".modal")) return;
      if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        !document.querySelector("select:open")
      ) {
        event.preventDefault();
        closeRef.current();
      }
      if (event.key === "Tab") {
        const list = controls(),
          first = list[0],
          last = list.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handle);
    return () => {
      document.removeEventListener("keydown", handle);
      panel.removeAttribute("role");
      panel.removeAttribute("aria-modal");
      previous?.focus();
    };
  }, [open, selector, maxWidth]);
}
