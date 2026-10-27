from datetime import date
from enum import Enum
from typing import Dict, List, Optional
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
    section_header: str = "General"
    text: str
    score: float = 0.0


class RequirementItem(BaseModel):
    req_id: str
    title: str
    keywords: List[str] = Field(default_factory=list)
    official_deadline: Optional[date] = None
    mandatory_flag: bool = True
    source_ref: str


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


class CitationVerificationResult(BaseModel):
    validated_claims: List[GeneratedClaim]
    hallucination_flags: List[GeneratedClaim]
    grounding_score: float


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


class EmailApproveRequest(BaseModel):
    recipient_email: str
    subject: str
    body: str
    user_confirmed: bool = True


class UserRequest(BaseModel):
    query: str
    selected_doc_ids: List[str] = Field(default_factory=list)
    recipient_email: Optional[str] = None
    reference_date: date = Field(default_factory=lambda: date(2026, 10, 26))
