import type { Evidence, Message, Source, Workspace } from "./data";

export type StudyKind = "flashcard" | "quiz";
export type StudyConfig = {
  kind: StudyKind;
  sourceIds: string[];
  count: number;
  difficulty: "easy" | "medium" | "hard";
  focus: string;
  language?: "auto" | "vi" | "en";
};
export type StudyCitation = {
  docId: string;
  file: string;
  page: number;
  startLine: number;
  endLine: number;
  quote: string;
  docHash?: string;
};
export type StudyItem = {
  id: string;
  question: string;
  answer: string;
  topic: string;
  citation: StudyCitation;
  options?: string[];
  correctIndex?: number;
};
export type QuizProgress = {
  order: string[];
  answers: Record<string, number>;
  complete: boolean;
};
export type StudySet = {
  id: string;
  title: string;
  createdAt: string;
  status: "generating" | "ready" | "error";
  config: StudyConfig;
  items: StudyItem[];
  engine?: "extractive" | "sample" | "review";
  error?: string;
  mastered?: Record<string, boolean>;
  quiz?: QuizProgress;
  lastScore?: { correct: number; total: number; completedAt?: string };
};

export function studySources(workspace: Workspace): Source[] {
  return workspace.sources.filter(
    (source) =>
      source.status === "Processed" &&
      (source.pages?.some((page) => page.raw_text.trim()) ||
        (source.origin === "server" &&
          (source.totalChunks === undefined || source.totalChunks > 0))),
  );
}

export function studyConfig(
  workspace: Workspace,
  kind: StudyKind,
): StudyConfig {
  return {
    kind,
    sourceIds: studySources(workspace)
      .filter((source) => source.selected)
      .map((source) => source.id),
    count: kind === "flashcard" ? 8 : 5,
    difficulty: "medium",
    focus: "",
    language: "auto",
  };
}

export function studyEvidence(citation: StudyCitation): Evidence {
  return {
    id: citation.docId,
    file: citation.file,
    locator: `Page ${citation.page}`,
    title: "Excerpt used to create the study set",
    quote: citation.quote,
    context: citation.quote,
    finding: citation.quote,
    page: citation.page,
    startLine: citation.startLine,
    endLine: citation.endLine,
    docHash: citation.docHash || undefined,
  };
}

export function scoreQuiz(items: StudyItem[], answers: Record<string, number>) {
  return {
    correct: items.filter(
      (item) =>
        item.correctIndex !== undefined &&
        answers[item.id] === item.correctIndex,
    ).length,
    total: items.length,
  };
}

export function quizTopics(
  items: StudyItem[],
  answers: Record<string, number>,
) {
  const groups = new Map<string, StudyItem[]>();
  for (const item of items) {
    const group = groups.get(item.topic) ?? [];
    group.push(item);
    groups.set(item.topic, group);
  }
  return [...groups].map(([topic, group]) => ({
    topic,
    ...scoreQuiz(group, answers),
  }));
}

export function reviewCards(items: StudyItem[]): StudyItem[] {
  return items.map((item) => ({
    id: item.id,
    question: item.question,
    answer:
      `${item.options?.[item.correctIndex ?? -1] ?? ""}\n\n${item.answer}`.trim(),
    topic: item.topic,
    citation: item.citation,
  }));
}

export function studySuggestion(
  workspace: Workspace,
  message: Message,
): { kind: StudyKind; focus: string } | null {
  const ready = studySources(workspace);
  if (!ready.some((source) => source.selected) || message.state !== "answer")
    return null;
  const request = message.request.toLocaleLowerCase();
  const latest = workspace.studySets?.find(
    (set) =>
      set.config.kind === "quiz" &&
      set.quiz?.complete &&
      set.engine !== "sample",
  );
  const weak = latest?.items.find((item) => {
    const attempt = latest.quiz;
    return (
      attempt?.answers[item.id] !== undefined &&
      attempt.answers[item.id] !== item.correctIndex &&
      request.includes(item.topic.toLocaleLowerCase())
    );
  });
  if (weak) return { kind: "flashcard", focus: weak.topic };
  if (
    /chưa hiểu|không hiểu|khó hiểu|khó nhớ|don.t understand|still confused/iu.test(
      request,
    )
  )
    return { kind: "flashcard", focus: message.request };
  if (
    /kiểm tra (?:kiến thức|mức độ hiểu)|quiz me|test my understanding/iu.test(
      request,
    )
  )
    return { kind: "quiz", focus: message.request };
  return null;
}

export function shuffled(ids: string[]) {
  const order = [...ids];
  for (let index = order.length - 1; index > 0; index--) {
    const next = Math.floor(Math.random() * (index + 1));
    [order[index], order[next]] = [order[next], order[index]];
  }
  return order;
}
