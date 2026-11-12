import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Settings2, LoaderCircle } from "lucide-react";
import { DialogCancel, Modal, Notice } from "./components";
import { getRuntimeStatus, selectProvider, type RuntimeStatus } from "./api";

export default function AISettings({
  onConfigured,
  onStatus,
  disabled = false,
}: {
  onConfigured: (status: RuntimeStatus) => void;
  onStatus?: (status: RuntimeStatus) => void;
  disabled?: boolean;
}) {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [checking, setChecking] = useState(true);
  const [open, setOpen] = useState(() =>
    new URLSearchParams(location.search).has("setup"),
  );
  const [selected, setSelected] = useState<"ollama" | "gemini">("ollama");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const receive = (value: RuntimeStatus) => {
    setStatus(value);
    setSelected(value.engine_mode === "gemini" ? "gemini" : "ollama");
    onStatus?.(value);
  };
  useEffect(() => {
    let active = true;
    getRuntimeStatus()
      .then((value) => {
        if (!active) return;
        setStatus(value);
        setSelected(value.engine_mode === "gemini" ? "gemini" : "ollama");
        onStatus?.(value);
      })
      .catch(() => {
        if (active)
          setError("Could not load AI settings. Check the server connection.");
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, [onStatus]);
  useEffect(() => {
    const leave = () => setOpen(false);
    addEventListener("hashchange", leave);
    return () => removeEventListener("hashchange", leave);
  }, []);
  const close = () => {
    if (pending) return;
    setOpen(false);
    const url = new URL(location.href);
    url.searchParams.delete("setup");
    history.replaceState(history.state, "", url);
  };
  const engine = status?.engine_mode;
  const options = status?.provider_options ?? [];
  const selectedOption = options.find((option) => option.id === selected);
  return (
    <>
      <button
        type="button"
        className="ai-settings-trigger"
        aria-label="Choose AI model"
        disabled={disabled}
        title={
          status?.model
            ? `${engine === "gemini" ? "Gemini" : engine === "ollama" ? "Ollama" : "Offline"} · ${status.model}`
            : "Choose AI model"
        }
        onClick={() => {
          setOpen(true);
          setChecking(true);
          setError("");
          getRuntimeStatus()
            .then(receive)
            .catch(() => setError("Could not load AI settings. Try again."))
            .finally(() => setChecking(false));
        }}
      >
        <Settings2 size={13} />
        <span>
          {!status
            ? "AI model"
            : engine === "ollama"
              ? "Ollama"
              : engine === "gemini"
                ? "Gemini"
                : "Offline"}
        </span>
      </button>
      {open &&
        createPortal(
          <Modal title="Choose AI model" onClose={close}>
            {checking ? (
              <p role="status" className="small muted window-loading">
                Loading AI settings…
              </p>
            ) : !status ? (
              <Notice tone="danger">
                {error || "The AI server is not ready."}
              </Notice>
            ) : (
              <form
                className="ai-settings-form"
                onSubmit={async (event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  if (pending) return;
                  setPending(true);
                  setError("");
                  try {
                    const value = await selectProvider(selected);
                    receive(value);
                    onConfigured(value);
                    setOpen(false);
                  } catch (err) {
                    setError(
                      err instanceof Error
                        ? err.message
                        : "Could not change the AI model.",
                    );
                  } finally {
                    setPending(false);
                  }
                }}
              >
                <p className="small">
                  In use:{" "}
                  <strong>
                    {status.engine_mode === "ollama"
                      ? "Ollama"
                      : status.engine_mode === "gemini"
                        ? "Gemini"
                        : "Offline"}
                  </strong>
                  {status.model ? ` · ${status.model}` : ""}
                </p>
                <label>
                  AI model
                  <select
                    aria-label="AI model"
                    value={selected}
                    onChange={(event) => {
                      setSelected(event.target.value as "ollama" | "gemini");
                      setError("");
                    }}
                    disabled={pending}
                  >
                    <option value="ollama">
                      Ollama ·{" "}
                      {options.find((option) => option.id === "ollama")
                        ?.model ?? "Local AI"}
                    </option>
                    <option value="gemini">
                      Gemini ·{" "}
                      {options.find((option) => option.id === "gemini")
                        ?.model ?? "Cloud AI"}
                    </option>
                  </select>
                </label>
                {selected === "ollama" ? (
                  <p className="small muted">
                    Requests are processed by the local Ollama server. The
                    connection and model are checked before switching.
                  </p>
                ) : (
                  <>
                    <p className="small muted">
                      Questions and relevant excerpts are sent to Google. The
                      administrator configures the API key on the server.
                    </p>
                    {!selectedOption?.configured && (
                      <Notice tone="neutral">
                        Gemini is unavailable until an administrator configures
                        the API key.
                      </Notice>
                    )}
                  </>
                )}
                {error && (
                  <div role="alert">
                    <Notice tone="danger">{error}</Notice>
                  </div>
                )}
                <div className="modal-actions">
                  <DialogCancel disabled={pending} />
                  <button
                    type="submit"
                    className="button primary"
                    disabled={pending || !selectedOption?.configured}
                  >
                    {pending && <LoaderCircle size={14} />}{" "}
                    {pending ? "Checking…" : "Apply"}
                  </button>
                </div>
              </form>
            )}
          </Modal>,
          document.body,
        )}
    </>
  );
}
