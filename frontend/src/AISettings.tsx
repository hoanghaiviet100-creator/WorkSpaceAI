import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Settings2, ExternalLink, LoaderCircle } from "lucide-react";
import { Modal, Notice } from "./components";
import {
  configureGemini,
  getRuntimeStatus,
  useOffline,
  type RuntimeStatus,
} from "./api";
import type { Mode } from "./data";

const models = ["gemini-3.5-flash-lite", "gemini-3.8-flash"];
export default function AISettings({
  onConfigured,
  onStatus,
  mode = "Ask",
}: {
  onConfigured: (status: RuntimeStatus) => void;
  onStatus?: (status: RuntimeStatus) => void;
  mode?: Mode;
}) {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [checking, setChecking] = useState(true);
  const [open, setOpen] = useState(
    () => new URLSearchParams(location.search).get("setup") === "gemini",
  );
  const [key, setKey] = useState("");
  const [model, setModel] = useState(models[0]);
  const [saveLocally, setSaveLocally] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    getRuntimeStatus()
      .then((value) => {
        if (!active) return;
        setStatus(value);
        if (value.model && models.includes(value.model)) setModel(value.model);
        onStatus?.(value);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, [onStatus]);
  useEffect(() => {
    const leaveView = () => {
      setOpen(false);
      setKey("");
    };
    addEventListener("hashchange", leaveView);
    return () => removeEventListener("hashchange", leaveView);
  }, []);
  const close = () => {
    setOpen(false);
    setKey("");
    setError("");
    const url = new URL(location.href);
    url.searchParams.delete("setup");
    history.replaceState(history.state, "", url);
  };
  const configured = (value: RuntimeStatus) => {
    setStatus(value);
    onStatus?.(value);
    close();
    onConfigured(value);
  };
  const engine =
    mode === "Ask"
      ? status?.engine_mode
      : mode === "Email"
        ? status?.feature_engines?.email
        : "offline";
  return (
    <>
      <button
        type="button"
        className="ai-settings-trigger"
        aria-label="AI settings"
        title={
          mode !== "Ask"
            ? "This feature runs locally. Gemini is available only for Feature 1 document Q&A and summaries."
            : engine === "gemini"
              ? `Gemini · ${status?.model} · Feature 1 only`
              : "Offline document lookup. Connect Gemini for Feature 1."
        }
        onClick={() => {
          setError("");
          setOpen(true);
        }}
      >
        <Settings2 size={13} />
        <span>
          {!status
            ? "Engine"
            : mode !== "Ask"
              ? engine === "ollama"
                ? "Ollama"
                : "Local"
              : engine === "gemini"
                ? "Gemini"
                : engine === "ollama"
                  ? "Ollama"
                  : "Offline"}
        </span>
      </button>
      {open &&
        createPortal(
          <Modal title="Feature 1 · Document AI" onClose={close}>
            {!status ? (
              <p className="small muted">
                {checking
                  ? "Reading local engine settings…"
                  : "Engine settings are unavailable. Check the backend connection and refresh."}
              </p>
            ) : (
              <>
                <Notice tone="neutral">
                  {status.engine_mode === "gemini"
                    ? `Gemini is connected with ${status.model}.`
                    : "Offline document lookup is active."}{" "}
                  Gemini applies only to document Q&A and summaries in Ask mode.
                  Tasks and email use local processing.
                </Notice>
                <p className="small muted">
                  When connected, your question and relevant excerpts from
                  selected files are sent to Google. Free access depends on your
                  project's billing tier and quota. Connecting checks model
                  access without generating an answer.
                </p>
                <p className="small">
                  <a
                    className="ai-key-link"
                    href="https://aistudio.google.com/api-keys"
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    API keys in Google AI Studio <ExternalLink size={12} />
                  </a>
                  {" · "}
                  <a
                    href="https://ai.google.dev/gemini-api/docs/rate-limits"
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    Check quota
                  </a>
                </p>
                <form
                  className="edit-task-form ai-settings-form"
                  onSubmit={async (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (pending) return;
                    setPending(true);
                    setError("");
                    try {
                      configured(
                        await configureGemini(key.trim(), saveLocally, model),
                      );
                    } catch (err) {
                      setError(
                        err instanceof Error
                          ? err.message
                          : "Gemini could not be configured.",
                      );
                    } finally {
                      setPending(false);
                    }
                  }}
                >
                  <label>
                    Model
                    <select
                      aria-label="Gemini model for Feature 1"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      disabled={pending}
                    >
                      <option value={models[0]}>Gemini 3.5 Flash-Lite</option>
                      <option value={models[1]}>Gemini 3.8 Flash</option>
                    </select>
                  </label>
                  <label>
                    Gemini API key
                    <input
                      autoFocus
                      aria-label="Gemini API key"
                      type="password"
                      autoComplete="off"
                      spellCheck={false}
                      value={key}
                      onChange={(e) => setKey(e.target.value)}
                      required={!status.gemini_configured}
                      maxLength={1024}
                      placeholder={
                        status.gemini_configured
                          ? "Leave blank to use the saved key"
                          : "Paste your key here"
                      }
                      disabled={pending}
                    />
                  </label>
                  <label className="schema-check">
                    <input
                      type="checkbox"
                      checked={saveLocally}
                      onChange={(e) => setSaveLocally(e.target.checked)}
                      disabled={pending}
                    />
                    Save these settings on this device
                  </label>
                  <p className="small muted">
                    The key stays in the local backend, outside browser storage
                    and frontend files. The selected model is fixed; quota
                    errors do not trigger another model.
                  </p>
                  {error && <Notice tone="danger">{error}</Notice>}
                  <div className="modal-actions">
                    {status.engine_mode === "gemini" && (
                      <button
                        type="button"
                        className="button"
                        disabled={pending}
                        onClick={async () => {
                          setPending(true);
                          setError("");
                          try {
                            configured(await useOffline(saveLocally));
                          } catch (err) {
                            setError(
                              err instanceof Error
                                ? err.message
                                : "Offline mode could not be applied.",
                            );
                          } finally {
                            setPending(false);
                          }
                        }}
                      >
                        Use Offline
                      </button>
                    )}
                    <button type="button" className="button" onClick={close}>
                      Cancel
                    </button>
                    <button
                      className="button primary"
                      disabled={
                        pending || (!key.trim() && !status.gemini_configured)
                      }
                    >
                      {pending && <LoaderCircle size={14} />}
                      {pending
                        ? "Checking key…"
                        : "Connect Gemini for Feature 1"}
                    </button>
                  </div>
                </form>
              </>
            )}
          </Modal>,
          document.body,
        )}
    </>
  );
}
