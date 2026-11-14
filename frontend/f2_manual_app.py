"""Temporary local manual UI over existing Q02–Q06 services; no demo data."""
from pathlib import Path
import sys

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from frontend.components.f2_manual_panel import render_controls, render_practice


st.set_page_config(page_title="WorkspaceAI · Thử F2", page_icon="📚", layout="wide")
st.title("WorkspaceAI · Quiz & Flashcards")
st.caption("Bản thử thủ công · Tài liệu của bạn · Offline, Gemini, NVIDIA NIM hoặc Ollama")
st.info(
    "Có thể xem văn bản đã trích xuất và sinh học liệu từ nội dung tài liệu. "
    "Quiz AI trả JSON để dựng câu hỏi tương tác; prompt yêu cầu câu hỏi đầy đủ ngữ cảnh. "
    "Câu chưa kiểm chứng giữ ở bản nháp và có chế độ làm thử theo đáp án AI đề xuất. "
    "Chưa tự giải bài Toán/Lý; lỗi API không tự chuyển sang offline."
)

sources, practice = st.columns([1, 2], gap="large")
with sources:
    with st.container(border=True):
        render_controls()
with practice:
    render_practice()

st.divider()
st.caption("Tài liệu và lượt làm chỉ lưu trong phiên thử hiện tại. Chưa lưu vào SQLite.")
