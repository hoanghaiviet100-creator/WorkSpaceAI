import { useCallback, useLayoutEffect, useRef, type RefObject } from "react";

const reducedMotion = "(prefers-reduced-motion: reduce)";
const windows = new WeakMap<HTMLElement, Animation>();
type Motion = "vertical" | "rise" | "fade" | "left" | "right";

function clearMotion(target: HTMLElement) {
  windows.get(target)?.cancel();
  windows.delete(target);
  target.style.removeProperty("will-change");
}

function playWindow(
  target: HTMLElement,
  opening: boolean,
  motion: Motion,
  duration = opening ? 160 : 110,
) {
  // Sample the visual state only when a click interrupts an entrance.
  const running = windows.get(target)?.playState === "running";
  const current = running ? getComputedStyle(target) : null;
  const slide = motion !== "fade";
  const rail = motion === "left" || motion === "right";
  const railOffset = (motion === "left" ? -1 : 1) * (opening ? 24 : 18);
  const offset = rail
    ? `translateX(${railOffset}px)`
    : `translateY(${motion === "rise" ? 16 : opening ? 3 : 2}px)`;
  const from: Keyframe = {
    opacity:
      current?.opacity ?? (opening ? (rail ? 0.86 : slide ? 0.8 : 0.9) : 1),
    ...(slide && {
      transform: current?.transform ?? (opening ? offset : "none"),
    }),
  };
  const to: Keyframe = {
    opacity: opening ? 1 : slide ? 0.5 : 0.76,
    ...(slide && { transform: opening ? "none" : offset }),
  };
  clearMotion(target);
  target.style.willChange = slide ? "transform, opacity" : "opacity";
  const animation = target.animate([from, to], {
    duration,
    easing: opening
      ? "cubic-bezier(0.2, 0, 0, 1)"
      : "cubic-bezier(0.4, 0, 1, 1)",
    fill: opening ? "none" : "forwards",
  });
  windows.set(target, animation);
  return animation;
}

export function useEntrance(
  scope: RefObject<HTMLElement | null>,
  visible = true,
  {
    revision,
    motion = "vertical",
    revealOnly = false,
    mountMotion,
    duration,
    onEntered,
  }: {
    revision?: boolean | string;
    motion?: Motion;
    revealOnly?: boolean;
    mountMotion?: Motion;
    duration?: number;
    onEntered?: () => void;
  } = {},
) {
  const entered = useRef(onEntered);
  entered.current = onEntered;
  const previous = useRef({ visible, revision });
  const mounted = useRef(false);

  useLayoutEffect(() => {
    const target = scope.current;
    if (!target) return;
    clearMotion(target);
    const changed =
      previous.current.visible !== visible ||
      previous.current.revision !== revision;
    previous.current = { visible, revision };
    const entryMotion = mounted.current ? undefined : mountMotion;
    if (!visible || (revealOnly && !changed && !entryMotion)) return;

    const preference = matchMedia(reducedMotion);
    if (preference.matches) {
      entered.current?.();
      return;
    }
    const animation = playWindow(target, true, entryMotion ?? motion, duration);
    const finish = () => {
      if (windows.get(target) !== animation) return;
      clearMotion(target);
      entered.current?.();
    };
    const onPreference = () => {
      if (preference.matches) finish();
    };
    animation.onfinish = finish;
    preference.addEventListener("change", onPreference);
    return () => {
      preference.removeEventListener("change", onPreference);
      clearMotion(target);
    };
  }, [scope, visible, revision, motion, revealOnly, mountMotion, duration]);

  useLayoutEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
}

export function useExit(duration?: number) {
  const current = useRef<{ target: HTMLElement; dispose: () => void } | null>(
    null,
  );
  const cancel = useCallback(() => {
    const exit = current.current;
    current.current = null;
    if (!exit) return;
    exit.dispose();
    clearMotion(exit.target);
  }, []);
  useLayoutEffect(() => cancel, [cancel]);

  return useCallback(
    (
      target: HTMLElement | null,
      done: () => void,
      motion: Motion = "vertical",
    ) => {
      if (target && current.current?.target === target) return;
      cancel();
      const preference = matchMedia(reducedMotion);
      if (!target || preference.matches) {
        done();
        return;
      }
      const animation = playWindow(target, false, motion, duration);
      const dispose = () =>
        preference.removeEventListener("change", onPreference);
      const finish = () => {
        if (current.current?.target !== target) return;
        current.current = null;
        dispose();
        target.style.removeProperty("will-change");
        done();
        // A guarded dismiss can leave the window open.
        requestAnimationFrame(() => {
          if (windows.get(target) === animation) clearMotion(target);
        });
      };
      const onPreference = () => {
        if (preference.matches) finish();
      };
      current.current = { target, dispose };
      animation.onfinish = finish;
      preference.addEventListener("change", onPreference);
    },
    [cancel, duration],
  );
}
