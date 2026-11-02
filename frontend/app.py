"""WorkspaceAI — Streamlit frontend.

Written against the Streamlit 1.4x API (container keys, st.dialog,
segmented_control, tertiary buttons, material icons). Use Streamlit >= 1.41.
Layout: 3-panel (Document Library | Chat Q&A | Evidence Viewer & Workspace).
"""
from __future__ import annotations

import csv
import html
import io
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is importable for direct script / streamlit executions
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import pypdf
import streamlit as st

from backend.core.schemas import (
    EmailState,
    RouteType,
    TaskRecord,
    UserRequest,
)
from backend.api.chat_routes import handle_user_request
from backend.api.email_routes import approve_email
from backend.core.config import settings
from backend.services.document_service import document_service
from backend.services.reconciliation_service import (
    get_default_requirements,
    get_default_tasks,
    reconciliation_service,
)
from backend.services.email_service import email_service
from backend.providers.llm_provider import llm_provider
from backend.algorithms.email_state_machine import prepare_draft_for_approval
from backend.repositories.workspace_repository import workspace_repository

# -----------------------------------------------------------------------------
# 0. Page config, constants, design tokens
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="WorkspaceAI — Trợ lý không gian làm việc",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="collapsed",
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
    "ollama": "Ollama cục bộ (Qwen2.5 / Llama3)",
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
    "- **Hỏi đáp tài liệu có căn cứ:** tra cứu ngữ cảnh kèm trích dẫn `[Doc, Page, Line]` đã kiểm chứng.\n"
    "- **Soi chiếu bằng chứng:** bấm trực tiếp vào mã trích dẫn để xem vị trí và đoạn văn bản gốc.\n"
    "- **Đối soát tiến độ đồ án:** so sánh đề bài với bảng phân công công việc.\n"
    "- **Soạn thảo email báo cáo:** hỗ trợ tạo bản nháp có kiểm chứng để bạn duyệt trước khi gửi.\n\n"
    "Chọn gợi ý nhanh bên dưới hoặc nhập câu hỏi vào ô chat để bắt đầu."
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap');

:root {
  --c-todo: #5B6B7A;
  --c-doing: #B7791F;
  --c-over: #C0392B;
  --c-done: #2E7D5B;
  --focus: #2C8FA8;
}

.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3,
.stApp h4, .stApp button, .stApp input, .stApp textarea {
  font-family: "Be Vietnam Pro", "Segoe UI", system-ui, -apple-system, Roboto,
               "Helvetica Neue", Arial, sans-serif;
}
.block-container { padding-top: 1.5rem; max-width: 1600px; }
.stApp h1 { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.01em; margin-bottom: 0.2rem; }
.stApp h2, .stApp h3 { font-weight: 600; letter-spacing: -0.005em; }

.stApp :focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.stButton > button, .stFormSubmitButton > button { min-height: 2.2rem; }

/* Sticky panels for wide screens */
@media (min-width: 992px) {
  [data-testid="stColumn"]:has(.st-key-doc-panel),
  [data-testid="column"]:has(.st-key-doc-panel),
  [data-testid="stColumn"]:has(.st-key-work-panel),
  [data-testid="column"]:has(.st-key-work-panel) {
    position: sticky;
    top: 3.5rem;
    align-self: flex-start;
    max-height: calc(100vh - 4.5rem);
    overflow-y: auto;
    padding-right: 0.25rem;
  }
}

/* Status ribbon */
.ribbon {
  display: flex; gap: 2px; height: 12px; border-radius: 6px; overflow: hidden;
  background: color-mix(in srgb, currentColor 12%, transparent);
  margin: 0.4rem 0 0.6rem;
}
.ribbon > span { display: block; min-width: 4px; }
.legend {
  display: flex; flex-wrap: wrap; gap: 0.2rem 1.1rem;
  margin: 0 0 0.5rem; padding: 0; list-style: none; font-size: 0.85rem;
}
.legend .dot {
  display: inline-block; width: 0.6rem; height: 0.6rem; border-radius: 50%;
  margin-right: 0.4rem;
}
.legend b { margin-left: 0.2rem; font-variant-numeric: tabular-nums; }

