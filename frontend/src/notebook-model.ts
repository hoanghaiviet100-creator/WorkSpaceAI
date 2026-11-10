import type { Draft, Message, Suggestion, Thread, Workspace } from "./data";

export type StudioKind = "plan" | "email";
export type StudioConfig = {
  kind: StudioKind;
  title: string;
  goal: string;
  timeframe: string;
  detail: "concise" | "standard" | "detailed";
  recipient: string;
  tone: string;
  length: string;
};
export type StudioResult = {
  id: string;
  kind: StudioKind;
  title: string;
  createdAt: string;
  updatedAt: string;
  status: "generating" | "ready" | "error";
  sourceIds: string[];
  sourceSnapshot: { id: string; name: string }[];
  evidenceIds: string[];
  content: string;
  config: StudioConfig;
  draft?: Draft;
  suggestions?: Suggestion[];
  error?: string;
  origin: "imported" | "generated" | "local";
  attemptId?: string;
};

export const defaultStudioConfig = (kind: StudioKind): StudioConfig => ({
  kind,
  title: "",
  goal: "",
  timeframe: "7 ngày",
  detail: "standard",
  recipient: "",
  tone: "Trang trọng",
  length: "Vừa phải",
});
const timestamp = (value?: string) => Date.parse(value ?? "") || 0;

/** Lossless UI migration: one active conversation, original sessions retained as an archive. */
export function notebookWorkspace(
  workspace: Workspace,
  recoverPending = true,
): Workspace {
  if (workspace.notebookVersion === 1) {
    if (
      !recoverPending ||
      !workspace.studioResults?.some((result) => result.status === "generating")
    )
      return workspace;
    return {
      ...workspace,
      studioResults: workspace.studioResults.map((result) =>
        result.status === "generating"
          ? {
              ...result,
              status: "error",
              error:
                "Tác vụ bị gián đoạn khi tải lại trang. Bạn có thể thử lại.",
            }
          : result,
      ),
    };
  }
  const originals = workspace.threads ?? [];
  const preferred =
    [...originals]
      .filter((thread) => thread.mode === "Ask")
      .sort((a, b) => timestamp(b.updated) - timestamp(a.updated))[0] ??
    originals[0];
  const seen = new Map<string, Message>();
  const messages: Message[] = [];
  const results: StudioResult[] = [...(workspace.studioResults ?? [])];
  for (const thread of originals) {
    const kind =
      thread.mode === "Email" ||
      (thread.mode === "Ask" && thread.messages.at(-1)?.state === "draft")
        ? "email"
        : "plan";
    const output =
      thread.mode !== "Ask" ||
      thread.messages.some((message) =>
        ["draft", "suggestions"].includes(message.state),
      );
    const resultId = `legacy-${thread.id}`;
    if (output && !results.some((result) => result.id === resultId)) {
      const sourceIds = [
        ...new Set(thread.messages.flatMap((message) => message.sourceIds)),
      ];
      const evidenceIds = [
        ...new Set(thread.messages.flatMap((message) => message.evidenceIds)),
      ];
      const suggestions = workspace.suggestions.filter(
        (suggestion) => suggestion.threadId === thread.id,
      );
      const content =
        thread.draft?.body ||
        thread.messages
          .map((message) => message.answerText)
          .filter(Boolean)
          .join("\n\n") ||
        suggestions
          .map((suggestion) => `${suggestion.title}\n${suggestion.description}`)
          .join("\n\n") ||
        "Kết quả từ lịch sử trước đây. Mở công cụ chỉnh sửa để tiếp tục với dữ liệu đã lưu.";
      results.push({
        id: resultId,
        kind,
        title: thread.title,
        createdAt: thread.createdAt || thread.updated,
        updatedAt: thread.updated,
        status: "ready",
        sourceIds,
        sourceSnapshot: sourceIds.map((id) => ({
          id,
          name:
            workspace.sources.find((source) => source.id === id)?.name ||
            "Nguồn không còn trong thư viện",
        })),
        evidenceIds,
        content,
        draft: thread.draft,
        suggestions,
        config: {
          ...defaultStudioConfig(kind),
          title: thread.title,
          goal: thread.messages.at(-1)?.request || thread.title,
          recipient: thread.draft?.to || "",
        },
        origin: "imported",
      });
    }
    for (const original of thread.messages) {
      const message: Message = {
        ...original,
        legacyThreadId: thread.id,
        ...(output && ["draft", "suggestions"].includes(original.state)
          ? { studioResultId: resultId }
          : {}),
      };
      const duplicate = seen.get(message.id);
      if (
        duplicate &&
        duplicate.request === message.request &&
        duplicate.at === message.at &&
        duplicate.state === message.state &&
        duplicate.answerText === message.answerText &&
        JSON.stringify(duplicate.sourceIds) ===
          JSON.stringify(message.sourceIds) &&
        JSON.stringify(duplicate.evidenceIds) ===
          JSON.stringify(message.evidenceIds) &&
        duplicate.studioResultId === message.studioResultId
      ) {
        duplicate.saved ||= message.saved;
        continue;
      }
      if (duplicate) message.id = `${thread.id}:${message.id}`;
      seen.set(message.id, message);
      messages.push(message);
    }
  }
  messages.sort((a, b) => timestamp(a.at) - timestamp(b.at));
  const conversation: Thread = {
    ...(preferred || {
      id: `${workspace.id}-chat`,
      createdAt: workspace.updated,
      engineMode: "offline",
    }),
    title: "Hội thoại workspace",
    mode: "Ask",
    view: "chat",
    updated: messages.at(-1)?.at || preferred?.updated || workspace.updated,
    messages,
  };
  return {
    ...workspace,
    notebookVersion: 1,
    legacyThreads: workspace.legacyThreads || structuredClone(originals),
    threads: [conversation],
    studioResults: results.sort(
      (a, b) => timestamp(b.createdAt) - timestamp(a.createdAt),
    ),
  };
}

