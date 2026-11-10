import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
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
  Copy,
  ThumbsUp,
  ThumbsDown,
  FileText,
} from "lucide-react";
import { apiFor, chatRequest, draftFromServer, selectDocuments } from "./api";
import { isVerified, featureRoute, type EngineMode } from "./schema";
import { validRecipient, resolveCitedSource } from "./workflow-model";
import { appendReport } from "./report-model";
import AISettings from "./AISettings";
import type { RuntimeStatus } from "./api";
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
  type Evidence,
  type Draft,
} from "./data";
export default function Chat({
  workspace,
  thread,
  update,
  onEvidence,
  onHandoff,
  onView,
  onFiles,
  active,
  notebook = false,
  onStudioOpen,
  onKanbanOpen,
}: {
  workspace: Workspace;
  thread: Thread;
  update: (fn: (w: Workspace) => Workspace) => void;
  onEvidence: (id: string) => void;
  onHandoff: (mode: Mode, context: Handoff) => void;
  onView: (v: View, tab?: string) => void;
  onFiles: () => void;
  active: boolean;
  notebook?: boolean;
  onStudioOpen?: (id: string) => void;
  onKanbanOpen?: () => void;
}) {
  const [input, setInput] = useState(thread.composerDraft ?? "");
  const [choice, setChoice] = useState<Mode | "Auto">(thread.mode);
  const [pending, setPending] = useState<Pick<
    Message,
    "request" | "mode" | "at"
  > | null>(null);
  const [filesExpanded, setFilesExpanded] = useState(false);
  const sourceListId = useId();
  const loading = pending !== null;
  const live = apiFor(workspace.id);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const requestLock = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollViewport = useRef<HTMLDivElement>(null);
  const wasActive = useRef(false);
  const followLatest = useRef(true);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (thread.composerDraft) inputRef.current?.focus();
  }, [thread.id]);
  const previousCount = useRef(thread.messages.length);
  const selected = workspace.sources.filter(
    (s) =>
      s.selected &&
      s.status === "Processed" &&
      (!live || s.origin === "server"),
  );
  const detected = detectMode(input);
  const mode = notebook ? "Ask" : choice === "Auto" ? detected : choice;
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  useLayoutEffect(() => {
    // A mounted but hidden chat has no usable scroll height until it is opened.
    if (!active) {
      wasActive.current = false;
      return;
    }
    const entering = !wasActive.current;
    const viewport = scrollViewport.current;
    // A short empty view starts at its greeting; real conversations still follow the latest reply.
    if (notebook && !thread.messages.length && !loading) {
      followLatest.current = false;
      viewport?.scrollTo({ top: 0, behavior: "auto" });
      wasActive.current = true;
      previousCount.current = 0;
      return;
    }
    if (
      viewport &&
      (entering || thread.messages.length > previousCount.current || loading)
    ) {
      followLatest.current = true;
      viewport.scrollTo({
        top: viewport.scrollHeight,
        behavior:
          entering || matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto"
            : "smooth",
      });
    }
    wasActive.current = true;
    previousCount.current = thread.messages.length;
  }, [active, thread.id, thread.messages.length, loading]);
  useEffect(() => {
    const viewport = scrollViewport.current;
    if (!active || !viewport) return;
    const onScroll = () => {
      followLatest.current =
        viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop < 96;
    };
    // Keep the latest answer visible as fonts or the selected-file composer settle.
    const observer = new ResizeObserver(() => {
      if (followLatest.current)
        viewport.scrollTo({ top: viewport.scrollHeight, behavior: "auto" });
    });
    viewport.addEventListener("scroll", onScroll, { passive: true });
    observer.observe(viewport);
    for (const child of viewport.children) observer.observe(child);
    return () => {
      observer.disconnect();
      viewport.removeEventListener("scroll", onScroll);
    };
  }, [active, thread.id, thread.messages.length, loading]);
  useEffect(() => {
    const field = inputRef.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, 136)}px`;
  }, [input]);
  const send = async (request = input, forced?: Message["state"]) => {
    if (!request.trim() || loading || requestLock.current) return;
    const ids = selected.map((s) => s.id);
    const activeMode = choice === "Auto" ? detectMode(request) : choice;
    const evidenceIds = relevantEvidence(workspace, request, ids);
    const at = new Date().toISOString();
    setInput("");
    if (thread.composerDraft)
      update((workspace) => ({
        ...workspace,
        threads: workspace.threads.map((item) =>
          item.id === thread.id ? { ...item, composerDraft: undefined } : item,
        ),
      }));
    setPending({ request: request.trim(), mode: activeMode, at });
    if (live) {
      requestLock.current = true;
      const result: Message = {
        id: crypto.randomUUID(),
        request: request.trim(),
        mode: activeMode,
        state: "answer",
        sourceIds: ids,
        evidenceIds: [],
        at,
        origin: "server",
      };
      try {
        if (selected.some((s) => s.origin !== "server"))
          throw new Error(
            "Sync the server library and select server documents before asking a live question.",
          );
        const recipient =
          request.match(
            /[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/,
          )?.[0] ??
          (validRecipient(workspace.draft.to) ? workspace.draft.to : undefined);
        if (activeMode === "Email" && !recipient)
          throw new Error(
            "Specify a recipient email address in your request or in the Email editor first.",
          );
        const history = thread.messages
          .filter((m) => m.origin === "server" && m.state === "answer")
          .flatMap((m) => [
            { role: "user", content: m.request },
            {
              role: "assistant",
              content:
                m.answerText ??
                m.evidenceIds
                  .map((id) => workspace.evidence[id]?.finding ?? "")
                  .join("\n"),
            },
          ]);
        const response = await chatRequest(
          request.trim(),
          ids,
          history,
          recipient,
          undefined,
          workspace.id,
        );
        result.routeType = response.route;
        result.groundingScore =
          typeof response.grounding_score === "number" &&
          response.grounding_score >= 0 &&
          response.grounding_score <= 1
            ? response.grounding_score
            : undefined;
        const claims: Record<string, Evidence> = {};
        const rejected: string[] = (response.hallucination_flags ?? []).map(
          (c) => c.verification_status ?? "Unverified claim",
        );
        for (const c of response.validated_claims ?? []) {
          const source = resolveCitedSource(c.cited_doc_id, workspace.sources);
          if (
            !isVerified(c.verification_status) ||
            !source ||
            !ids.includes(source.id)
          ) {
            rejected.push(
              c.verification_status ?? "Unverified or out-of-scope claim",
            );
            continue;
          }
          const id = c.claim_id || crypto.randomUUID();
          result.evidenceIds.push(id);
          claims[id] = {
            id: source.id,
            file: source.name,
            title: "Supported finding",
            finding: c.claim_text,
            quote: c.evidence_quote,
            locator: `p. ${c.cited_page}${c.cited_start_line ? ` · lines ${c.cited_start_line}–${c.cited_end_line ?? c.cited_start_line}` : ""}`,
            context: "Server-verified citation",
            claimId: c.claim_id,
            messageId: c.message_id,
            page: c.cited_page,
            startLine: c.cited_start_line ?? undefined,
            endLine: c.cited_end_line ?? undefined,
            verificationStatus: c.verification_status,
            matchScore: c.match_score,
            matchedSpan: c.matched_span ?? undefined,
            docVersion: c.doc_version,
            docHash: c.doc_hash,
            verifiedAt: c.verified_at,
            origin: "server",
          };
        }
        result.rejectedClaims = rejected;
        let draft: Draft | undefined;
        let report: Workspace | undefined;
        if (response.draft) {
          draft = draftFromServer(response.draft, thread.id, workspace);
          result.state = "draft";
        } else if (response.reconciliation_report) {
          report = appendReport(
            workspace,
            response.reconciliation_report,
            new Date().toLocaleDateString("en-CA"),
          );
          result.answerText =
            "The server reconciliation report is ready in Tasks → Reconciliation. It uses server requirements and tasks; local board edits are not included.";
        } else if (response.route === "QA_FLOW") {
          result.state = result.evidenceIds.length ? "answer" : "abstention";
          result.answerText = result.evidenceIds.length
            ? response.status === "SUMMARY_GENERATED"
              ? response.message
              : undefined
            : response.message;
        } else {
          result.answerText =
            response.message ??
            "The server needs more information before continuing.";
        }
        update((w) => ({
          ...w,
          ...(draft ? { draft } : {}),
          ...(report
            ? {
                reconciliationRuns: [
                  ...(w.reconciliationRuns ?? []),
                  report.reconciliationRuns!.at(-1)!,
                ],
                reconciledItems: [
                  ...(w.reconciledItems ?? []),
                  ...report.reconciledItems!.filter(
                    (i) =>
                      i.run_id === report!.reconciliationRuns!.at(-1)!.run_id,
                  ),
                ],
              }
            : {}),
          evidence: { ...w.evidence, ...claims },
          updated: at,
          threads: w.threads.map((t) =>
            t.id === thread.id
              ? {
                  ...t,
                  ...(draft ? { draft } : {}),
                  mode: activeMode,
                  updated: at,
                  title: t.messages.length
                    ? t.title
                    : request.trim().slice(0, 70),
                  messages: [...t.messages, result],
                }
              : t,
          ),
        }));
      } catch (err) {
        result.state = "error";
        result.errorText =
          err instanceof Error
            ? err.message
            : "The server response could not be confirmed.";
        update((w) => ({
          ...w,
          threads: w.threads.map((t) =>
            t.id === thread.id
              ? { ...t, messages: [...t.messages, result], updated: at }
              : t,
          ),
        }));
      } finally {
        requestLock.current = false;
        setPending(null);
      }
      return;
    }
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
          origin: "sample",
          routeType: featureRoute(activeMode),
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
  const welcome = notebook && !thread.messages.length && !pending;
  return (
    <div className={`chat-view${welcome ? " nb-chat-welcome" : ""}`}>
      <div className="chat-scroll" ref={scrollViewport}>
        {notebook && (
          <section
            className={`nb-source-overview${welcome ? " is-welcome" : ""}`}
          >
            {welcome && (
              <div className="nb-chat-emblem" aria-hidden="true">
                <BookOpen size={44} strokeWidth={1.35} />
              </div>
            )}
            <h3>
              {welcome
                ? "Bạn muốn tìm hiểu điều gì?"
                : "Tài liệu trong workspace"}
            </h3>
            <p>
              {workspace.sources.length
                ? `${selected.length} nguồn đã chọn trong ${workspace.sources.length} tài liệu. Câu trả lời dựa trên những nguồn bạn chọn.`
                : "Thêm tài liệu ở cột Nguồn để bắt đầu hỏi đáp."}
            </p>
            {!!workspace.sources.length && (
              <details>
                <summary>Xem các nguồn đã sẵn sàng</summary>
                <ul>
                  {workspace.sources
                    .filter((source) => source.status === "Processed")
                    .slice(0, 8)
                    .map((source) => (
                      <li key={source.id}>
                        <FileText size={13} />
                        {source.name}
                      </li>
                    ))}
                </ul>
              </details>
            )}
            <div className="nb-prompt-cards">
              {[
                {
                  label: "Tóm tắt tài liệu",
                  query: "Tóm tắt các ý chính trong tài liệu",
                },
                {
                  label: "Các yêu cầu chính",
                  query: "Các yêu cầu cần hoàn thành là gì?",
                },
                {
                  label: "Mốc thời gian",
                  query: "Những mốc thời gian nào được đề cập?",
                },
              ].map((prompt) => (
                <button
                  key={prompt.query}
                  disabled={!selected.length || loading}
                  onClick={() => void send(prompt.query)}
                >
                  {prompt.label}
                  <ArrowRight size={14} />
                </button>
              ))}
            </div>
          </section>
        )}
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
        {!notebook && !thread.messages.length && (
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
        {thread.messages.map((m) =>
          notebook && m.kanbanEvent ? (
            <div className="nb-studio-event" key={m.id}>
              <Check size={15} />
              <button onClick={onKanbanOpen}>
                {m.kanbanEvent.initial ? "Đã tạo Kanban" : "Đã thêm vào Kanban"}
                : {m.kanbanEvent.count} thẻ
                <ArrowRight size={14} />
              </button>
            </div>
          ) : notebook && m.studioResultId ? (
            <div className="nb-studio-event" key={m.id}>
              <Check size={15} />
              <span>
                Đã lưu {m.state === "draft" ? "bản nháp email" : "kế hoạch"}:
              </span>
              <button onClick={() => onStudioOpen?.(m.studioResultId!)}>
                {workspace.studioResults?.find(
                  (result) => result.id === m.studioResultId,
                )?.title || "Kết quả đã xóa"}
                <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            <article className="exchange" key={m.id}>
              <UserMessage message={m} />
              <div className="answer" aria-label="WorkspaceAI response">
                <div className="answer-heading">
                  <BookOpen size={19} />
                  <div className="answer-identity">
                    <strong>WorkspaceAI</strong>
                    <span className="small muted">
                      {m.state === "answer"
                        ? m.origin === "server"
                          ? "Server response"
                          : "Sample conversation"
                        : m.state === "abstention"
                          ? "Evidence check"
                          : m.state === "error"
                            ? "Generation interrupted"
                            : "For your review"}
                    </span>
                  </div>
                  <button
                    hidden={notebook}
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
                    {m.answerText && (
                      <p className="server-answer-text">{m.answerText}</p>
                    )}
                    {m.groundingScore !== undefined && !notebook && (
                      <p className="small muted">
                        Grounding score · {Math.round(m.groundingScore * 100)}%
                      </p>
                    )}
                    {m.evidenceIds.map((id, index) => {
                      const e = workspace.evidence[id];
                      return e &&
                        !(
                          e.origin === "server" &&
                          !isVerified(e.verificationStatus)
                        ) ? (
                        <section
                          className={`finding${id === "conflict" ? " finding-conflict" : ""}`}
                          key={id}
                        >
                          <div
                            className="finding-heading"
                            hidden={notebook && e.title === "Supported finding"}
                          >
                            {id === "conflict" && <AlertTriangle size={16} />}
                            <h3>{e.title}</h3>
                          </div>
                          <p>{e.finding}</p>
                          <Badge
                            tone={
                              e.origin === "server" &&
                              isVerified(e.verificationStatus)
                                ? "document"
                                : "neutral"
                            }
                          >
                            {e.verificationStatus?.replaceAll("_", " ") ??
                              "Unverified sample"}
                          </Badge>
                          <Citation
                            id={id}
                            onOpen={onEvidence}
                            number={notebook ? index + 1 : undefined}
                          />
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
                    {!!m.rejectedClaims?.length && (
                      <Notice tone="neutral">
                        {m.rejectedClaims.length} unsupported claim
                        {m.rejectedClaims.length === 1 ? " was" : "s were"}{" "}
                        excluded from this answer.
                      </Notice>
                    )}
                    {m.routeType === "RECONCILE_FLOW" && (
                      <button
                        className="button"
                        onClick={() => onView("tasks", "reconciliation")}
                      >
                        Open Tasks & reconciliation
                        <ArrowRight size={13} />
                      </button>
                    )}
                    <div className="answer-footer">
                      <div className="answer-actions">
                        <button
                          className="button"
                          onClick={() => handoff(m, "Tasks")}
                        >
                          <Columns3 size={15} />
                          {notebook
                            ? "Lên kế hoạch từ đây"
                            : "Break down into tasks"}{" "}
                          <ArrowRight size={13} />
                        </button>
                        <button
                          className="button"
                          onClick={() => handoff(m, "Email")}
                        >
                          <Mail size={15} />
                          {notebook
                            ? "Soạn email từ đây"
                            : "Draft email from this"}{" "}
                          <ArrowRight size={13} />
                        </button>
                      </div>
                      <p className="provenance-note">
                        <Check size={13} />
                        {m.origin === "server"
                          ? `${m.sourceIds.length} documents selected for this request.`
                          : "Sample evidence · original documents not verified."}
                      </p>
                    </div>
                  </>
                ) : m.state === "abstention" ? (
                  <div className="abstention">
                    <AlertTriangle size={21} />
                    <h3>There isn’t enough evidence to answer this.</h3>
                    <p>
                      {m.answerText ||
                        "The ticked files don’t establish this information. Missing details stay unspecified."}
                    </p>
                    {!!m.rejectedClaims?.length && (
                      <p className="small muted">
                        {m.rejectedClaims.length} unsupported claims excluded.
                      </p>
                    )}
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
                      {m.errorText ||
                        "Your question is preserved. Try again when you’re ready."}
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
                      Review the suggested work, fill in unspecified details,
                      and confirm only the tasks you want to create.
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
                      tone. Your review is required before approval and sending.
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
                {notebook && m.state === "answer" && (
                  <div className="nb-answer-tools">
                    <button
                      title="Sao chép câu trả lời"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(
                            [
                              m.answerText,
                              ...m.evidenceIds.map(
                                (id) => workspace.evidence[id]?.finding,
                              ),
                            ]
                              .filter(Boolean)
                              .join("\n\n"),
                          );
                        } catch {
                          /* The answer remains selectable for manual copying. */
                        }
                      }}
                    >
                      <Copy size={15} />
                      <span>Sao chép</span>
                    </button>
                    <button
                      aria-pressed={!!m.saved}
                      onClick={() =>
                        update((current) => ({
                          ...current,
                          threads: current.threads.map((item) => ({
                            ...item,
                            messages: item.messages.map((message) =>
                              message.id === m.id
                                ? { ...message, saved: !message.saved }
                                : message,
                            ),
                          })),
                        }))
                      }
                    >
                      <Bookmark size={15} />
                      <span>{m.saved ? "Đã lưu ghi chú" : "Lưu ghi chú"}</span>
                    </button>
                    {(["helpful", "unhelpful"] as const).map((feedback) => (
                      <button
                        key={feedback}
                        aria-label={
                          feedback === "helpful" ? "Hữu ích" : "Chưa hữu ích"
                        }
                        aria-pressed={m.feedback === feedback}
                        title={
                          feedback === "helpful" ? "Hữu ích" : "Chưa hữu ích"
                        }
                        onClick={() =>
                          update((current) => ({
                            ...current,
                            threads: current.threads.map((item) => ({
                              ...item,
                              messages: item.messages.map((message) =>
                                message.id === m.id
                                  ? {
                                      ...message,
                                      feedback:
                                        message.feedback === feedback
                                          ? undefined
                                          : feedback,
                                    }
                                  : message,
                              ),
                            })),
                          }))
                        }
                      >
                        {feedback === "helpful" ? (
                          <ThumbsUp size={15} />
                        ) : (
                          <ThumbsDown size={15} />
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </article>
          ),
        )}
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
        {!notebook && !!thread.messages.length && !pending && (
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
              notebook
                ? "Hỏi điều gì đó về tài liệu của bạn…"
                : mode === "Ask"
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
                    onClick={async () => {
                      if (s.origin === "server") {
                        try {
                          await selectDocuments(
                            selected
                              .filter(
                                (x) => x.origin === "server" && x.id !== s.id,
                              )
                              .map((x) => x.id),
                            workspace.id,
                          );
                        } catch {
                          onFiles();
                          return;
                        }
                      }
                      update((w) => ({
                        ...w,
                        sources: w.sources.map((x) =>
                          x.id === s.id ? { ...x, selected: false } : x,
                        ),
                      }));
                    }}
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          )}
          {!notebook &&
            !!input.trim() &&
            (choice === "Auto" || choice !== detected) && (
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
              <div className="mode-field" hidden={notebook}>
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
              <div className="mode-field engine-field">
                <label htmlFor="engine-mode">Engine</label>
                {live ? (
                  <AISettings
                    mode={mode}
                    onStatus={setRuntime}
                    onConfigured={(status) =>
                      update((w) => ({
                        ...w,
                        threads: w.threads.map((t) =>
                          t.id === thread.id
                            ? { ...t, engineMode: status.engine_mode }
                            : t,
                        ),
                      }))
                    }
                  />
                ) : (
                  <select
                    id="engine-mode"
                    aria-label="Session engine preference"
                    title={
                      live
                        ? "The live engine is managed by the server."
                        : "Saved preference only. This standalone preview uses sample responses."
                    }
                    disabled={live || loading}
                    value={live ? "server" : (thread.engineMode ?? "offline")}
                    onChange={(e) =>
                      update((w) => ({
                        ...w,
                        threads: w.threads.map((t) =>
                          t.id === thread.id
                            ? { ...t, engineMode: e.target.value as EngineMode }
                            : t,
                        ),
                      }))
                    }
                  >
                    <option value="offline">Offline</option>
                    <option value="ollama">Ollama</option>
                    <option value="gemini">Gemini</option>
                    {live && <option value="server">Server managed</option>}
                  </select>
                )}
              </div>
              <div className="composer-source-tools">
                <button type="button" className="using-files" onClick={onFiles}>
                  <Paperclip size={14} />
                  <span>
                    {notebook ? (
                      `Đang dùng ${selected.length} nguồn`
                    ) : (
                      <>
                        <span className="files-prefix">Using </span>
                        {selected.length} of {workspace.sources.length} files
                      </>
                    )}
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
              {notebook && <span>Gửi</span>}
              <ArrowUp size={19} />
            </button>
          </div>
        </form>
        <div className="composer-caption">
          <span>
            {!live
              ? "Local preview · engine preference only"
              : mode !== "Ask"
                ? "Local processing · Gemini is used only in Ask mode"
                : runtime?.engine_mode === "gemini"
                  ? `Gemini · ${runtime.model} · selected document excerpts`
                  : runtime?.engine_mode === "ollama"
                    ? "Ollama · local model"
                    : "Offline · documents stay on this device"}{" "}
            · Enter to send
          </span>
          {!live && (
            <details>
              <summary>Preview states</summary>
              <div className="state-menu">
                <button
                  onClick={() =>
                    send(
                      "Where will the presentation take place?",
                      "abstention",
                    )
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
          )}
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