/* Task rows */
.task { border-left: 3px solid var(--c); padding: 0.1rem 0 0.1rem 0.85rem; margin: 0.8rem 0 0.2rem; }
.t-todo { --c: var(--c-todo); }
.t-doing { --c: var(--c-doing); }
.t-overdue { --c: var(--c-over); }
.t-done { --c: var(--c-done); }
.task-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.2rem 0.6rem; }
.task-id {
  font-size: 0.78rem; font-weight: 600; padding: 0 0.4rem; border-radius: 4px;
  border: 1px solid color-mix(in srgb, currentColor 28%, transparent);
  font-variant-numeric: tabular-nums;
}
.task-title { font-weight: 600; line-height: 1.35; flex: 1 1 12rem; }
.state {
  display: inline-flex; align-items: center; font-size: 0.8rem; font-weight: 600;
  padding: 0 0.55rem; border-radius: 999px; border: 1px solid var(--c);
  background: color-mix(in srgb, var(--c) 12%, transparent); white-space: nowrap;
}
.task-facts { display: flex; flex-wrap: wrap; gap: 0.15rem 1.1rem; margin-top: 0.3rem; font-size: 0.86rem; }
.task-facts b { font-weight: 500; opacity: 0.7; margin-right: 0.3rem; }
.task-bar {
  height: 6px; border-radius: 3px; margin-top: 0.5rem; overflow: hidden;
  background: color-mix(in srgb, currentColor 12%, transparent);
}
.task-bar > span { display: block; height: 100%; background: var(--c); }

