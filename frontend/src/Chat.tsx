import { questionVietnamese } from "./api";
import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowUp,
  ArrowDown,
  ArrowRight,
  X,
  Paperclip,
  ChevronDown,
  Mail,
  Bookmark,
  RotateCcw,
  Check,
  BookOpen,
  AlertTriangle,
  Copy,
  ThumbsUp,
  ThumbsDown,
  FileText,
  GraduationCap,
  Target,
  Layers,
  ChartNoAxesColumnIncreasing,
  CalendarDays,
  Sparkles,
} from "lucide-react";
import { apiFor, chatRequest, draftFromServer, selectDocuments } from "./api";
import { isVerified, featureRoute, type EngineMode } from "./schema";
import { validRecipient, resolveCitedSource } from "./workflow-model";
import { isRetiredThread, visibleChatMessages } from "./notebook-model";
import { studySuggestion, type StudyKind } from "./study-model";
import AISettings from "./AISettings";
import { sourceSupportDisclosure, citationIntegrityDisclosure } from "./api";
import { preprocessCitationMarkdown } from "./surfsense-citation-markdown";
import type { RuntimeStatus, VerificationProfile, EvidenceVerification } from "./api";
import { Badge, Citation, Notice } from "./components";
import {
  detectMode,
  relevantEvidence,
  initialEmail,
  blankDraft,
  type Workspace,
  type Thread,
  type Message,
  type Handoff,
  type Evidence,
  type Draft,
} from "./data";

const summarySectionIcons = [
  [/rủi ro|thách thức|\brisk\b/i, AlertTriangle],
  [/đánh giá|kết quả|số liệu|\bevaluation\b|\bresults\b/i, ChartNoAxesColumnIncreasing],
  [/kiến trúc|thiết kế|\barchitecture\b|\bdesign\b/i, Layers],
  [/kế hoạch|lộ trình|tiến độ|\broadmap\b|\btimeline\b/i, CalendarDays],
  [/mục tiêu|phạm vi|\bobjectives?\b|\bscope\b/i, Target],
] as const;


function renderAcademicAnswer(text: string, keys: Record<string,string>, onOpen: (id:string) => void): React.ReactNode {
  const citations=Object.keys(keys).map((key) => ({source_id:Number(key),chunk_id:Number(key)}));
  const prepared=preprocessCitationMarkdown(text,citations);
  return prepared.split(/(<citation data-chunk-id="[0-9]+">[0-9]+<\/citation>)/g).map((part,index) => {
    const match=part.match(/^<citation data-chunk-id="([0-9]+)">/);
    if (match && keys[match[1]]) return <Citation key={index} id={keys[match[1]]} number={Number(match[1])} onOpen={onOpen} />;
    return <span key={index}>{renderFormattedMarkdown(part)}</span>;
  });
}

function formatMathSnippet(latex: string): string {
  return latex
    .replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, "($1)/($2)")
    .replace(/\\Delta/g, "Δ")
    .replace(/\\ge/g, "≥")
    .replace(/\\le/g, "≤")
    .replace(/\\ne/g, "≠")
    .replace(/\\cdot/g, "·")
    .replace(/\\times/g, "×")
    .replace(/\\sqrt\{([^}]+)\}/g, "√($1)")
    .replace(/\\text\{([^}]+)\}/g, "$1")
    .replace(/\\quad/g, "   ")
    .replace(/\\,/g, " ")
    .trim();
}

