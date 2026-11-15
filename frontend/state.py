"""
frontend/state.py
Centralized State Management and Core Helper Utilities for WorkspaceAI.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from backend.core.config import settings
from backend.core.schemas import RouteType
from backend.providers.llm_provider import llm_provider
from backend.repositories.workspace_repository import workspace_repository
from backend.services.document_service import document_service
def _st_version() -> Tuple[int, int]:
    try:
        major, minor = st.__version__.split(".")[:2]
        return int(major), int(minor)
    except Exception:
        return (1, 0)


# `use_container_width` is deprecated in newer Streamlit in favour of width="stretch".
STRETCH: Dict[str, Any] = (
    {"width": "stretch"} if _st_version() >= (1, 50) else {"use_container_width": True}
)

DEFAULT_DOCS = ["Project_Brief.pdf"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

AI_MODES = {
    "offline": "Trợ lý cục bộ (nhanh, không cần mạng)",
    "ollama": "Ollama cục bộ (Qwen2.5:7b / Llama3)",
    "gemini": "Google Gemini (đám mây)",
}
PROVIDER_FOR_MODE = {"offline": "mock", "ollama": "ollama", "gemini": "gemini"}

GREETING = (
    "Xin chào, tôi là WorkspaceAI. Tôi có thể giúp bạn:\n\n"
    "- **Hỏi đáp tài liệu có căn cứ (Feature 1):** tra cứu ngữ cảnh kèm trích dẫn `[Doc, Page, Line]` đã kiểm chứng.\n"
    "- **Soi chiếu bằng chứng gốc:** bấm trực tiếp vào mã trích dẫn để mở Evidence Viewer và tô sáng đoạn văn bản gốc.\n"
    "- **Soạn thảo email báo cáo (Feature 3):** hỗ trợ tạo bản nháp có kiểm chứng để bạn duyệt trước khi gửi.\n\n"
    "Chọn gợi ý nhanh bên dưới hoặc nhập câu hỏi vào ô chat để bắt đầu."
)


def esc(value: Any) -> str:
    """Escapes HTML special characters safely."""
    return html.escape(str(value if value is not None else ""))


def is_route(value: Any, route: RouteType) -> bool:
    """Checks if a route value equals a specified RouteType."""
    return (
        value == route
        or value == getattr(route, "value", route)
        or value == getattr(route, "name", None)
    )


def extract_draft_attr(draft: Any, field_name: str, default: Any = "") -> Any:
    if draft is None:
        return default
    if isinstance(draft, dict):
        return draft.get(field_name, default)
    return getattr(draft, field_name, default)


@st.cache_data(ttl=15, show_spinner=False)
def ollama_online(base_url: str = "") -> bool:
    return bool(llm_provider.is_ollama_online())


def add_message(role: str, content: str, data: Any = None) -> None:
    st.session_state["chat_messages"].append(
        {"role": role, "content": content, "time": datetime.now().strftime("%H:%M"), "data": data}
    )


def queue_query(text: str, toast: Optional[str] = None) -> None:
    st.session_state["queued_query"] = text
    if toast:
        st.session_state["flash"] = toast


def reset_chat() -> None:
    st.session_state["chat_messages"] = [
        {
            "role": "assistant",
            "content": "Đã xóa lịch sử chat. Bạn muốn bắt đầu tra cứu nội dung gì?",
            "time": datetime.now().strftime("%H:%M"),
            "data": None,
        }
    ]
    st.session_state["active_evidence"] = None


def reset_workspace() -> None:
    workspace_repository.chunks.clear()
    workspace_repository.seed_demo_workspace()
    ss = st.session_state
    ss["current_draft"] = None
    ss["email_sent_result"] = None
    ss["upload_log"] = []
    ss["active_evidence"] = None
    ss["selected_doc_ids"] = document_service.get_selected_doc_ids()
    for key in [k for k in ss.keys() if str(k).startswith("processed_")]:
        del ss[key]
    ss["uploader_nonce"] += 1
    reset_chat()
    ss["flash"] = "Đã khôi phục dữ liệu mẫu ban đầu của Workspace."


def clear_sent_email() -> None:
    st.session_state["email_sent_result"] = None
    st.session_state["current_draft"] = None


def highlight_evidence_in_page(page_text: str, quote: str, matched_span: Optional[str] = None) -> str:
    """
    Highlights verified citation span inside full page text with physical line formatting.
    Seamlessly handles both single-line and multi-line quotation spans without broken HTML.
    """
    target = matched_span if (matched_span and matched_span in page_text) else quote
    if not target or not target.strip():
        lines = page_text.splitlines()
        rendered_lines = []
        for i, l in enumerate(lines, start=1):
            rendered_lines.append(
                f'<div class="evidence-line"><span class="line-no">{i}</span><span class="line-content">{esc(l)}</span></div>'
            )
        return "".join(rendered_lines)

    target_clean = target.strip()
    marked_text: Optional[str] = None

    # Step A: Direct exact substring replacement
    if target_clean in page_text:
        marked_text = page_text.replace(target_clean, f"@@START_CITE@@{target_clean}@@END_CITE@@", 1)
    else:
        # Step B: Case-insensitive regex replacement
        pattern = re.escape(target_clean)
        if re.search(pattern, page_text, re.IGNORECASE):
            marked_text = re.sub(
                pattern,
                lambda m: f"@@START_CITE@@{m.group(0)}@@END_CITE@@",
                page_text,
                count=1,
                flags=re.IGNORECASE,
            )

    rendered_lines = []

    if marked_text is not None:
        raw_lines = marked_text.splitlines()
        in_highlight = False

        for i, line in enumerate(raw_lines, start=1):
            line_html_parts = []
            curr_pos = 0

            # Scan tokens @@START_CITE@@ and @@END_CITE@@ in this line
            line_content = line
            if in_highlight:
                line_html_parts.append('<mark class="cite-mark">')

            while True:
                idx_start = line_content.find("@@START_CITE@@", curr_pos)
                idx_end = line_content.find("@@END_CITE@@", curr_pos)

                if idx_start == -1 and idx_end == -1:
                    line_html_parts.append(esc(line_content[curr_pos:]))
                    break

                # Determine next marker
                if idx_start != -1 and (idx_end == -1 or idx_start < idx_end):
                    line_html_parts.append(esc(line_content[curr_pos:idx_start]))
                    line_html_parts.append('<mark class="cite-mark">')
                    in_highlight = True
                    curr_pos = idx_start + len("@@START_CITE@@")
                else:
                    line_html_parts.append(esc(line_content[curr_pos:idx_end]))
                    line_html_parts.append("</mark>")
                    in_highlight = False
                    curr_pos = idx_end + len("@@END_CITE@@")

            if in_highlight:
                line_html_parts.append("</mark>")

            rendered_lines.append(
                f'<div class="evidence-line"><span class="line-no">{i}</span><span class="line-content">{"".join(line_html_parts)}</span></div>'
            )
        return "".join(rendered_lines)

    # Step C: Fallback to line-by-line sub-phrase matching for multi-line quotes
    sub_targets = [tl.strip() for tl in target_clean.splitlines() if len(tl.strip()) >= 5]
    if not sub_targets:
        sub_targets = [target_clean]

    lines = page_text.splitlines()
    for i, line in enumerate(lines, start=1):
        line_matched = False
        line_html = esc(line)
        for st_part in sub_targets:
            if st_part in line:
                parts = line.split(st_part, 1)
                line_html = esc(parts[0]) + f'<mark class="cite-mark">{esc(st_part)}</mark>' + esc(parts[1])
                line_matched = True
                break
            elif re.search(re.escape(st_part), line, re.IGNORECASE):
                line_html = re.sub(
                    re.escape(st_part),
                    lambda m: f'<mark class="cite-mark">{esc(m.group(0))}</mark>',
                    esc(line),
                    flags=re.IGNORECASE,
                )
                line_matched = True
                break

        rendered_lines.append(
            f'<div class="evidence-line"><span class="line-no">{i}</span><span class="line-content">{line_html}</span></div>'
        )

    return "".join(rendered_lines)


def init_state() -> None:
    """Initializes and synchronizes all session state variables."""
    if not workspace_repository.chunks:
        workspace_repository.seed_demo_workspace()
    ss = st.session_state
    ss.setdefault(
        "chat_messages",
        [
            {
                "role": "assistant",
                "content": GREETING,
                "time": datetime.now().strftime("%H:%M"),
                "data": None,
            }
        ],
    )
    ss.setdefault("current_draft", None)
    ss.setdefault("email_sent_result", None)

    # Auto-detect best active AI mode: Gemini if key configured, or Ollama if online
    initial_ai_mode = "offline"
    if settings.gemini_api_key and settings.gemini_api_key != "your_gemini_api_key_here" and len(settings.gemini_api_key) > 10:
        initial_ai_mode = "gemini"
    elif settings.llm_provider == "gemini":
        initial_ai_mode = "gemini"
    elif settings.llm_provider == "ollama" or ollama_online():
        initial_ai_mode = "ollama"

    ss.setdefault("active_ai_mode", initial_ai_mode)
    ss.setdefault("upload_log", [])
    ss.setdefault("uploader_nonce", 0)
    ss.setdefault("active_evidence", None)
    ss.setdefault("selected_doc_ids", document_service.get_selected_doc_ids())
