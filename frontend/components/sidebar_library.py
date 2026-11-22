"""
frontend/components/sidebar_library.py
Column 1: Document Library Management, File Ingestion, and System Configuration.
"""
from __future__ import annotations

from typing import Tuple

import streamlit as st
from backend.core.config import settings
from backend.services.document_service import document_service
from frontend.state import (
    AI_MODES,
    PROVIDER_FOR_MODE,
    STRETCH,
    esc,
    ollama_online,
    queue_query,
    reset_workspace,
)


def process_uploaded_file(uploaded_file) -> Tuple[bool, str]:
    filename = uploaded_file.name
    content_bytes = uploaded_file.getvalue()
    try:
        res = document_service.ingest_file(filename, content_bytes)
        msg = res.get("message", "Nạp tệp thành công.")

        # Ensure newly ingested doc is in selected list
        doc_meta = res.get("document")
        doc_id = getattr(doc_meta, "doc_id", filename) if doc_meta else filename
        selected = list(st.session_state.get("selected_doc_ids", []))
        if doc_id not in selected:
            selected.append(doc_id)
            st.session_state["selected_doc_ids"] = selected
            document_service.set_selected_documents(selected)

        return True, msg
    except ValueError as val_err:
        return False, str(val_err)
    except Exception as exc:
        return False, f"Không xử lý được `{filename}`: {exc}"


def render_document_library() -> None:
    """Renders the Left Panel: Document Library & Ingestion."""
    st.subheader("📚 Thư viện tài liệu")
    st.caption("Tải PDF (text layer), TXT hoặc CSV. Chọn nguồn để lọc phạm vi hỏi đáp.")

    uploaded = st.file_uploader(
        "Tải tệp lên thư viện",
        type=["pdf", "csv", "txt", "md"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.get('uploader_nonce', 0)}",
    )
    if uploaded:
        changed = False
        for f in uploaded:
            file_key = f"processed_{f.name}_{f.size}"
            if file_key not in st.session_state:
                ok, msg = process_uploaded_file(f)
                st.session_state[file_key] = True
                st.session_state["upload_log"].append((ok, msg))
                changed = True
        if changed:
            st.session_state["upload_log"] = st.session_state["upload_log"][-4:]
            st.rerun()

    for ok, msg in st.session_state.get("upload_log", []):
        (st.success if ok else st.error)(msg)

    docs = document_service.list_documents()
    selected_set = set(st.session_state.get("selected_doc_ids", []))

    st.divider()
    c_all, c_none = st.columns(2)
    if c_all.button("Chọn tất cả", icon=":material/select_all:", type="tertiary", **STRETCH):
        all_ids = [d["doc_id"] for d in docs]
        st.session_state["selected_doc_ids"] = all_ids
        document_service.set_selected_documents(all_ids)
        st.rerun()
    if c_none.button("Bỏ chọn hết", icon=":material/deselect:", type="tertiary", **STRETCH):
        st.session_state["selected_doc_ids"] = []
        document_service.set_selected_documents([])
        st.rerun()

    st.markdown(f"**Danh sách nguồn ({len(selected_set)}/{len(docs)} đang chọn):**")
    if not docs:
        st.info("Chưa có tài liệu nào trong thư viện.")
        return

    for d in docs:
        d_id = d["doc_id"]
        is_chk = d_id in selected_set
        with st.container(border=True):
            r1_col, r2_col = st.columns([4, 1], vertical_alignment="center")
            new_checked = r1_col.checkbox(
                f"**{esc(d['doc_name'])}**",
                value=is_chk,
                key=f"chk_doc_{d_id}",
            )
            if new_checked != is_chk:
                if new_checked:
                    selected_set.add(d_id)
                else:
                    selected_set.discard(d_id)
                st.session_state["selected_doc_ids"] = list(selected_set)
                document_service.set_selected_documents(list(selected_set))
                st.rerun()

            with r2_col.popover("", icon=":material/delete:"):
                st.write(f"Xóa `{d_id}` khỏi thư viện?")
                if st.button("Xác nhận xóa", key=f"del_{d_id}", type="primary", **STRETCH):
                    document_service.delete_document(d_id)
                    selected_set.discard(d_id)
                    st.session_state["selected_doc_ids"] = list(selected_set)
                    if st.session_state.get("active_evidence", {}).get("doc_id") == d_id:
                        st.session_state["active_evidence"] = None
                    st.session_state["flash"] = f"Đã xóa tài liệu '{d_id}'."
                    st.rerun()

            st.caption(
                f"Bản `{d.get('version_id', 'v1')}` • {d.get('chunk_count', 0)} đoạn • {d.get('page_count', 1)} trang"
            )
            act_col1, act_col2 = st.columns([1, 1])
            act_col1.button(
                "Tóm tắt",
                key=f"sum_lib_{d_id}",
                icon=":material/summarize:",
                type="tertiary",
                on_click=queue_query,
                args=(f"Tóm tắt tài liệu {d_id}", f"Đang tóm tắt {d_id}..."),
                **STRETCH,
            )
            with act_col2.popover("Chi tiết", icon=":material/info:"):
                st.markdown(f"- **Mã:** `{d_id}`")
                st.markdown(f"- **Phiên bản:** `{d.get('version_id', 'v1')}`")
                st.markdown(f"- **Định dạng:** `{d.get('file_type', 'pdf')}`")
                st.markdown(f"- **Tổng dòng:** `{d.get('total_lines', 0)}`")
                st.markdown(f"- **SHA-256:** `{d.get('file_hash', 'N/A')[:16]}...`")
                st.markdown(f"- **Thời gian tải:** `{d.get('uploaded_at', 'N/A')}`")


