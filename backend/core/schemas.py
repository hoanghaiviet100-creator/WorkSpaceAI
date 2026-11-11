from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid
from uuid import UUID
from pydantic import BaseModel, Field


class RouteType(str, Enum):
    QA_FLOW = "QA_FLOW"
    RECONCILE_FLOW = "RECONCILE_FLOW"
    EMAIL_FLOW = "EMAIL_FLOW"
    CLARIFICATION_FLOW = "CLARIFICATION_FLOW"
    REJECTED_SAFEGUARD = "REJECTED_SAFEGUARD"


class DocumentChunk(BaseModel):
    chunk_id: str
    doc_id: str
    doc_name: str
    page_number: int = 1
    start_line: int = 1
    end_line: int = 1
    section_header: str = "General"
    text: str
    score: float = 0.0
    bm25_score: float = 0.0
    dense_score: float = 0.0
    rrf_score: float = 0.0
    pinpoint_score: float = 0.0
    doc_version: str = "v1"
    doc_hash: str = ""


class DocumentMetadata(BaseModel):
    doc_id: str
    doc_name: str
    file_type: str = "pdf"
    page_count: int = 1
    chunk_count: int = 0
    total_lines: int = 0
    file_hash: str = ""
    version_id: str = "v1"
    uploaded_at: str = ""
    is_selected: bool = True


class RequirementItem(BaseModel):
    req_id: str
    title: str
    keywords: List[str] = Field(default_factory=list)
    official_deadline: Optional[date] = None
    mandatory_flag: bool = True
    source_ref: str


# Alias for backward and forward compatibility
RequirementRecord = RequirementItem


class TaskRecord(BaseModel):
    task_id: str
    mapped_req_id: Optional[str] = None
    title: str
    owner: Optional[str] = None
    status: str = "IN_PROGRESS"
    logged_deadline: Optional[date] = None
    completion_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    source_ref: str


class DateConflict(BaseModel):
    doc_a: str
    date_a: date
    doc_b: str
    date_b: date


class ReconciledItemReport(BaseModel):
    req_id: str
    title: str
    state: str
    risk_level: str
    avg_completion: float
    days_remaining: Optional[int]
    owners: List[str]
    date_conflicts: List[DateConflict]
    citations: List[str]


class ReconciliationSummary(BaseModel):
    coverage_ratio: float
    overdue_count: int
    conflict_count: int
    item_reports: List[ReconciledItemReport]


class GeneratedClaim(BaseModel):
    claim_text: str
    cited_doc_id: str
    cited_page: int
    evidence_quote: str
    verification_status: str = "UNVERIFIED"
    cited_start_line: Optional[int] = None
    cited_end_line: Optional[int] = None
    doc_version: Optional[str] = None
    doc_hash: Optional[str] = None
    match_score: float = 0.0
    matched_span: Optional[str] = None
    evidence_span: Optional[Dict[str, Any]] = None


class CitationVerificationResult(BaseModel):
    validated_claims: List[GeneratedClaim]
    hallucination_flags: List[GeneratedClaim]
    grounding_score: float


class EmailFSMState(str, Enum):
    """
    Feature 3 FSM States according to WorkspaceAI Database Schema and Computational Thinking Report:
    - DRAFT: Initial mutable draft state.
    - APPROVED: Human-approved snapshot locked with SHA-256 digest.
    - SENT: Dispatched via SMTP and accepted by server.
    - FAILED: Transmission failed (e.g. SMTPAuthenticationError).
    - DELIVERY_UNKNOWN: Connection timed out or dropped; no automatic retry (NFR-04).
    """
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SENT = "SENT"
    FAILED = "FAILED"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"


class EmailDraftRecord(BaseModel):
    """
    Feature 3: Table EmailDraft in WorkspaceAI Database Schema.
    Stores email draft with SHA-256 integrity hash, FSM state, and audit timestamp.
    """
    id: UUID = Field(default_factory=uuid.uuid4)
    workspace_id: UUID
    recipients: Union[List[str], str]
    subject: str
    body: str
    fsm_state: EmailFSMState = EmailFSMState.DRAFT
    sha256_digest: Optional[str] = None
    audit_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    citations: List[str] = Field(default_factory=list)


class CreateDraftRequest(BaseModel):
    workspace_id: UUID
    recipients: Union[List[str], str]
    subject: str
    body: str
    citations: Optional[List[str]] = None


class ApproveDraftRequest(BaseModel):
    recipients: Optional[Union[List[str], str]] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    user_confirmed: bool = True


class EmailState(str, Enum):
    IDLE = "IDLE"
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SENT = "SENT"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"


class EmailDraftPayload(BaseModel):
    draft_id: str
    recipient_email: str
    subject: str
    body: str
    attachment_ids: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    state: EmailState = EmailState.PENDING_APPROVAL
    payload_hash: str = ""
    fsm_state: Optional[EmailFSMState] = None
    audit_timestamp: Optional[datetime] = None


class EmailApproveRequest(BaseModel):
    recipient_email: str
    subject: str
    body: str
    user_confirmed: bool = True


class UserRequest(BaseModel):
    query: str
    selected_doc_ids: Optional[List[str]] = None
    recipient_email: Optional[str] = None
    reference_date: date = Field(default_factory=lambda: date(2026, 10, 26))
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)


class DocumentSelectRequest(BaseModel):
    selected_doc_ids: List[str]
