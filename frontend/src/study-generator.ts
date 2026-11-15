import { getDocumentPage } from "./api";
import type { Workspace } from "./data";
import { visibleChatMessages } from "./notebook-model";
import { isVerified } from "./schema";
import {
  shuffled,
  studySources,
  type StudyCitation,
  type StudyConfig,
  type StudyItem,
} from "./study-model";

type Fact = { text: string; topic: string; citation: StudyCitation };
const normalized = (value: string) =>
  value.toLocaleLowerCase().replace(/\s+/g, " ").trim();
const terms = (value: string) =>
  new Set(value.toLocaleLowerCase().match(/[\p{L}\p{N}]{3,}/gu) ?? []);

function extractFacts(
  text: string,
  file: string,
  base: Omit<StudyCitation, "quote" | "startLine" | "endLine">,
): Fact[] {
  let topic = file.replace(/\.[^.]+$/, "");
  return text.split(/\r?\n/).flatMap((line, index) => {
    const trimmed = line.trim();
    const heading = trimmed.match(
      /^(?:#{1,6}\s+|(?:chương|chapter|phần|section)\s+\S+\s*[:.\-]?\s*)(.+)$/iu,
    );
    if (heading) {
      topic = heading[1].trim().slice(0, 100);
      return [];
    }
    return trimmed.split(/(?<=[.!?;])\s+(?=[\p{Lu}\d])/u).flatMap((part) => {
      const value = part.trim();
      if (value.length < 28 || value.length > 560 || terms(value).size < 5)
        return [];
      return [
        {
          text: value,
          topic,
          citation: {
            ...base,
            quote: value,
            startLine: index + 1,
            endLine: index + 1,
          },
        },
      ];
    });
  });
}

function cloze(text: string, { difficulty, language }: StudyConfig) {
  const definition =
    /^(?<subject>[^:]{3,90}?)\s+(?<connector>là|means|is defined as|refers to|is|are)\s+(?<value>[^.!?;]{3,110})[.!?]?$/iu.exec(
      text,
    );
  if (definition?.groups && difficulty === "easy") {
    const vietnamese =
      language === "vi" ||
      (language !== "en" && definition.groups.connector.toLowerCase() === "là");
    return {
      question: vietnamese
        ? `${definition.groups.subject} — khái niệm này được mô tả thế nào?`
        : `How does the source describe “${definition.groups.subject}”?`,
      value: definition.groups.value,
    };
  }
  const words = [...text.matchAll(/[\p{L}\p{N}]+(?:[.,–-][\p{L}\p{N}]+)*/gu)];
  const size = { easy: 1, medium: 2, hard: 4 }[difficulty];
  if (words.length < size + 3) return null;
  // Leave context on both sides of the blank whenever the excerpt allows it.
  const position = words.findIndex(
    (word, index) =>
      index > 1 && index < words.length - size && /\d/.test(word[0]),
  );
  const start = position < 0 ? Math.max(2, words.length - size - 1) : position;
  const left = words[start].index!;
  const tail = words[start + size - 1];
  const right = tail.index! + tail[0].length;
  const instruction =
    language === "vi"
      ? "Điền phần còn thiếu.\n"
      : language === "en"
        ? "Fill in the blank.\n"
        : "";
  return {
    question: instruction + text.slice(0, left) + "[…]" + text.slice(right),
    value: text.slice(left, right),
  };
}

function pageNumbers(total: number) {
  const count = Math.min(6, Math.max(1, total));
  return Array.from({ length: count }, (_, index) =>
    count === 1 ? 1 : 1 + Math.round((index * (total - 1)) / (count - 1)),
  );
}

export async function createStudyItems(
  workspace: Workspace,
  config: StudyConfig,
): Promise<StudyItem[]> {
  const available = studySources(workspace);
  const sources = config.sourceIds.map((id) =>
    available.find((source) => source.id === id),
  );
  if (!sources.length || sources.some((source) => !source))
    throw Error("Select ready sources from this note.");
  const factsBySource: Fact[][] = [];
  // Bound requests for large libraries and give each selected document a turn.
  for (const source of sources) {
    if (!source) continue;
    const pages = await Promise.all(
      (source.origin === "server"
        ? pageNumbers(source.totalPages ?? 1)
        : (source.pages ?? []).map((page) => page.page_number)
      ).map(async (number) => {
        const page =
          source.pages?.find((entry) => entry.page_number === number) ??
          (await getDocumentPage(source.id, number, workspace.id));
        const docHash =
          "doc_hash" in page ? (page.doc_hash as string) : source.fileHash;
        if (source.fileHash && docHash && source.fileHash !== docHash)
          throw Error(
            `Source “${source.name}” changed. Try creating the set again.`,
          );
        return extractFacts(page.raw_text, source.name, {
          docId: source.id,
          file: source.name,
          page: number,
          docHash,
        });
      }),
    );
    factsBySource.push(pages.flat());
  }
  const seen = new Set<string>();
  const focus = terms(config.focus);
  const thread = workspace.threads[0];
  // Give passages previously verified by Q&A precedence without another model request.
  const cited = thread
    ? visibleChatMessages(workspace, thread)
        .slice(-12)
        .flatMap((message) => message.evidenceIds)
        .map((id) => workspace.evidence[id])
        .filter(
          (evidence) =>
            evidence &&
            isVerified(evidence.verificationStatus) &&
            evidence.quote.trim().length >= 28,
        )
    : [];
  const entries = factsBySource
    .flatMap((facts) =>
      facts.map((fact, rank) => ({
        fact,
        rank,
        cited: cited.some(
          (evidence) =>
            evidence.id === fact.citation.docId &&
            (!evidence.docHash || evidence.docHash === fact.citation.docHash) &&
            normalized(evidence.quote).includes(normalized(fact.text)),
        ),
        relevance: [...terms(fact.text + " " + fact.topic)].filter((term) =>
          focus.has(term),
        ).length,
      })),
    )
    .sort(
      (a, b) =>
        b.relevance - a.relevance ||
        Number(b.cited) - Number(a.cited) ||
        a.rank - b.rank,
    )
    .flatMap(({ fact }) => {
      const key = fact.text.toLocaleLowerCase();
      if (seen.has(key)) return [];
      seen.add(key);
      const blank = cloze(fact.text, config);
      return blank ? [{ fact, ...blank }] : [];
    });
  const items: StudyItem[] = [];
  for (const entry of entries) {
    const { fact, question, value } = entry;
    const item: StudyItem = {
      id: crypto.randomUUID(),
      question,
      answer: fact.text,
      topic: fact.topic,
      citation: fact.citation,
    };
    if (config.kind === "quiz") {
      const alternatives = new Map<string, string>();
      for (const other of entries) {
        const key = other.value.toLocaleLowerCase();
        if (!fact.text.toLocaleLowerCase().includes(key))
          alternatives.set(key, other.value);
        if (alternatives.size === 3) break;
      }
      if (!alternatives.size) continue;
      item.options = shuffled([value, ...alternatives.values()]);
      item.correctIndex = item.options.indexOf(value);
    }
    items.push(item);
    if (items.length === config.count) break;
  }
  if (!items.length)
    throw Error(
      "There is too little readable text to create a study set. Select more documents and try again.",
    );
  return items;
}
