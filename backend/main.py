from datetime import date
from typing import Dict
from fastapi import FastAPI, HTTPException
from backend.Algorithms_R2 import (
    SecurityError,
    approve_and_verify_email_send,
    prepare_draft_for_approval,
    reconcile_requirements_and_tasks,
    verify_citations,
)
from backend.config import settings
from backend.LLM_Provider_R4 import LLMProvider
from backend.Retrieval_R3 import HybridWorkspaceIndex
from backend.schemas import (
    EmailDraftPayload,
    EmailState,
    RequirementItem,
    RouteType,
    TaskRecord,
    UserRequest,
)
from backend.Understanding_Guardrails import route_user_request

app = FastAPI(title="WorkspaceAI — CSC10014 Virtual Assistant Backend")
workspace_index = HybridWorkspaceIndex()
llm_provider = LLMProvider()
draft_store: Dict[str, EmailDraftPayload] = {}


@app.on_event("startup")
def seed_demo_workspace() -> None:
    """Seeds default CSC10014 project brief and team progress notes for instant local testing."""
    workspace_index.ingest_text_document(
        doc_id="Project_Brief.pdf",
        doc_name="Project_Brief.pdf",
        pages=[
            (
                3,
                "Minimum System Requirements: R1 Problem boundary, R2 Deterministic capability, "
                "R3 Data retrieval capability, R4 AI-enabled capability, R5 Routing orchestration.",
            ),
            (
                6,
                "Submission Package: 01 Engineering Report (12-18 pages recommended), "
                "02 Source Repository and Demo, 03 Architecture Pack, 04 Evaluation Pack.",
            ),
        ],
    )


@app.post("/api/chat")
def handle_user_request(req: UserRequest):
    route, missing_slots = route_user_request(req)

    if route == RouteType.REJECTED_SAFEGUARD:
        return {
            "route": route,
            "status": "BLOCKED_BY_SAFEGUARD",
            "message": "Request blocked by R7 Prompt-Injection / Security Safeguard.",
            "details": missing_slots,
        }

    if route == RouteType.CLARIFICATION_FLOW:
        return {
            "route": route,
            "status": "AWAITING_CLARIFICATION",
            "message": f"Please clarify the following missing information before proceeding: {', '.join(missing_slots)}",
            "missing_slots": missing_slots,
        }

    if route == RouteType.QA_FLOW:
        retrieved = workspace_index.search(req.query, top_k=3)
        if not retrieved or retrieved[0].score < settings.retrieval_min_score:
            return {
                "route": route,
                "status": "ABSTAINED_INSUFFICIENT_EVIDENCE",
                "message": "Insufficient evidence in your workspace documents to answer this question.",
                "citations": [],
            }

        raw_claims = llm_provider.generate_grounded_qa(req.query, retrieved)
        verification = verify_citations(
            raw_claims,
            workspace_index.build_page_lookup(),
            theta_match=settings.citation_verify_threshold,
        )
        return {
            "route": route,
            "status": "ANSWER_VERIFIED",
            "grounding_score": verification.grounding_score,
            "validated_claims": verification.validated_claims,
            "hallucination_flags": verification.hallucination_flags,
        }

    if route == RouteType.RECONCILE_FLOW:
        # Demo sample requirements & tasks for Algorithm 1
        sample_reqs = [
            RequirementItem(
                req_id="R1",
                title="Problem boundary & 10 use cases",
                keywords=["boundary", "use", "cases"],
                official_deadline=date(2026, 10, 20),
                mandatory_flag=True,
                source_ref="Project_Brief.pdf#p3",
            ),
            RequirementItem(
                req_id="R2",
                title="Deterministic capability & algorithms",
                keywords=["deterministic", "algorithm"],
                official_deadline=date(2026, 10, 24),
                mandatory_flag=True,
                source_ref="Project_Brief.pdf#p3",
            ),
            RequirementItem(
                req_id="R8",
                title="Evaluation benchmark & improvement cycle",
                keywords=["evaluation", "benchmark"],
                official_deadline=date(2026, 11, 15),
                mandatory_flag=True,
                source_ref="Project_Brief.pdf#p3",
            ),
        ]
        sample_tasks = [
            TaskRecord(
                task_id="T-01",
                mapped_req_id="R1",
                title="Define problem boundary and 10 use cases",
                owner="Minh",
                status="COMPLETED",
                logged_deadline=date(2026, 10, 20),
                completion_pct=100.0,
                source_ref="team_tasks.csv#row1",
            ),
            TaskRecord(
                task_id="T-02",
                mapped_req_id="R2",
                title="Implement deterministic reconciliation engine",
                owner="Lan",
                status="IN_PROGRESS",
                logged_deadline=date(2026, 10, 28),  # Intentional conflict with Oct 24
                completion_pct=60.0,
                source_ref="team_tasks.csv#row2",
            ),
        ]
        report = reconcile_requirements_and_tasks(sample_reqs, sample_tasks, req.reference_date)
        return {
            "route": route,
            "status": "RECONCILIATION_COMPLETE",
            "reconciliation_report": report,
        }

    if route == RouteType.EMAIL_FLOW:
        retrieved = workspace_index.search(req.query, top_k=2)
        citations = [f"{c.doc_name} (Page {c.page_number})" for c in retrieved]
        draft = EmailDraftPayload(
            draft_id="draft_001",
            recipient_email=req.recipient_email or "lecturer@hcmus.edu.vn",
            subject="[CSC10014] WorkspaceAI Project Progress Update",
            body=(
                "Dear Instructor,\n\n"
                "Here is our grounded project status update based on our workspace records:\n"
                "- Completed R1 (Problem Boundary & 10 Use Cases).\n"
                "- R2 (Deterministic Algorithms) is currently at 60% completion.\n\n"
                "Best regards,\nWorkspaceAI Team"
            ),
            citations=citations,
        )
        staged = prepare_draft_for_approval(draft)
        draft_store[staged.draft_id] = staged
        return {
            "route": route,
            "status": staged.state,
            "draft": staged,
        }


@app.post("/api/email/approve/{draft_id}")
def approve_email(
    draft_id: str,
    recipient_email: str,
    subject: str,
    body: str,
    user_confirmed: bool = True,
):
    if draft_id not in draft_store:
        raise HTTPException(status_code=404, detail="Draft ID not found.")
    stored = draft_store[draft_id]
    try:
        approved = approve_and_verify_email_send(
            stored_draft=stored,
            approved_recipient=recipient_email,
            approved_subject=subject,
            approved_body=body,
            approved_attachments=stored.attachment_ids,
            user_confirmed=user_confirmed,
        )
        approved.state = EmailState.SENT
        return {
            "status": approved.state,
            "dispatch_mode": settings.email_dispatch_mode,
            "payload_hash": approved.payload_hash,
            "message": f"Email successfully verified and dispatched to {approved.recipient_email}.",
        }
    except (PermissionError, ValueError, RuntimeError, SecurityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
