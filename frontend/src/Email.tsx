import { useState, useRef, useEffect, useContext } from "react";
import {
  Check,
  ShieldCheck,
  Send,
  ArrowRight,
  Paperclip,
  RefreshCw,
} from "lucide-react";
import { type Draft, type Source, type EvidenceKey } from "./data";
import { Badge, Citation, Modal, Notice, EvidenceContext } from "./components";
import {
  apiFor,
  approveAndSend,
  chatRequest,
  draftFromServer,
  ApiError,
} from "./api";
import { draftPayload, validRecipient, sha256 } from "./workflow-model";
import { isVerified, type EmailState } from "./schema";

type Lock = { status: "pending" | "uncertain" | "sent"; mode?: string };
const stateLabels: Record<EmailState, string> = {
  IDLE: "Draft",
  AWAITING_CLARIFICATION: "Needs clarification",
  PENDING_APPROVAL: "Pending approval",
  APPROVED: "Approved by server",
  SENT: "Server accepted",
  FAILED_RETRYABLE: "Failed · retryable",
};
const localReviewKey = (d: Draft) =>
  JSON.stringify({ payload: draftPayload(d), cc: d.cc });
export default function Email({
  draft,
  onChange,
  onEvidence,
  notify,
  workspaceId,
  sources,
}: {
  draft: Draft;
  onChange: (d: Draft) => void;
  onEvidence: (k: EvidenceKey) => void;
  notify: (s: string) => void;
  workspaceId: string;
  sources: Source[];
}) {
  const [snapshot, setSnapshot] = useState<{
    draft: Draft;
    hash: string;
  } | null>(null);
  const [review, setReview] = useState<{ draft: Draft; hash: string } | null>(
    null,
  );
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [locks, setLocks] = useState<Record<string, Lock>>(() => {
    try {
      return JSON.parse(
        localStorage.getItem(`wai-email-submissions-${workspaceId}`) || "{}",
      );
    } catch {
      return {};
    }
  });
  const evidence = useContext(EvidenceContext);
  const mounted = useRef(true);
  const sending = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const key = localReviewKey(draft);
  const reviewed = snapshot && localReviewKey(snapshot.draft) === key;
  const lockKey = `${draft.id ?? "local"}:${draft.payloadHash ?? ""}`;
  const lock = locks[lockKey];
  const state =
    lock?.status === "sent" ? "SENT" : (draft.currentState ?? "IDLE");
  const blocked =
    busy ||
    lock?.status === "pending" ||
    lock?.status === "uncertain" ||
    state === "SENT";
  const connected = apiFor(workspaceId);
  const sameAsServer =
    draft.serverSnapshot &&
    draftPayload({ ...draft, ...draft.serverSnapshot }) === draftPayload(draft);
  const canSend =
    connected &&
    draft.origin === "server" &&
    !!draft.id &&
    !!draft.payloadHash &&
    sameAsServer &&
    !draft.cc.trim() &&
    !(draft.attachmentIds ?? []).length &&
    ["PENDING_APPROVAL", "FAILED_RETRYABLE", "APPROVED"].includes(state);
  const change = (field: keyof Draft, value: string | string[]) => {
    onChange({ ...draft, [field]: value, updatedAt: new Date().toISOString() });
    setError("");
  };
  const saveLock = (next: Lock) => {
    const stored = JSON.parse(
      localStorage.getItem(`wai-email-submissions-${workspaceId}`) || "{}",
    );
    const values = { ...stored, [lockKey]: next };
    // Persist before dispatch: a reload must not permit a second submission.
    localStorage.setItem(
      `wai-email-submissions-${workspaceId}`,
      JSON.stringify(values),
    );
    setLocks(values);
  };
  const openReview = async () => {
    if (
      !validRecipient(draft.to) ||
      !draft.subject.trim() ||
      !draft.body.trim()
    ) {
      notify(
        "Enter one valid recipient, a subject and a message before reviewing.",
      );
      return;
    }
    const copy = structuredClone(draft);
    const hash = await sha256(new TextEncoder().encode(draftPayload(copy)));
    if (mounted.current) setReview({ draft: copy, hash });
  };
  const submit = async () => {
    if (!reviewed || !canSend || blocked || sending.current) return;
    sending.current = true;
    setBusy(true);
    setError("");
    try {
      saveLock({ status: "pending" });
    } catch {
      setError(
        "The submission could not be saved on this device. Sending is paused.",
      );
      setBusy(false);
      sending.current = false;
      return;
    }
    try {
      const result = await approveAndSend(snapshot!.draft, workspaceId);
      if (result.status === "SENT") {
        saveLock({ status: "sent", mode: result.dispatch_mode });
        if (mounted.current) {
          onChange({
            ...draft,
            currentState: "SENT",
            sentAt: result.sent_at ?? draft.sentAt,
            updatedAt: new Date().toISOString(),
          });
          notify(
            result.dispatch_mode === "local_mock"
              ? "Server simulation completed. No real email was sent."
              : "The server accepted the email submission.",
          );
        }
      } else {
        saveLock({ status: "uncertain" });
        if (mounted.current)
          setError(
            "The server did not confirm SENT. Further sending is paused until the operation is checked.",
          );
      }
    } catch (err) {
      // The API has no operation-status endpoint. Never turn a timeout into SENT or blindly retry.
      saveLock({ status: "uncertain" });
      if (mounted.current)
        setError(
          `${err instanceof Error ? err.message : "Submission not confirmed."} ${err instanceof ApiError && err.status ? "The server rejected or could not complete this request." : "The delivery outcome is unknown."}`,
        );
    } finally {
      sending.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  return (
    <div className="email-screen">
      <div className="email-titlebar">
        <div className="tabs">
          <button
            className={!preview ? "selected" : ""}
            onClick={() => setPreview(false)}
          >
            Draft editor
          </button>
          <button
            className={preview ? "selected" : ""}
            onClick={() => setPreview(true)}
          >
            Message preview
          </button>
        </div>
        <Badge tone={state === "SENT" ? "document" : "neutral"}>
          {stateLabels[state]} ·{" "}
          {draft.origin === "server" ? "Server draft" : "Local draft"}
        </Badge>
      </div>
      {draft.context && (
        <div className="handoff-context small">
          Continued from: {draft.context}
        </div>
      )}
      <div className="email-layout">
        <section className="email-editor">
          <div className="email-purpose">
            <label>
              Purpose
              <select
                disabled={blocked}
                value={draft.purpose}
                onChange={(e) => change("purpose", e.target.value)}
              >
                <option>Clarification request</option>
                <option>Progress report</option>
                <option>Lecturer inquiry</option>
              </select>
            </label>
            <label>
              Tone
              <select
                disabled={blocked}
                value={draft.tone}
                onChange={(e) => change("tone", e.target.value)}
              >
                <option>Formal and respectful</option>
                <option>Friendly and concise</option>
                <option>Direct and professional</option>
              </select>
            </label>
          </div>
          <div className="email-fields">
            <label>
              <span>To</span>
              <textarea
                aria-label="Email recipients"
                placeholder="One recipient address"
                value={draft.to}
                readOnly={preview || blocked}
                onChange={(e) => change("to", e.target.value)}
                rows={2}
              />
            </label>
            <label>
              <span>CC notes</span>
              <textarea
                aria-label="CC recipients"
                placeholder="Local note only · not sent"
                value={draft.cc}
                readOnly={preview || blocked}
                onChange={(e) => change("cc", e.target.value)}
                rows={2}
              />
            </label>
            <label>
              <span>Subject</span>
              <input
                aria-label="Email subject"
                placeholder="Unspecified"
                value={draft.subject}
                readOnly={preview || blocked}
                onChange={(e) => change("subject", e.target.value)}
              />
            </label>
          </div>
          {preview ? (
            <div className="email-body-preview">
              {draft.body || "No message body yet."}
            </div>
          ) : (
            <textarea
              className="email-body"
              aria-label="Email body"
              placeholder="Write your message here…"
              value={draft.body}
              readOnly={blocked}
              onChange={(e) => change("body", e.target.value)}
            />
          )}
          <details className="email-attachments">
            <summary>
              <Paperclip size={14} />
              Attachments <span>{draft.attachmentIds?.length ?? 0}</span>
            </summary>
            <p className="small muted">
              Select files separately from the documents used as evidence. The
              current server cannot stage or send attachments yet.
            </p>
            {sources.map((s) => (
              <label className="schema-check" key={s.id}>
                <input
                  type="checkbox"
                  disabled={preview || blocked}
                  checked={draft.attachmentIds?.includes(s.id) ?? false}
                  onChange={(e) =>
                    change(
                      "attachmentIds",
                      e.target.checked
                        ? [...(draft.attachmentIds ?? []), s.id]
                        : (draft.attachmentIds ?? []).filter(
                            (id) => id !== s.id,
                          ),
                    )
                  }
                />
                {s.name}
              </label>
            ))}
            {(draft.attachmentIds ?? [])
              .filter((id) => !sources.some((s) => s.id === id))
              .map((id) => (
                <p className="small" key={id}>
                  Unavailable attachment: {id}
                </p>
              ))}
          </details>
          <div className="email-editor-footer">
            <span>
              <Check size={13} />
              Saved on this device
            </span>
            <span>
              {draft.body.trim() ? draft.body.trim().split(/\s+/).length : 0}{" "}
              words
            </span>
          </div>
        </section>
        <aside className="email-evidence">
          <h2>Behind the message</h2>
          <p className="small muted">Facts you can return to.</p>
          {draft.evidenceIds
            .filter((id) => evidence[id])
            .map((id) => (
              <div className="evidence-fact" key={id}>
                <Badge
                  tone={
                    isVerified(evidence[id].verificationStatus)
                      ? "document"
                      : "neutral"
                  }
                >
                  {isVerified(evidence[id].verificationStatus)
                    ? "Verified by server"
                    : "Unverified excerpt"}
                </Badge>
                <strong>{evidence[id].title}</strong>
                <Citation id={id} onOpen={onEvidence} />
              </div>
            ))}
          {draft.serverCitations?.map((c) => (
            <p className="small" key={c}>
              {c}
            </p>
          ))}
          {!draft.evidenceIds.length && !draft.serverCitations?.length && (
            <p className="small muted">No supporting citations attached.</p>
          )}
          {draft.cc.trim() && (
            <Notice tone="neutral">
              CC notes are kept locally. The server supports one recipient and
              does not send CC.
            </Notice>
          )}
          {/example\.edu/.test(draft.to) && (
            <Notice>
              This is a sample recipient address. Confirm it before sending.
            </Notice>
          )}
        </aside>
      </div>
      <section className="approval-section">
        <div className="approval-summary">
          <ShieldCheck size={23} />
          <div>
            <h2>
              {reviewed
                ? "This version has been reviewed."
                : snapshot
                  ? "The draft changed. Review again."
                  : "Your review comes before sending."}
            </h2>
            <p>
              {reviewed
                ? `Local SHA-256 · ${snapshot.hash.slice(0, 16)}…`
                : "Check the recipient, message and attachment list together."}
            </p>
          </div>
          <button
            className="button primary"
            disabled={busy}
            onClick={openReview}
          >
            {reviewed ? "View reviewed snapshot" : "Review exact version"}
            <ArrowRight size={14} />
          </button>
        </div>
        {error && <Notice tone="danger">{error}</Notice>}
        {lock?.status === "uncertain" || lock?.status === "pending" ? (
          <Notice>
            Submission outcome needs checking. Sending is locked for this draft.
            The current server does not provide an operation lookup; confirm the
            result on the server before creating a replacement.
          </Notice>
        ) : null}
        <div className="send-controls">
          <span className="small muted">
            {state === "SENT"
              ? lock?.mode === "local_mock"
                ? "Server mock completed · no real email sent"
                : "Server accepted · delivery receipt unavailable"
              : connected
                ? "Approval and dispatch are confirmed by the server"
                : "Backend not connected · draft stays local"}
          </span>
          <button
            className="button primary"
            disabled={!reviewed || !canSend || blocked}
            onClick={submit}
          >
            <Send size={14} />
            {busy
              ? "Submitting…"
              : state === "SENT"
                ? "Submission completed"
                : "Approve & send"}
          </button>
        </div>
        {connected && !sameAsServer && !blocked && (
          <Notice tone="neutral">
            This version is not staged on the server. Keep the local draft or
            request a new server-generated draft and review its content.
          </Notice>
        )}
        {connected && !blocked && (
          <button
            className="button"
            disabled={
              busy ||
              !validRecipient(draft.to) ||
              !draft.body.trim() ||
              !!draft.cc.trim() ||
              !!draft.attachmentIds?.length
            }
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                const result = await chatRequest(
                  `Draft an email. Subject: ${draft.subject}\nRequest: ${draft.body}`,
                  sources
                    .filter((s) => s.selected && s.origin === "server")
                    .map((s) => s.id),
                  [],
                  draft.to,
                  undefined,
                  workspaceId,
                );
                if (!result.draft)
                  throw new Error(
                    result.message || "The server did not create a draft.",
                  );
                const next = draftFromServer(
                  result.draft,
                  draft.sessionId ?? "",
                  { name: draft.context ?? "Email" },
                );
                if (mounted.current) {
                  onChange(next);
                  setSnapshot(null);
                  notify(
                    "Server draft created. Review the generated content before sending.",
                  );
                }
              } catch (err) {
                if (mounted.current)
                  setError(
                    err instanceof Error
                      ? err.message
                      : "Could not stage a new draft.",
                  );
              } finally {
                if (mounted.current) setBusy(false);
              }
            }}
          >
            <RefreshCw size={14} />
            Request a new server draft
          </button>
        )}
        <details className="email-audit">
          <summary>Approval state & audit history</summary>
          <p className="small">
            Current state: <strong>{state}</strong>
          </p>
          <p className="small muted">
            {draft.payloadHash
              ? `Server payload hash: ${draft.payloadHash}`
              : "Server payload hash unavailable."}
          </p>
          <p className="small muted">
            {draft.hmacSignature
              ? "Server signature provided."
              : "Server signature unavailable. Local review does not generate a server signature."}
          </p>
          {draft.auditLogs?.length ? (
            draft.auditLogs.map((log) => (
              <article className="audit-row" key={log.log_id}>
                <Badge tone={log.is_tampered ? "danger" : "neutral"}>
                  {log.from_state} → {log.to_state}
                </Badge>
                <p>
                  {log.trigger_event} · {log.actor} ·{" "}
                  {new Date(log.recorded_at).toLocaleString()}
                </p>
                {log.is_tampered && (
                  <Notice tone="danger">
                    The server recorded a tampered payload.
                  </Notice>
                )}
              </article>
            ))
          ) : (
            <p className="small muted">
              No server audit records are available. The current API does not
              expose audit history.
            </p>
          )}
        </details>
      </section>
      {review && (
        <Modal
          title="Review exact email snapshot"
          onClose={() => setReview(null)}
        >
          <div className="snapshot-field">
            <span>To</span>
            <p>{review.draft.to}</p>
          </div>
          {review.draft.cc && (
            <div className="snapshot-field">
              <span>CC notes · local only</span>
              <p>{review.draft.cc}</p>
            </div>
          )}
          <div className="snapshot-field">
            <span>Subject</span>
            <p>{review.draft.subject}</p>
          </div>
          <div className="snapshot-body">{review.draft.body}</div>
          <div className="snapshot-field">
            <span>Attachments</span>
            <p>
              {review.draft.attachmentIds?.length
                ? review.draft.attachmentIds
                    .map(
                      (id) =>
                        sources.find((s) => s.id === id)?.name ??
                        `Unavailable: ${id}`,
                    )
                    .join(", ")
                : "None"}
            </p>
          </div>
          <p className="fingerprint">Local SHA-256 · {review.hash}</p>
          <Notice tone="neutral">
            Any content or attachment change requires another review. Approval
            and sending happen when you select “Approve & send”.
          </Notice>
          <div className="modal-actions">
            <button className="button" onClick={() => setReview(null)}>
              Back to editing
            </button>
            <button
              className="button primary"
              disabled={localReviewKey(review.draft) !== key}
              onClick={() => {
                setSnapshot(review);
                setReview(null);
                notify(
                  "Review saved for this version. No email has been sent.",
                );
              }}
            >
              Confirm review
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
