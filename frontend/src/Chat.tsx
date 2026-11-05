import { useEffect, useId, useRef, useState } from "react";
import {
  ArrowUp,
  ArrowRight,
  X,
  Paperclip,
  ChevronDown,
  Columns3,
  Mail,
  Bookmark,
  RotateCcw,
  Check,
  BookOpen,
  CornerDownRight,
  AlertTriangle,
  LoaderCircle,
} from "lucide-react";
import { Badge, Citation, Notice } from "./components";
import {
  detectMode,
  relevantEvidence,
  initialEmail,
  blankDraft,
  type Workspace,
  type Thread,
  type Mode,
  type Message,
  type Handoff,
  type View,
} from "./data";
export default function Chat({
  workspace,
  thread,
  update,
  onEvidence,
  onHandoff,
  onView,
  onFiles,
}: {
  workspace: Workspace;
  thread: Thread;
  update: (fn: (w: Workspace) => Workspace) => void;
  onEvidence: (id: string) => void;
  onHandoff: (mode: Mode, context: Handoff) => void;
  onView: (v: View) => void;
  onFiles: () => void;
}) {
  const [input, setInput] = useState("");
  const [choice, setChoice] = useState<Mode | "Auto">(thread.mode);
  const [pending, setPending] = useState<Pick<
    Message,
    "request" | "mode" | "at"
  > | null>(null);
  const [filesExpanded, setFilesExpanded] = useState(false);
  const sourceListId = useId();
  const loading = pending !== null;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const previousCount = useRef(thread.messages.length);
  const selected = workspace.sources.filter(
    (s) => s.selected && s.status === "Processed",
  );
  const detected = detectMode(input);
  const mode = choice === "Auto" ? detected : choice;
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  useEffect(() => {
    if (thread.messages.length > previousCount.current || loading)
      bottom.current?.scrollIntoView({
        block: "end",
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
      });
    previousCount.current = thread.messages.length;
  }, [thread.messages.length, loading]);
  useEffect(() => {
    const field = inputRef.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, 136)}px`;
  }, [input]);
  const send = (request = input, forced?: Message["state"]) => {
    if (!request.trim() || loading) return;
    const ids = selected.map((s) => s.id);
    const activeMode = choice === "Auto" ? detectMode(request) : choice;
    const evidenceIds = relevantEvidence(workspace, request, ids);
    const at = new Date().toISOString();
    setInput("");
    setPending({ request: request.trim(), mode: activeMode, at });
    timer.current = setTimeout(() => {
      update((w) => {
        const result: Message = {
          id: crypto.randomUUID(),
          request: request.trim(),
          mode: activeMode,
          state:
            forced ??
            (activeMode === "Tasks"
              ? "suggestions"
              : activeMode === "Email"
                ? "draft"
                : evidenceIds.length
                  ? "answer"
                  : "abstention"),
          sourceIds: ids,
          evidenceIds,
          at,
        };
        let next = {
          ...w,
          updated: at,
          threads: w.threads.map((t) =>
            t.id === thread.id
              ? {
                  ...t,
                  mode: activeMode,
                  updated: at,
                  title: t.messages.length
                    ? t.title
                    : request.trim().slice(0, 70),
                  messages: [...t.messages, result],
                }
              : t,
          ),
        };
        if (result.state === "suggestions")
          next.suggestions = [
            ...w.suggestions,
            ...(evidenceIds.length
              ? evidenceIds.slice(0, 3).map((id) => ({
                  id: crypto.randomUUID(),
                  title: `Review ${w.evidence[id].title.toLowerCase()}`,
                  description: w.evidence[id].finding,
                  owner: "",
                  due: "",
                  selected: true,
                  source: id,
                  threadId: thread.id,
                }))
              : [
                  {
                    id: crypto.randomUUID(),
                    title: request.trim(),
                    description:
                      "Review this requested work and fill in the owner and deadline before confirming.",
                    owner: "",
                    due: "",
                    selected: true,
                    threadId: thread.id,
                  },
                ]),
          ];
        if (result.state === "draft") {
          const withRecipients = evidenceIds.includes("cc");
          next.draft = {
            ...blankDraft(),
            to: withRecipients ? initialEmail.to : "",
            cc: withRecipients ? initialEmail.cc : "",
            subject: `[${w.name}] ${request.trim().slice(0, 65)}`,
            body: evidenceIds.length
              ? `Dear ${withRecipients ? "Mr. Đức, Mr. Hào, and Mr. Quân" : "recipient"},\n\n${evidenceIds.map((id) => w.evidence[id].finding).join("\n\n")}\n\nCould you please clarify these points?\n\nThank you for your guidance.\n\nBest regards,\nPhạm Gia Khiêm`
              : `Hello,\n\nI’m writing about the following request:\n${request.trim()}\n\nPlease let me know what information you need from our team.\n\nBest regards,\nPhạm Gia Khiêm`,
            evidenceIds,
            context: thread.handoff?.question,
          };
          next.threads = next.threads.map((t) =>
            t.id === thread.id ? { ...t, draft: next.draft } : t,
          );
        }
        return next;
      });
      setPending(null);
    }, 550);
  };
  const handoff = (m: Message, to: Mode) =>
    onHandoff(to, {
      question: m.request,
      answer: m.evidenceIds
        .map((id) => workspace.evidence[id]?.finding)
        .filter(Boolean)
        .join("\n"),
      evidenceIds: m.evidenceIds,
      sourceIds: m.sourceIds,
    });
  return (
    <div className="chat-view">
      <div className="chat-scroll">
        {thread.handoff && (
          <div className="handoff-context">
            <CornerDownRight size={15} />
            <div>
              <span>Continued from</span>
              <p>{thread.handoff.question}</p>
              <small>
                {thread.handoff.evidenceIds.length} citations carried over ·{" "}
                {thread.handoff.sourceIds.length} selected files
              </small>
            </div>
          </div>
        )}
        {!thread.messages.length && (
          <div className="chat-empty">
            <div className="empty-brand">
              <BookOpen size={29} />
            </div>
            <span className="small muted">A new conversation</span>
            <h2>
              {workspace.sources.length
                ? "What would you like to understand?"
                : "Every good idea starts somewhere."}
            </h2>
            <p>
              {workspace.sources.length
                ? "Ask your sources, plan the work, or find the right words."
                : "Add your first documents, or start planning directly from chat."}
            </p>
            <div className="empty-actions">
              {!workspace.sources.length && (
                <button className="button primary" onClick={onFiles}>
                  <Paperclip size={15} />
                  Add your first files
                </button>
              )}
              <button
                className="button"
                onClick={() => {
                  setChoice("Tasks");
                  setInput("Plan the next steps for our project");
                  inputRef.current?.focus();
                }}
              >
                Plan some tasks <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}
        {thread.messages.map((m) => (
          <article className="exchange" key={m.id}>
            <UserMessage message={m} />
            <div className="answer" aria-label="WorkspaceAI response">
              <div className="answer-heading">
                <BookOpen size={19} />
                <div className="answer-identity">
                  <strong>WorkspaceAI</strong>
                  <span className="small muted">
                    {m.state === "answer"
                      ? "Grounded in your files"
                      : m.state === "abstention"
                        ? "Evidence check"
                        : m.state === "error"
                          ? "Generation interrupted"
                          : "For your review"}
                  </span>
                </div>
                <button
                  className={`icon-button save-answer ${m.saved ? "saved" : ""}`}
                  aria-label={m.saved ? "Unsave answer" : "Save answer"}
                  onClick={() =>
                    update((w) => ({
                      ...w,
                      threads: w.threads.map((t) =>
                        t.id === thread.id
                          ? {
                              ...t,
                              messages: t.messages.map((x) =>
                                x.id === m.id ? { ...x, saved: !x.saved } : x,
                              ),
                            }
                          : t,
                      ),
                    }))
                  }
                >
                  <Bookmark size={16} />
                </button>
              </div>
              {m.state === "answer" ? (
                <>
                  {m.evidenceIds.map((id) => {
                    const e = workspace.evidence[id];
                    return e ? (
                      <section
                        className={`finding${id === "conflict" ? " finding-conflict" : ""}`}
                        key={id}
                      >
                        <div className="finding-heading">
                          {id === "conflict" && <AlertTriangle size={16} />}
                          <h3>{e.title}</h3>
                        </div>
                        <p>{e.finding}</p>
                        <Citation id={id} onOpen={onEvidence} />
                        {id === "conflict" &&
                          m.evidenceIds.includes("deadline") && (
                            <p className="conflict-next-step">
                              Ask your lecturers to confirm the date before
                              updating the deadline.
                            </p>
                          )}
                      </section>
                    ) : (
                      <Notice key={id} tone="neutral">
                        This source is no longer available in this workspace.
                      </Notice>
                    );
                  })}
                  <div className="answer-footer">
                    <div className="answer-actions">
                      <button
                        className="button"
                        onClick={() => handoff(m, "Tasks")}
                      >
                        <Columns3 size={15} />
                        Break down into tasks <ArrowRight size={13} />
                      </button>
                      <button
                        className="button"
                        onClick={() => handoff(m, "Email")}
                      >
                        <Mail size={15} />
                        Draft email from this <ArrowRight size={13} />
                      </button>
                    </div>
                    <p className="provenance-note">
                      <Check size={13} />
                      Based only on the {m.sourceIds.length} files selected for
                      this response.
                    </p>
                  </div>
                </>
              ) : m.state === "abstention" ? (
                <div className="abstention">
                  <AlertTriangle size={21} />
                  <h3>There isn’t enough evidence to answer this.</h3>
                  <p>
                    The ticked files don’t establish this information. Missing
                    details stay unspecified.
                  </p>
                  <div className="flex-actions">
                    <button className="button" onClick={onFiles}>
                      Tick other files
                    </button>
                    <button
                      className="button"
                      onClick={() => {
                        setInput(m.request);
                        inputRef.current?.focus();
                      }}
                    >
                      Rephrase question
                    </button>
                  </div>
                </div>
              ) : m.state === "error" ? (
                <Notice tone="danger">
                  <strong>The answer couldn’t be generated.</strong>
                  <p>
                    Your question is preserved. Try again when you’re ready.
                  </p>
                  <button className="button" onClick={() => send(m.request)}>
                    <RotateCcw size={14} />
                    Retry
                  </button>
                </Notice>
              ) : m.state === "suggestions" ? (
                <div className="chat-result">
                  <Badge>
                    <Columns3 size={12} />
                    Suggested · Not confirmed
                  </Badge>
                  <h3>A plan to review, not a commitment.</h3>
                  <p>
                    Review the suggested work, fill in unspecified details, and
                    confirm only the tasks you want to create.
                  </p>
                  <div className="inline-evidence">
                    {m.evidenceIds.map((id) => (
                      <Citation key={id} id={id} onOpen={onEvidence} />
                    ))}
                  </div>
                  {!m.evidenceIds.length && <Badge>You provided</Badge>}
                  <button className="button" onClick={() => onView("tasks")}>
                    Review task suggestions <ArrowRight size={14} />
                  </button>
                </div>
              ) : (
                <div className="chat-result">
                  <Badge>
                    <Mail size={12} />
                    Draft · Not approved
                  </Badge>
                  <h3>The first words are ready for your review.</h3>
                  <p>
                    Open the draft to check recipients, supporting facts, and
                    tone. Approval and sending remain separate steps.
                  </p>
                  <div className="inline-evidence">
                    {m.evidenceIds.map((id) => (
                      <Citation key={id} id={id} onOpen={onEvidence} />
                    ))}
                  </div>
                  {!m.evidenceIds.length && <Badge>You provided</Badge>}
                  <button className="button" onClick={() => onView("email")}>
                    Review email draft <ArrowRight size={14} />
                  </button>
                </div>
              )}
            </div>
          </article>
        ))}
        {pending && (
          <article className="exchange pending-exchange">
            <UserMessage message={pending} />
            <div className="loading-answer" role="status">
              <LoaderCircle size={16} />
              <span>Reading the selected context…</span>
              <div className="loading-bars">
                <span />
                <span />
              </div>
            </div>
          </article>
        )}
        {!!thread.messages.length && !pending && (
          <div className="followups">
            <button
              onClick={() => {
                setChoice("Ask");
                setInput(
                  workspace.id === "midterm"
                    ? "What is the deadline for the midterm report?"
                    : "What should we prepare for the reading group?",
                );
                inputRef.current?.focus();
              }}
            >
              Explore the requirements
            </button>
            <button
              onClick={() => {
                setChoice("Tasks");
                setInput("Break down our next steps into tasks");
                inputRef.current?.focus();
              }}
            >
              Plan the next steps
            </button>
          </div>
        )}
        <div ref={bottom} />
      </div>
      <div className="composer-area">
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <textarea
            ref={inputRef}
            aria-label="Message your workspace"
            placeholder={
              mode === "Ask"
                ? "Ask anything about your files…"
                : mode === "Tasks"
                  ? "Describe the work you want to plan…"
                  : "What would you like your email to say?"
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                send();
              }
            }}
          />
          {filesExpanded && selected.length > 0 && (
            <div className="composer-file-chips" id={sourceListId}>
              {selected.map((s) => (
                <span className="file-chip" key={s.id} title={s.name}>
                  <span className="file-chip-name">{s.name}</span>
                  <button
                    type="button"
                    aria-label={`Stop using ${s.name}`}
                    onClick={() =>
                      update((w) => ({
                        ...w,
                        sources: w.sources.map((x) =>
                          x.id === s.id ? { ...x, selected: false } : x,
                        ),
                      }))
                    }
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          )}
          {!!input.trim() && (choice === "Auto" || choice !== detected) && (
            <div className="detected-mode">
              Suggested: {detected}
              {choice !== detected && choice !== "Auto" && (
                <button type="button" onClick={() => setChoice(detected)}>
                  Use
                </button>
              )}
            </div>
          )}
          <div className="composer-bottom">
            <div className="composer-tools">
              <div className="mode-field">
                <label htmlFor="composer-mode">Mode</label>
                <select
                  id="composer-mode"
                  aria-label="Composer mode"
                  value={choice}
                  onChange={(e) => {
                    const v = e.target.value as Mode | "Auto";
                    setChoice(v);
                    if (v !== "Auto")
                      update((w) => ({
                        ...w,
                        threads: w.threads.map((t) =>
                          t.id === thread.id ? { ...t, mode: v } : t,
                        ),
                      }));
                  }}
                >
                  <option>Auto</option>
                  <option>Ask</option>
                  <option>Tasks</option>
                  <option>Email</option>
                </select>
              </div>
              <div className="composer-source-tools">
                <button type="button" className="using-files" onClick={onFiles}>
                  <Paperclip size={14} />
                  <span>
                    <span className="files-prefix">Using </span>
                    {selected.length} of {workspace.sources.length} files
                  </span>
                </button>
                {selected.length > 0 && (
                  <button
                    type="button"
                    className="selected-files-toggle"
                    aria-label={
                      filesExpanded
                        ? "Hide selected files"
                        : "Show selected files"
                    }
                    aria-expanded={filesExpanded}
                    aria-controls={filesExpanded ? sourceListId : undefined}
                    onClick={() => setFilesExpanded(!filesExpanded)}
                  >
                    <ChevronDown size={14} />
                  </button>
                )}
              </div>
            </div>
            <button
              className="send-button"
              aria-label="Send message"
              disabled={!input.trim() || loading}
            >
              <ArrowUp size={19} />
            </button>
          </div>
        </form>
        <div className="composer-caption">
          <span>Enter to send · Shift + Enter for a new line</span>
          <details>
            <summary>Preview states</summary>
            <div className="state-menu">
              <button
                onClick={() =>
                  send("Where will the presentation take place?", "abstention")
                }
              >
                Insufficient evidence
              </button>
              <button
                onClick={() => send("Summarize the requirements.", "error")}
              >
                Generation failure
              </button>
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}
function UserMessage({
  message,
}: {
  message: Pick<Message, "request" | "mode" | "at">;
}) {
  return (
    <div className="question" aria-label="Your message">
      <div className="speaker">
        <strong>You</strong>
        <time dateTime={message.at}>
          {new Date(message.at).toLocaleTimeString("en-US", {
            hour: "numeric",
            minute: "2-digit",
            timeZone: "Asia/Bangkok",
          })}
        </time>
        <Badge>{message.mode}</Badge>
        <span className="avatar" aria-hidden="true">
          GK
        </span>
      </div>
      <p className="question-bubble">{message.request}</p>
    </div>
  );
}
