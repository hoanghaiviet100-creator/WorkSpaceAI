import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from backend.algorithms.email_state_machine import (
    approve_and_verify_email_send,
    prepare_draft_for_approval,
)
from backend.core.config import settings
from backend.core.guardrails import validate_email_address
from backend.core.schemas import EmailDraftPayload, EmailState, RouteType, UserRequest
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

    def create_draft(self, req: UserRequest) -> Dict[str, Any]:
        """
        Creates a context-aware email draft based on user free-form query and workspace data,
        stages it, and locks in the SHA-256 hash.
        """
        recipient = req.recipient_email
        if not recipient:
            extracted = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", req.query)
            recipient = extracted[0] if extracted else "an.nguyen@hcmus.edu.vn"

        # Retrieve relevant chunks from workspace documents
        retrieved = self.workspace_repo.search(req.query, top_k=2)
        citations = [f"{c.doc_name} (Page {c.page_number})" for c in retrieved]

        # Use LLMProvider to generate dynamic Subject and Body according to user topic
        subject, body = self.provider.generate_email_draft(
            query=req.query,
            chunks=retrieved,
            recipient_email=recipient,
        )

        draft = EmailDraftPayload(
            draft_id="draft_001",
            recipient_email=recipient,
            subject=subject,
            body=body,
            citations=citations,
        )
        staged = prepare_draft_for_approval(draft)
        self.draft_repo.save(staged)
        return {
            "route": RouteType.EMAIL_FLOW,
            "status": staged.state,
            "draft": staged,
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
        Verifies draft approval against the stored hash and dispatches email (Real SMTP or Mock).
        Advances state to SENT on success.
        """
        stored = self.draft_repo.get(draft_id)
        if stored is None:
            raise KeyError(f"Draft ID '{draft_id}' not found.")

        # Verify FSM transition & SHA-256 integrity hash
        approved = approve_and_verify_email_send(
            stored_draft=stored,
            approved_recipient=recipient_email,
            approved_subject=subject,
            approved_body=body,
            approved_attachments=stored.attachment_ids,
            user_confirmed=user_confirmed,
        )

        dispatch_details: Dict[str, Any] = {}

        if settings.email_dispatch_mode == "gmail_real":
            try:
                dispatch_details = send_real_email_via_smtp(
                    to_email=recipient_email,
                    subject=subject,
                    body_text=body,
                )
                approved.state = EmailState.SENT
                self.draft_repo.save(approved)
                message = f"Email thật đã được gửi thành công qua Gmail đến {approved.recipient_email}!"
            except smtplib.SMTPAuthenticationError as exc:
                approved.state = EmailState.FAILED_RETRYABLE
                self.draft_repo.save(approved)
                error_detail = (
                    exc.smtp_error.decode("utf-8", errors="ignore")
                    if hasattr(exc, "smtp_error") and isinstance(exc.smtp_error, bytes)
                    else str(exc)
                )
                raise RuntimeError(
                    f"Xác thực Gmail thất bại (SMTP Authentication Error): Vui lòng kiểm tra lại GMAIL_SENDER_EMAIL "
                    f"và GMAIL_APP_PASSWORD (mật khẩu ứng dụng 16 ký tự). Chi tiết từ Gmail: {error_detail}"
                )
            except Exception as exc:
                approved.state = EmailState.FAILED_RETRYABLE
                self.draft_repo.save(approved)
                raise RuntimeError(f"Lỗi khi gửi email qua Gmail SMTP: {str(exc)}")
        else:
            # local_mock dispatch mode
            approved.state = EmailState.SENT
            self.draft_repo.save(approved)
            message = f"Email đã được phê duyệt và gửi thành công (Chế độ Local Mock) đến {approved.recipient_email}."
            dispatch_details = {"mode": "local_mock", "recipient": approved.recipient_email}

        return {
            "status": approved.state,
            "dispatch_mode": settings.email_dispatch_mode,
            "payload_hash": approved.payload_hash,
            "message": message,
            "details": dispatch_details,
        }


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
