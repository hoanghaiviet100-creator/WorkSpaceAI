"""
backend/api/email_routes.py
FastAPI router for Feature 3: Context-Aware Email Reporting & FSM Send Gate.

Endpoints:
- POST /api/email/draft: Creates draft (DRAFT state)
- POST /api/email/{draft_id}/approve: Approves snapshot, computes SHA-256 (APPROVED state)
- POST /api/email/{draft_id}/send: Dispatches email via mock/SMTP (SENT/FAILED/DELIVERY_UNKNOWN)
- GET  /api/email/audit-log: Queries transmission audit trail (PII-redacted, filterable by workspace_id)
- POST /api/email/approve/{draft_id}: Legacy combined approve & send endpoint
"""
from __future__ import annotations

import smtplib
import socket
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, HTTPException

from backend.algorithms.email_state_machine import FSMStateError, SecurityError
from backend.core.schemas import ApproveDraftRequest, CreateDraftRequest, EmailDraftRecord
from backend.services.email_service import email_service

router = APIRouter(prefix="/api/email", tags=["Email Reporting & FSM Send Gate"])


@router.post("/draft", response_model=Union[EmailDraftRecord, Dict[str, Any]])
def create_draft_endpoint(req: CreateDraftRequest) -> Union[EmailDraftRecord, Dict[str, Any]]:
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{draft_id}/approve", response_model=EmailDraftRecord)
def approve_snapshot_endpoint(
    draft_id: str,
    req: Optional[ApproveDraftRequest] = None,
    recipients: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    user_confirmed: bool = True,
) -> EmailDraftRecord:
    """
    POST /api/email/{draft_id}/approve
    UC-08: Review and Approve Email Snapshot.
    Locks in canonical SHA-256 digest and transitions draft state to APPROVED.
    """
    try:
        target_recipients = (req.recipients if req and req.recipients is not None else recipients)
        target_subject = (req.subject if req and req.subject is not None else subject)
        target_body = (req.body if req and req.body is not None else body)
        target_confirmed = (req.user_confirmed if req is not None else user_confirmed)

        return email_service.approve_draft_snapshot(
            draft_id=draft_id,
            recipients=target_recipients,
            subject=target_subject,
            body=target_body,
            user_confirmed=target_confirmed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{draft_id}/send", response_model=Dict[str, Any])
def send_email_endpoint(draft_id: str) -> Dict[str, Any]:
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
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPException, socket.timeout, TimeoutError, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/audit-log", response_model=List[Dict[str, Any]])
def get_audit_log_endpoint(workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    GET /api/email/audit-log?workspace_id=...
    Retrieves transmission audit trail with snapshot hashes, timestamps, and delivery states.
    PII-protected: Excludes plaintext recipient email addresses and body content.
    """
    if workspace_id:
        records = email_service.draft_repo.list_by_workspace(workspace_id)
    else:
        records = email_service.draft_repo.list_all()

    sanitized: List[Dict[str, Any]] = []
    for r in records:
        entry = {
            "id": getattr(r, "id", None) or getattr(r, "draft_id", ""),
            "draft_id": str(getattr(r, "id", None) or getattr(r, "draft_id", "")),
            "workspace_id": getattr(r, "workspace_id", None),
            "fsm_state": getattr(r, "fsm_state", None) or getattr(r, "state", ""),
            "state": getattr(r, "fsm_state", None) or getattr(r, "state", ""),
            "sha256_digest": getattr(r, "sha256_digest", None) or getattr(r, "payload_hash", None),
            "audit_timestamp": getattr(r, "audit_timestamp", None),
        }
        sanitized.append(entry)
    return sanitized


@router.post("/approve/{draft_id}", response_model=Dict[str, Any])
def approve_email(
    draft_id: str,
    recipient_email: str,
    subject: str,
    body: str,
    user_confirmed: bool = True,
) -> Dict[str, Any]:
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
            user_confirmed=user_confirmed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (PermissionError, ValueError, RuntimeError, SecurityError, FSMStateError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# Export alias
approve_email_send = approve_email
