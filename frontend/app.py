import html
from datetime import date
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Ensure project root directory is in sys.path for direct script/streamlit executions
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

# Core Layered Architecture Imports (CSC10014 Virtual Assistant)
from backend.core.schemas import (
    EmailDraftPayload,
    EmailState,
    GeneratedClaim,
    ReconciledItemReport,
    ReconciliationSummary,
    RequirementItem,
    RouteType,
    TaskRecord,
    UserRequest,
)
from backend.api.chat_routes import handle_chat
from backend.api.email_routes import approve_email_send
from backend.core.config import settings
from backend.services.reconciliation_service import (
    get_default_requirements,
    get_default_tasks,
)
from backend.services.email_service import email_service
from backend.algorithms.email_state_machine import (
    compute_draft_hash,
    prepare_draft_for_approval,
)
from backend.repositories.workspace_repository import workspace_repository

# -----------------------------------------------------------------------------
# 0. Page Configuration & Seeding
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="WorkspaceAI — CSC10014 Intelligent Workspace",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Seed demo workspace documents if repository index is currently empty
if not workspace_repository.chunks:
    workspace_repository.seed_demo_workspace()

# Initialize Streamlit session states
if "chat_response" not in st.session_state:
    st.session_state["chat_response"] = None
if "current_draft" not in st.session_state:
    st.session_state["current_draft"] = None
if "email_sent_result" not in st.session_state:
    st.session_state["email_sent_result"] = None
if "active_query" not in st.session_state:
    st.session_state["active_query"] = ""


# Helper functions to extract draft fields safely (whether dict or Pydantic model)
def extract_draft_attr(draft: Any, field_name: str, default: Any = "") -> Any:
    if draft is None:
        return default
    if isinstance(draft, dict):
        return draft.get(field_name, default)
    return getattr(draft, field_name, default)


# -----------------------------------------------------------------------------
# 1. Sidebar (Workspace & Config)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("🛠️ Workspace & Config")
    st.caption("CSC10014 — Virtual Assistant System")

    st.subheader("📁 Tài liệu đã nạp (Workspace Docs)")
    with st.container(border=True):
        st.markdown(
            "📄 **`Project_Brief.pdf`**  \n"
            "*(Unstructured PDF — Đề bài & Tiêu chí đồ án)*  \n"
            "- Trang 3: Yêu cầu tối thiểu R1 — R5  \n"
            "- Trang 6: Quy định Submission Package"
        )
        st.markdown("---")
        st.markdown(
            "📊 **`team_tasks.csv`**  \n"
            "*(Structured CSV — Tiến độ công việc nhóm)*  \n"
            "- Hàng 1: Task T-01 (Problem boundary)  \n"
            "- Hàng 2: Task T-02 (Deterministic engine)"
        )

    st.subheader("⚙️ Tham số đối chiếu & Email")
    ref_date = st.date_input(
        "Reference Date (t_now)",
        value=date(2026, 10, 26),
        help="Ngày mốc để tính toán hạn chót (overdue) và độ trễ công việc.",
    )
    recipient_email = st.text_input(
        "Recipient Email (Email Flow)",
        value="an.nguyen@hcmus.edu.vn",
        help="Email giảng viên hoặc người nhận mặc định cho Tính năng 3.",
    )

    with st.container(border=True):
        st.markdown(f"**Email Dispatch Mode:** `{settings.email_dispatch_mode}`")
        if settings.gmail_sender_email and "your_email" not in settings.gmail_sender_email:
            st.markdown(f"**Tài khoản gửi (Sender):** `{settings.gmail_sender_email}`")
        else:
            st.caption("ℹ️ Đang dùng mẫu cấu hình. Điền `GMAIL_SENDER_EMAIL` và `GMAIL_APP_PASSWORD` trong file `.env` để gửi thư thật 100%.")

    st.divider()

    st.markdown("### 🏛️ CSC10014 Pipeline Flow")
    st.markdown(
        "`REQUEST` ➔ `UNDERSTAND` ➔ `ROUTE` ➔ `RETRIEVE/COMPUTE` ➔ `REASON` ➔ `VERIFY` ➔ `RESPOND/ACT`"
    )
    st.info(
        "🛡️ **Safeguards Active:**  \n"
        "- R2: Thuật toán đối soát hoàn toàn tất định (Pure Python)  \n"
        "- R3: Truy xuất Hybrid BM25 + Token Overlap  \n"
        "- R7: Khóa SHA-256 & Cổng Human-in-the-Loop Approval"
    )

    if st.button("🔄 Tải lại dữ liệu Demo", use_container_width=True):
        workspace_repository.chunks.clear()
        workspace_repository.seed_demo_workspace()
        st.session_state["chat_response"] = None
        st.session_state["current_draft"] = None
        st.session_state["email_sent_result"] = None
        st.session_state["active_query"] = ""
        st.rerun()