def render_sidebar_settings() -> str:
    """Render model settings and return the default email recipient."""
    with st.sidebar:
        st.subheader("⚙️ Thiết lập hệ thống")

        recipient_email = st.text_input(
            "Email nhận báo cáo mặc định",
            value="an.nguyen@hcmus.edu.vn",
            key="recipient_email",
        )

        st.divider()
        mode = st.selectbox(
            "Mô hình xử lý", list(AI_MODES), format_func=AI_MODES.get, key="active_ai_mode"
        )
        settings.llm_provider = PROVIDER_FOR_MODE[mode]
        if mode == "offline":
            st.caption("Xử lý trực tiếp trên máy, không cần internet.")
        elif mode == "ollama":
            if ollama_online(settings.ollama_base_url):
                st.success(f"Ollama đang chạy ({settings.ollama_model}).")
            else:
                st.warning(
                    f"Chưa kết nối được Ollama ở {settings.ollama_base_url}. "
                    "Hệ thống sẽ dùng Trợ lý cục bộ khi cần."
                )
        else:
            key_value = settings.gemini_api_key
            key_in = st.text_input(
                "Gemini API key",
                value="" if key_value == "your_gemini_api_key_here" else key_value,
                type="password",
                placeholder="Dán API key (AIzaSy...) vào đây",
            )
            if key_in.strip():
                settings.gemini_api_key = key_in.strip()
                st.success("Đã nhận API key.")
            else:
                st.info("Nhập API key để dùng Gemini (lấy tại aistudio.google.com).")

            gemini_models = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest"]
            curr_model_idx = (
                gemini_models.index(settings.gemini_model)
                if settings.gemini_model in gemini_models
                else 0
            )
            sel_model = st.selectbox(
                "Phiên bản Gemini",
                gemini_models,
                index=curr_model_idx,
                key="sel_gemini_model",
            )
            settings.gemini_model = sel_model

        st.divider()
        with st.expander("Thông tin kiến trúc CSC10014"):
            st.code(
                "REQUEST > UNDERSTAND > ROUTE > RETRIEVE/COMPUTE > REASON > VERIFY > RESPOND/ACT",
                language="text",
            )
            st.markdown(
                "- **R1:** Bounded query & Ingestion\n"
                "- **R2:** Pure Python Citation Verifier\n"
                "- **R3:** Hybrid BM25 + Dense RRF Search\n"
                "- **R4:** Grounded QA with Line Locators (Ollama qwen2.5:7b)\n"
                "- **R7:** Human-in-the-Loop Safeguards"
            )
        with st.popover("Khôi phục dữ liệu mẫu", icon=":material/restart_alt:"):
            st.write("Thao tác này xóa tài liệu mới tải và lịch sử chat.")
            st.button(
                "Xác nhận khôi phục",
                type="primary",
                on_click=reset_workspace,
                key="confirm_reset",
                **STRETCH,
            )

    return recipient_email
