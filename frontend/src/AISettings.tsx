import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, LoaderCircle } from "lucide-react";
import { getRuntimeStatus, selectProvider, type RuntimeStatus } from "./api";

const providers = [
  { id: "ollama", name: "Ollama", detail: "Local model" },
  { id: "gemini", name: "Gemini", detail: "Cloud model" },
] as const;
type Provider = (typeof providers)[number]["id"];

export default function AISettings({
  onConfigured,
  onStatus,
  disabled = false,
}: {
  onConfigured: (status: RuntimeStatus) => void;
  onStatus?: (status: RuntimeStatus) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const picker = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const checkId = useRef(0);
  const changing = useRef(false);
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [checking, setChecking] = useState(true);
  const [pending, setPending] = useState<Provider | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const requestId = ++checkId.current;
    setChecking(true);
    setError("");
    try {
      const value = await getRuntimeStatus();
      if (checkId.current !== requestId) return;
      setStatus(value);
      onStatus?.(value);
    } catch {
      if (checkId.current === requestId)
        setError("Could not load AI settings. Try again.");
    } finally {
      if (checkId.current === requestId) setChecking(false);
    }
  }, [onStatus]);

  useEffect(() => {
    void refresh();
    const menu = picker.current;
    if (
      menu &&
      new URLSearchParams(location.search).has("setup") &&
      !menu.matches(":popover-open")
    )
      menu.showPopover();
    const leave = () => menu?.hidePopover();
    addEventListener("hashchange", leave);
    return () => {
      checkId.current++;
      removeEventListener("hashchange", leave);
    };
  }, [refresh]);

  const choose = async (provider: Provider) => {
    if (changing.current || checking) return;
    if (provider === status?.engine_mode) {
      picker.current?.hidePopover();
      trigger.current?.focus();
      return;
    }
    changing.current = true;
    setPending(provider);
    setError("");
    try {
      const value = await selectProvider(provider);
      setStatus(value);
      onStatus?.(value);
      onConfigured(value);
      const wasOpen = picker.current?.matches(":popover-open");
      picker.current?.hidePopover();
      if (wasOpen) trigger.current?.focus();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not change the AI model.",
      );
    } finally {
      changing.current = false;
      setPending(null);
    }
  };

  const currentProvider = providers.find(
    ({ id }) => id === status?.engine_mode,
  );
  const modelName =
    status?.model || currentProvider?.name || (status ? "Offline" : "AI model");

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="ai-settings-trigger"
        aria-label="Choose AI model"
        popoverTarget={id}
        disabled={disabled}
        title={modelName}
        onClick={() => {
          if (
            !picker.current?.matches(":popover-open") &&
            !checking &&
            !changing.current
          )
            void refresh();
        }}
      >
        <span>{modelName}</span>
        <ChevronDown size={13} aria-hidden="true" />
      </button>
      <div
        id={id}
        ref={picker}
        popover="auto"
        className="ai-model-picker"
        role="group"
        aria-label="AI models"
        onToggle={(event) => {
          if (event.newState !== "closed") return;
          const url = new URL(location.href);
          if (!url.searchParams.has("setup")) return;
          url.searchParams.delete("setup");
          history.replaceState(history.state, "", url);
        }}
      >
        <p className="ai-model-picker-heading">Model</p>
        {checking && !status && (
          <p className="ai-model-feedback" role="status">
            Loading models…
          </p>
        )}
        {status &&
          providers.map(({ id, name, detail }) => {
            const option = status.provider_options?.find(
              (option) => option.id === id,
            );
            const active = status.engine_mode === id;
            const unavailable = !option?.configured && !active;
            return (
              <button
                key={id}
                type="button"
                className="ai-model-option"
                aria-pressed={active}
                disabled={checking || pending !== null || unavailable}
                onClick={() => void choose(id)}
              >
                <span>
                  <strong>{option?.model || name}</strong>
                  <small>
                    {name} · {unavailable ? "Not configured" : detail}
                  </small>
                </span>
                {pending === id ? (
                  <LoaderCircle size={15} aria-label="Checking model" />
                ) : (
                  active && <Check size={15} aria-hidden="true" />
                )}
              </button>
            );
          })}
        {error && (
          <div className="ai-model-feedback" role="alert">
            {error}
            {!checking && !pending && (
              <button type="button" onClick={() => void refresh()}>
                Refresh models
              </button>
            )}
          </div>
        )}
      </div>
    </>
  );
}
