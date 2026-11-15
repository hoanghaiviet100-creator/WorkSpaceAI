import { useEffect, useRef, useState } from "react";
import { Mail } from "lucide-react";
import { ApiError, apiFor, getEmailConnection, sendStudioEmail } from "./api";
import { DialogCancel, Modal } from "./components";
import type { Workspace } from "./data";
import {
  defaultStudioConfig,
  visibleStudioResults,
  type StudioConfig,
  type StudioResult,
} from "./notebook-model";
import { generateStudio } from "./studio-service";
import { validRecipient } from "./workflow-model";

const undoWindow = 5000;

export function emailStatus(result: StudioResult, queuedId?: string) {
  if (result.id === queuedId) return "Waiting to send";
  if (result.status === "generating") return "Drafting…";
  if (result.delivery === "sending") return "Sending…";
  if (result.delivery === "sent")
    return result.dispatchMode === "local_mock" ? "Sent · Simulation" : "Sent";
  if (result.delivery === "unknown") return "Delivery unconfirmed";
  if (result.status === "error" || result.delivery === "failed")
    return "Failed";
  return "Draft";
}

export function useStudioEmail(
  workspace: Workspace,
  update: (change: (current: Workspace) => Workspace) => void,
  active: boolean,
) {
  const [config, setConfig] = useState<StudioConfig | null>(null);
  const [opened, setOpened] = useState<string | null>(null);
  const [connection, setConnection] =
    useState<Awaited<ReturnType<typeof getEmailConnection>>>();
  const [connectionError, setConnectionError] = useState("");
  const [showSetup, setShowSetup] = useState(false);
  const [queued, setQueued] = useState<{ id: string; until: number }>();
  const [seconds, setSeconds] = useState(5);
  const busy = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const mounted = useRef(false);
  const automatic = useRef(false);
  automatic.current = active && workspace.emailSendMode === "automatic";
  const results = visibleStudioResults(workspace);
  const result = results.find((item) => item.id === opened);
  const canSend =
    !!connection && (connection.mode === "local_mock" || connection.configured);
  const working = results.some(
    (item) => item.status === "generating" || item.delivery === "sending",
  );
  const refresh = async () => {
    if (!apiFor(workspace.id)) {
      setConnectionError("Start WorkspaceAI with its backend to use email.");
      return;
    }
    setConnectionError("");
    try {
      setConnection(await getEmailConnection());
    } catch {
      setConnection(undefined);
      setConnectionError(
        "Could not reach the email service. Check your connection.",
      );
    }
  };
  const openConfig = () => {
    setShowSetup(false);
    setConfig(defaultStudioConfig());
    void refresh();
  };
  const change = (id: string, fields: Partial<StudioResult>) =>
    update((current) => ({
      ...current,
      studioResults: current.studioResults?.map((row) =>
        row.id === id
          ? { ...row, ...fields, updatedAt: new Date().toISOString() }
          : row,
      ),
    }));
  const cancel = () => {
    window.clearTimeout(timer.current);
    timer.current = undefined;
    setQueued(undefined);
  };
  useEffect(() => {
    if (!active) cancel();
  }, [active]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      window.clearTimeout(timer.current);
    };
  }, []);
  useEffect(() => {
    if (!queued) return;
    const interval = window.setInterval(
      () =>
        setSeconds(Math.max(1, Math.ceil((queued.until - Date.now()) / 1000))),
      200,
    );
    return () => window.clearInterval(interval);
  }, [queued]);

  const send = async (row: StudioResult) => {
    if (!row.draft?.id || !connection || busy.current) return;
    busy.current = true;
    change(row.id, { delivery: "sending", error: undefined });
    try {
      const response = await sendStudioEmail(
        row.draft.id,
        workspace.id,
        connection.mode,
      );
      if (response.status === "FAILED") {
        change(row.id, {
          delivery: "failed",
          error: response.error?.includes("Authentication")
            ? "Gmail rejected the connection. Check or replace the app password, then try again."
            : "The email could not be sent. Check Gmail settings or your network and try again.",
        });
        return;
      }
      if (response.status !== "SENT") throw new Error("Delivery unconfirmed");
      const at = response.audit_timestamp || new Date().toISOString();
      update((current) => ({
        ...current,
        studioResults: current.studioResults?.map((item) =>
          item.id === row.id
            ? {
                ...item,
                delivery: "sent",
                dispatchMode: response.dispatch_mode,
                updatedAt: at,
              }
            : item,
        ),
        threads: current.threads.map((thread, index) =>
          index === 0 &&
          !thread.messages.some((message) => message.id === `sent-${row.id}`)
            ? {
                ...thread,
                messages: [
                  ...thread.messages,
                  {
                    id: `sent-${row.id}`,
                    studioResultId: row.id,
                    mode: "Email",
                    state: "answer",
                    request: "",
                    sourceIds: [],
                    evidenceIds: [],
                    at,
                  },
                ],
              }
            : thread,
        ),
      }));
    } catch (error) {
      const expired = error instanceof ApiError && error.status === 404;
      const modeChanged = error instanceof ApiError && error.status === 412;
      change(row.id, {
        delivery: expired || modeChanged ? "failed" : "unknown",
        ...(expired && { draft: undefined }),
        error: expired
          ? "This draft expired after the server restarted. Generate it again."
          : modeChanged
            ? "The delivery mode changed. Review the draft before trying again."
            : "Delivery could not be confirmed. Check Gmail before sending again.",
      });
    } finally {
      busy.current = false;
    }
  };
  const queue = (row: StudioResult) => {
    if (timer.current !== undefined || busy.current) return;
    setOpened(null);
    setSeconds(5);
    setQueued({ id: row.id, until: Date.now() + undoWindow });
    timer.current = window.setTimeout(() => {
      cancel();
      void send(row);
    }, undoWindow);
  };
  const review = (id: string) => {
    if (timer.current !== undefined) cancel();
    setShowSetup(false);
    setOpened(id);
    void refresh();
  };
  const create = async (options: StudioConfig, retry?: StudioResult) => {
    if (
      !canSend ||
      !validRecipient(options.recipient) ||
      !options.goal.trim() ||
      busy.current ||
      timer.current !== undefined
    )
      return;
    busy.current = true;
    const at = new Date().toISOString();
    const row: StudioResult = {
      id: retry?.id ?? crypto.randomUUID(),
      kind: "email",
      title: options.goal.trim().slice(0, 100),
      createdAt: retry?.createdAt ?? at,
      updatedAt: at,
      status: "generating",
      delivery: "draft",
      sourceIds: [],
      sourceSnapshot: [],
      evidenceIds: [],
      content: "",
      config: options,
      origin: "generated",
    };
    setConfig(null);
    update((current) => ({
      ...current,
      studioResults: [
        row,
        ...(current.studioResults ?? []).filter((item) => item.id !== row.id),
      ],
    }));
    let generated: StudioResult | undefined;
    try {
      const data = await generateStudio(workspace, options, true);
      generated = {
        ...row,
        ...data,
        title: data.draft?.subject || row.title,
        status: "ready",
      };
      change(row.id, generated);
    } catch (error) {
      change(row.id, {
        status: "error",
        error:
          error instanceof Error ? error.message : "Could not draft the email.",
      });
    } finally {
      busy.current = false;
    }
    if (!generated || !mounted.current) return;
    if (!retry && automatic.current) queue(generated);
    else review(generated.id);
  };
  const patch = (fields: Partial<StudioConfig>) =>
    setConfig((current) => current && { ...current, ...fields });
  const connectionNotice = (
    <div className="studio-email-connection">
      {connectionError ? (
        <>
          <p role="status">{connectionError}</p>
          <button
            type="button"
            className="button"
            onClick={() => void refresh()}
          >
            Retry
          </button>
        </>
      ) : !connection ? (
        <p role="status">Checking Gmail connection…</p>
      ) : (
        <>
          <p>
            {connection.mode === "local_mock"
              ? "Simulation mode. No email is delivered."
              : connection.configured
                ? "Gmail SMTP configured."
                : "Gmail is not connected."}
          </p>
          {(!connection.configured || connection.mode === "local_mock") && (
            <button
              type="button"
              className="button"
              onClick={() => setShowSetup(!showSetup)}
            >
              Connect Gmail
            </button>
          )}
          {showSetup && (
            <p>
              Set <code>EMAIL_DISPATCH_MODE=gmail_real</code>,{" "}
              <code>GMAIL_SENDER_EMAIL</code> and{" "}
              <code>GMAIL_APP_PASSWORD</code> in the server’s <code>.env</code>,
              then restart the backend. Enter the app password on the server.
            </p>
          )}
        </>
      )}
    </div>
  );
  const windows = (
    <>
      {queued && (
        <div className="studio-email-queue">
          <span role="status" className="sr-only">
            Email queued for five seconds. Undo or review before it sends.
          </span>
          <span aria-hidden="true">
            Sending in {seconds} {seconds === 1 ? "second" : "seconds"}
          </span>
          <button className="button" onClick={cancel}>
            Undo
          </button>
          <button className="button" onClick={() => review(queued.id)}>
            Review
          </button>
        </div>
      )}
      {config && (
        <Modal
          title="Draft & send email"
          titleIcon={<Mail size={18} />}
          onClose={() => setConfig(null)}
        >
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              void create(config);
            }}
          >
            <label>
              Recipient
              <input
                required
                type="email"
                value={config.recipient}
                onChange={(e) => patch({ recipient: e.target.value })}
              />
            </label>
            <label>
              What should the email cover?
              <textarea
                required
                maxLength={1500}
                rows={3}
                value={config.goal}
                onChange={(e) => patch({ goal: e.target.value })}
              />
            </label>
            <div className="studio-email-options">
              <label>
                Tone
                <select
                  value={config.tone}
                  onChange={(e) => patch({ tone: e.target.value })}
                >
                  <option>Formal</option>
                  <option>Friendly</option>
                  <option>Direct</option>
                </select>
              </label>
              <label>
                Length
                <select
                  value={config.length}
                  onChange={(e) => patch({ length: e.target.value })}
                >
                  <option>Short</option>
                  <option>Medium</option>
                  <option>Detailed</option>
                </select>
              </label>
            </div>
            {connectionNotice}
            <div className="modal-actions">
              <DialogCancel />
              <button
                className="button nb-add-source studio-email-primary"
                disabled={
                  !canSend ||
                  working ||
                  !!queued ||
                  !validRecipient(config.recipient) ||
                  !config.goal.trim()
                }
              >
                {workspace.emailSendMode === "automatic"
                  ? "Draft & queue send"
                  : "Create draft"}
              </button>
            </div>
          </form>
        </Modal>
      )}
      {result && (
        <Modal
          title="Email details"
          className="studio-email-drawer"
          motion="right"
          exitDuration={150}
          onClose={() => setOpened(null)}
        >
          <div className="form-stack studio-email-detail">
            <div>
              <strong>{result.title}</strong>
              <p>
                To {result.draft?.to || result.config.recipient} ·{" "}
                {emailStatus(result, queued?.id)}
              </p>
              <time dateTime={result.updatedAt}>
                {new Date(result.updatedAt).toLocaleString()}
              </time>
            </div>
            {result.error && (
              <p className="study-error" role="alert">
                {result.error}
              </p>
            )}
            {result.draft && (
              <p className="studio-email-body">{result.draft.body}</p>
            )}
            {result.draft?.serverCitations?.length ? (
              <p>Sources · {result.draft.serverCitations.join(" · ")}</p>
            ) : null}
            {["draft", "failed"].includes(result.delivery ?? "") &&
              result.status !== "generating" && (
                <>
                  {connectionNotice}
                  <button
                    className="button nb-add-source studio-email-primary"
                    disabled={!canSend || working || !!queued}
                    onClick={() => {
                      if (result.draft) queue(result);
                      else void create(result.config, result);
                    }}
                  >
                    {result.status === "error" || result.delivery === "failed"
                      ? "Retry"
                      : "Send email"}
                  </button>
                </>
              )}
          </div>
        </Modal>
      )}
    </>
  );
  return { openConfig, review, windows, queuedId: queued?.id };
}
