import type { Draft, Message, Suggestion, Thread, Workspace } from "./data";
import { sampleStudy } from "./study-sample";

export type StudioKind = "plan" | "email";
export type StudioConfig = {
  kind: StudioKind;
  title: string;
  goal: string;
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

export const defaultStudioConfig = (): StudioConfig => ({
  kind: "email",
  title: "",
  goal: "",
  recipient: "",
  tone: "Formal",
  length: "Medium",
});
const timestamp = (value?: string) => Date.parse(value ?? "") || 0;

export function isRetiredThread(thread: Thread) {
  return thread.mode === "Tasks" || thread.view === "tasks";
}

export function visibleStudioResults(workspace: Workspace) {
  return (workspace.studioResults ?? []).filter(
    (result) => result.kind === "email",
  );
}

/** Legacy feature records stay in storage without appearing in the UI or chat context. */
export function visibleChatMessages(workspace: Workspace, thread: Thread) {
  if (workspace.notebookVersion !== 1 && isRetiredThread(thread)) return [];
  const retiredThreads = new Set(
    (workspace.legacyThreads ?? [])
      .filter(isRetiredThread)
      .map((item) => item.id),
  );
  const retiredResults = new Set(
    (workspace.studioResults ?? [])
      .filter((result) => result.kind === "plan")
      .map((result) => result.id),
  );
  return thread.messages.filter(
    (message) =>
      message.mode !== "Tasks" &&
      message.state !== "suggestions" &&
      message.routeType !== "RECONCILE_FLOW" &&
      !("kanbanEvent" in message && message.kanbanEvent) &&
      !retiredThreads.has(message.legacyThreadId ?? "") &&
      !retiredResults.has(message.studioResultId ?? "") &&
      !(
        workspace.id === "midterm" &&
        message.id === "m5" &&
        message.origin !== "server"
      ),
  );
}

/** Lossless UI migration: one active conversation, original sessions retained as an archive. */
export function notebookWorkspace(
  workspace: Workspace,
  recoverPending = true,
): Workspace {
  const hasLegacySample = (set: NonNullable<Workspace["studySets"]>[number]) =>
    set.engine === "sample" &&
    (set.id === "sample-flashcard" || set.id === "sample-quiz") &&
    set.items[0]?.citation.file === "Tư duy tính toán · tài liệu mẫu";
  if (workspace.studySets?.some(hasLegacySample)) {
    workspace = {
      ...workspace,
      studySets: workspace.studySets.map((set) => {
        if (!hasLegacySample(set)) return set;
        const sample = sampleStudy(set.config.kind);
        const defaultTitle =
          set.title === "Nền tảng tư duy tính toán" ||
          set.title === "Kiểm tra tư duy tính toán";
        return {
          ...set,
          title: defaultTitle ? sample.title : set.title,
          items: sample.items,
        };
      }),
    };
  }
  if (
    recoverPending &&
    workspace.studySets?.some((set) => set.status === "generating")
  ) {
    workspace = {
      ...workspace,
      studySets: workspace.studySets.map((set) =>
        set.status === "generating"
          ? {
              ...set,
              status: "error",
              error: "Study set creation was interrupted. Try again.",
            }
          : set,
      ),
    };
  }
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
              error: "The page was reloaded before this finished. Try again.",
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
    const output =
      !isRetiredThread(thread) &&
      (thread.mode === "Email" ||
        thread.messages.some((message) => message.state === "draft"));
    const resultId = `legacy-${thread.id}`;
    if (output && !results.some((result) => result.id === resultId)) {
      const sourceIds = [
        ...new Set(thread.messages.flatMap((message) => message.sourceIds)),
      ];
      const evidenceIds = [
        ...new Set(thread.messages.flatMap((message) => message.evidenceIds)),
      ];
      const content =
        thread.draft?.body ||
        thread.messages
          .map((message) => message.answerText)
          .filter(Boolean)
          .join("\n\n") ||
        "Result from an earlier conversation. Open the editor to continue with the saved data.";
      results.push({
        id: resultId,
        kind: "email",
        title: thread.title,
        createdAt: thread.createdAt || thread.updated,
        updatedAt: thread.updated,
        status: "ready",
        sourceIds,
        sourceSnapshot: sourceIds.map((id) => ({
          id,
          name:
            workspace.sources.find((source) => source.id === id)?.name ||
            "Source no longer in the library",
        })),
        evidenceIds,
        content,
        draft: thread.draft,
        config: {
          ...defaultStudioConfig(),
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
        ...(output && original.state === "draft"
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
    title: "Note conversation",
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
      message.state !== "draft" ||
      message.mode === "Tasks"
    )
      return message;
    const id = `chat-${message.id}`;
    if (!results.some((result) => result.id === id)) {
      const draft = thread.draft || workspace.draft;
      results.unshift({
        id,
        kind: "email",
        title: draft?.subject || message.request.slice(0, 80),
        createdAt: message.at,
        updatedAt: message.at,
        status: "ready",
        sourceIds: message.sourceIds,
        sourceSnapshot: message.sourceIds.map((sourceId) => ({
          id: sourceId,
          name:
            workspace.sources.find((source) => source.id === sourceId)?.name ||
            "Removed source",
        })),
        evidenceIds: message.evidenceIds,
        content:
          draft?.body ||
          message.answerText ||
          "Open Studio to view the email draft.",
        draft,
        config: {
          ...defaultStudioConfig(),
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