# -----------------------------------------------------------------------------
# 2. Main Title Banner
# -----------------------------------------------------------------------------
st.title("🤖 WorkspaceAI — Intelligent Document Workspace")
st.markdown(
    "**Trợ lý điều phối đồ án & Tài liệu thông minh** | Kiến trúc phân tầng CSC10014 Track C"
)
st.caption(
    "Hỗ trợ Q&A có trích dẫn kiểm chứng, đối chiếu đa tài liệu Taskboard vs Đề bài, và soạn email báo cáo có xác thực người dùng."
)

st.markdown("---")

# -----------------------------------------------------------------------------
# 3. Two-Column Layout (1.2 : 1)
# -----------------------------------------------------------------------------
col_left, col_right = st.columns([1.2, 1], gap="medium")

# =============================================================================
# CỘT TRÁI: Taskboard & Chat Assistant
# =============================================================================
with col_left:
    st.subheader("📋 Team Taskboard & Chat Assistant")

    # --- Phần Trên: Hiển thị bảng Team Taskboard trực quan ---
    with st.container(border=True):
        st.markdown("##### 📌 Team Taskboard (`team_tasks.csv`)")

        raw_tasks: List[TaskRecord] = get_default_tasks()
        raw_reqs: List[RequirementItem] = get_default_requirements()

        # Metrics tổng quan
        completed_count = sum(1 for t in raw_tasks if t.completion_pct >= 100.0)
        in_progress_count = len(raw_tasks) - completed_count

        m1, m2, m3 = st.columns(3)
        m1.metric("Tổng số Task", len(raw_tasks))
        m2.metric("Hoàn thành (100%)", completed_count)
        m3.metric("Đang thực hiện", in_progress_count)

        # Bảng hiển thị các đầu việc
        task_data = []
        for t in raw_tasks:
            task_data.append(
                {
                    "Task ID": t.task_id,
                    "Requirement ID": t.mapped_req_id or "N/A",
                    "Title": t.title,
                    "Owner": t.owner or "Chưa giao",
                    "Deadline": (
                        t.logged_deadline.strftime("%Y-%m-%d")
                        if t.logged_deadline
                        else "N/A"
                    ),
                    "Completion %": f"{t.completion_pct:.0f}%",
                    "Status": t.status,
                }
            )

        task_df = pd.DataFrame(task_data)
        st.dataframe(task_df, use_container_width=True, hide_index=True)

        with st.expander(
            "🔍 Xem Danh mục Yêu cầu Đề bài (`Project_Brief.pdf`)", expanded=False
        ):
            req_data = [
                {
                    "Req ID": r.req_id,
                    "Tiêu đề yêu cầu": r.title,
                    "Hạn chót đề bài": (
                        r.official_deadline.strftime("%Y-%m-%d")
                        if r.official_deadline
                        else "N/A"
                    ),
                    "Bắt buộc": "Có" if r.mandatory_flag else "Không",
                    "Nguồn trích lục": r.source_ref,
                }
                for r in raw_reqs
            ]
            st.dataframe(
                pd.DataFrame(req_data), use_container_width=True, hide_index=True
            )
            st.caption(
                "💡 Chú ý: Yêu cầu R8 (Evaluation pack) có trong Đề bài nhưng chưa có Task trong Taskboard!"
            )

    st.markdown("##### 💬 Khung Chat & Điều phối (Chat Assistant)")

    # 6 Nút bấm Demo nhanh (Quick Demo Buttons)
    st.markdown("**Nút bấm Demo nhanh (Quick Demo Buttons):**")
    q_col1, q_col2, q_col3 = st.columns(3)
    q2_col1, q2_col2, q2_col3 = st.columns(3)

    query_to_run: Optional[str] = None

    if q_col1.button(
        "1. Demo Q&A\n(Có trích dẫn)",
        use_container_width=True,
        help="Gửi câu hỏi về Submission Package được đặc tả trong Project_Brief.pdf",
    ):
        query_to_run = "Submission Package"
        st.session_state["active_query"] = query_to_run

    if q_col2.button(
        "2. Demo Đối chiếu\nTaskboard vs Đề bài",
        use_container_width=True,
        help="Đối chiếu tiến độ Taskboard so với Project_Brief.pdf, phát hiện trễ hạn và xung đột ngày",
    ):
        query_to_run = "Compare Project_Brief.pdf requirements against team_tasks.csv and check overdue and date conflicts"
        st.session_state["active_query"] = query_to_run

    if q_col3.button(
        "3. Soạn mail\nBáo cáo tiến độ",
        use_container_width=True,
        help="Soạn email báo cáo tiến độ đồ án gửi giảng viên",
    ):
        query_to_run = "Soạn email báo cáo tiến độ đồ án WorkspaceAI cho giảng viên"
        st.session_state["active_query"] = query_to_run

    if q2_col1.button(
        "4. Soạn mail\nXin dời deadline",
        use_container_width=True,
        help="Soạn email xin gia hạn thời hạn nộp bài",
    ):
        query_to_run = "Soạn mail xin dời deadline nộp bài tập lớn môn học"
        st.session_state["active_query"] = query_to_run

    if q2_col2.button(
        "5. Soạn mail\nHỏi điểm môn học",
        use_container_width=True,
        help="Soạn email xin trao đổi và hỏi điểm môn học",
    ):
        query_to_run = "Soạn mail hỏi điểm môn học CSC10014 và xin nhận xét chi tiết"
        st.session_state["active_query"] = query_to_run

    if q2_col3.button(
        "6. Soạn mail\nBáo cáo Task T-01",
        use_container_width=True,
        help="Soạn email báo cáo chi tiết task T-01",
    ):
        query_to_run = "Soạn mail báo cáo tiến độ hoàn thành task T-01"
        st.session_state["active_query"] = query_to_run

    # Input chatbox
    active_query_val = st.session_state.get("active_query", "")
    user_query_input = st.text_input(
        "Nhập câu hỏi hoặc yêu cầu điều phối:",
        value=active_query_val,
        placeholder="Gõ câu hỏi tự do hoặc bấm các nút Demo ở trên...",
    )


    col_btn_send, col_btn_clear = st.columns([3, 1])
    with col_btn_send:
        btn_send = st.button(
            "🚀 Gửi yêu cầu / Run Pipeline",
            type="primary",
            use_container_width=True,
        )
    with col_btn_clear:
        if st.button("🗑️ Xóa", use_container_width=True):
            st.session_state["active_query"] = ""
            st.session_state["chat_response"] = None
            st.rerun()

    # Xử lý khi nhấn nút gửi hoặc chọn quick demo
    chosen_query = query_to_run if query_to_run else (user_query_input if btn_send else None)

    if chosen_query:
        chosen_query = chosen_query.strip()
        if chosen_query:
            with st.spinner("Đang xử lý qua Router và các Service phân tầng..."):
                req_obj = UserRequest(
                    query=chosen_query,
                    recipient_email=recipient_email.strip() if recipient_email else None,
                    reference_date=ref_date,
                )
                response_data = handle_chat(req_obj)
                st.session_state["chat_response"] = response_data
                st.session_state["email_sent_result"] = None

                # Lưu bản nháp vào session_state khi status == PENDING_APPROVAL
                resp_status = response_data.get("status")
                if (
                    resp_status == "PENDING_APPROVAL"
                    or resp_status == EmailState.PENDING_APPROVAL
                ):
                    st.session_state["current_draft"] = response_data.get("draft")

    # --- Phần Dưới: Hiển thị rõ kết quả trả về ---
    chat_res = st.session_state.get("chat_response")
    if chat_res:
        st.markdown("---")
        st.markdown("##### 🎯 Kết quả Điều phối (Orchestration Result)")

        route_val = chat_res.get("route")
        status_val = chat_res.get("status")

        # Hiển thị Route & Status Badge
        badge_col1, badge_col2 = st.columns(2)
        with badge_col1:
            st.markdown(f"**Selected Route:** `{route_val}`")
        with badge_col2:
            st.markdown(f"**Execution Status:** `{status_val}`")

        # 1. Trường hợp: RECONCILE_FLOW
        if route_val in (RouteType.RECONCILE_FLOW, "RECONCILE_FLOW"):
            summary: Optional[ReconciliationSummary] = chat_res.get(
                "reconciliation_report"
            )
            if summary:
                st.success("✅ Đã hoàn thành đối soát tất định (R2 Deterministic Engine)!")
                r_m1, r_m2, r_m3 = st.columns(3)
                r_m1.metric("Tỷ lệ bao phủ (Coverage)", f"{summary.coverage_ratio * 100:.1f}%")
                r_m2.metric("Số mục trễ hạn (Overdue)", summary.overdue_count)
                r_m3.metric("Xung đột ngày (Conflicts)", summary.conflict_count)

                st.markdown("**Bảng phân tích đối chiếu chi tiết từng yêu cầu:**")
                report_rows = []
                for item in summary.item_reports:
                    conflict_str = (
                        " | ".join(
                            [
                                f"{c.doc_a} ({c.date_a}) vs {c.doc_b} ({c.date_b})"
                                for c in item.date_conflicts
                            ]
                        )
                        if item.date_conflicts
                        else "Không"
                    )
                    report_rows.append(
                        {
                            "Req ID": item.req_id,
                            "Yêu cầu": item.title,
                            "Trạng thái": item.state,
                            "Mức rủi ro": item.risk_level,
                            "Tiến độ": f"{item.avg_completion:.0f}%",
                            "Ngày còn lại": (
                                f"{item.days_remaining} ngày"
                                if item.days_remaining is not None
                                else "N/A"
                            ),
                            "Phụ trách": (
                                ", ".join(item.owners)
                                if item.owners
                                else "Chưa có"
                            ),
                            "Xung đột ngày": conflict_str,
                            "Trích dẫn nguồn": ", ".join(item.citations),
                        }
                    )
                st.dataframe(
                    pd.DataFrame(report_rows),
                    use_container_width=True,
                    hide_index=True,
                )

        # 2. Trường hợp: QA_FLOW
        elif route_val in (RouteType.QA_FLOW, "QA_FLOW"):
            if status_val == "ANSWER_VERIFIED":
                grounding = chat_res.get("grounding_score", 0.0)
                st.success(
                    f"✅ **Câu trả lời đã được kiểm chứng trích dẫn!** (Grounding Score: **{grounding * 100:.0f}%**)"
                )

                validated_claims: List[GeneratedClaim] = chat_res.get(
                    "validated_claims", []
                )
                for idx, claim in enumerate(validated_claims, start=1):
                    with st.container(border=True):
                        st.markdown(f"**Khẳng định {idx}:** {claim.claim_text}")
                        st.markdown(
                            f"📄 **Nguồn trích dẫn:** `{claim.cited_doc_id}` *(Trang {claim.cited_page})*"
                        )
                        st.markdown(
                            f"🔍 **Bằng chứng nguyên văn:** *\"{html.escape(claim.evidence_quote)}\"*"
                        )
                        st.caption(f"Trạng thái xác thực: `{claim.verification_status}`")

                hallucinations: List[GeneratedClaim] = chat_res.get(
                    "hallucination_flags", []
                )
                if hallucinations:
                    st.error("⚠️ Phát hiện thông tin không có căn cứ (Ảo giác):")
                    for h in hallucinations:
                        st.markdown(f"- ❌ {h.claim_text} *(Status: {h.verification_status})*")
            else:
                st.warning(
                    f"⚠️ {chat_res.get('message', 'Không đủ bằng chứng trong tài liệu để trả lời.')}"
                )

        # 3. Trường hợp: EMAIL_FLOW
        elif route_val in (RouteType.EMAIL_FLOW, "EMAIL_FLOW"):
            st.info(
                "✉️ Bản nháp email báo cáo tiến độ đã được tạo và khóa mã băm an toàn! "
                "Vui lòng chuyển sang **Cột Phải (Panel Phê duyệt)** để kiểm tra và duyệt gửi."
            )

        # 4. Trường hợp: CLARIFICATION_FLOW
        elif route_val in (RouteType.CLARIFICATION_FLOW, "CLARIFICATION_FLOW"):
            st.warning(f"⚠️ {chat_res.get('message')}")
            missing = chat_res.get("missing_slots", [])
            st.markdown(f"**Các trường còn thiếu:** `{', '.join(missing)}`")

        # 5. Trường hợp: REJECTED_SAFEGUARD
        elif route_val in (RouteType.REJECTED_SAFEGUARD, "REJECTED_SAFEGUARD"):
            st.error(f"🛡️ {chat_res.get('message')}")
            st.caption(f"Chi tiết chặn: {chat_res.get('details')}")


