import type { Workspace, Draft, Source } from "./data";
import { clampProgress, normalizeTaskStatus } from "./schema";

export const SCHEMA_VERSION = 3;
export function normalizeDraft(draft: Draft): Draft {
  return {
    ...draft,
    attachmentIds: [...(draft.attachmentIds ?? [])],
    currentState: draft.currentState ?? "IDLE",
    origin: draft.origin ?? "local",
  };
}
/** Migrate on read without discarding records, legacy labels, CC or drafts. */
export function migrateWorkspace(w: Workspace): Workspace {
  const requirements = w.requirements ?? [];
  return {
    ...w,
    schemaVersion: SCHEMA_VERSION,
    requirements,
    reconciliationRuns: w.reconciliationRuns ?? [],
    reconciledItems: w.reconciledItems ?? [],
    sources: w.sources.map((s) => ({
      ...s,
      origin: s.origin ?? (s.status === "Preview only" ? "local" : "sample"),
    })),
    evidence: Object.fromEntries(
      Object.entries(w.evidence).map(([id, e]) => [
        id,
        { ...e, origin: e.origin ?? "sample" },
      ]),
    ),
    tasks: w.tasks.map((t) => {
      const legacyStatus = t.status as string;
      const status = normalizeTaskStatus(legacyStatus);
      const localLabel = [
        "Design Review",
        "Rework",
        "Not Started",
        "Blocked",
        "On Hold",
      ].includes(legacyStatus)
        ? legacyStatus
        : t.localLabel;
      return {
        ...t,
        status,
        localLabel,
        archived: t.archived ?? legacyStatus === "Archived",
        completionPct: clampProgress(
          t.completionPct,
          status === "DONE" ? 100 : 0,
        ),
        sourceRef:
          t.sourceRef ??
          (t.source && w.evidence[t.source]
            ? `${w.evidence[t.source].file} ${w.evidence[t.source].locator}`
            : ""),
        createdAt: t.createdAt ?? w.updated,
        updatedAt: t.updatedAt ?? w.updated,
      };
    }),
    suggestions: w.suggestions.map((s) => ({
      ...s,
      status: normalizeTaskStatus(s.status ?? "TODO"),
    })),
    draft: normalizeDraft(w.draft),
    threads: w.threads.map((t) => ({
      ...t,
      engineMode: t.engineMode ?? "offline",
      createdAt: t.createdAt ?? t.updated,
      draft: t.draft ? normalizeDraft(t.draft) : undefined,
      messages: t.messages.map((m) => ({ ...m, origin: m.origin ?? "sample" })),
    })),
  };
}
export function draftPayload(d: Draft) {
  // Recipient, content and attachments are the server approval boundary. CC is a local note.
  return JSON.stringify({
    recipient_email: recipientAddress(d.to),
    subject: d.subject,
    body: d.body,
    attachment_ids: [...(d.attachmentIds ?? [])].sort(),
  });
}
export function recipientAddress(value: string) {
  const trimmed = value.trim();
  const match = /^[^<>]*<([^<>]+)>$/.exec(trimmed);
  return match ? match[1].trim() : trimmed;
}
export function validRecipient(value: string) {
  return /^[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+$/.test(recipientAddress(value));
}
export async function sha256(bytes: BufferSource) {
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
}
export function sourceFromServer(row: Record<string, unknown>): Source {
  const text = (name: string) =>
    typeof row[name] === "string" ? (row[name] as string) : undefined;
  const number = (...names: string[]) => {
    for (const name of names)
      if (typeof row[name] === "number") return row[name] as number;
    return undefined;
  };
  if (!text("doc_id") || !text("doc_name"))
    throw new Error("The server returned an invalid document record.");
  const pages = number("total_pages", "page_count");
  return {
    id: text("doc_id")!,
    name: text("doc_name")!,
    kind: (text("file_type") ?? text("doc_name")!.split(".").pop() ?? "")
      .toUpperCase()
      .replace(/^\./, ""),
    detail: `${pages ?? "—"} pages · ${number("total_chunks", "chunk_count") ?? "—"} passages`,
    status: "Processed",
    selected: row.is_selected === true,
    origin: "server",
    fileHash: text("file_hash"),
    fileSizeBytes: number("file_size_bytes"),
    versionId: text("version_id"),
    totalPages: pages,
    totalLines: number("total_lines"),
    totalChunks: number("total_chunks", "chunk_count"),
    mimeType: text("mime_type"),
    uploadedAt: text("uploaded_at"),
    updatedAt: text("updated_at"),
    sourceUrl: text("source_url"),
  };
}
/** Replace device previews only after the server has indexed their actual bytes. */
export function syncWorkspaceLibrary(
  w: Workspace,
  serverSources: Source[],
  replacements: Record<string, string> = {},
): Workspace {
  const ids = new Map<string, string>();
  const matched = new Map<string, Source[]>();
  for (const old of w.sources) {
    const current = serverSources.find(
      (s) =>
        s.id === replacements[old.id] ||
        (old.origin === "server" && s.id === old.id) ||
        (old.origin !== "sample" &&
          !!old.fileHash &&
          s.fileHash === old.fileHash),
    );
    if (current) {
      ids.set(old.id, current.id);
      matched.set(current.id, [...(matched.get(current.id) ?? []), old]);
    }
  }
  const sources = [
    ...w.sources
      .filter((s) => !ids.has(s.id))
      .map((s): Source =>
        s.origin === "server"
          ? {
              ...s,
              origin: "local",
              status: "Needs upload",
              selected: false,
              limitation:
                "The server no longer has this file. Re-upload the original to use it again.",
            }
          : { ...s, selected: false },
      ),
    ...serverSources.map((s) => {
      const sameFile = matched
        .get(s.id)
        ?.find((old) => !!s.fileHash && old.fileHash === s.fileHash);
      return {
        ...s,
        fileSizeBytes: s.fileSizeBytes ?? sameFile?.fileSizeBytes,
        mimeType: s.mimeType ?? sameFile?.mimeType,
        pages: s.pages ?? sameFile?.pages?.map((p) => ({ ...p, doc_id: s.id })),
      };
    }),
  ];
  const remapDraft = (draft: Draft): Draft => ({
    ...draft,
    attachmentIds: draft.attachmentIds?.map((id) => ids.get(id) ?? id),
  });
  return {
    ...w,
    sources,
    requirements: w.requirements?.map((r) => ({
      ...r,
      doc_id: r.doc_id ? (ids.get(r.doc_id) ?? r.doc_id) : null,
    })),
    evidence: Object.fromEntries(
      Object.entries(w.evidence).map(([key, e]) => [
        key,
        ids.has(e.id) ? { ...e, id: ids.get(e.id)! } : e,
      ]),
    ),
    draft: remapDraft(w.draft),
    threads: w.threads.map((t) => ({
      ...t,
      draft: t.draft ? remapDraft(t.draft) : undefined,
    })),
  };
}
export function resolveCitedSource(
  docId: string,
  sources: Source[],
): Source | undefined {
  const key = docId.trim().toLowerCase();
  const exact = sources.filter(
    (s) => s.id.toLowerCase() === key || s.name.toLowerCase() === key,
  );
  if (exact.length === 1) return exact[0];
  if (exact.length > 1) return undefined;
  const stem = key.replace(/\.[^.]+$/, "");
  const matches = sources.filter(
    (s) => s.name.toLowerCase().replace(/\.[^.]+$/, "") === stem,
  );
  return matches.length === 1 ? matches[0] : undefined;
}
