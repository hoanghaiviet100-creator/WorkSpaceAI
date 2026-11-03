"""
frontend/components/chat_panel.py
Column 2: Conversational Q&A Panel with Clickable Citations and Hallucination Indicators.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
from backend.api.chat_routes import handle_user_request
from backend.core.schemas import EmailState, RouteType, UserRequest
from backend.repositories.workspace_repository import workspace_repository
from backend.services.reconciliation_service import reconciliation_service
from frontend.components.email_assistant import email_dialog
from frontend.state import (
    RECON_STATE_LABEL,
    RECON_STATE_PRIORITY,
    STRETCH,
    add_message,
    esc,
    is_route,
    queue_query,
    reset_chat,
)


def tag(text: str, state: str = "done") -> None:
    st.markdown(
        f'<span class="state t-{state}">{esc(text)}</span>', unsafe_allow_html=True
    )


def render_reconciliation(summary: Any) -> None:
    if not summary:
        return
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Độ bao phủ yêu cầu",
        f"{summary.coverage_ratio * 100:.0f}%",
        help="Tỷ lệ yêu cầu của đề bài đã có công việc tương ứng.",
    )
    c2.metric("Việc trễ hạn", summary.overdue_count)
    c3.metric("Xung đột ngày", summary.conflict_count)

    def state_key(item: Any) -> str:
        return str(getattr(item.state, "value", item.state))

    items = sorted(
        summary.item_reports, key=lambda i: RECON_STATE_PRIORITY.get(state_key(i), 9)
    )
    rows = [
        {
            "Mã": it.req_id,
            "Nội dung": it.title,
            "Trạng thái": RECON_STATE_LABEL.get(state_key(it), state_key(it)),
            "Rủi ro": it.risk_level,
            "Tiến độ": float(it.avg_completion),
            "Hạn còn lại": f"{it.days_remaining} ngày"
            if it.days_remaining is not None
            else "—",
            "Người làm": ", ".join(it.owners) if it.owners else "Chưa có",
        }
        for it in items
    ]
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            "Tiến độ": st.column_config.ProgressColumn(
                "Tiến độ", min_value=0, max_value=100, format="%d%%"
            )
        },
        **STRETCH,
    )
    conflicts = [it for it in items if it.date_conflicts]
    if conflicts:
        with st.expander(f"Xung đột ngày ({len(conflicts)} yêu cầu)", expanded=True):
            for it in conflicts:
                for c in it.date_conflicts:
                    st.markdown(
                        f"- **{it.req_id}**: {c.doc_a} ghi {c.date_a}, {c.doc_b} ghi {c.date_b}"
                    )


def render_structured(
    data: Dict[str, Any], idx: int, last_email_idx: Optional[int]
) -> None:
    route, status = data.get("route"), data.get("status")

    if status == "SUMMARY_GENERATED":
        tag(f"Tóm tắt từ {data.get('doc_name', 'tài liệu')}")
    elif is_route(route, RouteType.RECONCILE_FLOW):
        render_reconciliation(data.get("reconciliation_report"))
    elif is_route(route, RouteType.QA_FLOW):
        if status == "ANSWER_VERIFIED":
            grounding_score = data.get("grounding_score", 1.0)
            tag(f"Đã kiểm chứng trích lục ({grounding_score*100:.0f}%)", "done")
            claims = data.get("validated_claims", [])
            if claims:
                st.markdown("**Căn cứ trích dẫn (bấm để soi chiếu văn bản gốc):**")
                for c_idx, cl in enumerate(claims, start=1):
                    doc_id = cl.cited_doc_id
                    page = cl.cited_page
                    s_line = cl.cited_start_line
                    e_line = cl.cited_end_line
                    line_str = (
                        f", Dòng {s_line}-{e_line}" if s_line and e_line else ""
                    )
                    btn_label = f"📄 {doc_id} (Trang {page}{line_str})"

                    if st.button(
                        btn_label,
                        key=f"cite_btn_{idx}_{c_idx}",
                        icon=":material/visibility:",
                    ):
                        lookup = workspace_repository.build_page_lookup()
                        page_info = lookup.get((doc_id, page)) or {}
                        full_txt = (
                            page_info.get("full_page_text")
                            or page_info.get("text", "")
                        )
                        st.session_state["active_evidence"] = {
                            "doc_id": doc_id,
                            "page": page,
                            "start_line": s_line,
                            "end_line": e_line,
                            "quote": cl.evidence_quote,
                            "matched_span": getattr(cl, "matched_span", None)
                            or cl.evidence_quote,
                            "verification_status": getattr(
                                cl, "verification_status", "VERIFIED"
                            ),
                            "match_score": getattr(cl, "match_score", 1.0),
                            "doc_version": getattr(cl, "doc_version", "v1"),
                            "doc_hash": getattr(cl, "doc_hash", ""),
                            "full_page_text": full_txt,
                        }
                        st.session_state["flash"] = (
                            f"Đang soi chiếu trích dẫn từ {doc_id} (Trang {page})."
                        )
                        st.rerun()

            flags = data.get("hallucination_flags", [])
            if flags:
                with st.expander(
                    f"⚠️ Đã loại bỏ {len(flags)} luận điểm chưa đủ căn cứ trích lục",
                    expanded=False,
                ):
                    for fl in flags:
                        st.markdown(
                            f"- *\"{fl.claim_text}\"* — Không tìm thấy nguyên văn trong `{fl.cited_doc_id}` (Trang {fl.cited_page})"
                        )
        elif status == "ABSTAINED_NO_SOURCE_SELECTED":
            st.warning(data.get("message", "Chưa chọn tài liệu nguồn nào."))
        elif data.get("message"):
            st.info(str(data["message"]))
    elif is_route(route, RouteType.EMAIL_FLOW):
        if idx == last_email_idx and st.session_state.get("current_draft"):
            if st.button(
                "Xem và duyệt email",
                key=f"open_email_{idx}",
                type="primary",
                icon=":material/mail:",
            ):
                email_dialog()
    elif is_route(route, RouteType.CLARIFICATION_FLOW):
        if data.get("message"):
            st.warning(str(data["message"]))
        missing = data.get("missing_slots", [])
        if missing:
            st.markdown(f"Thông tin còn thiếu: `{', '.join(missing)}`")
    elif is_route(route, RouteType.REJECTED_SAFEGUARD):
        st.error(
            f"{data.get('message') or 'Yêu cầu bị bộ lọc an toàn chặn.'} "
            "Hãy diễn đạt lại yêu cầu theo đúng nội dung đồ án."
        )


def render_message(
    msg: Dict[str, Any], idx: int, last_email_idx: Optional[int]
) -> None:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        data = msg.get("data")
        if msg["role"] == "assistant" and isinstance(data, dict):
            render_structured(data, idx, last_email_idx)


def build_reply_text(resp: Dict[str, Any]) -> str:
    route, status = resp.get("route"), resp.get("status")
    if status == "SUMMARY_GENERATED":
        return f"**Tóm tắt `{resp.get('doc_name')}`**\n\n{resp.get('summary', '')}"
    if is_route(route, RouteType.RECONCILE_FLOW):
        return "Kết quả đối soát giữa đề bài và bảng công việc:"
    if is_route(route, RouteType.QA_FLOW):
        if status == "ANSWER_VERIFIED":
            claims = resp.get("validated_claims", [])
            if len(claims) > 1:
                # Deduplicate if multiple citations share the same full answer
                texts = [c.claim_text for c in claims if c.claim_text]
                if len(set(texts)) == 1:
                    return texts[0]
                return "\n".join(f"- {c.claim_text}" for c in claims)
            if claims:
                return claims[0].claim_text
            return "Dưới đây là câu trả lời đã được kiểm chứng từ tài liệu nguồn:"
        if status == "ABSTAINED_NO_SOURCE_SELECTED":
            return resp.get(
                "message",
                "Chưa chọn tài liệu nguồn nào. Vui lòng chọn ít nhất một tài liệu ở cột bên trái.",
            )
        return resp.get(
            "message",
            "Tôi không tìm thấy đủ căn cứ đã kiểm chứng trong các tài liệu hiện có để trả lời.",
        )
    if is_route(route, RouteType.EMAIL_FLOW):
        return "Tôi đã tạo bản nháp email. Hãy kiểm tra nội dung và trích dẫn rồi duyệt để gửi."
    if is_route(route, RouteType.CLARIFICATION_FLOW):
        return "Tôi cần thêm thông tin để tiếp tục:"
    if is_route(route, RouteType.REJECTED_SAFEGUARD):
        return "Tôi không thực hiện yêu cầu này:"
    return "Tôi đã xử lý yêu cầu của bạn."


def run_assistant(query: str, recipient: str, ref: date) -> Dict[str, Any]:
    try:
        recent_history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.get("chat_messages", [])[-4:]
            if m.get("content")
        ]
        user_req = UserRequest(
            query=query,
            recipient_email=recipient.strip() or None,
            reference_date=ref,
            selected_doc_ids=st.session_state.get("selected_doc_ids"),
            conversation_history=recent_history,
        )
        resp = handle_user_request(user_req)

        if is_route(resp.get("route"), RouteType.RECONCILE_FLOW):
            live = reconciliation_service.reconcile(
                reference_date=ref,
                requirements=st.session_state["requirements"],
                tasks=st.session_state["tasks"],
            )
            resp["reconciliation_report"] = live["reconciliation_report"]
        if resp.get("status") in ("PENDING_APPROVAL", EmailState.PENDING_APPROVAL):
            st.session_state["current_draft"] = resp.get("draft")
            st.session_state["email_sent_result"] = None
        return {
            "role": "assistant",
            "content": build_reply_text(resp),
            "time": datetime.now().strftime("%H:%M"),
            "data": resp,
        }
    except Exception as exc:
        return {
            "role": "assistant",
            "content": f"Lỗi xử lý yêu cầu ({exc}). Vui lòng kiểm tra lại cấu hình mô hình.",
            "time": datetime.now().strftime("%H:%M"),
            "data": None,
        }


def render_chat_panel(recipient_email: str, ref_date: date) -> None:
    """Renders the Middle Panel: Multi-turn Chat, Suggestions, and Evidence Badges."""
    head, clear = st.columns([3, 2], vertical_alignment="center")
    head.subheader("💬 Trò chuyện & Hỏi đáp")
    with clear.popover("Xóa chat", icon=":material/delete:"):
        st.write("Xóa toàn bộ lịch sử trò chuyện?")
        st.button(
            "Xác nhận xóa",
            type="primary",
            on_click=reset_chat,
            key="confirm_clear_chat",
            **STRETCH,
        )

    # Active documents status notification
    sel_docs = st.session_state.get("selected_doc_ids", [])
    if sel_docs:
        st.caption(
            f"🎯 **Phạm vi tra cứu:** Đang lọc trên {len(sel_docs)} tài liệu được chọn."
        )
    else:
        st.warning(
            "⚠️ **Chưa chọn tài liệu nào!** Vui lòng tick chọn ít nhất 1 nguồn ở cột bên trái để đặt câu hỏi."
        )

    messages: List[Dict[str, Any]] = st.session_state["chat_messages"]

    suggestions = [
        (
            "📄 Tóm tắt tài liệu",
            "Tóm tắt toàn diện tài liệu Project_Brief.pdf theo phong cách NotebookLM",
        ),
        (
            "⏱️ Báo cáo kỹ thuật có mấy trang?",
            "Báo cáo kỹ thuật (Engineering Report) trong Submission Package có mấy trang và nộp những gì?",
        ),
        (
            "📌 Tiêu chuẩn kỹ thuật R1 – R5",
            "Hệ thống quy định các tiêu chuẩn kỹ thuật R1 đến R5 như thế nào?",
        ),
        (
            "📊 Đối soát tiến độ",
            "Đối chiếu Project_Brief.pdf với bảng công việc và kiểm tra công việc trễ hạn",
        ),
        (
            "✉️ Soạn email báo cáo",
            "Soạn email báo cáo tiến độ đồ án WorkspaceAI cho giảng viên",
        ),
    ]

    with st.expander("Gợi ý câu hỏi nhanh", expanded=len(messages) <= 1):
        grid = st.columns(2)
        for i, (label, prompt) in enumerate(suggestions):
            grid[i % 2].button(
                label,
                key=f"sg_{i}",
                on_click=queue_query,
                args=(prompt,),
                **STRETCH,
            )

    last_email_idx = next(
        (
            i
            for i in range(len(messages) - 1, -1, -1)
            if isinstance(messages[i].get("data"), dict)
            and is_route(messages[i]["data"].get("route"), RouteType.EMAIL_FLOW)
        ),
        None,
    )
    for i, m in enumerate(messages):
        render_message(m, i, last_email_idx)

    queued = st.session_state.pop("queued_query", None)
    if queued:
        add_message("user", queued)
        render_message(messages[-1], len(messages) - 1, last_email_idx)
        with st.chat_message("assistant"):
            with st.spinner("Đang truy xuất và đối soát căn cứ trích dẫn…"):
                reply = run_assistant(queued, recipient_email, ref_date)
        messages.append(reply)
        st.rerun()
