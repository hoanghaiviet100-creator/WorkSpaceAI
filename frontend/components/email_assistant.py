"""
frontend/components/email_assistant.py
Column 3 (Tab 3): Human-in-the-Loop Email Assistant with Cryptographic Verification (Feature 3).
"""
from __future__ import annotations

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


def send_draft(draft_id: str, recipient: str, subject: str, body: str) -> None:
    """Verifies and executes sending of an approved email draft."""
    stored = email_service.draft_repo.get(draft_id)
    if stored and (
        stored.recipient_email != recipient
        or stored.subject != subject
        or stored.body != body
    ):
        stored.recipient_email = recipient
        stored.subject = subject
        stored.body = body
        prepare_draft_for_approval(stored)
        email_service.draft_repo.save(stored)

    result = approve_email(
        draft_id=draft_id,
        recipient_email=recipient,
        subject=subject,
        body=body,
        user_confirmed=True,
    )
    st.session_state["email_sent_result"] = result
    st.session_state["current_draft"] = None
    add_message("assistant", f"Đã gửi email tới {recipient}.")


def render_email_review(scope: str) -> None:
    """Renders the Email Review panel with Human-in-the-Loop approval gate."""
    draft = st.session_state.get("current_draft")
    sent = st.session_state.get("email_sent_result")

    if sent:
        st.success(sent.get("message") or "Email đã được gửi thành công.")
        details = sent.get("details", {})
        if isinstance(details, dict):
            if details.get("sender"):
                st.markdown(f"Người gửi: `{details['sender']}`")
            if details.get("recipient"):
                st.markdown(f"Người nhận: `{details['recipient']}`")
            if details.get("draft_hash"):
                st.caption(f"🔒 SHA-256 Checksum: `{details['draft_hash'][:24]}...`")
        st.button(
            "Soạn thư mới",
            key=f"{scope}_new_mail",
            on_click=clear_sent_email,
            **STRETCH,
        )
        return

    if not draft:
        st.info("Chưa có bản nháp nào đang chờ duyệt.")
        st.markdown(
            "Yêu cầu trợ lý soạn email ở khung chat (ví dụ: *“Soạn email báo cáo tiến độ đồ án”*). "
            "Bản nháp sẽ xuất hiện ở đây để bạn chỉnh sửa và xác nhận gửi."
        )
        st.button(
            "Soạn email báo cáo tiến độ",
            key=f"{scope}_compose",
            icon=":material/edit:",
            on_click=queue_query,
            args=(
                "Soạn email báo cáo tiến độ đồ án WorkspaceAI cho giảng viên",
                "Đang soạn email...",
            ),
            **STRETCH,
        )
        return

    draft_id = extract_draft_attr(draft, "draft_id", "draft_001")
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

    citations = extract_draft_attr(draft, "citations", [])
    if citations:
        with st.expander(f"Căn cứ trích dẫn ({len(citations)})"):
            for c in citations:
                st.markdown(f"- `{c}`")

    draft_hash = extract_draft_attr(draft, "draft_hash", "")
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
            send_draft(draft_id, recipient.strip(), subject.strip(), body)
        except Exception as exc:
            st.error(
                f"Không gửi được email: {exc}. Kiểm tra cấu hình gửi thư rồi thử lại."
            )
        else:
            st.rerun()


@st.dialog("Duyệt email trước khi gửi", width="large")
def email_dialog() -> None:
    render_email_review("dlg")