/* Evidence Viewer styling */
.evidence-quote {
  background: #fff8e1;
  border-left: 3px solid #ffb300;
  padding: 0.6rem 0.8rem;
  font-style: italic;
  font-size: 0.9rem;
  margin: 0.5rem 0;
  border-radius: 4px;
  line-height: 1.45;
}
.highlighted-page-view {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.82rem;
  white-space: pre-wrap;
  background: #fdfefe;
  border: 1px solid #dcdfe3;
  padding: 0.75rem;
  border-radius: 6px;
  max-height: 380px;
  overflow-y: auto;
  line-height: 1.5;
}
mark.cite-mark {
  background-color: #ffd54f;
  color: #14202B;
  padding: 2px 4px;
  border-radius: 3px;
  font-weight: 600;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 1. Helpers
# -----------------------------------------------------------------------------
def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def is_route(value: Any, route: RouteType) -> bool:
    return value == route or value == getattr(route, "value", route) or value == getattr(route, "name", None)


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


def highlight_evidence_in_page(page_text: str, quote: str, matched_span: Optional[str] = None) -> str:
    """Highlights verified citation span inside the full page text."""
    target = matched_span if (matched_span and matched_span in page_text) else quote
    if not target or not target.strip():
        return html.escape(page_text)

    # 1. Exact substring match
    if target in page_text:
        parts = page_text.split(target, 1)
        return (
            html.escape(parts[0])
            + f'<mark class="cite-mark">{html.escape(target)}</mark>'
            + html.escape(parts[1])
        )

    # 2. Case-insensitive search
    pattern = re.escape(target.strip())
    match = re.search(pattern, page_text, re.IGNORECASE)
    if match:
        start, end = match.span()
        return (
            html.escape(page_text[:start])
            + f'<mark class="cite-mark">{html.escape(page_text[start:end])}</mark>'
            + html.escape(page_text[end:])
        )

    # 3. Fallback: Highlight content keywords
    words = [w for w in re.findall(r"\w+", target) if len(w) > 3][:6]
    if words:
        kw_pattern = r"\b(" + "|".join(re.escape(w) for w in words) + r")\b"
        return re.sub(
            kw_pattern,
            r'<mark class="cite-mark">\1</mark>',
            html.escape(page_text),
            flags=re.IGNORECASE,
        )

    return html.escape(page_text)


# -----------------------------------------------------------------------------
# 2. State Management
# -----------------------------------------------------------------------------
def init_state() -> None:
    if not workspace_repository.chunks:
        workspace_repository.seed_demo_workspace()
    ss = st.session_state
    ss.setdefault("tasks", get_default_tasks())
    ss.setdefault("requirements", get_default_requirements())
    ss.setdefault("chat_messages", [{"role": "assistant", "content": GREETING,
                                     "time": datetime.now().strftime("%H:%M"), "data": None}])
    ss.setdefault("current_draft", None)
    ss.setdefault("email_sent_result", None)
    ss.setdefault("active_ai_mode", "offline")
    ss.setdefault("upload_log", [])
    ss.setdefault("uploader_nonce", 0)
    ss.setdefault("active_evidence", None)
    ss.setdefault("selected_doc_ids", document_service.get_selected_doc_ids())


# -----------------------------------------------------------------------------
# 3. Callbacks
# -----------------------------------------------------------------------------
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
        {"role": "assistant", "content": "Đã xóa lịch sử chat. Bạn muốn bắt đầu tra cứu nội dung gì?",
         "time": datetime.now().strftime("%H:%M"), "data": None}
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


# -----------------------------------------------------------------------------
# 4. File Ingestion Service Wrapper
# -----------------------------------------------------------------------------
def parse_tasks_csv(content: str, filename: str) -> List[TaskRecord]:
    reader = csv.DictReader(io.StringIO(content))
    tasks: List[TaskRecord] = []
    seen: set = set()
    for row_idx, row in enumerate(reader, start=1):
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        task_id = clean.get("task_id") or clean.get("id") or f"T-{row_idx:02d}"
        if task_id in seen:
            task_id = f"{task_id}-{row_idx}"
        seen.add(task_id)

        comp_raw = clean.get("completion_pct") or clean.get("progress") or clean.get("completion") or "0"
        try:
            comp = float(comp_raw.replace("%", "").strip())
        except ValueError:
            comp = 0.0

        tasks.append(
            TaskRecord(
                task_id=task_id,
                mapped_req_id=clean.get("mapped_req_id") or clean.get("req_id") or clean.get("req") or None,
                title=clean.get("title") or clean.get("task") or clean.get("name") or f"Nhiệm vụ {row_idx}",
                owner=clean.get("owner") or clean.get("assignee") or "Chưa phân công",
                status=(clean.get("status") or "IN_PROGRESS").upper(),
                logged_deadline=parse_date(
                    clean.get("logged_deadline") or clean.get("deadline") or clean.get("due_date")
                ),
                completion_pct=min(100.0, max(0.0, comp)),
                source_ref=f"{filename}#row{row_idx}",
            )
        )
    return tasks


def process_uploaded_file(uploaded_file) -> Tuple[bool, str]:
    filename = uploaded_file.name
    content_bytes = uploaded_file.getvalue()
    try:
        res = document_service.ingest_file(filename, content_bytes)
        msg = res.get("message", "Nạp tệp thành công.")
        
        # If CSV, sync taskboard
        if filename.lower().endswith(".csv"):
            csv_text = content_bytes.decode("utf-8-sig", errors="ignore")
            new_tasks = parse_tasks_csv(csv_text, filename)
            if new_tasks:
                st.session_state["tasks"] = new_tasks

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


# -----------------------------------------------------------------------------
# 5. Assistant Pipeline & Chat
# -----------------------------------------------------------------------------
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
                return "\n".join(f"- {c.claim_text}" for c in claims)
            if claims:
                return claims[0].claim_text
            return "Dưới đây là câu trả lời đã được kiểm chứng từ tài liệu nguồn:"
        if status == "ABSTAINED_NO_SOURCE_SELECTED":
            return resp.get("message", "Chưa chọn tài liệu nguồn nào. Vui lòng chọn ít nhất một tài liệu ở cột bên trái.")
        return resp.get("message", "Tôi không tìm thấy đủ căn cứ đã kiểm chứng trong các tài liệu hiện có để trả lời.")
    if is_route(route, RouteType.EMAIL_FLOW):
        return "Tôi đã tạo bản nháp email. Hãy kiểm tra nội dung và trích dẫn rồi duyệt để gửi."
    if is_route(route, RouteType.CLARIFICATION_FLOW):
        return "Tôi cần thêm thông tin để tiếp tục:"
    if is_route(route, RouteType.REJECTED_SAFEGUARD):
        return "Tôi không thực hiện yêu cầu này:"
    return "Tôi đã xử lý yêu cầu của bạn."


def run_assistant(query: str, recipient: str, ref: date) -> Dict[str, Any]:
    try:
        # Pass conversation history (last 4 turns) and selected_doc_ids
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


# -----------------------------------------------------------------------------
# 6. Renderers
# -----------------------------------------------------------------------------
def tag(text: str, state: str = "done") -> None:
    st.markdown(
        f'<span class="state t-{state}">{esc(text)}</span>', unsafe_allow_html=True
    )


def render_reconciliation(summary: Any) -> None:
    if not summary:
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Độ bao phủ yêu cầu", f"{summary.coverage_ratio * 100:.0f}%",
              help="Tỷ lệ yêu cầu của đề bài đã có công việc tương ứng.")
    c2.metric("Việc trễ hạn", summary.overdue_count)
    c3.metric("Xung đột ngày", summary.conflict_count)

    def state_key(item: Any) -> str:
        return str(getattr(item.state, "value", item.state))

    items = sorted(summary.item_reports, key=lambda i: RECON_STATE_PRIORITY.get(state_key(i), 9))
    rows = [
        {
            "Mã": it.req_id,
            "Nội dung": it.title,
            "Trạng thái": RECON_STATE_LABEL.get(state_key(it), state_key(it)),
            "Rủi ro": it.risk_level,
            "Tiến độ": float(it.avg_completion),
            "Hạn còn lại": f"{it.days_remaining} ngày" if it.days_remaining is not None else "—",
            "Người làm": ", ".join(it.owners) if it.owners else "Chưa có",
        }
        for it in items
    ]
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            "Tiến độ": st.column_config.ProgressColumn("Tiến độ", min_value=0, max_value=100, format="%d%%")
        },
        **STRETCH,
    )
    conflicts = [it for it in items if it.date_conflicts]
    if conflicts:
        with st.expander(f"Xung đột ngày ({len(conflicts)} yêu cầu)", expanded=True):
            for it in conflicts:
                for c in it.date_conflicts:
                    st.markdown(f"- **{it.req_id}**: {c.doc_a} ghi {c.date_a}, {c.doc_b} ghi {c.date_b}")


