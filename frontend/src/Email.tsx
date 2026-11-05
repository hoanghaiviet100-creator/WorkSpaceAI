import { useState, useRef, useEffect, useContext } from "react";
import {
  Check,
  ShieldCheck,
  Send,
  Mail,
  ArrowRight,
  Clock,
  Link2,
  RotateCcw,
} from "lucide-react";
import { type Draft, type EvidenceKey } from "./data";
import { Badge, Citation, Modal, Notice, EvidenceContext } from "./components";
type SendState = "Not sent" | "Pending" | "Sent" | "Failed" | "Uncertain";
type Delivery = { status: SendState; key: string };
const payload = (d: Draft) =>
  JSON.stringify({ to: d.to, cc: d.cc, subject: d.subject, body: d.body });
export default function Email({
  draft,
  onChange,
  onEvidence,
  notify,
  workspaceId,
}: {
  draft: Draft;
  onChange: (d: Draft) => void;
  onEvidence: (k: EvidenceKey) => void;
  notify: (s: string) => void;
  workspaceId: string;
}) {
  const [snapshot, setSnapshot] = useState<Draft | null>(null);
  const [fingerprint, setFingerprint] = useState("");
  const [review, setReview] = useState<{
    draft: Draft;
    fingerprint: string;
  } | null>(null);
  const [outdated, setOutdated] = useState(false);
  const [outcome, setOutcome] = useState<SendState>("Sent");
  const [connected, setConnected] = useState(true);
  const [preview, setPreview] = useState(false);
  const [deliveries, setDeliveries] = useState<Record<string, SendState>>(
    () => {
      try {
        return JSON.parse(
          localStorage.getItem(`wai-delivery-${workspaceId}`) || "{}",
        );
      } catch {
        return {};
      }
    },
  );
  const evidence = useContext(EvidenceContext);
  const key = payload(draft);
  const sendState = deliveries[key] || "Not sent";
  const pending = useRef(false);
  useEffect(
    () =>
      localStorage.setItem(
        `wai-delivery-${workspaceId}`,
        JSON.stringify(deliveries),
      ),
    [deliveries, workspaceId],
  );
  useEffect(() => {
    if (snapshot && payload(snapshot) !== key) {
      setSnapshot(null);
      setOutdated(true);
    }
  }, [key, snapshot]);
  const change = (field: keyof Draft, value: string) => {
    onChange({ ...draft, [field]: value });
    if (snapshot) {
      setSnapshot(null);
      setOutdated(true);
    }
  };
  const reviewDraft = async () => {
    if (!draft.to.trim() || !draft.subject.trim() || !draft.body.trim()) {
      notify("Complete the recipient, subject, and body first.");
      return;
    }
    const valid = (v: string) =>
      v
        .split(/[,;]/)
        .filter((x) => x.trim())
        .every(
          (x) =>
            /^[^<>]*<[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+>$/.test(x.trim()) ||
            /^[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+$/.test(x.trim()),
        );
    if (!valid(draft.to) || !valid(draft.cc)) {
      notify("Check each recipient address before reviewing.");
      return;
    }
    const reviewed = { ...draft };
    const bytes = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(payload(reviewed)),
    );
    const hash = Array.from(new Uint8Array(bytes))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("")
      .slice(0, 16);
    setReview({ draft: reviewed, fingerprint: hash });
  };
  const send = () => {
    if (
      !snapshot ||
      payload(snapshot) !== key ||
      !connected ||
      pending.current ||
      ["Pending", "Sent", "Uncertain"].includes(sendState)
    )
      return;
    pending.current = true;
    const sendKey = key;
    setDeliveries((d) => ({ ...d, [sendKey]: "Pending" }));
    setTimeout(() => {
      setDeliveries((d) => ({ ...d, [sendKey]: outcome }));
      pending.current = false;
      notify(
        outcome === "Sent"
          ? "Demo server accepted the email. Delivery is not confirmed."
          : outcome === "Failed"
            ? "Demo submission failed. Your draft is preserved."
            : "Outcome uncertain. Checking the existing operation.",
      );
    }, 650);
  };
  const blocked = sendState === "Pending" || sendState === "Uncertain";
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
        <Badge tone={snapshot ? "document" : outdated ? "warning" : "neutral"}>
          {snapshot ? (
            <>
              <ShieldCheck size={12} />
              Approved
            </>
          ) : outdated ? (
            "Approval outdated"
          ) : (
            "Draft · Not approved"
          )}
        </Badge>
      </div>
      {draft.context && (
        <div className="handoff-context small">
          Continued from: {draft.context}
        </div>
      )}
      {!draft.body && (
        <Notice tone="neutral">
          Start a request in Email mode, or write a draft directly below.
          Recipients and missing details remain unspecified.
        </Notice>
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
                placeholder="Unspecified"
                value={draft.to}
                readOnly={preview || blocked}
                onChange={(e) => change("to", e.target.value)}
                rows={2}
              />
            </label>
            <label>
              <span>CC</span>
              <textarea
                aria-label="CC recipients"
                placeholder="Unspecified"
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
          <div className="email-editor-footer">
            <span>
              <Check size={13} />
              Saved in this workspace
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
                <Badge tone="document">
                  <Check size={11} />
                  From document
                </Badge>
                <strong>{evidence[id].title}</strong>
                <Citation id={id} onOpen={onEvidence} />
              </div>
            ))}
          <div className="evidence-fact">
            <Badge>You provided</Badge>
            <p>Sender details and the communication request.</p>
          </div>
          {/example\.edu/.test(draft.to + draft.cc) && (
            <Notice>
              <strong>Check recipient addresses.</strong>
              <p>These example.edu addresses are sample data.</p>
            </Notice>
          )}
          {!draft.to && (
            <Notice>
              <strong>Recipient unspecified.</strong>
              <p>Add a verified address before approval.</p>
            </Notice>
          )}
          {(!draft.evidenceIds.length ||
            draft.evidenceIds.includes("conflict")) && (
            <Notice tone="neutral">
              <strong>Information is incomplete.</strong>
              <p>
                {draft.evidenceIds.includes("conflict")
                  ? "The date conflict still needs confirmation."
                  : "No document evidence supports this draft. Review user-provided facts."}
              </p>
            </Notice>
          )}
        </aside>
      </div>
      <section className="approval-section">
        <div className="approval-summary">
          <ShieldCheck size={23} />
          <div>
            <h2>
              {snapshot
                ? "This exact version is approved."
                : outdated
                  ? "Approval outdated. Review again."
                  : "Your review comes before sending."}
            </h2>
            <p>
              {snapshot
                ? `Integrity fingerprint · ${fingerprint}`
                : outdated
                  ? "The recipients or message changed after approval."
                  : "Check the complete message, then approve this version."}
            </p>
          </div>
          <button
            className={`button ${snapshot ? "" : "primary"}`}
            disabled={blocked}
            onClick={reviewDraft}
          >
            {snapshot ? "View approved snapshot" : "Review & approve"}
            <ArrowRight size={14} />
          </button>
        </div>
        <div className="send-controls">
          <span className="small muted">
            {connected
              ? "Demo email account connected"
              : "Email account disconnected"}
          </span>
          {!connected ? (
            <button className="button" onClick={() => setConnected(true)}>
              <Link2 size={14} />
              Reconnect email account
            </button>
          ) : (
            <button
              className="button primary"
              disabled={!snapshot || blocked || sendState === "Sent"}
              onClick={send}
            >
              <Send size={14} />
              {sendState === "Pending"
                ? "Submission pending…"
                : sendState === "Sent"
                  ? "Sent · Server accepted"
                  : "Send approved email"}
            </button>
          )}
        </div>
        <div className="send-timeline" aria-live="polite">
          {(["Prepared", "Pending", "Sent"] as const).map((s, i) => (
            <div
              key={s}
              className={
                i === 0 ||
                (i === 1 && sendState !== "Not sent") ||
                (i === 2 && sendState === "Sent")
                  ? "reached"
                  : ""
              }
            >
              <span>
                {i === 0 ? (
                  <Check size={13} />
                ) : i === 1 ? (
                  <Clock size={13} />
                ) : (
                  <Mail size={13} />
                )}
              </span>
              <div>
                <strong>
                  {i === 0
                    ? "Draft prepared"
                    : i === 1
                      ? "Pending"
                      : sendState === "Failed"
                        ? "Failed"
                        : sendState === "Uncertain"
                          ? "Uncertain"
                          : "Sent · Server accepted"}
                </strong>
                <p>
                  {i === 0
                    ? "Approval required"
                    : i === 1
                      ? "One controlled submission"
                      : sendState === "Failed"
                        ? "Draft retained for retry"
                        : sendState === "Uncertain"
                          ? "Checking existing operation"
                          : "Confirmed delivery: unknown"}
                </p>
              </div>
            </div>
          ))}
        </div>
        {sendState === "Failed" && (
          <Notice tone="danger">
            The demo email service rejected this submission.
            <button className="text-button" onClick={send}>
              Retry approved submission
            </button>
          </Notice>
        )}
        {sendState === "Uncertain" && (
          <Notice>
            Resending is blocked while the existing operation is checked.
            <button
              className="text-button"
              onClick={() => setDeliveries((d) => ({ ...d, [key]: "Sent" }))}
            >
              Check existing operation
            </button>
          </Notice>
        )}
        {sendState === "Pending" && !pending.current && (
          <Notice tone="neutral">
            An earlier submission is still pending.
            <button
              className="text-button"
              onClick={() => setDeliveries((d) => ({ ...d, [key]: "Sent" }))}
            >
              Check existing operation
            </button>
          </Notice>
        )}
        <details className="demo-controls">
          <summary>Delivery preview controls</summary>
          <div>
            <label>
              Next outcome
              <select
                aria-label="Mock delivery outcome"
                value={outcome}
                onChange={(e) => setOutcome(e.target.value as SendState)}
              >
                <option>Sent</option>
                <option>Failed</option>
                <option>Uncertain</option>
              </select>
            </label>
            <button className="button" onClick={() => setConnected(!connected)}>
              {connected ? "Simulate disconnection" : "Reconnect account"}
            </button>
            <button
              className="button"
              disabled={pending.current}
              onClick={() =>
                setDeliveries((d) => {
                  const copy = { ...d };
                  delete copy[key];
                  return copy;
                })
              }
            >
              Reset demo delivery
            </button>
          </div>
          <p>Local simulation. No email is sent.</p>
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
          <div className="snapshot-field">
            <span>CC</span>
            <p>{review.draft.cc || "Unspecified"}</p>
          </div>
          <div className="snapshot-field">
            <span>Subject</span>
            <p>{review.draft.subject}</p>
          </div>
          <div className="snapshot-body">{review.draft.body}</div>
          <p className="fingerprint">
            <ShieldCheck size={14} />
            SHA-256 · {review.fingerprint}
          </p>
          <Notice tone="neutral">
            Any edit invalidates approval. Sending remains a separate action.
          </Notice>
          <div className="modal-actions">
            <button className="button" onClick={() => setReview(null)}>
              Back to editing
            </button>
            <button
              className="button primary"
              disabled={payload(review.draft) !== key}
              onClick={() => {
                setSnapshot(review.draft);
                setFingerprint(review.fingerprint);
                setOutdated(false);
                setReview(null);
                notify("This exact version is approved.");
              }}
            >
              <Check size={14} />
              Approve this version
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
