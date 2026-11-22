"""
frontend/components/email_assistant.py
Column 3 (Tab 3): Human-in-the-Loop Email Assistant with Cryptographic Verification (Feature 3).
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Optional

import streamlit as st
from backend.algorithms.email_state_machine import prepare_draft_for_approval
from backend.api.email_routes import approve_email
from backend.core.config import settings
from backend.services.email_service import email_service
from frontend.state import (
    EMAIL_RE,
    STRETCH,
    add_message,
    clear_sent_email,
    extract_draft_attr,
    queue_query,
)

ATTACHMENTS_DIR = Path(".workspace_data/email_attachments")
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


def send_draft(
    draft_id: str,
    recipient: str,
    subject: str,
    body: str,
    attachments: Optional[List[str]] = None,
) -> None:
    """Verifies and executes sending of an approved email draft."""
    from backend.algorithms.email_state_machine import prepare_draft_for_approval
    from backend.core.schemas import EmailDraftPayload

    stored = email_service.draft_repo.get(draft_id)

    if stored is None:
        # Draft not in repo (e.g. generated via /api/email/generate without saving,
        # or draft_id is a fake "generated_xxx"). Create a new real record now.
        draft_payload = EmailDraftPayload(
            draft_id="draft_001",
            recipient_email=recipient,
            subject=subject,
            body=body,
            citations=[],
            attachments=attachments or [],
        )
        staged = prepare_draft_for_approval(draft_payload)
        email_service.draft_repo.save(staged)
        real_draft_id = str(getattr(staged, "id", None) or getattr(staged, "draft_id", "draft_001"))
    else:
        # Update existing draft if anything changed
        if (
            stored.recipient_email != recipient
            or stored.subject != subject
            or stored.body != body
            or (attachments is not None and getattr(stored, "attachments", None) != attachments)
        ):
            stored.recipient_email = recipient
            stored.subject = subject
            stored.body = body
            if hasattr(stored, "attachments"):
                stored.attachments = attachments or []
            if hasattr(stored, "attachment_ids"):
                stored.attachment_ids = attachments or []
            prepare_draft_for_approval(stored)
            email_service.draft_repo.save(stored)
        real_draft_id = draft_id

    result = approve_email(
        draft_id=real_draft_id,
        recipient_email=recipient,
        subject=subject,
        body=body,
        attachments=attachments,
        user_confirmed=True,
    )
    st.session_state["email_sent_result"] = result
    if result.get("status") == "SENT":
        st.session_state["current_draft"] = None
        add_message("assistant", f"Đã gửi email thành công tới {recipient}.")
    else:
        # Keep current_draft so user can retry without re-typing or re-uploading
        add_message("assistant", f"Gửi email tới {recipient} thất bại: {result.get('error', 'Lỗi không xác định')}")


def render_email_review(scope: str) -> None:
    """Renders the Email Review panel with Human-in-the-Loop approval gate."""
    draft = st.session_state.get("current_draft")
    sent = st.session_state.get("email_sent_result")

    if sent:
        is_sent = sent.get("status") == "SENT" or sent.get("fsm_state") == "SENT"
        if is_sent:
            st.success(sent.get("message") or "Email đã được gửi thành công qua Gmail SMTP!")
        else:
            st.error(sent.get("error") or sent.get("message") or "Gửi email thất bại.")

        sender = sent.get("sender") or (sent.get("details", {}) if isinstance(sent.get("details"), dict) else {}).get("sender")
        recipient = sent.get("recipient") or (sent.get("details", {}) if isinstance(sent.get("details"), dict) else {}).get("recipient")
        digest = sent.get("sha256_digest") or (sent.get("details", {}) if isinstance(sent.get("details"), dict) else {}).get("draft_hash")
        sent_attachments = sent.get("attachments") or (sent.get("details", {}) if isinstance(sent.get("details"), dict) else {}).get("attachments") or []

        if sender:
            st.markdown(f"**Người gửi:** `{sender}`")
        if recipient:
            st.markdown(f"**Người nhận:** `{recipient}`")
        if sent_attachments:
            st.markdown(f"**📎 Tệp đính kèm ({len(sent_attachments)}):**")
            for a in sent_attachments:
                st.markdown(f"- 📄 `{os.path.basename(a)}`")
        if digest:
            st.caption(f"🔒 SHA-256 Checksum: `{digest[:24]}...`")

        if not is_sent:
            col_retry, col_new = st.columns(2)
            if col_retry.button("🔄 Thử gửi lại ngay", key=f"{scope}_retry_mail", type="primary", **STRETCH):
                st.session_state["email_sent_result"] = None
                st.rerun()
            col_new.button(
                "Soạn thư mới",
                key=f"{scope}_new_mail",
                on_click=clear_sent_email,
                **STRETCH,
            )
        else:
            st.button(
                "Soạn thư mới",
                key=f"{scope}_new_mail",
                on_click=clear_sent_email,
                **STRETCH,
            )
        return

    if not draft:
        st.info("Chưa có bản nháp nào đang chờ duyệt.")
        # Prompt for AI generation
        prompt = st.text_input("Yêu cầu tạo email (prompt)", value="", key=f"{scope}_prompt")
        if st.button("Tạo email bằng AI", key=f"{scope}_gen", **STRETCH):
            if not prompt.strip():
                st.error("Vui lòng nhập yêu cầu (prompt) để tạo email.")
            else:
                try:
                    import httpx
                    resp = httpx.post("http://localhost:8000/api/email/generate", params={"prompt": prompt.strip()}, timeout=30.0)
                    resp.raise_for_status()
                    data = resp.json()
                    # Store generated draft – use real draft_id from server so approve+send works
                    st.session_state["current_draft"] = {
                        "draft_id": data.get("draft_id", "draft_001"),
                        "recipient_email": "",
                        "subject": data.get("subject", ""),
                        "body": data.get("body", ""),
                        "attachments": [],
                        "citations": [],
                    }
                    st.rerun()
                except Exception as exc:
                    st.error(f"Không tạo được email: {exc}")
        return


    draft_id = str(extract_draft_attr(draft, "draft_id", "") or extract_draft_attr(draft, "id", "draft_001"))
    default_to = extract_draft_attr(
        draft, "recipient_email", st.session_state.get("recipient_email", "")
    )
    sender = settings.gmail_sender_email or "Gmail (chế độ mô phỏng an toàn)"
    st.caption(f"Người gửi: {sender}")

    k = f"{scope}_{draft_id}"
    recipient = st.text_input("Người nhận", value=default_to, key=f"{k}_to")
    subject = st.text_input(
        "Tiêu đề", value=extract_draft_attr(draft, "subject", ""), key=f"{k}_subject"
    )
    body = st.text_area(
        "Nội dung",
        value=extract_draft_attr(draft, "body", ""),
        height=220,
        key=f"{k}_body",
    )

    # Attachments handling
    existing_attachments = extract_draft_attr(draft, "attachments", []) or []
    uploaded_files = st.file_uploader(
        "Tệp đính kèm (tùy chọn)",
        accept_multiple_files=True,
        key=f"{k}_files",
        help="Tải lên tệp tin bất kỳ để gửi kèm theo email.",
    )

    final_attachments: List[str] = list(existing_attachments)
    if uploaded_files:
        for uf in uploaded_files:
            file_dest = ATTACHMENTS_DIR / uf.name
            with open(file_dest, "wb") as f:
                f.write(uf.getbuffer())
            dest_str = str(file_dest.resolve())
            if dest_str not in final_attachments:
                final_attachments.append(dest_str)

        # Persist attachments to current_draft in session state so they don't disappear
        if isinstance(draft, dict):
            draft["attachments"] = final_attachments
        elif hasattr(draft, "attachments"):
            draft.attachments = final_attachments

    if final_attachments:
        st.markdown(f"**📎 Tệp đính kèm sẵn sàng gửi ({len(final_attachments)}):**")
        for att_path in final_attachments:
            size_b = os.path.getsize(att_path) if os.path.exists(att_path) else 0
            st.info(f"📄 **`{os.path.basename(att_path)}`** ({size_b / 1024:.1f} KB)")

    citations = extract_draft_attr(draft, "citations", [])
    if citations:
        with st.expander(f"Căn cứ trích dẫn ({len(citations)})"):
            for c in citations:
                st.markdown(f"- `{c}`")

    draft_hash = extract_draft_attr(draft, "draft_hash", "") or extract_draft_attr(draft, "sha256_digest", "")
    if draft_hash:
        st.caption(f"🔒 Khóa toàn vẹn SHA-256: `{draft_hash[:24]}...`")

    errors = []
    if not EMAIL_RE.match(recipient.strip()):
        errors.append("Địa chỉ email người nhận chưa hợp lệ.")
    if not subject.strip():
        errors.append("Tiêu đề đang trống.")
    if not body.strip():
        errors.append("Nội dung đang trống.")
    for e in errors:
        st.error(e)

    if st.button(
        f"Gửi tới {recipient.strip() or '…'}",
        key=f"{k}_send",
        type="primary",
        icon=":material/send:",
        disabled=bool(errors),
        **STRETCH,
    ):
        try:
            send_draft(draft_id, recipient.strip(), subject.strip(), body, attachments=final_attachments)
        except Exception as exc:
            st.error(
                f"Không gửi được email: {exc}. Kiểm tra cấu hình gửi thư rồi thử lại."
            )
        else:
            st.rerun()


@st.dialog("Duyệt email trước khi gửi", width="large")
def email_dialog() -> None:
    render_email_review("dlg")