def render_structured(data: Dict[str, Any], idx: int, last_email_idx: Optional[int]) -> None:
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
                st.markdown("**Căn cứ trích dẫn (bấm để xem đoạn gốc):**")
                for c_idx, cl in enumerate(claims, start=1):
                    doc_id = cl.cited_doc_id
                    page = cl.cited_page
                    s_line = cl.cited_start_line
                    e_line = cl.cited_end_line
                    line_str = f", Dòng {s_line}-{e_line}" if s_line and e_line else ""
                    btn_label = f"📄 {doc_id} (Trang {page}{line_str})"
                    
                    if st.button(btn_label, key=f"cite_btn_{idx}_{c_idx}", icon=":material/visibility:"):
                        lookup = workspace_repository.build_page_lookup()
                        page_info = lookup.get((doc_id, page)) or {}
                        st.session_state["active_evidence"] = {
                            "doc_id": doc_id,
                            "page": page,
                            "start_line": s_line,
                            "end_line": e_line,
                            "quote": cl.evidence_quote,
                            "matched_span": getattr(cl, "matched_span", None) or cl.evidence_quote,
                            "verification_status": getattr(cl, "verification_status", "VERIFIED"),
                            "match_score": getattr(cl, "match_score", 1.0),
                            "doc_version": getattr(cl, "doc_version", "v1"),
                            "doc_hash": getattr(cl, "doc_hash", ""),
                            "full_page_text": page_info.get("full_page_text", ""),
                        }
                        st.session_state["flash"] = f"Đang soi chiếu trích dẫn từ {doc_id} (Trang {page})."
                        st.rerun()

            flags = data.get("hallucination_flags", [])
            if flags:
                with st.expander(f"⚠️ Đã loại bỏ {len(flags)} luận điểm chưa đủ căn cứ trích lục"):
                    for fl in flags:
                        st.markdown(f"- *\"{fl.claim_text}\"* — Không khớp tài liệu `{fl.cited_doc_id}`")
        elif status == "ABSTAINED_NO_SOURCE_SELECTED":
            st.warning(data.get("message", "Chưa chọn tài liệu nguồn nào."))
        elif data.get("message"):
            st.info(str(data["message"]))
    elif is_route(route, RouteType.EMAIL_FLOW):
        if idx == last_email_idx and st.session_state.get("current_draft"):
            if st.button("Xem và duyệt email", key=f"open_email_{idx}", type="primary",
                         icon=":material/mail:"):
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


def render_message(msg: Dict[str, Any], idx: int, last_email_idx: Optional[int]) -> None:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        data = msg.get("data")
        if msg["role"] == "assistant" and isinstance(data, dict):
            render_structured(data, idx, last_email_idx)


