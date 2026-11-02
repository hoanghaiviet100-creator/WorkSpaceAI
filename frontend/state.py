"""
frontend/state.py
Centralized State Management and Core Helper Utilities for WorkspaceAI.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from backend.core.schemas import RouteType, TaskRecord
from backend.providers.llm_provider import llm_provider
from backend.repositories.workspace_repository import workspace_repository
from backend.services.document_service import document_service
from backend.services.reconciliation_service import (
    get_default_requirements,
    get_default_tasks,
)


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

DEMO_REFERENCE_DATE = date(2026, 10, 26)
DEFAULT_DOCS = ["Project_Brief.pdf", "team_tasks.csv"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

AI_MODES = {
    "offline": "Trợ lý cục bộ (nhanh, không cần mạng)",
    "ollama": "Ollama cục bộ (Qwen2.5:7b / Llama3)",
    "gemini": "Google Gemini (đám mây)",
}
PROVIDER_FOR_MODE = {"offline": "mock", "ollama": "ollama", "gemini": "gemini"}

TASK_STATE_LABEL = {
    "done": "Hoàn thành",
    "doing": "Đang làm",
    "todo": "Chờ làm",
    "overdue": "Quá hạn",
}
TASK_STATE_COLOR = {
    "done": "var(--c-done)",
    "doing": "var(--c-doing)",
    "todo": "var(--c-todo)",
    "overdue": "var(--c-over)",
}
TASK_FILTERS = {
    "all": "Tất cả",
    "overdue": "Quá hạn",
    "doing": "Đang làm",
    "todo": "Chờ làm",
    "done": "Đã xong",
}
STATUS_OPTIONS = {"TODO": "Chờ làm", "IN_PROGRESS": "Đang làm", "COMPLETED": "Đã xong"}

RECON_STATE_LABEL = {
    "COMPLETED": "Hoàn thành",
    "IN_PROGRESS_ON_TIME": "Đúng hạn",
    "OVERDUE": "Quá hạn",
    "UNTRACKED_MISSING": "Chưa phân công",
    "CONFLICTING_DATE": "Xung đột ngày",
}
RECON_STATE_PRIORITY = {
    "OVERDUE": 0,
    "CONFLICTING_DATE": 1,
    "UNTRACKED_MISSING": 2,
    "IN_PROGRESS_ON_TIME": 3,
    "COMPLETED": 4,
}

GREETING = (
    "Xin chào, tôi là WorkspaceAI. Tôi có thể giúp bạn:\n\n"
    "- **Hỏi đáp tài liệu có căn cứ (Feature 1):** tra cứu ngữ cảnh kèm trích dẫn `[Doc, Page, Line]` đã kiểm chứng.\n"
    "- **Soi chiếu bằng chứng gốc:** bấm trực tiếp vào mã trích dẫn để mở Evidence Viewer và tô sáng đoạn văn bản gốc.\n"
    "- **Đối soát chéo tiến độ đồ án (Feature 2):** so sánh đề bài với bảng phân công công việc.\n"
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


def classify_task_status(task: TaskRecord) -> str:
    s_upper = (task.status or "").strip().upper()
    if s_upper in ("COMPLETED", "DONE", "FINISHED") or task.completion_pct >= 100.0:
        return "COMPLETED"
    if s_upper in ("IN_PROGRESS", "DOING", "WIP") or task.completion_pct > 0.0:
        return "IN_PROGRESS"
    return "TODO"


def is_overdue(task: TaskRecord, ref: date) -> bool:
    return bool(task.logged_deadline and task.logged_deadline < ref and task.completion_pct < 100.0)


def task_state(task: TaskRecord, ref: date) -> str:
    status = classify_task_status(task)
    if status == "COMPLETED":
        return "done"
    if is_overdue(task, ref):
        return "overdue"
    return "doing" if status == "IN_PROGRESS" else "todo"


def deadline_text(task: TaskRecord, ref: date) -> str:
    if not task.logged_deadline:
        return "Chưa có hạn"
    label = task.logged_deadline.strftime("%d/%m/%Y")
    if classify_task_status(task) == "COMPLETED":
        return label
    delta = (task.logged_deadline - ref).days
    if delta < 0:
        return f"{label} (quá {-delta} ngày)"
    if delta == 0:
        return f"{label} (hôm nay)"
    return f"{label} (còn {delta} ngày)"


def parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def extract_draft_attr(draft: Any, field_name: str, default: Any = "") -> Any:
    if draft is None:
        return default
    if isinstance(draft, dict):
        return draft.get(field_name, default)
    return getattr(draft, field_name, default)


def next_task_id(tasks: List[TaskRecord]) -> str:
    existing = {t.task_id for t in tasks}
    n = len(tasks) + 1
    while f"T-{n:02d}" in existing:
        n += 1
    return f"T-{n:02d}"


@st.cache_data(ttl=15, show_spinner=False)
def ollama_online(base_url: str) -> bool:
    return bool(llm_provider.is_ollama_online())


def add_message(role: str, content: str, data: Any = None) -> None:
    st.session_state["chat_messages"].append(
        {"role": role, "content": content, "time": datetime.now().strftime("%H:%M"), "data": data}
    )


def queue_query(text: str, toast: Optional[str] = None) -> None:
    st.session_state["queued_query"] = text
    if toast:
        st.session_state["flash"] = toast


def set_task(idx: int, status: str, pct: float) -> None:
    tasks = st.session_state["tasks"]
    if 0 <= idx < len(tasks):
        tasks[idx].status = status
        tasks[idx].completion_pct = pct


def advance_task(idx: int) -> None:
    tasks = st.session_state["tasks"]
    if 0 <= idx < len(tasks):
        pct = min(100.0, tasks[idx].completion_pct + 25.0)
        set_task(idx, "COMPLETED" if pct >= 100.0 else "IN_PROGRESS", pct)


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
    ss["tasks"] = get_default_tasks()
    ss["requirements"] = get_default_requirements()
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
    """Highlights verified citation span inside the full page text with line formatting."""
    target = matched_span if (matched_span and matched_span in page_text) else quote
    if not target or not target.strip():
        # Render lines
        lines = page_text.splitlines()
        rendered_lines = []
        for i, l in enumerate(lines, start=1):
            rendered_lines.append(
                f'<div class="evidence-line"><span class="line-no">{i}</span><span class="line-content">{esc(l)}</span></div>'
            )
        return "".join(rendered_lines)

    lines = page_text.splitlines()
    target_clean = target.strip()
    rendered_lines = []

    for i, line in enumerate(lines, start=1):
        if target_clean in line:
            parts = line.split(target_clean, 1)
            line_html = (
                esc(parts[0])
                + f'<mark class="cite-mark">{esc(target_clean)}</mark>'
                + esc(parts[1])
            )
        else:
            # Case insensitive match
            pattern = re.escape(target_clean)
            if re.search(pattern, line, re.IGNORECASE):
                line_html = re.sub(
                    pattern,
                    lambda m: f'<mark class="cite-mark">{esc(m.group(0))}</mark>',
                    esc(line),
                    flags=re.IGNORECASE,
                )
            else:
                line_html = esc(line)

        rendered_lines.append(
            f'<div class="evidence-line"><span class="line-no">{i}</span><span class="line-content">{line_html}</span></div>'
        )

    return "".join(rendered_lines)


def init_state() -> None:
    """Initializes and synchronizes all session state variables."""
    if not workspace_repository.chunks:
        workspace_repository.seed_demo_workspace()
    ss = st.session_state
    ss.setdefault("tasks", get_default_tasks())
    ss.setdefault("requirements", get_default_requirements())
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
    ss.setdefault("active_ai_mode", "offline")
    ss.setdefault("upload_log", [])
    ss.setdefault("uploader_nonce", 0)
    ss.setdefault("active_evidence", None)
    ss.setdefault("selected_doc_ids", document_service.get_selected_doc_ids())
