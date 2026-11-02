"""
WorkspaceAI — Streamlit Frontend Entrypoint.
Modular 3-Panel Architecture: Document Library | Chat Q&A | Evidence Viewer & Workspace.
"""
from __future__ import annotations

import sys
from pathlib import Path
import streamlit as st

# Ensure project root is importable for direct script / streamlit executions
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from frontend.components.chat_panel import render_chat_panel
from frontend.components.email_assistant import render_email_review
from frontend.components.evidence_viewer import render_evidence_viewer
from frontend.components.reconciliation_board import render_taskboard
from frontend.components.sidebar_library import (
    render_document_library,
    render_sidebar_settings,
)
from frontend.state import init_state, queue_query
from frontend.styles import apply_custom_styles

# 1. Page Configuration
st.set_page_config(
    page_title="WorkspaceAI — Trợ lý không gian làm việc",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 2. State & Styling
init_state()
apply_custom_styles()

flash = st.session_state.pop("flash", None)
if flash:
    st.toast(flash)

# 3. Sidebar (Settings, Engine Status, Date Picker)
ref_date, recipient_email = render_sidebar_settings()

# 4. App Header
st.title("WorkspaceAI — Intelligent Document Workspace")
st.caption(
    "Tra cứu tài liệu có trích dẫn đã kiểm chứng • Soi chiếu bằng chứng gốc • Đối soát tiến độ • Soạn thảo email báo cáo"
)

# 5. 3-Panel Layout: Left (26%) | Middle (39%) | Right (35%)
col_docs, col_chat, col_work = st.columns(
    [1.0, 1.5, 1.3], gap="medium", vertical_alignment="top"
)

# === PANEL 1 (LEFT): DOCUMENT LIBRARY =========================================
with col_docs:
    with st.container(key="doc-panel"):
        render_document_library()

# === PANEL 2 (MIDDLE): CHAT Q&A ===============================================
with col_chat:
    render_chat_panel(recipient_email, ref_date)

# === PANEL 3 (RIGHT): EVIDENCE VIEWER & WORKSPACE TABS ========================
with col_work:
    with st.container(key="work-panel"):
        tab_evidence, tab_tasks, tab_mail = st.tabs(
            ["🔍 Soi bằng chứng", "📋 Công việc", "✉️ Email"]
        )
        with tab_evidence:
            render_evidence_viewer()
        with tab_tasks:
            render_taskboard(ref_date)
        with tab_mail:
            render_email_review("tab")

# 6. Floating Chat Input
user_input = st.chat_input("Hỏi về tài liệu, yêu cầu đối soát hoặc soạn email…")
if user_input and user_input.strip():
    queue_query(user_input.strip())
    st.rerun()