# --- Left Panel: Document Library --------------------------------------------
def render_document_library() -> None:
    st.subheader("📚 Thư viện tài liệu")
    st.caption("Tải PDF (có text layer), TXT hoặc CSV. Chọn/bỏ chọn nguồn để giới hạn phạm vi hỏi đáp.")

    uploaded = st.file_uploader(
        "Tải tệp lên thư viện",
        type=["pdf", "csv", "txt", "md"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['uploader_nonce']}",
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

    for ok, msg in st.session_state["upload_log"]:
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


# --- Right Panel: Evidence Viewer & Taskboard / Email ------------------------
def render_evidence_viewer() -> None:
    ev = st.session_state.get("active_evidence")
    if not ev:
        st.info(
            "💡 **Chưa có trích dẫn nào được chọn.**\n\n"
            "Bấm vào bất kỳ nút trích dẫn `📄 [Tên tài liệu, Trang X, Dòng Y]` trong câu trả lời ở khung chat "
            "để soi chiếu đoạn văn bản gốc và kiểm chứng độ chính xác tại đây."
        )
        return

    st.markdown("##### 🔍 Soi chiếu trích dẫn tài liệu")
    top_c1, top_c2 = st.columns([3, 1], vertical_alignment="center")
    top_c1.markdown(f"**Tài liệu:** `{ev['doc_id']}` (Bản `{ev.get('doc_version', 'v1')}`)")
    if top_c2.button("Đóng", icon=":material/close:", type="tertiary", **STRETCH):
        st.session_state["active_evidence"] = None
        st.rerun()

    m1, m2, m3 = st.columns(3)
    m1.metric("Trang", ev["page"])
    lines_label = f"{ev['start_line']} - {ev['end_line']}" if ev.get("start_line") else "Toàn trang"
    m2.metric("Dòng", lines_label)
    m3.metric("Khớp căn cứ", f"{ev.get('match_score', 1.0) * 100:.0f}%")

    status = ev.get("verification_status", "VERIFIED_EXACT")
    if status == "VERIFIED_EXACT":
        st.success("✅ Trích lục chính xác 100% (Exact Substring Match)")
    elif status == "VERIFIED_FUZZY":
        st.info(f"🔍 Trích lục tương đồng cao ({ev.get('match_score', 0.8) * 100:.0f}% Token-LCS Match)")
    else:
        st.warning(f"⚠️ Trạng thái: {status}")

    st.markdown("**Đoạn trích làm căn cứ (Evidence Quote):**")
    st.markdown(f'<div class="evidence-quote">“{esc(ev.get("quote", ""))}”</div>', unsafe_allow_html=True)

    st.markdown("**Toàn văn trang gốc (văn bản được tô sáng):**")
    page_text = ev.get("full_page_text", "")
    if page_text:
        highlighted = highlight_evidence_in_page(page_text, ev.get("quote", ""), ev.get("matched_span"))
        st.markdown(
            f'<div class="highlighted-page-view">{highlighted}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("Không có dữ liệu toàn văn trang gốc cho tài liệu này.")

    if ev.get("doc_hash"):
        st.caption(f"🔒 SHA-256 Checksum: `{ev['doc_hash']}`")


def render_ribbon(tasks: List[TaskRecord], ref: date) -> None:
    counts = {"done": 0, "doing": 0, "overdue": 0, "todo": 0}
    for t in tasks:
        counts[task_state(t, ref)] += 1
    total = len(tasks)
    avg = sum(t.completion_pct for t in tasks) / total if total else 0.0
    order = ("done", "doing", "overdue", "todo")

    summary = ", ".join(f"{TASK_STATE_LABEL[k].lower()} {counts[k]}" for k in order)
    segments = "".join(
        f'<span style="flex:{counts[k]};background:{TASK_STATE_COLOR[k]}"></span>'
        for k in order if counts[k]
    )
    legend = "".join(
        f'<li><span class="dot" style="background:{TASK_STATE_COLOR[k]}"></span>'
        f"{TASK_STATE_LABEL[k]}<b>{counts[k]}</b></li>"
        for k in order
    )
    st.markdown(
        f"**{avg:.0f}% hoàn thành** trên {total} công việc, tính đến {ref:%d/%m/%Y}"
        f'<div class="ribbon" role="img" aria-label="Tiến độ {avg:.0f}%: {esc(summary)}">{segments}</div>'
        f'<ul class="legend">{legend}</ul>',
        unsafe_allow_html=True,
    )


def render_task_row(idx: int, t: TaskRecord, ref: date) -> None:
    state = task_state(t, ref)
    status = classify_task_status(t)
    pct = max(0.0, min(100.0, t.completion_pct))
    started = status != "TODO"

    facts = [
        f"<span><b>Phụ trách</b>{esc(t.owner or 'Chưa giao')}</span>",
        f"<span><b>Hạn</b>{esc(deadline_text(t, ref))}</span>",
    ]
    if t.mapped_req_id:
        facts.append(f"<span><b>Yêu cầu</b>{esc(t.mapped_req_id)}</span>")
    if started:
        facts.append(f"<span><b>Tiến độ</b>{pct:.0f}%</span>")
    bar = (
        f'<div class="task-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" '
        f'aria-valuenow="{pct:.0f}" aria-label="Tiến độ {esc(t.task_id)}"><span style="width:{pct:.0f}%"></span></div>'
        if started and status != "COMPLETED"
        else ""
    )
    st.markdown(
        f'<div class="task t-{state}">'
        f'<div class="task-head"><span class="task-id">{esc(t.task_id)}</span>'
        f'<span class="task-title">{esc(t.title)}</span>'
        f'<span class="state">{TASK_STATE_LABEL[state]}</span></div>'
        f'<div class="task-facts">{"".join(facts)}</div>{bar}</div>',
        unsafe_allow_html=True,
    )

    tid = t.task_id
    if status == "TODO":
        st.button(f"Bắt đầu {tid}", key=f"start_{idx}", icon=":material/play_arrow:", type="tertiary",
                  on_click=set_task, args=(idx, "IN_PROGRESS", 25.0))
    elif status == "IN_PROGRESS":
        a, b, c = st.columns(3)
        a.button(f"+25% {tid}", key=f"adv_{idx}", icon=":material/add:", type="tertiary",
                 on_click=advance_task, args=(idx,), **STRETCH)
        b.button(f"Xong {tid}", key=f"done_{idx}", icon=":material/check:", type="tertiary",
                 on_click=set_task, args=(idx, "COMPLETED", 100.0), **STRETCH)
        c.button(f"Trả về {tid}", key=f"back_{idx}", icon=":material/undo:", type="tertiary",
                 on_click=set_task, args=(idx, "TODO", 0.0), **STRETCH)
    else:
        st.button(f"Mở lại {tid}", key=f"reopen_{idx}", icon=":material/replay:", type="tertiary",
                   on_click=set_task, args=(idx, "IN_PROGRESS", 50.0))


def render_add_task_form(ref: date) -> None:
    tasks: List[TaskRecord] = st.session_state["tasks"]
    req_ids = [r.req_id for r in st.session_state["requirements"]]
    with st.expander("Thêm công việc mới"):
        with st.form("form_add_task", clear_on_submit=True):
            title = st.text_input("Tiêu đề", placeholder="Ví dụ: Hoàn thiện báo cáo kỹ thuật")
            c1, c2 = st.columns(2)
            owner = c1.text_input("Người phụ trách")
            deadline = c2.date_input("Hạn chót", value=ref, format="DD/MM/YYYY")
            req = c1.selectbox("Yêu cầu liên quan", [None] + req_ids,
                               format_func=lambda r: "Không liên kết" if r is None else r)
            status = c2.selectbox("Trạng thái", list(STATUS_OPTIONS), format_func=STATUS_OPTIONS.get)
            pct = st.slider("Tiến độ (%)", 0, 100, 50, help="Chỉ dùng khi trạng thái là Đang làm.")
            task_id = st.text_input("Mã công việc", value=next_task_id(tasks))
            submitted = st.form_submit_button("Lưu công việc", type="primary", **STRETCH)

        if submitted:
            task_id = task_id.strip()
            if not title.strip():
                st.error("Nhập tiêu đề cho công việc.")
            elif not task_id or any(t.task_id == task_id for t in tasks):
                st.error(f"Mã `{task_id}` đã tồn tại hoặc để trống. Chọn mã khác.")
            else:
                final_pct = {"TODO": 0.0, "COMPLETED": 100.0}.get(status, float(pct))
                tasks.append(
                    TaskRecord(
                        task_id=task_id,
                        mapped_req_id=req,
                        title=title.strip(),
                        owner=owner.strip() or "Chưa phân công",
                        status=status,
                        logged_deadline=deadline,
                        completion_pct=final_pct,
                        source_ref="manual_entry#ui",
                    )
                )
                st.session_state["flash"] = f"Đã thêm công việc {task_id}."
                st.rerun()


def render_taskboard(ref: date) -> None:
    tasks: List[TaskRecord] = st.session_state["tasks"]

    if not tasks:
        st.info("Chưa có công việc nào. Tải tệp CSV ở Thư viện tài liệu hoặc thêm công việc bên dưới.")
    else:
        render_ribbon(tasks, ref)
        chosen = st.segmented_control(
            "Lọc công việc", list(TASK_FILTERS), default="all", key="task_filter",
            format_func=TASK_FILTERS.get, label_visibility="collapsed",
            help="Việc quá hạn được tách riêng khỏi Đang làm và Chờ làm.",
        ) or "all"

        priority = {"overdue": 0, "doing": 1, "todo": 2, "done": 3}
        rows = [(i, t, task_state(t, ref)) for i, t in enumerate(tasks)]
        rows.sort(key=lambda r: (priority[r[2]], r[1].logged_deadline or date.max))
        shown = [r for r in rows if chosen == "all" or r[2] == chosen]
        if not shown:
            st.caption(f"Không có công việc nào ở nhóm “{TASK_FILTERS[chosen]}”.")
        for i, t, _ in shown:
            render_task_row(i, t, ref)

    st.divider()
    render_add_task_form(ref)

    with st.expander("Yêu cầu trong đề bài"):
        req_rows = [
            {
                "Mã": r.req_id,
                "Tiêu chí": r.title,
                "Hạn chót": r.official_deadline.strftime("%d/%m/%Y") if r.official_deadline else "—",
                "Bắt buộc": "Có" if r.mandatory_flag else "Không",
                "Nguồn": r.source_ref,
            }
            for r in st.session_state["requirements"]
        ]
        st.dataframe(pd.DataFrame(req_rows), hide_index=True, **STRETCH)


# --- Email Review ---
def send_draft(draft_id: str, recipient: str, subject: str, body: str) -> None:
    stored = email_service.draft_repo.get(draft_id)
    if stored and (
        stored.recipient_email != recipient or stored.subject != subject or stored.body != body
    ):
        stored.recipient_email = recipient
        stored.subject = subject
        stored.body = body
        prepare_draft_for_approval(stored)
        email_service.draft_repo.save(stored)

    result = approve_email(
        draft_id=draft_id, recipient_email=recipient, subject=subject, body=body, user_confirmed=True
    )
    st.session_state["email_sent_result"] = result
    st.session_state["current_draft"] = None
    add_message("assistant", f"Đã gửi email tới {recipient}.")


def render_email_review(scope: str) -> None:
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
        st.button("Soạn thư mới", key=f"{scope}_new_mail", on_click=clear_sent_email, **STRETCH)
        return

    if not draft:
        st.info("Chưa có bản nháp nào đang chờ duyệt.")
        st.markdown(
            "Yêu cầu trợ lý soạn email ở khung chat (ví dụ: *“Soạn email báo cáo tiến độ đồ án”*). "
            "Bản nháp sẽ xuất hiện ở đây để bạn chỉnh sửa và xác nhận gửi."
        )
        st.button(
            "Soạn email báo cáo tiến độ", key=f"{scope}_compose", icon=":material/edit:",
            on_click=queue_query,
            args=("Soạn email báo cáo tiến độ đồ án WorkspaceAI cho giảng viên",
                  "Đang soạn email..."),
            **STRETCH,
        )
        return

    draft_id = extract_draft_attr(draft, "draft_id", "draft_001")
    default_to = extract_draft_attr(draft, "recipient_email", st.session_state.get("recipient_email", ""))
    sender = settings.gmail_sender_email or "Gmail (chế độ mô phỏng an toàn)"
    st.caption(f"Người gửi: {sender}")

    k = f"{scope}_{draft_id}"
    recipient = st.text_input("Người nhận", value=default_to, key=f"{k}_to")
    subject = st.text_input("Tiêu đề", value=extract_draft_attr(draft, "subject", ""), key=f"{k}_subject")
    body = st.text_area("Nội dung", value=extract_draft_attr(draft, "body", ""), height=220, key=f"{k}_body")

    citations = extract_draft_attr(draft, "citations", [])
    if citations:
        with st.expander(f"Căn cứ trích dẫn ({len(citations)})"):
            for c in citations:
                st.markdown(f"- `{c}`")

    errors = []
    if not EMAIL_RE.match(recipient.strip()):
        errors.append("Địa chỉ email người nhận chưa hợp lệ.")
    if not subject.strip():
        errors.append("Tiêu đề đang trống.")
    if not body.strip():
        errors.append("Nội dung đang trống.")
    for e in errors:
        st.error(e)

    if st.button(f"Gửi tới {recipient.strip() or '…'}", key=f"{k}_send", type="primary",
                 icon=":material/send:", disabled=bool(errors), **STRETCH):
        try:
            send_draft(draft_id, recipient.strip(), subject.strip(), body)
        except Exception as exc:
            st.error(f"Không gửi được email: {exc}. Kiểm tra cấu hình gửi thư rồi thử lại.")
        else:
            st.rerun()


@st.dialog("Duyệt email trước khi gửi", width="large")
def email_dialog() -> None:
    render_email_review("dlg")


# -----------------------------------------------------------------------------
# 7. App Execution (3-Panel Layout)
# -----------------------------------------------------------------------------
init_state()

flash = st.session_state.pop("flash", None)
if flash:
    st.toast(flash)

# --- Sidebar: Settings --------------------------------------------------------
with st.sidebar:
    st.subheader("⚙️ Thiết lập hệ thống")

    ref_date = st.date_input(
        "Ngày đối soát mốc tiến độ",
        value=DEMO_REFERENCE_DATE,
        format="DD/MM/YYYY",
        help="Công việc có hạn trước ngày này và chưa hoàn thành sẽ tính là trễ hạn.",
    )
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
            placeholder="Dán API key vào đây",
        )
        if key_in.strip():
            settings.gemini_api_key = key_in.strip()
            st.success("Đã nhận API key.")
        else:
            st.info("Nhập API key để dùng Gemini.")

    st.divider()
    with st.expander("Thông tin kiến trúc CSC10014"):
        st.code("REQUEST > UNDERSTAND > ROUTE > RETRIEVE/COMPUTE > REASON > VERIFY > RESPOND/ACT",
                language="text")
        st.markdown(
            "- **R1:** Bounded query & Ingestion\n"
            "- **R2:** Pure Python Reconciliation & Citation Verifier\n"
            "- **R3:** Hybrid BM25 + Dense RRF Search\n"
            "- **R4:** Grounded QA with Line Locators\n"
            "- **R7:** Human-in-the-Loop Safeguards"
        )
    with st.popover("Khôi phục dữ liệu mẫu", icon=":material/restart_alt:"):
        st.write("Thao tác này xóa tài liệu mới tải, hoàn tác tiến độ và lịch sử chat.")
        st.button("Xác nhận khôi phục", type="primary", on_click=reset_workspace, key="confirm_reset")

# --- App Header ---------------------------------------------------------------
st.title("WorkspaceAI — Intelligent Document Workspace")
st.caption("Tra cứu tài liệu có trích dẫn đã kiểm chứng • Soi chiếu bằng chứng gốc • Đối soát tiến độ • Soạn thảo email báo cáo")

# --- 3-Panel Columns: Left (25%) | Middle (42%) | Right (33%) -----------------
col_docs, col_chat, col_work = st.columns([1.0, 1.5, 1.3], gap="medium", vertical_alignment="top")

# === PANEL 1 (LEFT): DOCUMENT LIBRARY =========================================
with col_docs:
    with st.container(key="doc-panel"):
        render_document_library()

# === PANEL 2 (MIDDLE): CHAT Q&A ===============================================
with col_chat:
    head, clear = st.columns([3, 2], vertical_alignment="center")
    head.subheader("💬 Trò chuyện & Hỏi đáp")
    with clear.popover("Xóa chat", icon=":material/delete:"):
        st.write("Xóa toàn bộ lịch sử trò chuyện?")
        st.button("Xác nhận xóa", type="primary", on_click=reset_chat, key="confirm_clear_chat", **STRETCH)

    # Active documents status notification
    sel_docs = st.session_state.get("selected_doc_ids", [])
    if sel_docs:
        st.caption(f"🎯 **Phạm vi tra cứu:** Đang lọc trên {len(sel_docs)} tài liệu được chọn.")
    else:
        st.warning("⚠️ **Chưa chọn tài liệu nào!** Vui lòng tick chọn ít nhất 1 nguồn ở cột bên trái để đặt câu hỏi.")

    messages: List[Dict[str, Any]] = st.session_state["chat_messages"]

    suggestions = [
        ("Gói nộp bài gồm gì?", "Submission Package gồm những thành phần bắt buộc nào? Nó có mấy trang?"),
        ("Đối soát tiến độ", "Đối chiếu Project_Brief.pdf với team_tasks.csv và kiểm tra công việc trễ hạn"),
        ("Tiêu chuẩn kỹ thuật", "Hệ thống quy định các tiêu chuẩn kỹ thuật R1 đến R5 như thế nào?"),
        ("Soạn email báo cáo", "Soạn email báo cáo tiến độ đồ án WorkspaceAI cho giảng viên"),
    ]

    with st.expander("Gợi ý câu hỏi nhanh", expanded=len(messages) <= 1):
        grid = st.columns(2)
        for i, (label, prompt) in enumerate(suggestions):
            grid[i % 2].button(label, key=f"sg_{i}", on_click=queue_query, args=(prompt,), **STRETCH)

    last_email_idx = next(
        (i for i in range(len(messages) - 1, -1, -1)
         if isinstance(messages[i].get("data"), dict)
         and is_route(messages[i]["data"].get("route"), RouteType.EMAIL_FLOW)),
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

# === PANEL 3 (RIGHT): EVIDENCE VIEWER & WORKSPACE TABS ========================
with col_work:
    with st.container(key="work-panel"):
        tab_evidence, tab_tasks, tab_mail = st.tabs(["🔍 Soi bằng chứng", "📋 Công việc", "✉️ Email"])
        with tab_evidence:
            render_evidence_viewer()
        with tab_tasks:
            render_taskboard(ref_date)
        with tab_mail:
            render_email_review("tab")

# --- Floating Chat Input -----------------------------------------------------
user_input = st.chat_input("Hỏi về tài liệu, yêu cầu đối soát hoặc soạn email…")
if user_input and user_input.strip():
    queue_query(user_input.strip())
    st.rerun()