# =============================================================================
# CỘT PHẢI: Email Review & Human-in-the-Loop Approval Panel (Tính năng 3)
# =============================================================================
with col_right:
    st.subheader("✉️ Email Review & HITL Panel")
    st.caption("Tính năng 3: Context-Aware Email Assistant với Human-in-the-Loop Approval")

    current_draft = st.session_state.get("current_draft")
    sent_result = st.session_state.get("email_sent_result")

    # Trường hợp 1: Đã bấm duyệt và gửi email thành công
    if sent_result:
        with st.container(border=True):
            st.success("🎉 EMAIL ĐÃ ĐƯỢC DUYỆT VÀ GỬI THÀNH CÔNG!")
            st.markdown(f"**Trạng thái FSM:** `{sent_result.get('status')}`")
            st.markdown(f"**Cơ chế gửi:** `{sent_result.get('dispatch_mode')}`")
            st.markdown(f"**Thông báo:** {sent_result.get('message')}")

            details = sent_result.get("details", {})
            if details and isinstance(details, dict):
                if details.get("sender"):
                    st.markdown(f"- 📤 **Người gửi (From):** `{details.get('sender')}`")
                if details.get("recipient"):
                    st.markdown(f"- 📥 **Người nhận (To):** `{details.get('recipient')}`")
                if details.get("smtp_server"):
                    st.markdown(f"- 🌐 **Máy chủ SMTP:** `{details.get('smtp_server')}`")

            st.markdown("**Mã xác thực SHA-256 đã khóa gửi:**")
            st.code(sent_result.get("payload_hash", ""), language="text")

            if st.button("🔄 Soạn bản nháp mới", use_container_width=True):
                st.session_state["email_sent_result"] = None
                st.session_state["current_draft"] = None
                st.rerun()

    # Trường hợp 2: Có bản nháp chờ phê duyệt (PENDING_APPROVAL)
    elif current_draft:
        # Hộp cảnh báo màu vàng theo yêu cầu đề bài
        st.warning(
            "⚠️ **Safeguard R7:** Hệ thống không tự động gửi email. "
            "Vui lòng kiểm tra và phê duyệt."
        )

        draft_id = extract_draft_attr(current_draft, "draft_id", "draft_001")
        init_recipient = extract_draft_attr(
            current_draft, "recipient_email", "an.nguyen@hcmus.edu.vn"
        )
        init_subject = extract_draft_attr(
            current_draft, "subject", "[CSC10014] Project Progress Update"
        )
        init_body = extract_draft_attr(current_draft, "body", "")
        payload_hash = extract_draft_attr(current_draft, "payload_hash", "")
        citations = extract_draft_attr(current_draft, "citations", [])

        sender_disp = settings.gmail_sender_email if settings.gmail_sender_email else "Chưa cấu hình trong .env"

        with st.container(border=True):
            st.markdown(f"**Bản nháp ID:** `{draft_id}` | **Trạng thái:** `PENDING_APPROVAL`")
            st.markdown(f"**Tài khoản gửi (From):** `{sender_disp}` *(SMTP: `{settings.smtp_host}:{settings.smtp_port}`)*")

            # Form cho phép xem và chỉnh sửa

            edit_recipient = st.text_input(
                "Người nhận (Recipient):",
                value=init_recipient,
                key="field_draft_recipient",
            )
            edit_subject = st.text_input(
                "Tiêu đề (Subject):",
                value=init_subject,
                key="field_draft_subject",
            )
            edit_body = st.text_area(
                "Nội dung email (Body):",
                value=init_body,
                height=180,
                key="field_draft_body",
            )

            # Danh sách tài liệu trích dẫn
            st.markdown("**📄 Căn cứ tài liệu trích lục (Citations):**")
            if citations:
                for c in citations:
                    st.markdown(f"- 🔗 `{c}`")
            else:
                st.caption("Được tổng hợp từ các bản ghi Workspace hiện tại.")

            # Hiển thị mã băm bảo mật SHA-256
            st.markdown("**🔒 Mã băm toàn vẹn SHA-256 (Payload Hash):**")
            st.code(payload_hash, language="text")

            # Kiểm tra xem người dùng có chỉnh sửa văn bản không
            current_input_hash = compute_draft_hash(
                edit_recipient, edit_subject, edit_body, []
            )
            if current_input_hash == payload_hash:
                st.caption("✅ Nội dung khớp 100% với mã băm đã khóa gốc.")
            else:
                st.caption(
                    "✏️ *Phát hiện thay đổi nội dung: Hệ thống sẽ tự động cập nhật và khóa mã băm mới khi bạn nhấn Phê duyệt.*"
                )

            st.markdown("---")

            # Nút bấm chính phê duyệt gửi
            if st.button(
                "✅ Approve & Send Email",
                type="primary",
                use_container_width=True,
            ):
                try:
                    # Đồng bộ lại draft trong repository nếu có chỉnh sửa trên UI
                    stored_draft = email_service.draft_repo.get(draft_id)
                    if stored_draft:
                        if (
                            stored_draft.recipient_email != edit_recipient
                            or stored_draft.subject != edit_subject
                            or stored_draft.body != edit_body
                        ):
                            stored_draft.recipient_email = edit_recipient
                            stored_draft.subject = edit_subject
                            stored_draft.body = edit_body
                            prepare_draft_for_approval(stored_draft)
                            email_service.draft_repo.save(stored_draft)

                    # Gọi API route approve_email_send
                    dispatch_res = approve_email_send(
                        draft_id=draft_id,
                        recipient_email=edit_recipient,
                        subject=edit_subject,
                        body=edit_body,
                        user_confirmed=True,
                    )

                    st.session_state["email_sent_result"] = dispatch_res
                    st.session_state["current_draft"] = None
                    st.rerun()

                except Exception as exc:
                    st.error(f"❌ Phê duyệt thất bại do vi phạm Safeguard: {exc}")

    # Trường hợp 3: Chưa có bản nháp nào được tạo
    else:
        with st.container(border=True):
            st.info("ℹ️ Hiện chưa có bản nháp email nào ở trạng thái chờ duyệt.")
            st.markdown(
                """
                **Quy trình Phê duyệt Human-in-the-Loop (HITL):**
                1. AI tổng hợp tiến độ và trích lục thông tin từ tài liệu.
                2. Khởi tạo bản nháp và **khóa mã băm SHA-256** chống sửa đổi ngầm.
                3. Trạng thái dừng ở `PENDING_APPROVAL` để người dùng rà soát.
                4. Nhấn **Approve & Send Email** để kích hoạt chuyển đổi FSM sang `SENT`.
                """
            )

            st.markdown("---")
            if st.button(
                "⚡ Soạn Email Báo cáo Tiến độ ngay",
                use_container_width=True,
                type="secondary",
            ):
                email_query = (
                    "Draft an email to report project progress and completed deliverables to lecturer"
                )
                st.session_state["active_query"] = email_query
                req_obj = UserRequest(
                    query=email_query,
                    recipient_email=recipient_email.strip() if recipient_email else None,
                    reference_date=ref_date,
                )
                resp = handle_chat(req_obj)
                st.session_state["chat_response"] = resp
                st.session_state["email_sent_result"] = None
                if (
                    resp.get("status") == "PENDING_APPROVAL"
                    or resp.get("status") == EmailState.PENDING_APPROVAL
                ):
                    st.session_state["current_draft"] = resp.get("draft")
                st.rerun()
