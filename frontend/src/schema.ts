/** Database contracts from database/schema.sql. UI-only preferences stay outside these rows. */
export type EngineMode = "offline" | "ollama" | "gemini";
export type TaskState = "TODO" | "IN_PROGRESS" | "REVIEW" | "DONE";
export type RouteType =
  | "QA_FLOW"
  | "RECONCILE_FLOW"
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
export type ReconciliationState =
  | "FULLY_COVERED"
  | "PARTIALLY_COVERED"
  | "NOT_COVERED"
  | "OVERDUE"
  | "DEADLINE_CONFLICT";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface DocumentRow {
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
  mime_type: string;
  uploaded_at: string;
  updated_at: string;
}
export interface DocumentPageRow {
  page_id: number;
  doc_id: string;
  page_number: number;
  line_count: number;
  raw_text: string;
  page_hash: string;
  created_at: string;
}
export interface DocumentChunkRow {
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
  created_at: string;
}
export interface RequirementRow {
  req_id: string;
  doc_id: string | null;
  title: string;
  description: string | null;
  keywords: string[];
  official_deadline: string | null;
  mandatory_flag: boolean;
  source_ref: string;
  created_at: string;
  updated_at: string;
}
export interface TaskRow {
  task_id: string;
  mapped_req_id: string | null;
  title: string;
  owner: string | null;
  status: TaskState;
  logged_deadline: string | null;
  completion_pct: number;
  source_ref: string;
  created_at: string;
  updated_at: string;
}
export interface ReconciliationRunRow {
  run_id: string;
  reference_date: string;
  coverage_ratio: number;
  total_requirements: number;
  covered_requirements: number;
  overdue_count: number;
  conflict_count: number;
  executed_at: string;
}
export interface DateConflict {
  doc_a: string;
  date_a: string;
  doc_b: string;
  date_b: string;
}
export interface ReconciledItemRow {
  id: number;
  run_id: string;
  req_id: string;
  state: ReconciliationState;
  risk_level: RiskLevel;
  avg_completion: number;
  days_remaining: number | null;
  owners: string[];
  date_conflicts: DateConflict[];
  citations: string[];
}
export interface ChatSessionRow {
  session_id: string;
  session_name: string;
  active_mode: EngineMode;
  created_at: string;
  updated_at: string;
}
export interface ChatMessageRow {
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
  claim_id: string;
  message_id: string;
  claim_text: string;
  cited_doc_id: string;
  cited_page: number;
  cited_start_line: number | null;
  cited_end_line: number | null;
  evidence_quote: string;
  verification_status: VerificationStatus;
  match_score: number;
  matched_span: string | null;
  doc_version: string;
  doc_hash: string;
  verified_at: string;
}
export interface EmailDraftRow {
  draft_id: string;
  session_id: string | null;
  recipient_email: string;
  subject: string;
  body: string;
  attachment_ids: string[];
  citations: string[];
  current_state: EmailState;
  payload_hash: string;
  hmac_signature: string;
  created_at: string;
  updated_at: string;
  sent_at: string | null;
}
export interface EmailAuditRow {
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
  documents: DocumentRow[];
  document_pages: DocumentPageRow[];
  document_chunks: DocumentChunkRow[];
  requirements: RequirementRow[];
  tasks: TaskRow[];
  reconciliation_runs: ReconciliationRunRow[];
  reconciled_items: ReconciledItemRow[];
  chat_sessions: ChatSessionRow[];
  chat_messages: ChatMessageRow[];
  citation_claims: CitationClaimRow[];
  email_drafts: EmailDraftRow[];
  email_audit_logs: EmailAuditRow[];
}
export const TASK_STATES: readonly TaskState[] = [
  "TODO",
  "IN_PROGRESS",
  "REVIEW",
  "DONE",
];
export const VERIFIED_STATUSES: readonly VerificationStatus[] = [
  "VERIFIED_EXACT",
  "VERIFIED_SUBSTRING",
  "VERIFIED_TOKEN_LCS",
  "VERIFIED_FUZZY",
];
export const isVerified = (status?: string): boolean =>
  VERIFIED_STATUSES.includes(status as VerificationStatus);
export const featureRoute = (mode: "Ask" | "Tasks" | "Email"): RouteType =>
  mode === "Ask"
    ? "QA_FLOW"
    : mode === "Tasks"
      ? "RECONCILE_FLOW"
      : "EMAIL_FLOW";
export function normalizeTaskStatus(value: string): TaskState {
  if (TASK_STATES.includes(value as TaskState)) return value as TaskState;
  if (["To do", "To-do", "Not Started"].includes(value)) return "TODO";
  if (["In Review", "Design Review"].includes(value)) return "REVIEW";
  if (value === "Done") return "DONE";
  return "IN_PROGRESS";
}
export function clampProgress(value: unknown, fallback = 0) {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : fallback;
}
