"""
backend/api/email_routes.py
FastAPI router for Feature 3: Context-Aware Email Reporting & FSM Send Gate.

Endpoints:
- POST /api/email/draft: Creates draft (DRAFT state)
- POST /api/email/{draft_id}/approve: Approves snapshot, computes SHA-256 (APPROVED state)
- POST /api/email/{draft_id}/send: Dispatches email via mock/SMTP (SENT/FAILED/DELIVERY_UNKNOWN)
- GET  /api/email/audit-log: Queries transmission audit trail (filterable by workspace_id)
- POST /api/email/approve/{draft_id}: Legacy combined approve & send endpoint
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.algorithms.email_state_machine import FSMStateError, SecurityError
from backend.core.schemas import ApproveDraftRequest, CreateDraftRequest
from backend.services.email_service import email_service

class GenerateEmailRequest(BaseModel):
    prompt: str

router = APIRouter(prefix="/api/email", tags=["Email Reporting & FSM Send Gate"])

@router.post("/generate")
def generate_email_endpoint(prompt: Optional[str] = None, req: Optional[GenerateEmailRequest] = None):
    """Generate an email subject and body from a free-form user prompt.
    Creates a real draft record in the FSM repo so it can be approved and sent.
    Accepts prompt via query param or JSON body {prompt: ...}."""
    effective_prompt = (req.prompt if req else None) or prompt or ""
    if not effective_prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")
    try:
        from backend.providers.llm_provider import llm_provider
        from backend.algorithms.email_state_machine import prepare_draft_for_approval
        from backend.core.schemas import EmailDraftPayload
        subject, body = llm_provider.generate_email_draft(effective_prompt, [])
        # Create a real draft record so approve+send flow works
        draft_payload = EmailDraftPayload(
            draft_id="draft_001",
            recipient_email="",
            subject=subject,
            body=body,
            citations=[],
        )
        staged = prepare_draft_for_approval(draft_payload)
        email_service.draft_repo.save(staged)
        assigned_id = str(getattr(staged, "id", None) or getattr(staged, "draft_id", "draft_001"))
        return {
            "subject": subject,
            "body": body,
            "draft_id": assigned_id,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/draft")
def create_draft_endpoint(req: CreateDraftRequest):
    """
    POST /api/email/draft
    Creates a new email draft in DRAFT state. Validates recipient format per RFC-5322.
    """
    try:
        return email_service.create_draft(
            workspace_id=req.workspace_id,
            recipients=req.recipients,
            subject=req.subject,
            body=req.body,
            citations=req.citations,
            attachments=req.attachments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{draft_id}/approve")
def approve_snapshot_endpoint(
    draft_id: str,
    req: Optional[ApproveDraftRequest] = None,
    recipients: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    user_confirmed: bool = True,
):
    """
    POST /api/email/{draft_id}/approve
    UC-08: Review and Approve Email Snapshot.
    Locks in canonical SHA-256 digest and transitions draft state to APPROVED.
    """
    try:
        target_recipients = (req.recipients if req and req.recipients is not None else recipients)
        target_subject = (req.subject if req and req.subject is not None else subject)
        target_body = (req.body if req and req.body is not None else body)
        target_attachments = (req.attachments if req and req.attachments is not None else None)
        target_confirmed = (req.user_confirmed if req is not None else user_confirmed)

        return email_service.approve_draft_snapshot(
            draft_id=draft_id,
            recipients=target_recipients,
            subject=target_subject,
            body=target_body,
            attachments=target_attachments,
            user_confirmed=target_confirmed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{draft_id}/send")
def send_email_endpoint(draft_id: str):
    """
    POST /api/email/{draft_id}/send
    UC-09: Send Email and Track Outcome.
    Enforces that state is APPROVED and SHA-256 digest matches. Prevents duplicate sends.
    Transmits via SMTP and records SENT, FAILED, or DELIVERY_UNKNOWN.
    """
    try:
        return email_service.dispatch_email(draft_id=draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (FSMStateError, SecurityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/audit-log")
def get_audit_log_endpoint(workspace_id: Optional[str] = None):
    """
    GET /api/email/audit-log?workspace_id=...
    Retrieves transmission audit trail with snapshot hashes, timestamps, and delivery states.
    """
    if workspace_id:
        return email_service.draft_repo.list_by_workspace(workspace_id)
    return email_service.draft_repo.list_all()


@router.post("/approve/{draft_id}")
def approve_email(
    draft_id: str,
    recipient_email: str,
    subject: str,
    body: str,
    attachments: Optional[list[str]] = None,
    user_confirmed: bool = True,
):
    """
    Legacy POST /api/email/approve/{draft_id}
    Maintained for backward compatibility: coordinates snapshot approval and dispatch.
    """
    try:
        return email_service.approve_and_send(
            draft_id=draft_id,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
            attachments=attachments,
            user_confirmed=user_confirmed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (PermissionError, ValueError, RuntimeError, SecurityError, FSMStateError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# Export alias
approve_email_send = approve_email