export function studioText(result: StudioResult) {
  return result.kind === "email" && result.draft
    ? `To: ${result.draft.to}\nSubject: ${result.draft.subject}\n\n${result.draft.body}`
    : result.content;
}

/** Capture outputs created by the existing chat flow without starting another conversation. */
export function captureChatOutputs(workspace: Workspace): Workspace {
  const thread = workspace.threads[0];
  if (!thread) return workspace;
  const results = [...(workspace.studioResults ?? [])];
  let changed = false;
  const messages = thread.messages.map((message) => {
    if (
      message.studioResultId ||
      !["draft", "suggestions"].includes(message.state)
    )
      return message;
    const kind = message.state === "draft" ? "email" : "plan";
    const id = `chat-${message.id}`;
    if (!results.some((result) => result.id === id)) {
      const draft =
        kind === "email" ? thread.draft || workspace.draft : undefined;
      results.unshift({
        id,
        kind,
        title: draft?.subject || message.request.slice(0, 80),
        createdAt: message.at,
        updatedAt: message.at,
        status: "ready",
        sourceIds: message.sourceIds,
        sourceSnapshot: message.sourceIds.map((sourceId) => ({
          id: sourceId,
          name:
            workspace.sources.find((source) => source.id === sourceId)?.name ||
            "Nguồn đã xóa",
        })),
        evidenceIds: message.evidenceIds,
        content:
          draft?.body ||
          message.answerText ||
          "Mở bảng công việc để xem và xác nhận các đề xuất.",
        draft,
        suggestions:
          kind === "plan"
            ? workspace.suggestions.filter(
                (suggestion) => suggestion.threadId === thread.id,
              )
            : undefined,
        config: {
          ...defaultStudioConfig(kind),
          title: message.request.slice(0, 80),
          goal: message.request,
          recipient: draft?.to || "",
        },
        origin: "generated",
      });
    }
    changed = true;
    return { ...message, studioResultId: id };
  });
  return changed
    ? {
        ...workspace,
        threads: [{ ...thread, messages }],
        studioResults: results,
      }
    : workspace;
}
