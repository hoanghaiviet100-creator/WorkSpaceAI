import type {
  CitationClaimRow,
  RouteType,
  EmailState,
  DocumentPageRow,
} from "./schema";
import type { Draft, Source, Workspace } from "./data";
import {
  recipientAddress,
  sourceFromServer,
  validRecipient,
  draftPayload,
} from "./workflow-model";

const env = import.meta.env;
export const apiConfig = {
  enabled: env.VITE_API_ENABLED === "true",
  base: (env.VITE_API_BASE_URL || "/api").replace(/\/$/, ""),
};
export const apiFor = (workspaceId: string) =>
  apiConfig.enabled && /^[A-Za-z0-9_-]{1,64}$/.test(workspaceId);
export type RuntimeStatus = {
  status: string;
  engine_mode: "offline" | "ollama" | "gemini";
  gemini_configured: boolean;
  model: string | null;
  saved_locally?: boolean;
  offline_only?: boolean;
  gemini_scope?: "feature1";
  model_options?: string[];
  provider_options?: {
    id: "ollama" | "gemini";
    model: string;
    configured: boolean;
  }[];
};
export const selectProvider = (provider: "ollama" | "gemini") =>
  request<RuntimeStatus>("/runtime/provider", json({ provider }));
export const getRuntimeStatus = () => request<RuntimeStatus>("/runtime");
export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}
async function request<T>(
  path: string,
  options: RequestInit = {},
  workspaceId?: string,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    path === "/chat" ? 150_000 : 60_000,
  );
  try {
    const headers = new Headers(options.headers);
    if (workspaceId) headers.set("X-Workspace-ID", workspaceId);
    const response = await fetch(`${apiConfig.base}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail =
        typeof data?.detail === "string"
          ? data.detail
          : `Server request failed (${response.status}).`;
      throw new ApiError(detail, response.status);
    }
    if (!data || typeof data !== "object")
      throw new ApiError("The server returned an unreadable response.");
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      "Could not confirm the server response. Check your connection.",
    );
  } finally {
    clearTimeout(timeout);
  }
}
const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export type ServerClaim = Partial<CitationClaimRow> & {
  claim_text: string;
  cited_doc_id: string;
  cited_page: number;
  evidence_quote: string;
};
export type ChatResponse = {
  route: RouteType;
  status: string;
  message?: string;
  answer?: string;
  grounding_score?: number;
  validated_claims?: ServerClaim[];
  hallucination_flags?: ServerClaim[];
  draft?: {
    draft_id: string;
    recipient_email: string;
    subject: string;
    body: string;
    attachment_ids: string[];
    citations: string[];
    state: EmailState;
    payload_hash: string;
    hmac_signature?: string;
    created_at?: string;
    updated_at?: string;
    sent_at?: string;
  };
};
export async function listDocuments(workspaceId?: string): Promise<Source[]> {
  const rows = await request<Record<string, unknown>[]>(
    "/documents",
    {},
    workspaceId,
  );
  if (!Array.isArray(rows))
    throw new ApiError("The document library response is invalid.");
  return rows.map(sourceFromServer);
}
export async function uploadDocument(
  file: File,
  workspaceId?: string,
): Promise<Source> {
  const body = new FormData();
  body.append("file", file);
  const result = await request<{ document: Record<string, unknown> }>(
    "/documents/upload",
    { method: "POST", body },
    workspaceId,
  );
  return sourceFromServer({
    ...result.document,
    file_size_bytes: file.size,
    mime_type: file.type,
  });
}
export async function deleteDocument(id: string, workspaceId?: string) {
  await request(
    `/documents/${encodeURIComponent(id)}`,
    { method: "DELETE" },
    workspaceId,
  );
}
export async function selectDocuments(ids: string[], workspaceId?: string) {
  await request(
    "/documents/select",
    json({ selected_doc_ids: ids }),
    workspaceId,
  );
}
export function chatRequest(
  query: string,
  selectedDocIds: string[],
  history: { role: string; content: string }[] = [],
  recipient?: string,
  referenceDate = new Date().toLocaleDateString("en-CA"),
  workspaceId?: string,
  studioTool?: "email",
) {
  return request<ChatResponse>(
    "/chat",
    json({
      query,
      selected_doc_ids: selectedDocIds,
      conversation_history: history,
      reference_date: referenceDate,
      allow_reconciliation: false,
      ...(recipient ? { recipient_email: recipientAddress(recipient) } : {}),
      ...(studioTool ? { studio_tool: studioTool } : {}),
    }),
    workspaceId,
  );
}
export async function renameDocument(
  id: string,
  name: string,
  workspaceId?: string,
) {
  return request<Record<string, unknown>>(
    `/documents/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    },
    workspaceId,
  );
}
export async function importSourceLink(
  url: string,
  title: string,
  workspaceId?: string,
): Promise<Source> {
  const result = await request<{ document: Record<string, unknown> }>(
    "/documents/import-url",
    json({ url, title }),
    workspaceId,
  );
  return {
    ...sourceFromServer(result.document),
    sourceUrl: String(result.document.source_url || url),
  };
}
export function getDocumentPage(id: string, page: number, workspaceId: string) {
  return request<
    DocumentPageRow & {
      doc_hash: string;
      doc_version: string;
      partial: boolean;
    }
  >(`/documents/${encodeURIComponent(id)}/pages/${page}`, {}, workspaceId);
}
export function draftFromServer(
  row: NonNullable<ChatResponse["draft"]>,
  sessionId: string,
  w: Pick<Workspace, "name">,
): Draft {
  if (
    !row.draft_id ||
    !validRecipient(row.recipient_email) ||
    !row.subject ||
    !row.body ||
    !/^[a-f\d]{64}$/i.test(row.payload_hash) ||
    ![
      "IDLE",
      "AWAITING_CLARIFICATION",
      "PENDING_APPROVAL",
      "APPROVED",
      "SENT",
      "FAILED_RETRYABLE",
    ].includes(row.state)
  )
    throw new ApiError("The server returned an incomplete email draft.");
  const attachmentIds = row.attachment_ids ?? [];
  return {
    id: row.draft_id,
    sessionId,
    to: row.recipient_email,
    cc: "",
    subject: row.subject,
    body: row.body,
    attachmentIds,
    currentState: row.state,
    payloadHash: row.payload_hash,
    hmacSignature: row.hmac_signature,
    purpose: "Clarification request",
    tone: "Formal and respectful",
    evidenceIds: [],
    serverCitations: row.citations ?? [],
    origin: "server",
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    sentAt: row.sent_at,
    serverSnapshot: {
      to: row.recipient_email,
      subject: row.subject,
      body: row.body,
      attachmentIds: [...attachmentIds],
    },
    context: w.name,
  };
}
export function approveAndSend(draft: Draft, workspaceId?: string) {
  if (
    !draft.id ||
    draft.origin !== "server" ||
    !draft.serverSnapshot ||
    !draft.payloadHash
  )
    throw new ApiError("Create a server draft before sending.");
  if (
    !validRecipient(draft.to) ||
    draft.cc.trim() ||
    draft.attachmentIds?.length ||
    draftPayload({ ...draft, ...draft.serverSnapshot }) !== draftPayload(draft)
  )
    throw new ApiError(
      "This version cannot be submitted. The current server accepts its staged single-recipient draft without attachments.",
    );
  if (
    !["PENDING_APPROVAL", "APPROVED", "FAILED_RETRYABLE"].includes(
      draft.currentState ?? "IDLE",
    )
  )
    throw new ApiError("This draft is not awaiting approval.");
  const params = new URLSearchParams({
    recipient_email: recipientAddress(draft.to),
    subject: draft.subject,
    body: draft.body,
    user_confirmed: "true",
  });
  // This route approves AND sends. The button must explicitly describe both actions.
  return request<{
    status: EmailState;
    dispatch_mode?: string;
    message?: string;
    sent_at?: string;
  }>(
    `/email/approve/${encodeURIComponent(draft.id)}?${params}`,
    {
      method: "POST",
    },
    workspaceId,
  );
}
