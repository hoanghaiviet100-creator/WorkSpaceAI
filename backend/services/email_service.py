"""
backend/services/email_service.py
CSC10014 Feature 3: Context-Aware Email Reporting Service.

Encapsulates draft creation, cryptographic snapshot approval, and controlled SMTP dispatch.
Adheres strictly to the 5 FSM states:
- DRAFT
- APPROVED
- SENT
- FAILED
- DELIVERY_UNKNOWN

Guarantees NFR-04:
- Tamper-proof SHA-256 payload binding (recipients, subject, body).
- Duplicate-send prevention.
- Single dispatch per approved digest.
- No automatic retries on DELIVERY_UNKNOWN (socket.timeout / SMTPServerDisconnected).
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re
import smtplib
import socket
from typing import Any, Dict, List, Optional, Union
import uuid
from uuid import UUID

from backend.algorithms.email_state_machine import (
    APPROVED,
    DELIVERY_UNKNOWN,
    DRAFT,
    FAILED,
    SENT,
    FSMStateError,
    SecurityError,
    _normalize_recipients,
    approve_and_verify_email_send,
    approve_snapshot,
    compute_draft_hash,
    prepare_draft_for_approval,
    validate_rfc5322_email,
    verify_and_lock_for_send,
)
from backend.core.config import settings
from backend.core.guardrails import validate_email_address
from backend.core.schemas import (
    EmailDraftPayload,
    EmailDraftRecord,
    EmailFSMState,
    EmailState,
    RouteType,
    UserRequest,
)
from backend.providers.llm_provider import LLMProvider, llm_provider
from backend.repositories.draft_repository import DraftRepository, draft_repository
from backend.repositories.workspace_repository import WorkspaceRepository, workspace_repository


def send_real_email_via_smtp(to_email: str, subject: str, body_text: str) -> Dict[str, Any]:
    """
    Sends real email via Gmail SMTP using Python standard libraries (smtplib & MIMEText).
    Connects to smtp.gmail.com:587 with STARTTLS authentication.
    """
    sender = settings.gmail_sender_email.strip()
    password = settings.gmail_app_password.strip().replace(" ", "")

    if not sender:
        raise ValueError(
            "Chưa cấu hình tài khoản gửi! Vui lòng điền GMAIL_SENDER_EMAIL trong file .env."
        )
    if not password:
        raise ValueError(
            "Chưa cấu hình mật khẩu ứng dụng Gmail (16 ký tự)! Vui lòng điền GMAIL_APP_PASSWORD trong file .env."
        )

    clean_recipient = to_email.strip()
    if not validate_email_address(clean_recipient):
        raise ValueError(f"Địa chỉ email người nhận không hợp lệ theo chuẩn RFC-5322: '{clean_recipient}'")

    # Construct standard multipart MIME message for robust UTF-8 encoding
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = clean_recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    host = settings.smtp_host or "smtp.gmail.com"
    port = settings.smtp_port or 587

    # Connect to Gmail SMTP server
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender, password)
        server.sendmail(sender, [clean_recipient], msg.as_string())

    return {
        "status": "SENT",
        "sender": sender,
        "recipient": clean_recipient,
        "smtp_server": f"{host}:{port}",
    }


class EmailService:
    """Nghiệp vụ nháp email & máy trạng thái duyệt gửi (Context-Aware Email Service)."""

    def __init__(
        self,
        draft_repo: Optional[DraftRepository] = None,
        workspace_repo: Optional[WorkspaceRepository] = None,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        self.draft_repo = draft_repo or draft_repository
        self.workspace_repo = workspace_repo or workspace_repository
        self.provider = provider or llm_provider

    def create_draft(
        self,
        workspace_id: Optional[Union[UserRequest, UUID, str]] = None,
        recipients: Optional[Union[List[str], str]] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        citations: Optional[List[str]] = None,
        req: Optional[UserRequest] = None,
    ) -> Union[EmailDraftRecord, Dict[str, Any]]:
        """
        Creates an email draft in DRAFT state.
        Supports both:
        1. Context-aware generation from UserRequest (backward compatibility for /api/chat).
        2. Direct manual composition with (workspace_id, recipients, subject, body, citations).
        """
        user_req = workspace_id if isinstance(workspace_id, UserRequest) else req
        if user_req is not None:
            recipient = user_req.recipient_email
            if not recipient:
                extracted = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", user_req.query)
                recipient = extracted[0] if extracted else "an.nguyen@hcmus.edu.vn"

            retrieved = self.workspace_repo.search(user_req.query, top_k=2)
            found_citations = [f"{c.doc_name} (Page {c.page_number})" for c in retrieved]

            gen_subject, gen_body = self.provider.generate_email_draft(
                query=user_req.query,
                chunks=retrieved,
                recipient_email=recipient,
            )

            draft_payload = EmailDraftPayload(
                draft_id="draft_001",
                recipient_email=recipient,
                subject=gen_subject,
                body=gen_body,
                citations=found_citations,
            )
            staged = prepare_draft_for_approval(draft_payload)
            self.draft_repo.save(staged)
            return {
                "route": RouteType.EMAIL_FLOW,
                "status": staged.state,
                "draft": staged,
            }

        # Feature 3 Direct Specification: (workspace_id, recipients, subject, body, citations)
        if isinstance(workspace_id, str):
            try:
                ws_uuid = UUID(workspace_id)
            except ValueError:
                # Deterministic uuid from name or fallback
                ws_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, workspace_id)
        elif isinstance(workspace_id, UUID):
            ws_uuid = workspace_id
        else:
            ws_uuid = uuid.uuid4()

        if not subject or not subject.strip():
            raise ValueError("Email subject cannot be empty.")

        norm_recipients = _normalize_recipients(recipients)
        if not norm_recipients:
            raise ValueError("Email recipients cannot be empty.")

        for r in norm_recipients.split(","):
            if not validate_rfc5322_email(r):
                raise ValueError(f"Invalid RFC-5322 recipient email address: '{r}'")

        new_draft = EmailDraftRecord(
            id=uuid.uuid4(),
            workspace_id=ws_uuid,
            recipients=recipients or norm_recipients,
            subject=subject.strip(),
            body=(body or "").strip(),
            fsm_state=EmailFSMState.DRAFT,
            sha256_digest=None,
            audit_timestamp=datetime.now(timezone.utc),
            citations=citations or [],
        )
        self.draft_repo.save(new_draft)
        return new_draft

    def approve_draft_snapshot(
        self,
        draft_id: Union[UUID, str],
        recipients: Optional[Union[List[str], str]] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        user_confirmed: bool = True,
    ) -> EmailDraftRecord:
        """
        UC-08: Review and Approve Email Snapshot.
        Validates payload, enforces explicit human confirmation, transitions to APPROVED,
        computes and binds the canonical SHA-256 digest, and updates audit timestamp.
        """
        stored = self.draft_repo.get(draft_id)
        if stored is None:
            raise KeyError(f"Draft with ID '{draft_id}' not found.")

        # Fall back to existing draft content if not overridden
        final_recipients = (
            recipients
            if recipients is not None
            else (getattr(stored, "recipients", None) or getattr(stored, "recipient_email", ""))
        )
        final_subject = subject if subject is not None else getattr(stored, "subject", "")
        final_body = body if body is not None else getattr(stored, "body", "")

        state, digest = approve_snapshot(
            recipients=final_recipients,
            subject=final_subject,
            body=final_body,
            user_confirmed=user_confirmed,
        )

        # Update fields conditionally based on model type (EmailDraftRecord vs legacy EmailDraftPayload)
        if hasattr(stored, "recipients"):
            stored.recipients = final_recipients
        if hasattr(stored, "recipient_email"):
            stored.recipient_email = str(final_recipients)
        if hasattr(stored, "subject"):
            stored.subject = final_subject
        if hasattr(stored, "body"):
            stored.body = final_body
        if hasattr(stored, "fsm_state"):
            stored.fsm_state = EmailFSMState.APPROVED
        if hasattr(stored, "sha256_digest"):
            stored.sha256_digest = digest
        if hasattr(stored, "state"):
            stored.state = EmailState.APPROVED
        if hasattr(stored, "payload_hash"):
            stored.payload_hash = digest
        if hasattr(stored, "audit_timestamp"):
            stored.audit_timestamp = datetime.now(timezone.utc)

        self.draft_repo.save(stored)
        return stored

    def _set_draft_state(self, stored: Any, fsm_state: EmailFSMState) -> str:
        """Safely updates state and audit timestamp across EmailDraftRecord and EmailDraftPayload."""
        now_ts = datetime.now(timezone.utc)
        if hasattr(stored, "fsm_state"):
            stored.fsm_state = fsm_state
        if hasattr(stored, "state"):
            if fsm_state == EmailFSMState.SENT:
                stored.state = EmailState.SENT
            elif fsm_state == EmailFSMState.APPROVED:
                stored.state = EmailState.APPROVED
            elif fsm_state in (EmailFSMState.FAILED, EmailFSMState.DELIVERY_UNKNOWN):
                stored.state = EmailState.FAILED_RETRYABLE
            else:
                stored.state = EmailState.PENDING_APPROVAL
        if hasattr(stored, "audit_timestamp"):
            stored.audit_timestamp = now_ts
        return now_ts.isoformat()

    def dispatch_email(self, draft_id: Union[UUID, str]) -> Dict[str, Any]:
        """
        UC-09: Send Email and Track Outcome.
        Pre-dispatch gate:
        - Checks FSM state == APPROVED
        - Blocks duplicate dispatch (state == SENT)
        - Verifies SHA-256 integrity digest against current payload

        Dispatches via mock mode or authenticated Gmail SMTP STARTTLS (port 587).
        Persists outcome to FSM:
        - SENT: accepted by relay
        - FAILED: SMTPAuthenticationError or general error
        - DELIVERY_UNKNOWN: timeout/disconnect (no auto-retry)
        """
        stored = self.draft_repo.get(draft_id)
        if stored is None:
            raise KeyError(f"Draft with ID '{draft_id}' not found.")

        current_state = getattr(stored, "fsm_state", None) or getattr(stored, "state", "")
        expected_digest = getattr(stored, "sha256_digest", None) or getattr(stored, "payload_hash", "")
        recipients = getattr(stored, "recipients", None) or getattr(stored, "recipient_email", "")
        subject = getattr(stored, "subject", "")
        body = getattr(stored, "body", "")

        # Verify integrity and duplicate-send gate (raises SecurityError or FSMStateError)
        verify_and_lock_for_send(
            current_state=current_state,
            expected_digest=expected_digest,
            recipients=recipients,
            subject=subject,
            body=body,
        )

        # 1. Mock Send Mode
        if settings.email_dispatch_mode != "gmail_real":
            ts_str = self._set_draft_state(stored, EmailFSMState.SENT)
            self.draft_repo.save(stored)
            return {
                "status": EmailFSMState.SENT.value,
                "fsm_state": EmailFSMState.SENT.value,
                "draft_id": str(draft_id),
                "dispatch_mode": "local_mock",
                "sha256_digest": expected_digest,
                "audit_timestamp": ts_str,
                "message": f"Email dispatched successfully (Local Mock Mode) to {recipients}.",
            }

        # 2. Real Gmail SMTP (STARTTLS, port 587)
        sender = settings.gmail_sender_email.strip()
        password = settings.gmail_app_password.strip().replace(" ", "")
        if not sender or not password:
            ts_str = self._set_draft_state(stored, EmailFSMState.FAILED)
            self.draft_repo.save(stored)
            return {
                "status": EmailFSMState.FAILED.value,
                "draft_id": str(draft_id),
                "error": "Gmail sender email or app password is not configured in environment.",
                "audit_timestamp": ts_str,
            }

        norm_r = _normalize_recipients(recipients)
        to_addrs = [r.strip() for r in norm_r.split(",") if r.strip()]

        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = ", ".join(to_addrs)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        host = settings.smtp_host or "smtp.gmail.com"
        port = settings.smtp_port or 587

        try:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender, password)
                server.sendmail(sender, to_addrs, msg.as_string())

            ts_str = self._set_draft_state(stored, EmailFSMState.SENT)
            self.draft_repo.save(stored)
            return {
                "status": EmailFSMState.SENT.value,
                "fsm_state": EmailFSMState.SENT.value,
                "draft_id": str(draft_id),
                "dispatch_mode": "gmail_real",
                "sha256_digest": expected_digest,
                "audit_timestamp": ts_str,
                "message": f"Email sent successfully via Gmail SMTP to {to_addrs}!",
            }
        except smtplib.SMTPAuthenticationError as exc:
            ts_str = self._set_draft_state(stored, EmailFSMState.FAILED)
            self.draft_repo.save(stored)
            return {
                "status": EmailFSMState.FAILED.value,
                "draft_id": str(draft_id),
                "error": f"SMTP Authentication Error: {str(exc)}",
                "audit_timestamp": ts_str,
            }
        except (socket.timeout, smtplib.SMTPServerDisconnected) as exc:
            # CRITICAL NFR-04: Mark DELIVERY_UNKNOWN without auto-retries
            ts_str = self._set_draft_state(stored, EmailFSMState.DELIVERY_UNKNOWN)
            self.draft_repo.save(stored)
            return {
                "status": EmailFSMState.DELIVERY_UNKNOWN.value,
                "draft_id": str(draft_id),
                "error": f"SMTP timeout or server disconnected. State marked DELIVERY_UNKNOWN. Automatic retries prohibited: {str(exc)}",
                "audit_timestamp": ts_str,
            }
        except Exception as exc:
            ts_str = self._set_draft_state(stored, EmailFSMState.FAILED)
            self.draft_repo.save(stored)
            return {
                "status": EmailFSMState.FAILED.value,
                "draft_id": str(draft_id),
                "error": f"SMTP delivery failure: {str(exc)}",
                "audit_timestamp": ts_str,
            }

    def approve_and_send(
        self,
        draft_id: str,
        recipient_email: str,
        subject: str,
        body: str,
        user_confirmed: bool = True,
    ) -> Dict[str, Any]:
        """
        Backward-compatibility convenience method:
        Approves draft snapshot and dispatches in one coordinated invocation.
        """
        self.approve_draft_snapshot(
            draft_id=draft_id,
            recipients=recipient_email,
            subject=subject,
            body=body,
            user_confirmed=user_confirmed,
        )
        return self.dispatch_email(draft_id=draft_id)


# Singleton instance
email_service = EmailService()


def handle_email_draft_request(req: UserRequest) -> Dict[str, Any]:
    return email_service.create_draft(req)


def handle_email_approve_request(
    draft_id: str,
    recipient_email: str,
    subject: str,
    body: str,
    user_confirmed: bool = True,
) -> Dict[str, Any]:
    return email_service.approve_and_send(
        draft_id=draft_id,
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        user_confirmed=user_confirmed,
    )
