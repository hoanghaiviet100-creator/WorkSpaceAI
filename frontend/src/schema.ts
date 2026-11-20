/** Frontend-facing database contracts. Credential fields stay on the server. */
export type EngineMode = "offline" | "ollama" | "gemini";
export type RouteType =
  | "QA_FLOW"
  | "EMAIL_FLOW"
  | "CLARIFICATION_FLOW"
  | "REJECTED_SAFEGUARD";
export type VerificationStatus =
  | "VERIFIED_EXACT"
  | "VERIFIED_SUBSTRING"
  | "VERIFIED_TOKEN_LCS"
  | "VERIFIED_FUZZY"
  | "UNGROUNDED_QUOTE"
  | "HALLUCINATED_CLAIM"
  | "OUT_OF_BOUNDS";
export type EmailState =
  | "IDLE"
  | "AWAITING_CLARIFICATION"
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "SENT"
  | "FAILED_RETRYABLE";

export interface UserRow {
  user_id: string;
  email: string;
  display_name: string;
  email_verified_at: string | null;
  created_at: string;
}
export interface WorkspaceRow {
  workspace_id: string;
  name: string;
  created_at: string;
  updated_at: string;
}
export interface WorkspaceMemberRow {
  workspace_id: string;
  user_id: string;
  role: "owner" | "editor" | "viewer";
  joined_at: string;
}

export interface DocumentRow {
  workspace_id: string;
  doc_id: string;
  doc_name: string;
  file_type: string;
  file_size_bytes: number;
  file_hash: string;
  version_id: string;
  total_pages: number;
  total_lines: number;
  total_chunks: number;
  is_selected: boolean;
  storage_path: string | null;
  source_url: string | null;
  headings: unknown[] | null;
  mime_type: string;
  uploaded_at: string;
  updated_at: string;
  archived_at: string | null;
}
export interface DocumentPageRow {
  workspace_id: string;
  page_id: number;
  doc_id: string;
  page_number: number;
  line_count: number;
  raw_text: string;
  page_hash: string;
  created_at: string;
}
export type DocumentPage = Omit<DocumentPageRow, "workspace_id">;

export interface DocumentChunkRow {
  workspace_id: string;
  chunk_id: string;
  doc_id: string;
  doc_name: string;
  page_number: number;
  start_line: number;
  end_line: number;
  section_header: string;
  text: string;
  chunk_hash: string;
  token_count: number;
  doc_version: string;
  embedding: number[] | null;
  embedding_encoder: string | null;
  created_at: string;
}
export interface ChatSessionRow {
  workspace_id: string;
  session_id: string;
  session_name: string;
  active_mode: EngineMode;
  created_at: string;
  updated_at: string;
}
export interface ChatMessageRow {
  workspace_id: string;
  message_id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  route_type: RouteType;
  grounding_score: number;
  selected_docs: string[];
  citations: string[];
  created_at: string;
}
export interface CitationClaimRow {
  workspace_id: string;
  claim_id: string;
  message_id: string;
  claim_text: string;
  cited_doc_id: string;
  cited_page: number;
  cited_start_line: number | null;
  cited_end_line: number | null;
  evidence_quote: string;
  verification_status: VerificationStatus;
  semantic_status: "SUPPORTED" | "CONTRADICTED" | "INSUFFICIENT" | "UNAVAILABLE" | null;
  match_score: number;
  matched_span: string | null;
  doc_version: string;
  doc_hash: string;
  verified_at: string;
}
export interface EmailDraftRow {
  workspace_id: string;
  draft_id: string;
  session_id: string | null;
  recipient_email: string;
  subject: string;
  body: string;
  attachment_ids: string[];
  citations: string[];
  current_state: EmailState | "DRAFT" | "FAILED" | "DELIVERY_UNKNOWN";
  payload_hash: string | null;
  hmac_signature: string | null;
  created_at: string;
  updated_at: string;
  sent_at: string | null;
}
export interface EmailAuditRow {
  workspace_id: string;
  log_id: number;
  draft_id: string;
  from_state: string;
  to_state: string;
  trigger_event: string;
  actor: string;
  is_tampered: boolean;
  details: Record<string, unknown> | null;
  recorded_at: string;
}
export interface SchemaTables {
  users: UserRow[];
  workspaces: WorkspaceRow[];
  workspace_members: WorkspaceMemberRow[];
  documents: DocumentRow[];
  document_pages: DocumentPageRow[];
  document_chunks: DocumentChunkRow[];
  chat_sessions: ChatSessionRow[];
  chat_messages: ChatMessageRow[];
  citation_claims: CitationClaimRow[];
  email_drafts: EmailDraftRow[];
  email_audit_logs: EmailAuditRow[];
}
export const VERIFIED_STATUSES: readonly VerificationStatus[] = [
  "VERIFIED_EXACT",
  "VERIFIED_SUBSTRING",
  "VERIFIED_TOKEN_LCS",
  "VERIFIED_FUZZY",
];
export const isVerified = (status?: string): boolean =>
  VERIFIED_STATUSES.includes(status as VerificationStatus);
export const featureRoute = (mode: "Ask" | "Email"): RouteType =>
  mode === "Email" ? "EMAIL_FLOW" : "QA_FLOW";
