import { useEffect, useRef, useState, type CSSProperties } from "react";

type Rail = "sources" | "studio";
type Preferences = Partial<Record<Rail, number>>;
const key = "workspaceai-panel-widths";
const limits = {
  sources: { min: 224, max: 520 },
  studio: { min: 264, max: 560 },
};
const clamp = (value: number, min: number, max: number) =>
  Math.round(Math.max(min, Math.min(value, max)));

function readPreferences(): Preferences {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? "{}");
    return {
      sources: Number.isFinite(saved.sources) ? saved.sources : undefined,
      studio: Number.isFinite(saved.studio) ? saved.studio : undefined,
    };
  } catch {
    return {};
  }
}

export function usePanelWidths({
  desktop,
  leftClosed,
  rightClosed,
  expanded,
  secondary,
}: {
  desktop: boolean;
  leftClosed: boolean;
  rightClosed: boolean;
  expanded: boolean;
  secondary: Rail;
}) {
  const [viewport, setViewport] = useState(
    () => document.documentElement.clientWidth,
  );
  const [preferences, setPreferences] = useState(readPreferences);
  const latest = useRef(preferences);
  useEffect(() => {
    const observer = new ResizeObserver(() =>
      setViewport(document.documentElement.clientWidth),
    );
    observer.observe(document.documentElement);
    return () => observer.disconnect();
  }, []);

  const defaults =
    viewport >= 1600
      ? { sources: 320, studio: 380 }
      : { sources: 300, studio: 360 };
  // Reserve the two 16 px gutters and the 32 px total outer padding.
  const budget = viewport - 64 - 360;
  const preferredSources = clamp(
    preferences.sources ?? defaults.sources,
    limits.sources.min,
    limits.sources.max,
  );
  const preferredStudio = clamp(
    preferences.studio ?? defaults.studio,
    limits.studio.min,
    limits.studio.max,
  );
  function desktopSizes(hideSources: boolean, hideStudio: boolean) {
    let sources = hideSources ? 48 : preferredSources;
    let studio = hideStudio ? 48 : preferredStudio;
    if (!expanded && sources + studio > budget) {
      if (!hideStudio)
        studio = clamp(budget - sources, limits.studio.min, studio);
      if (!hideSources)
        sources = clamp(budget - studio, limits.sources.min, sources);
    }
    return { sources, studio };
  }
  const { sources, studio } = desktopSizes(leftClosed, rightClosed);
  const tabletMax = (rail: Rail) =>
    Math.min(limits[rail].max, viewport - 48 - 320);
  const tablet = clamp(
    preferences[secondary] ?? 304,
    limits[secondary].min,
    tabletMax(secondary),
  );
  const style = {
    "--nb-left-size": `${sources}px`,
    "--nb-right-size": `${studio}px`,
    "--nb-left-open-size": `${desktopSizes(false, rightClosed).sources}px`,
    "--nb-right-open-size": `${desktopSizes(leftClosed, false).studio}px`,
    "--nb-tablet-size": `${tablet}px`,
  } as CSSProperties;

  const save = () => {
    try {
      localStorage.setItem(key, JSON.stringify(latest.current));
    } catch {
      /* Widths remain available until this workspace closes. */
    }
  };
  function handle(rail: Rail) {
    const { min, max } = limits[rail];
    const rangeMax = desktop
      ? Math.min(
          max,
          expanded ? max : budget - (rail === "sources" ? studio : sources),
        )
      : tabletMax(rail);
    const value = desktop ? (rail === "sources" ? sources : studio) : tablet;
    const update = (width: number | undefined, persist: boolean) => {
      const next = {
        ...latest.current,
        [rail]: width === undefined ? undefined : clamp(width, min, rangeMax),
      };
      latest.current = next;
      setPreferences(next);
      if (persist) save();
    };
    return {
      rail,
      value,
      min,
      max: rangeMax,
      direction: desktop && rail === "sources" ? 1 : -1,
      update,
      save,
    };
  }
  return { style, handle };
}

export function PanelDivider({
  rail,
  value,
  min,
  max,
  direction,
  update,
  save,
}: ReturnType<ReturnType<typeof usePanelWidths>["handle"]>) {
  const activeDrag = useRef<AbortController | null>(null);
  const [dragging, setDragging] = useState(false);
  useEffect(() => () => activeDrag.current?.abort(), []);
  const label = rail === "sources" ? "Sources" : "Studio";
  return (
    <div
      className={`nb-resize nb-resize-${rail}${dragging ? " is-dragging" : ""}`}
      role="separator"
      tabIndex={0}
      aria-label={`Resize the ${label} panel`}
      aria-orientation="vertical"
      aria-controls={`nb-pane-${rail}`}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-valuetext={`${value} pixel`}
      title={`Drag to resize ${label}. Double-click to reset.`}
      onPointerDown={(event) => {
        if (event.button !== 0 || activeDrag.current) return;
        event.preventDefault();
        event.currentTarget.focus({ preventScroll: true });
        const { pointerId, clientX } = event;
        const controller = new AbortController();
        activeDrag.current = controller;
        const options = { signal: controller.signal };
        const resize = (pointer: PointerEvent) => {
          if (pointer.pointerId === pointerId)
            update(value + direction * (pointer.clientX - clientX), false);
        };
        const finish = () => {
          controller.abort();
          activeDrag.current = null;
          setDragging(false);
          save();
        };
        window.addEventListener("pointermove", resize, options);
        window.addEventListener(
          "pointerup",
          (pointer) => {
            if (pointer.pointerId !== pointerId) return;
            resize(pointer);
            finish();
          },
          options,
        );
        window.addEventListener(
          "pointercancel",
          (pointer) => {
            if (pointer.pointerId === pointerId) finish();
          },
          options,
        );
        window.addEventListener("blur", finish, options);
        setDragging(true);
      }}
      onDoubleClick={() => update(undefined, true)}
      onKeyDown={(event) => {
        const positions: Record<string, number> = {
          ArrowLeft: value - direction * 24,
          ArrowRight: value + direction * 24,
          Home: min,
          End: max,
        };
        if (!Object.hasOwn(positions, event.key)) return;
        event.preventDefault();
        update(positions[event.key], true);
      }}
    />
  );
}