function renderFormattedMarkdown(text: string): React.ReactNode {
  if (!text) return null;

  // Split into lines first so markdown block structures (headings, bullet points) format properly
  const lines = text.split("\n");
  return lines.map((rawLine, lIdx) => {
    let line = rawLine;

    // Display math block: $$...$$
    if (line.trim().startsWith("$$") && line.trim().endsWith("$$") && line.trim().length >= 4) {
      const mathContent = line.trim().slice(2, -2).trim();
      const readable = formatMathSnippet(mathContent);
      return (
        <div
          key={lIdx}
          className="my-2.5 p-2.5 text-center font-mono text-sm bg-neutral-100/90 dark:bg-neutral-800/90 text-indigo-700 dark:text-indigo-300 rounded-lg border border-indigo-100 dark:border-indigo-900/40 overflow-x-auto shadow-xs"
        >
          {readable}
        </div>
      );
    }

    let isHeading = false;
    if (/^#{1,6}\s+/.test(line)) {
      isHeading = true;
      line = line.replace(/^#{1,6}\s+/, "");
    }

    // Split by inline code: `...`
    const codeSegments = line.split(/(`[^`]+`)/g);
    const renderedLine = codeSegments.map((seg, sIdx) => {
      if (seg.startsWith("`") && seg.endsWith("`") && seg.length >= 2) {
        return (
          <code key={sIdx} className="inline-code">
            {seg.slice(1, -1)}
          </code>
        );
      }

      // Split by bold: **...**
      const boldSegments = seg.split(/(\*\*[^*]+\*\*)/g);
      return boldSegments.map((bSeg, bIdx) => {
        if (bSeg.startsWith("**") && bSeg.endsWith("**") && bSeg.length >= 4) {
          return (
            <strong key={`${sIdx}-${bIdx}`}>
              {bSeg.slice(2, -2)}
            </strong>
          );
        }

        // Split by italic: *...*
        const italicSegments = bSeg.split(/(\*[^*]+\*)/g);
        return italicSegments.map((iSeg, iIdx) => {
          if (iSeg.startsWith("*") && iSeg.endsWith("*") && iSeg.length >= 2) {
            return (
              <em key={`${sIdx}-${bIdx}-${iIdx}`}>
                {iSeg.slice(1, -1)}
              </em>
            );
          }

          // Split by inline math: $...$
          const mathSegments = iSeg.split(/(\$[^$\n]+\$)/g);
          return mathSegments.map((mSeg, mIdx) => {
            if (mSeg.startsWith("$") && mSeg.endsWith("$") && mSeg.length >= 3) {
              const innerMath = mSeg.slice(1, -1);
              return (
                <span
                  key={`${sIdx}-${bIdx}-${iIdx}-${mIdx}`}
                  className="font-mono text-[0.92em] font-medium text-indigo-700 dark:text-indigo-300 bg-indigo-50/80 dark:bg-indigo-950/50 px-1 py-0.5 rounded border border-indigo-200/60 dark:border-indigo-800/50 mx-0.5"
                >
                  {formatMathSnippet(innerMath)}
                </span>
              );
            }
            return mSeg;
          });
        });
      });
    });

    return (
      <span
        key={lIdx}
        style={{
          display: isHeading ? "block" : "inline",
          fontWeight: isHeading ? 700 : undefined,
          marginTop: isHeading && lIdx > 0 ? "8px" : undefined,
          marginBottom: isHeading ? "4px" : undefined,
        }}
      >
        {renderedLine}
        {!isHeading && lIdx < lines.length - 1 && <br />}
      </span>
    );
  });
}

export default function Chat({
  workspace,
  thread,
  update,
  onEvidence,
  onEmailHandoff,
  onEmailDraft,
  onFiles,
  active,
  notebook = false,
  onStudioOpen,
  onStudy,
  autoAsk = false,
}: {
  workspace: Workspace;
  thread: Thread;
  update: (fn: (w: Workspace) => Workspace) => void;
  onEvidence: (id: string) => void;
  onEmailHandoff: (context: Handoff) => void;
  onEmailDraft: () => void;
  onFiles: () => void;
  active: boolean;
  notebook?: boolean;
  onStudioOpen?: (id: string) => void;
  onStudy?: (kind: StudyKind, focus: string) => void;
  autoAsk?: boolean;
}) {
  const [input, setInput] = useState(
    isRetiredThread(thread) ? "" : (thread.composerDraft ?? ""),
  );
  const messages = useMemo(
    () => visibleChatMessages(workspace, thread),
    [workspace, thread],
  );
  const latestMessage = messages.at(-1);
  const suggestion =
    onStudy && latestMessage ? studySuggestion(workspace, latestMessage) : null;
  const [pending, setPending] = useState<Pick<
    Message,
    "request" | "mode" | "at"
  > | null>(null);
  const [verificationProfile, setVerificationProfile] = useState<VerificationProfile>("academic_grounded");
  const [verificationDetails, setVerificationDetails] = useState<Record<string, EvidenceVerification>>({});
  const sourceSupported = (m: Message) => m.evidenceIds.some((id) => workspace.evidence[id]?.context === sourceSupportDisclosure);
  const [progressText, setProgressText] = useState("Reading selected sources…");
  const [filesExpanded, setFilesExpanded] = useState(false);
  const [showLatestButton, setShowLatestButton] = useState(false);
  const transcriptId = useId();
  const sourceListId = useId();
  const loading = pending !== null;
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const live = apiFor(workspace.id);
  const [generationState,setGenerationState] = useState<{ready:boolean;preparing:boolean;message:string} | null>(null);
  useEffect(() => {
    if (!live || !active) return;
    let disposed=false;
    const refresh=async () => {
      try {
        const language=questionVietnamese(input || pending?.request || messages.at(-1)?.request || '') ? 'vi' : 'en';
        const response=await fetch(`/api/runtime/generation-ready?language=${language}`);
        if(response.ok && !disposed) setGenerationState(await response.json());
      } catch { /* A request displays its own natural-language connection error. */ }
    };
    void refresh(); const interval=setInterval(() => void refresh(),1500);
    return () => {disposed=true;clearInterval(interval);};
  },[active,live,input,pending?.request,messages.length]);
  const requestLock = useRef(false);
  const submittedIntake = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollViewport = useRef<HTMLDivElement>(null);
  const chatHistory = useRef<HTMLDivElement>(null);
  const wasActive = useRef(false);
  const followLatest = useRef(true);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (thread.composerDraft && !isRetiredThread(thread))
      inputRef.current?.focus();
  }, [thread.id]);
  const previousCount = useRef(messages.length);
  const selected = workspace.sources.filter(
    (s) =>
      s.selected &&
      s.status === "Processed" &&
      (!live || s.origin === "server"),
  );
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
    if (notebook && !messages.length && !loading) {
      followLatest.current = false;
      viewport?.scrollTo({ top: 0, behavior: "auto" });
      wasActive.current = true;
      previousCount.current = 0;
      return;
    }
    if (
      viewport &&
      (entering ||
        (followLatest.current &&
          (messages.length > previousCount.current || loading)))
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
    previousCount.current = messages.length;
  }, [active, thread.id, messages.length, loading]);
  useEffect(() => {
    const viewport = scrollViewport.current;
    if (!active || !viewport) return;
    let buttonVisible: boolean | undefined;
    const onScroll = () => {
      const away =
        viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop >=
        96;
      followLatest.current = !away;
      if (buttonVisible !== away) {
        buttonVisible = away;
        setShowLatestButton(away);
      }
    };
    // Keep the latest answer visible as fonts or the selected-file composer settle.
    const observer = new ResizeObserver(() => {
      if (followLatest.current) {
        const bottom = viewport.scrollHeight - viewport.clientHeight;
        if (bottom - viewport.scrollTop > 1) viewport.scrollTop = bottom;
      }
      onScroll();
    });
    viewport.addEventListener("scroll", onScroll, { passive: true });
    observer.observe(viewport);
    if (chatHistory.current) observer.observe(chatHistory.current);
    onScroll();
    return () => {
      observer.disconnect();
      viewport.removeEventListener("scroll", onScroll);
    };
  }, [active, thread.id]);
  useEffect(() => {
    const field = inputRef.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, 136)}px`;
  }, [input]);
  const send = async (request = input, forced?: Message["state"]) => {
    if (!request.trim() || loading || requestLock.current || (live && generationState?.preparing)) return;
    followLatest.current = true;
    const ids = selected.map((s) => s.id);
    const activeMode = live ? "Ask" : detectMode(request);
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
    setProgressText(questionVietnamese(request) ? "Đang đọc tài liệu đã chọn…" : "Reading selected sources…");
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
        const history = messages
          .filter((m) => m.origin === "server" && m.state === "answer" && [...m.sourceIds].sort().join("|") === [...ids].sort().join("|"))
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
          undefined,
          activeMode === "Ask" ? verificationProfile : "strict",
          setProgressText,
        );
        if (response.route === "RECONCILE_FLOW")
          throw new Error(
            "Update the server to continue asking questions in this note.",
          );
        result.routeType = response.route;
        result.citationChecked = response.verification_method === "citation_integrity_only";
        result.citationKeys = {};
        result.sourceCoverage = response.coverage;
        result.responseLatencyMs = response.latency_ms;
        if (response.verification) {
          setVerificationDetails((current) => ({ ...current, [result.id]: response.verification! }));
        }
        if (response.status === "SOURCE_SUPPORTED") {
          const check = response.verification;
          if (!check || check.profile !== "evidence_centric_v0" || check.contract_version !== "ec-v0" ||
              !check.limitations.length || !check.claims.length ||
              check.claims.some((c) => c.disposition !== "SOURCE_SUPPORTED" ||
                c.support !== "SUPPORTED_BY_CITED_EVIDENCE" || !c.citations.length ||
                c.competing_evidence.some((e) => e.verdict !== "NO_CONFLICT_ESTABLISHED"))) {
            throw new Error("The evidence profile response is incomplete.");
          }
          result.state = "answer";
          result.answerText = undefined;
        }
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
          if (c.citation_index !== undefined) result.citationKeys![String(c.citation_index)] = id;
          claims[id] = {
            id: source.id,
            file: source.name,
            title: result.citationChecked ? (questionVietnamese(request) ? "Nguồn trích dẫn" : "Cited source") : c.section || "Supported finding",
            finding: c.claim_text,
            section: c.section || undefined,
            quote: c.evidence_quote,
            locator: `p. ${c.cited_page}${c.cited_start_line ? ` · lines ${c.cited_start_line}–${c.cited_end_line ?? c.cited_start_line}` : ""}`,
            context: result.citationChecked ? (questionVietnamese(request) ? "Mở đoạn trích để đối chiếu với tài liệu gốc." : "Open this passage to compare it with the original document.") : "Server-verified citation",
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
        if (response.status === "SOURCE_SUPPORTED" && response.verification) {
          for (const claim of response.verification.claims) {
            const c = claim.citations[0];
            const source = resolveCitedSource(c.doc_id, workspace.sources);
            if (!source || !ids.includes(source.id) || !/^[a-f0-9]{64}$/.test(c.source_sha256) ||
                (source.fileHash && source.fileHash !== c.source_sha256) ||
                (source.versionId && source.versionId !== c.doc_version)) {
              throw new Error("The source-supported citation does not match the selected library.");
            }
            const id = crypto.randomUUID();
            result.evidenceIds.push(id);
            claims[id] = { id: source.id, file: source.name, title: "Được nguồn hỗ trợ",
              finding: claim.text, quote: c.quote,
              locator: `p. ${c.page} · lines ${c.line_start}–${c.line_end}`,
              context: sourceSupportDisclosure, page: c.page, startLine: c.line_start, endLine: c.line_end,
              docVersion: c.doc_version, docHash: c.source_sha256,
              verificationStatus: "VERIFIED_EXACT", origin: "server" };
          }
        }
        result.rejectedClaims = rejected;
        result.suggestedQuestions = response.suggested_questions;
        if (response.thinking) {
          result.thinking = response.thinking;
        } else if (response.validated_claims?.[0]?.thinking) {
          result.thinking = response.validated_claims[0].thinking;
        }
        let draft: Draft | undefined;
        if (response.draft) {
          draft = draftFromServer(response.draft, thread.id, workspace);
          result.state = "draft";
          result.mode = "Email";
        } else if (response.route === "QA_FLOW") {
          result.state =
            result.evidenceIds.length || response.status === "CONVERSATION"
              ? "answer"
              : "abstention";
          result.answerText = result.citationChecked && result.evidenceIds.length
            ? response.answer
            : result.evidenceIds.length
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
            (activeMode === "Email"
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
  const sendRef = useRef(send);
  sendRef.current = send;
  useEffect(() => {
    if (!active || !autoAsk || !thread.composerDraft || submittedIntake.current)
      return;
    submittedIntake.current = true;
    void sendRef.current(thread.composerDraft);
  }, [active, autoAsk, thread.composerDraft]);
  const handoff = (m: Message) =>
    onEmailHandoff({
      question: m.request,
      answer: m.evidenceIds
        .map((id) => workspace.evidence[id]?.finding)
        .filter(Boolean)
        .join("\n"),
      evidenceIds: m.evidenceIds,
      sourceIds: m.sourceIds,
    });
  const welcome = notebook && !messages.length && !pending;
  return (
    <div className={`chat-view${welcome ? " nb-chat-welcome" : ""}`}>
      <div
        className="chat-scroll"
        id={transcriptId}
        tabIndex={-1}
        ref={scrollViewport}
      >
        <div className="chat-history" ref={chatHistory}>
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
                  ? "What would you like to explore?"
                  : "Documents in this note"}
              </h3>
              <p>
                {workspace.sources.length
                  ? `${selected.length} of ${workspace.sources.length} sources selected. Answers use the sources you select.`
                  : "Add documents in Sources to start asking questions."}
              </p>
              {!!workspace.sources.length && (
                <details>
                  <summary>View ready sources</summary>
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
                    label: "Summarize documents",
                    description: "Find the main ideas.",
                    query: "Summarize the main points in these documents.",
                  },
                  {
                    label: "Key requirements",
                    description: "See what needs to be done.",
                    query: "What are the requirements?",
                  },
                  {
                    label: "Key dates",
                    description: "Find deadlines and milestones.",
                    query: "What key dates are mentioned?",
                  },
                ].map((prompt) => (
                  <button
                    key={prompt.query}
                    disabled={!selected.length || loading}
                    onClick={() => void send(prompt.query)}
                  >
                    <span>
                      {prompt.label}
                      {welcome && <small>{prompt.description}</small>}
                    </span>
                    <ArrowRight size={14} aria-hidden="true" />
                  </button>
                ))}
              </div>
            </section>
          )}
          {messages.map((m) =>
            notebook && m.studioResultId ? (
              <div className="nb-studio-event" key={m.id}>
                <Check size={15} />
                <span>Email draft saved</span>
                <button onClick={() => onStudioOpen?.(m.studioResultId!)}>
                  {workspace.studioResults?.find(
                    (result) => result.id === m.studioResultId,
                  )?.title || "Deleted result"}
                  <ArrowRight size={14} />
                </button>
              </div>
            ) : (
              <article
                className="exchange"
                data-offscreen-ready={m !== latestMessage || undefined}
                key={m.id}
              >
                <UserMessage message={m} />
                <div className="answer" aria-label="WorkspaceAI response">
                  <div className="answer-heading">
                    <BookOpen size={19} />
                    <div className="answer-identity">
                      <strong>WorkspaceAI</strong>
                      <span className="small muted">
                        {m.state === "answer"
                          ? m.origin === "server"
                            ? "Document answer"
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
                                    x.id === m.id
                                      ? { ...x, saved: !x.saved }
                                      : x,
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
                      {sourceSupported(m) && (
                        <Notice tone="neutral"><strong>Được nguồn hỗ trợ — chưa kiểm chứng toàn cục</strong><p>{sourceSupportDisclosure}</p></Notice>
                      )}
                      {m.thinking && (
                        <details
                          className="reasoning-box"
                          style={{
                            marginBottom: "12px",
                            borderRadius: "8px",
                            border: "1px solid rgba(139, 92, 246, 0.3)",
                            background: "rgba(139, 92, 246, 0.06)",
                            padding: "10px 14px",
                            fontSize: "12px",
                            color: "#c4b5fd",
                          }}
                        >
                          <summary
                            style={{
                              cursor: "pointer",
                              fontWeight: 600,
                              display: "flex",
                              alignItems: "center",
                              gap: "6px",
                              userSelect: "none",
                              color: "#a78bfa",
                            }}
                          >
                            <Sparkles size={14} />
                            <span>💭 Quá trình suy luận (Reasoning Process)</span>
                          </summary>
                          <div
                            style={{
                              marginTop: "8px",
                              paddingLeft: "12px",
                              borderLeft: "2px solid rgba(139, 92, 246, 0.4)",
                              fontFamily: "monospace",
                              fontSize: "11px",
                              lineHeight: "1.6",
                              whiteSpace: "pre-wrap",
                              opacity: 0.95,
                            }}
                          >
                            {m.thinking}
                          </div>
                        </details>
                      )}
                      {m.answerText && (
                        <div className="server-answer-text">{m.citationChecked ? renderAcademicAnswer(m.answerText, m.citationKeys ?? {}, onEvidence) : renderFormattedMarkdown(m.answerText)}</div>
                      )}
                      {m.citationChecked && <Notice tone="neutral">{questionVietnamese(m.request) ? "Bạn có thể mở trích dẫn để đối chiếu câu trả lời với tài liệu gốc." : "Open a citation to compare the answer with the original document."}</Notice>}
                      {m.groundingScore !== undefined && !notebook && (
                        <p className="small muted">
                          Grounding score · {Math.round(m.groundingScore * 100)}
                          %
                        </p>
                      )}
                      {m.evidenceIds.map((id, index) => {
                        const e = workspace.evidence[id];
                        const section = e?.section;
                        const continuesSection = !!section &&
                          workspace.evidence[m.evidenceIds[index - 1]]?.section === section;
                        const SectionIcon = section && !continuesSection
                          ? summarySectionIcons.find(([pattern]) => pattern.test(section))?.[1]
                          : undefined;
                        return e &&
                          !(
                            e.origin === "server" &&
                            !isVerified(e.verificationStatus)
                          ) ? (
                          <section
                            className={`finding${id === "conflict" ? " finding-conflict" : ""}${e.section ? " summary-finding" : ""}${continuesSection ? " summary-continuation" : ""}`}
                            key={id}
                          >
                            <div
                              className="finding-heading"
                              hidden={
                                continuesSection || (notebook && !e.section && e.title === "Supported finding")
                              }
                            >
                              {id === "conflict" && <AlertTriangle size={16} />}
                              {SectionIcon && <SectionIcon size={15} aria-hidden="true" />}
                              <h3>{e.title}</h3>
                            </div>
                            {!m.citationChecked && <p>{renderFormattedMarkdown(e.finding)}</p>}
                            <Badge
                              tone={
                                e.context !== sourceSupportDisclosure && e.origin === "server" &&
                                isVerified(e.verificationStatus)
                                  ? "document"
                                  : "neutral"
                              }
                            >
                              {m.citationChecked ? (questionVietnamese(m.request) ? "Nguồn trích dẫn" : "Source citation") : e.context === sourceSupportDisclosure ? "SOURCE SUPPORTED" : e.verificationStatus?.replaceAll("_", " ") ??
                                "Unverified sample"}
                            </Badge>
                            <Citation
                              id={id}
                              onOpen={onEvidence}
                              number={index + 1}
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
                            This source is no longer available in this
                            workspace.
                          </Notice>
                        );
                      })}
                      {!!m.rejectedClaims?.length && (
                        <Notice tone="neutral">
                          {m.rejectedClaims.length} unsupported claim
                          {m.rejectedClaims.length === 1
                            ? " was"
                            : "s were"}{" "}
                          excluded from this answer.
                        </Notice>
                      )}
                      <div className="answer-footer">
                        <div className="answer-actions">
                          <button className="button" onClick={() => handoff(m)}>
                            <Mail size={15} />
                            {notebook
                              ? "Draft an email"
                              : "Draft email from this"}{" "}
                            <ArrowRight size={13} />
                          </button>
                        </div>
                        <p className="provenance-note">
                          {sourceSupported(m) ? <AlertTriangle size={13} /> : <Check size={13} />}
                          {sourceSupported(m) ? "SOURCE_SUPPORTED · giới hạn kiểm chứng đã công bố" : m.origin === "server"
                            ? `${m.sourceIds.length} documents selected for this request.`
                            : "Sample evidence · original documents not verified."}
                        </p>
                        {m.suggestedQuestions && m.suggestedQuestions.length > 0 && (
                          <div className="suggested-prompts-block">
                            <div className="suggested-prompts-title">
                              <Sparkles size={14} className="sparkle-icon" />
                              <span>Gợi ý câu hỏi tiếp theo:</span>
                            </div>
                            <div className="suggested-prompts-chips">
                              {m.suggestedQuestions.map((q, qIdx) => (
                                <button
                                  key={qIdx}
                                  className="prompt-chip"
                                  type="button"
                                  onClick={() => send(q)}
                                >
                                  <span>{q}</span>
                                  <ArrowRight size={12} className="chip-arrow" />
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </>
                  ) : m.state === "abstention" ? (
                    <div className="abstention">
                      <AlertTriangle size={21} />
                      <h3>{questionVietnamese(m.request) ? "Tài liệu chưa có đủ thông tin để trả lời." : "There isn’t enough evidence to answer this."}</h3>
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
                      <strong>{questionVietnamese(m.request) ? "Mình chưa thể hoàn thành câu trả lời." : "The answer couldn’t be generated."}</strong>
                      <p>
                        {(m.errorText ? (/[A-Z]+_[A-Z_]+/.test(m.errorText) ? "The request could not be completed. Please check the local service and try again." : m.errorText) : undefined) ||
                          "Your question is preserved. Try again when you’re ready."}
                      </p>
                      <button
                        className="button"
                        onClick={() => send(m.request)}
                      >
                        <RotateCcw size={14} />
                        {questionVietnamese(m.request) ? "Thử lại" : "Retry"}
                      </button>
                    </Notice>
                  ) : (
                    <div className="chat-result">
                      <Badge>
                        <Mail size={12} />
                        Draft · Not approved
                      </Badge>
                      <h3>The first words are ready for your review.</h3>
                      <p>
                        Open the draft to check recipients, supporting facts,
                        and tone. Your review is required before approval and
                        sending.
                      </p>
                      <div className="inline-evidence">
                        {m.evidenceIds.map((id) => (
                          <Citation key={id} id={id} onOpen={onEvidence} />
                        ))}
                      </div>
                      {!m.evidenceIds.length && <Badge>You provided</Badge>}
                      <button className="button" onClick={onEmailDraft}>
                        Review email draft <ArrowRight size={14} />
                      </button>
                    </div>
                  )}
                  {notebook && m.state === "answer" && (
                    <div className="nb-answer-tools">
                      <button
                        title="Copy reply"
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
                        <span>Copy</span>
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
                        <span>{m.saved ? "Reply saved" : "Save reply"}</span>
                      </button>
                      {(["helpful", "unhelpful"] as const).map((feedback) => (
                        <button
                          key={feedback}
                          aria-label={
                            feedback === "helpful" ? "Helpful" : "Not helpful"
                          }
                          aria-pressed={m.feedback === feedback}
                          title={
                            feedback === "helpful" ? "Helpful" : "Not helpful"
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
                  {verificationDetails[m.id] && m.state === "abstention" && (
                    <details><summary>Bằng chứng cần đối chiếu</summary>
                      {verificationDetails[m.id].claims.flatMap((c) => c.competing_evidence).filter((e) => e.verdict !== "NO_CONFLICT_ESTABLISHED").map((e) => (
                        <div key={e.evidence_id}><strong>{e.verdict === "CONFLICT" ? "Mâu thuẫn được xác nhận" : "Tín hiệu chưa giải quyết"}</strong>
                          {e.citations.map((c, i) => <blockquote key={i}>{c.quote}<p>{c.doc_id} · trang {c.page} · dòng {c.line_start}–{c.line_end} · {c.doc_version}</p></blockquote>)}
                        </div>
                      ))}
                    </details>
                  )}
                  {m === latestMessage && suggestion && (
                    <button
                      className="button study-chat-suggestion"
                      onClick={() =>
                        onStudy?.(suggestion.kind, suggestion.focus)
                      }
                    >
                      <GraduationCap size={17} />{" "}
                      {suggestion.kind === "quiz"
                        ? "Take a quiz"
                        : "Review with flashcards"}{" "}
                      <ArrowRight size={15} />
                    </button>
                  )}
                </div>
              </article>
            ),
          )}
          {pending && (
            <article className="exchange pending-exchange">
              <UserMessage message={pending} />
              <div className="loading-answer" role="status">
                <span className="loading-answer-dots" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
                <span>{progressText}</span>
              </div>
            </article>
          )}
        </div>
      </div>
      <div className="composer-area">
        {live && generationState && !generationState.ready && <Notice tone="neutral"><span role="status">{generationState.message}</span></Notice>}
        
        {notebook && active && !welcome && showLatestButton && (
          <button
            type="button"
            className="chat-jump-latest"
            aria-label="Jump to latest message"
            aria-controls={transcriptId}
            title="Jump to latest message"
            onClick={(event) => {
              const viewport = scrollViewport.current;
              if (!viewport) return;
              if (event.detail === 0) viewport.focus({ preventScroll: true });
              followLatest.current = true;
              viewport.scrollTop = viewport.scrollHeight;
            }}
          >
            <ArrowDown size={18} aria-hidden="true" />
          </button>
        )}
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <div className="composer-main">
            <button
              type="button"
              className="composer-sources-button"
              aria-label="Open Sources"
              title="Open Sources"
              onClick={onFiles}
            >
              <Paperclip size={17} aria-hidden="true" />
            </button>
            <textarea
              ref={inputRef}
              rows={1}
              aria-label="Message this note"
              placeholder="Ask a question…"
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
            <button
              className="send-button"
              type="submit"
              aria-label="Send message"
              disabled={!input.trim() || loading || (live && generationState?.preparing)}
            >
              <ArrowUp size={19} aria-hidden="true" />
            </button>
          </div>
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
          <div className="composer-bottom">
            <div className="composer-tools">
              <div className="mode-field engine-field">
                <label htmlFor="engine-mode">Engine</label>
                {live ? (
                  <AISettings
                    disabled={loading}
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
                  <span className="ai-model-preview">
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
                              ? {
                                  ...t,
                                  engineMode: e.target.value as EngineMode,
                                }
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
                    <ChevronDown size={13} aria-hidden="true" />
                  </span>
                )}
              </div>
              <div className="composer-source-tools">
                <span className="composer-source-count">
                  {notebook
                    ? `${selected.length} ${selected.length === 1 ? "source" : "sources"} selected`
                    : `Using ${selected.length} of ${workspace.sources.length} files`}
                </span>
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
          </div>
        </form>
        <div className="composer-caption">
          <span>
            {!live
              ? "Local preview · engine preference only"
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
