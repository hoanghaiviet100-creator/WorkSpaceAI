from fastapi import APIRouter, HTTPException
from backend.algorithms.email_state_machine import SecurityError
from backend.services.email_service import email_service

router = APIRouter(prefix="/api/email", tags=["Email Approval"])


@router.post("/approve/{draft_id}")
def approve_email(
    draft_id: str,
    recipient_email: str,
    subject: str,
    body: str,
    user_confirmed: bool = True,
):
    """
    POST /api/email/approve/{draft_id}
    Router endpoint: Receives human approval signal and dispatches email after hash verification.
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
    except (PermissionError, ValueError, RuntimeError, SecurityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# Alias for backward-compatibility and clean route API
approve_email_send = approve_email

