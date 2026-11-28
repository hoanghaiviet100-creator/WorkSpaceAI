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
    path === "/chat" || path === "/documents/upload" ? 150_000 : 60_000,
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
      const displayDetail=path.startsWith('/documents') && /^[A-Z]+_[A-Z_]+:/.test(detail)
        ? (/RESOURCE/.test(detail) ? 'There is not enough available memory to process this document. Free memory, then try again.'
          : /TIMEOUT/.test(detail) ? 'Document processing took too long. Try a smaller document or split it into sections.'
          : /BUSY/.test(detail) ? 'Another document or question is being processed. Please wait a moment.'
          : 'The document could not be processed. Check the local AI service and refresh the source list.')
        : detail;
      throw new ApiError(displayDetail, response.status);
    }
    if (!data || typeof data !== "object")
      throw new ApiError("The server returned an unreadable response.");
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (path === "/documents/upload" && error instanceof DOMException && error.name === "AbortError")
      throw new ApiError("Document processing took longer than expected. Refresh the source list before uploading again.");
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
  citation_index?: number;
  claim_text: string;
  section?: string | null;
  cited_doc_id: string;
  cited_page: number;
  evidence_quote: string;
  thinking?: string;
};
export const sourceSupportDisclosure = "Được hỗ trợ bởi nguồn trích dẫn. Chưa kiểm chứng đầy đủ mâu thuẫn trong toàn bộ phạm vi tài liệu được phép.";
export type VerificationProfile = "academic_grounded" | "strict" | "evidence_centric_v0";
export type EvidenceCitation = {
  doc_id: string; doc_version: string; source_sha256: string;
  page: number; line_start: number; line_end: number; quote: string; quote_sha256: string;
};
export type EvidenceVerification = {
  profile: "evidence_centric_v0"; contract_version: "ec-v0";
  scope_manifest_sha256: string;
  coverage: "COMPLETE" | "INCOMPLETE" | "ERROR" | "NOT_ASSESSED";
  limitations: string[];
  claims: Array<{
    claim_id: string; text: string;
    disposition: "FULLY_VERIFIED" | "SOURCE_SUPPORTED" | "CONFIRMED_CONFLICT" |
      "INSUFFICIENT_CONFLICT_COVERAGE" | "INSUFFICIENT_EVIDENCE" | "ERROR";
    support: "SUPPORTED_BY_CITED_EVIDENCE" | "NOT_ESTABLISHED";
    reason: string; method: string; citations: EvidenceCitation[];
    competing_evidence: Array<{ evidence_id: string; relation: "COMPARABLE" | "DISTINCT" | "UNRESOLVED";
      verdict: "CONFLICT" | "NO_CONFLICT_ESTABLISHED" | "UNRESOLVED_SIGNAL";
      citations: EvidenceCitation[]; reason: string }>;
  }>;
};
export const citationIntegrityDisclosure = "Citation locations and source text checked. Answer meaning has not been independently semantically verified.";
export type ChatResponse = {
  semantic_verified?: boolean;
  verification_method?: string;
  coverage?: string;
  latency_ms?: number;
  verification?: EvidenceVerification;
  route: RouteType;
  status: string;
  message?: string;
  answer?: string;
  grounding_score?: number;
  validated_claims?: ServerClaim[];
  hallucination_flags?: ServerClaim[];
  suggested_questions?: string[];
  thinking?: string;
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
  verificationProfile: VerificationProfile = "strict",
  onProgress?: (stage: string) => void,
) {
  if (verificationProfile === "academic_grounded" && studioTool !== "email") {
    return streamAcademicQuestion({ query, selected_doc_ids: selectedDocIds,
      conversation_history: history.slice(-8), verification_profile: verificationProfile,
      allow_reconciliation: false }, workspaceId, onProgress);
  }
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
      ...(verificationProfile !== "strict" ? { verification_profile: verificationProfile } : {}),
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

export const getEmailConnection = () =>
  request<{ mode: "local_mock" | "gmail_real"; configured: boolean }>(
    "/email/connection",
  );

export const sendStudioEmail = (
  draftId: string,
  workspaceId: string,
  mode: "local_mock" | "gmail_real",
) =>
  request<{
    status: "SENT" | "FAILED" | "DELIVERY_UNKNOWN";
    dispatch_mode?: "local_mock" | "gmail_real";
    audit_timestamp?: string;
    error?: string;
  }>(
    `/email/studio/${encodeURIComponent(draftId)}/send?expected_mode=${mode}`,
    { method: "POST" },
    workspaceId,
  );


export function questionVietnamese(query: string): boolean {
  if (/in English|bằng tiếng Anh/i.test(query)) return false;
  return /in Vietnamese|bằng tiếng Việt|[\u0102-\u01b0\u1ea0-\u1ef9]/i.test(query);
}

function academicFailure(query: string, code = ""): string {
  const vi = questionVietnamese(query);
  if (code === 'GENERATION_PREPARING') return vi ? 'Đang chuẩn bị mô hình AI. Bạn có thể tải tài liệu lên trong lúc chờ.' : 'The AI model is getting ready. You can upload documents while you wait.';
  if (/MODEL_LOAD_TIMEOUT|GENERATION_RESIDENCY_LOST|GENERATION_UNAVAILABLE/.test(code)) return vi ? 'Mô hình AI chưa sẵn sàng. Hãy kiểm tra dịch vụ AI cục bộ rồi khởi động lại ứng dụng.' : 'The AI model is unavailable. Check the local AI service, then restart the app.';
  if (/BUSY/.test(code)) return vi ? "Mình đang xử lý một yêu cầu khác. Bạn chờ một chút nhé." : "Another request is being processed. Please wait a moment.";
  if (/RESOURCE/.test(code)) return vi ? "Máy hiện chưa đủ bộ nhớ để tiếp tục. Bạn hãy giải phóng bộ nhớ rồi thử lại nhé." : "There is not enough available memory to continue. Please free some memory and try again.";
  return vi ? "Mình chưa thể hoàn thành câu trả lời từ các tài liệu đã chọn. Bạn thử lại sau nhé." : "I could not complete an answer from the selected documents. Please try again later.";
}

async function streamAcademicQuestion(body: unknown, workspaceId?: string, onProgress?: (stage: string) => void): Promise<ChatResponse> {
  const query = (body as {query?: string}).query ?? "";
  const vi = questionVietnamese(query);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 150_000);
  try {
    const headers = new Headers({"Content-Type":"application/json"});
    if (workspaceId) headers.set("X-Workspace-ID", workspaceId);
    const response = await fetch(`${apiConfig.base}/chat/stream`, {
      method:"POST", headers, body:JSON.stringify(body), signal:controller.signal,
    });
    if (!response.ok || !response.body) {
      const error = await response.json().catch(() => null);
      throw new ApiError(academicFailure(query, error?.detail ?? ""), response.status);
    }
    const reader=response.body.getReader(); const decoder=new TextDecoder();
    let pending=""; let result: ChatResponse | undefined;
    while (true) {
      const part=await reader.read();
      pending += decoder.decode(part.value, {stream:!part.done});
      let boundary: number;
      while ((boundary=pending.indexOf("\n\n")) >= 0) {
        const frame=pending.slice(0,boundary); pending=pending.slice(boundary+2);
        if (!frame.startsWith("data: ")) continue;
        const event=JSON.parse(frame.slice(6));
        if (event.type === "error") throw new ApiError(academicFailure(query,event.code));
        if (event.type === "status") onProgress?.(event.stage === "retrieving" ? (vi ? "Đang đọc tài liệu đã chọn…" : "Reading selected sources…") : (vi ? "Đang viết câu trả lời…" : "Writing an answer…"));
        if (event.type === "progress") onProgress?.(vi ? "Đang viết câu trả lời…" : "Writing an answer…");
        if (event.type === "result") result=event.result as ChatResponse;
      }
      if (part.done) break;
    }
    if (!result) throw new ApiError(academicFailure(query));
    return result;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(academicFailure(query));
  } finally { clearTimeout(timeout); }
}
