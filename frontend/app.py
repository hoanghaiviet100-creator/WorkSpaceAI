"""WorkspaceAI — Streamlit frontend.

Written against the Streamlit 1.4x API (container keys, st.dialog,
segmented_control, tertiary buttons, material icons). Use Streamlit >= 1.41.
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
from backend.api.chat_routes import handle_chat
from backend.api.email_routes import approve_email_send
from backend.core.config import settings
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
    initial_sidebar_state="expanded",
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
    "- **Hỏi đáp tài liệu:** trả lời kèm trích dẫn từ PDF, TXT, CSV đã tải lên.\n"
    "- **Đối soát tiến độ:** so đề bài với bảng công việc và tìm việc trễ hạn.\n"
    "- **Soạn email báo cáo:** tạo bản nháp để bạn duyệt trước khi gửi.\n\n"
    "Chọn một gợi ý nhanh hoặc nhập câu hỏi vào ô chat."
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

/* One typeface (designed for Vietnamese diacritics). Icon fonts are left alone. */
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3,
.stApp h4, .stApp button, .stApp input, .stApp textarea {
  font-family: "Be Vietnam Pro", "Segoe UI", system-ui, -apple-system, Roboto,
               "Helvetica Neue", Arial, sans-serif;
}
.block-container { padding-top: 2.25rem; max-width: 1440px; }
.stApp h1 { font-size: 1.7rem; font-weight: 700; letter-spacing: -0.01em; }
.stApp h2, .stApp h3 { font-weight: 600; letter-spacing: -0.005em; }

/* Keyboard focus + comfortable touch targets */
.stApp :focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.stButton > button, .stFormSubmitButton > button { min-height: 2.5rem; }

/* Wide screens: workspace panel stays in view while the chat scrolls */
@media (min-width: 992px) {
  [data-testid="stColumn"]:has(.st-key-workspace),
  [data-testid="column"]:has(.st-key-workspace) {
    position: sticky;
    top: 4rem;
    align-self: flex-start;
    max-height: calc(100vh - 5rem);
    overflow-y: auto;
    padding-right: 0.25rem;
  }
}

/* Status ribbon: the one signature element */
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

/* Task rows: left edge encodes status, no card chrome */
.task { border-left: 3px solid var(--c); padding: 0.1rem 0 0.1rem 0.85rem; margin: 1rem 0 0.2rem; }
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

@media (prefers-reduced-motion: reduce) {
  .stApp * { animation: none !important; transition: none !important; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 1. Small helpers
# -----------------------------------------------------------------------------
def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def is_route(value: Any, route: RouteType) -> bool:
    return value == route or value == getattr(route, "value", route) or value == getattr(route, "name", None)


def classify_task_status(task: TaskRecord) -> str:
    """TODO / IN_PROGRESS / COMPLETED from status text and completion percentage."""
    s_upper = (task.status or "").strip().upper()
    if s_upper in ("COMPLETED", "DONE", "FINISHED") or task.completion_pct >= 100.0:
        return "COMPLETED"
    if s_upper in ("IN_PROGRESS", "DOING", "WIP") or task.completion_pct > 0.0:
        return "IN_PROGRESS"
    return "TODO"


def is_overdue(task: TaskRecord, ref: date) -> bool:
    return bool(task.logged_deadline and task.logged_deadline < ref and task.completion_pct < 100.0)


def task_state(task: TaskRecord, ref: date) -> str:
    """Mutually exclusive: done / overdue / doing / todo."""
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
    """Cached so the sidebar does not hit the network on every rerun."""
    return bool(llm_provider.is_ollama_online())


def add_message(role: str, content: str, data: Any = None) -> None:
    st.session_state["chat_messages"].append(
        {"role": role, "content": content, "time": datetime.now().strftime("%H:%M"), "data": data}
    )


# -----------------------------------------------------------------------------
# 2. State
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
    ss.setdefault("uploaded_doc_names", list(DEFAULT_DOCS))
    ss.setdefault("active_ai_mode", "offline")
    ss.setdefault("upload_log", [])
    ss.setdefault("uploader_nonce", 0)


# -----------------------------------------------------------------------------
# 3. Callbacks (run before the script reruns, so the UI is never one step behind)
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
        {"role": "assistant", "content": "Đã xóa lịch sử chat. Bạn muốn bắt đầu với việc gì?",
         "time": datetime.now().strftime("%H:%M"), "data": None}
    ]


def reset_workspace() -> None:
    workspace_repository.chunks.clear()
    workspace_repository.seed_demo_workspace()
    ss = st.session_state
    ss["tasks"] = get_default_tasks()
    ss["requirements"] = get_default_requirements()
    ss["current_draft"] = None
    ss["email_sent_result"] = None
    ss["uploaded_doc_names"] = list(DEFAULT_DOCS)
    ss["upload_log"] = []
    for key in [k for k in ss.keys() if str(k).startswith("processed_")]:
        del ss[key]
    ss["uploader_nonce"] += 1  # clears the file_uploader widget
    reset_chat()
    ss["flash"] = "Đã khôi phục dữ liệu mẫu ban đầu."


def clear_sent_email() -> None:
    st.session_state["email_sent_result"] = None
    st.session_state["current_draft"] = None


# -----------------------------------------------------------------------------
# 4. File ingestion
# -----------------------------------------------------------------------------
def parse_tasks_csv(content: str, filename: str) -> List[TaskRecord]:
    reader = csv.DictReader(io.StringIO(content))
    tasks: List[TaskRecord] = []
    seen: set = set()
    for row_idx, row in enumerate(reader, start=1):
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        task_id = clean.get("task_id") or clean.get("id") or f"T-{row_idx:02d}"
        if task_id in seen:  # duplicate ids would collide as widget keys
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


def register_doc(filename: str) -> None:
    if filename not in st.session_state["uploaded_doc_names"]:
        st.session_state["uploaded_doc_names"].append(filename)


def process_uploaded_file(uploaded_file) -> Tuple[bool, str]:
    """Ingest an uploaded file into the workspace; sync the task list for CSV."""
    filename = uploaded_file.name
    lower = filename.lower()
    try:
        if lower.endswith(".pdf"):
            reader = pypdf.PdfReader(uploaded_file)
            pages: List[Tuple[int, str]] = []
            for page_idx, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append((page_idx, text))
            if not pages:
                return False, f"`{filename}` là PDF dạng ảnh, không có lớp văn bản. Hãy chạy OCR rồi tải lại."
            workspace_repository.ingest_text_document(doc_id=filename, doc_name=filename, pages=pages)
            register_doc(filename)
            return True, f"Đã nạp {len(pages)} trang từ `{filename}`."

        if lower.endswith(".csv"):
            # utf-8-sig strips the BOM that Excel adds, otherwise the first column name breaks
            content = uploaded_file.getvalue().decode("utf-8-sig", errors="ignore")
            workspace_repository.ingest_csv_tasks(doc_id=filename, doc_name=filename, csv_content=content)
            register_doc(filename)
            new_tasks = parse_tasks_csv(content, filename)
            if new_tasks:
                st.session_state["tasks"] = new_tasks
                return True, f"Đã nạp `{filename}` và thay bảng công việc bằng {len(new_tasks)} công việc từ tệp."
            return True, f"Đã nạp `{filename}`. Tệp không có dòng công việc nào nên bảng công việc giữ nguyên."

        if lower.endswith((".txt", ".md")):
            content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
            workspace_repository.ingest_text_document(doc_id=filename, doc_name=filename, pages=[(1, content)])
            register_doc(filename)
            return True, f"Đã nạp `{filename}`."

        return False, f"`{filename}` có định dạng chưa được hỗ trợ. Dùng PDF, CSV, TXT hoặc MD."
    except Exception as exc:  # noqa: BLE001
        return False, f"Không xử lý được `{filename}`: {exc}"


# -----------------------------------------------------------------------------
# 5. Assistant pipeline
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
            return "Đây là câu trả lời trích từ tài liệu của bạn."
        return (
            "Tôi không tìm thấy đủ căn cứ trong các tài liệu hiện có để trả lời. "
            "Hãy hỏi cụ thể hơn hoặc tải thêm tài liệu."
        )
    if is_route(route, RouteType.EMAIL_FLOW):
        return "Tôi đã tạo bản nháp email. Hãy kiểm tra nội dung rồi duyệt để gửi."
    if is_route(route, RouteType.CLARIFICATION_FLOW):
        return "Tôi cần thêm thông tin để tiếp tục:"
    if is_route(route, RouteType.REJECTED_SAFEGUARD):
        return "Tôi không thực hiện yêu cầu này:"
    return "Tôi đã xử lý yêu cầu của bạn."


def run_assistant(query: str, recipient: str, ref: date) -> Dict[str, Any]:
    try:
        resp = handle_chat(
            UserRequest(query=query, recipient_email=recipient.strip() or None, reference_date=ref)
        )
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
        return {"role": "assistant", "content": build_reply_text(resp),
                "time": datetime.now().strftime("%H:%M"), "data": resp}
    except Exception as exc:  # noqa: BLE001
        return {
            "role": "assistant",
            "content": (
                f"Tôi không xử lý được yêu cầu này ({exc}). "
                "Kiểm tra mô hình AI ở thanh bên rồi thử lại."
            ),
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
            tag("Có trích dẫn từ tài liệu gốc")
            claims = data.get("validated_claims", [])
            with st.expander("Xem căn cứ trích dẫn"):
                for n, cl in enumerate(claims, start=1):
                    quote = " ".join(str(cl.evidence_quote).split())
                    st.markdown(f"**{n}. `{cl.cited_doc_id}`, trang {cl.cited_page}**")
                    st.markdown(f"> {quote}")
        elif data.get("message"):
            st.caption(str(data["message"]))
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
            "Hãy diễn đạt lại yêu cầu theo nội dung đồ án."
        )


def render_message(msg: Dict[str, Any], idx: int, last_email_idx: Optional[int]) -> None:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        data = msg.get("data")
        if msg["role"] == "assistant" and isinstance(data, dict):
            render_structured(data, idx, last_email_idx)


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
    with st.expander("Thêm công việc"):
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
        st.info("Chưa có công việc nào. Tải tệp CSV ở tab Tài liệu hoặc thêm công việc bên dưới.")
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


def render_documents() -> None:
    st.caption("Tải PDF, CSV, TXT hoặc MD. CSV có cột công việc sẽ thay bảng công việc hiện tại.")
    uploaded = st.file_uploader(
        "Tải tệp lên workspace",
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
            st.rerun()  # so the task list (rendered earlier in the script) refreshes

    for ok, msg in st.session_state["upload_log"]:
        (st.success if ok else st.error)(msg)

    st.markdown("##### Tài liệu trong workspace")
    names: List[str] = st.session_state["uploaded_doc_names"]
    if not names:
        st.info("Workspace chưa có tài liệu. Tải một tệp ở trên để bắt đầu hỏi đáp.")
    for i, name in enumerate(names):
        n_chunks = sum(1 for c in workspace_repository.chunks if c.doc_id == name or c.doc_name == name)
        with st.container(border=True):
            left, right = st.columns([3, 2], vertical_alignment="center")
            left.markdown(f"**{esc(name)}**")
            left.caption(f"{n_chunks} đoạn trích")
            right.button(
                "Tóm tắt", key=f"sum_{i}", icon=":material/summarize:",
                on_click=queue_query,
                args=(f"Tóm tắt tài liệu {name}", "Đang tóm tắt. Kết quả hiện ở khung chat."),
                **STRETCH,
            )


# --- Email review (shared by the tab and the dialog) --------------------------
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

    result = approve_email_send(
        draft_id=draft_id, recipient_email=recipient, subject=subject, body=body, user_confirmed=True
    )
    st.session_state["email_sent_result"] = result
    st.session_state["current_draft"] = None
    add_message("assistant", f"Đã gửi email tới {recipient}.")


def render_email_review(scope: str) -> None:
    draft = st.session_state.get("current_draft")
    sent = st.session_state.get("email_sent_result")

    if sent:
        st.success(sent.get("message") or "Email đã được gửi.")
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
            "Bạn yêu cầu trợ lý soạn email ở khung chat, ví dụ “Soạn email báo cáo tiến độ đồ án”. "
            "Bản nháp xuất hiện ở đây để bạn chỉnh sửa và duyệt. Email chỉ được gửi khi bạn bấm nút gửi."
        )
        st.button(
            "Soạn email báo cáo tiến độ", key=f"{scope}_compose", icon=":material/edit:",
            on_click=queue_query,
            args=("Soạn email báo cáo tiến độ đồ án WorkspaceAI cho giảng viên",
                  "Đang soạn email. Bản nháp sẽ xuất hiện ở khung chat."),
            **STRETCH,
        )
        return

    draft_id = extract_draft_attr(draft, "draft_id", "draft_001")
    default_to = extract_draft_attr(draft, "recipient_email", st.session_state.get("recipient_email", ""))
    sender = settings.gmail_sender_email or "Gmail (chế độ mô phỏng an toàn)"
    st.caption(f"Người gửi: {sender}")

    # draft_id in the key: a new draft must not inherit text the user edited in the previous one
    k = f"{scope}_{draft_id}"
    recipient = st.text_input("Người nhận", value=default_to, key=f"{k}_to")
    subject = st.text_input("Tiêu đề", value=extract_draft_attr(draft, "subject", ""), key=f"{k}_subject")
    body = st.text_area("Nội dung", value=extract_draft_attr(draft, "body", ""), height=240, key=f"{k}_body")

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
        except Exception as exc:  # noqa: BLE001
            st.error(f"Không gửi được email: {exc}. Kiểm tra cấu hình gửi thư rồi thử lại.")
        else:
            st.rerun()


@st.dialog("Duyệt email trước khi gửi", width="large")
def email_dialog() -> None:
    render_email_review("dlg")


# -----------------------------------------------------------------------------
# 7. App
# -----------------------------------------------------------------------------
init_state()

flash = st.session_state.pop("flash", None)
if flash:
    st.toast(flash)

# --- Sidebar: session + model settings ---------------------------------------
with st.sidebar:
    st.subheader("Thiết lập")

    ref_date = st.date_input(
        "Ngày dùng để tính trễ hạn",
        value=DEMO_REFERENCE_DATE,
        format="DD/MM/YYYY",
        help="Công việc có hạn trước ngày này và chưa xong sẽ bị tính là quá hạn.",
    )
    recipient_email = st.text_input(
        "Email người nhận mặc định",
        value="an.nguyen@hcmus.edu.vn",
        key="recipient_email",
        help="Dùng khi trợ lý soạn email báo cáo.",
    )

    st.divider()
    mode = st.selectbox(
        "Mô hình xử lý", list(AI_MODES), format_func=AI_MODES.get, key="active_ai_mode"
    )
    # NOTE: `settings` is process-wide, so in a multi-user deployment these values are shared
    # between sessions. Pass provider/key per request from the backend if that matters.
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
            st.info("Nhập API key để dùng Gemini, hoặc chuyển về Trợ lý cục bộ (miễn phí).")

    st.divider()
    with st.expander("Thông tin kỹ thuật"):
        st.code("REQUEST > UNDERSTAND > ROUTE > RETRIEVE/COMPUTE > REASON > VERIFY > RESPOND/ACT",
                language="text")
        st.markdown(
            "- **R2:** đối soát tất định, Python thuần\n"
            "- **R3:** lập chỉ mục lai BM25 + token overlap\n"
            "- **R7:** khóa SHA-256 và cổng Human-in-the-Loop"
        )
    with st.popover("Khôi phục dữ liệu mẫu", icon=":material/restart_alt:"):
        st.write("Thao tác này xóa tài liệu đã tải, công việc đã sửa và lịch sử chat.")
        st.button("Xác nhận khôi phục", type="primary", on_click=reset_workspace, key="confirm_reset")

# --- Header -------------------------------------------------------------------
st.title("WorkspaceAI")
st.caption("Hỏi đáp tài liệu, đối soát tiến độ và soạn email báo cáo cho nhóm đồ án.")

col_chat, col_work = st.columns([1.1, 1.0], gap="large", vertical_alignment="top")

# --- Left: chat ---------------------------------------------------------------
with col_chat:
    head, clear = st.columns([3, 2], vertical_alignment="center")
    head.subheader("Trò chuyện")
    with clear.popover("Xóa chat", icon=":material/delete:"):
        st.write("Xóa toàn bộ lịch sử chat?")
        st.button("Xóa lịch sử", type="primary", on_click=reset_chat, key="confirm_clear_chat")

    messages: List[Dict[str, Any]] = st.session_state["chat_messages"]
    docs: List[str] = st.session_state["uploaded_doc_names"]
    brief = next((d for d in docs if d.lower().endswith(".pdf")), docs[0] if docs else None)
    sheet = next((d for d in docs if d.lower().endswith(".csv")), None)

    suggestions: List[Tuple[str, str]] = []
    if brief:
        suggestions.append((f"Tóm tắt {brief}", f"Tóm tắt tài liệu {brief}"))
    if "Project_Brief.pdf" in docs:
        suggestions.append(("Gói nộp bài gồm gì?", "Submission Package gồm những thành phần bắt buộc nào?"))
    if brief and sheet:
        suggestions.append(("Đối soát tiến độ", f"Đối chiếu {brief} với {sheet} và kiểm tra công việc trễ hạn"))
    suggestions.append(("Soạn email báo cáo", "Soạn email báo cáo tiến độ đồ án WorkspaceAI cho giảng viên"))
    suggestions.append(("Xin dời deadline", "Soạn mail xin dời deadline nộp bài tập lớn môn học"))

    with st.expander("Gợi ý nhanh", expanded=len(messages) <= 1):
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
            with st.spinner("Đang tìm trong tài liệu…"):
                reply = run_assistant(queued, recipient_email, ref_date)
        messages.append(reply)
        st.rerun()  # re-render from history so the right-hand panel reflects the new state

# --- Right: workspace ---------------------------------------------------------
with col_work:
    with st.container(key="workspace"):
        # Static tab labels on purpose: changing a label makes Streamlit reset the active tab.
        tab_tasks, tab_docs, tab_mail = st.tabs(["Công việc", "Tài liệu", "Email"])
        with tab_tasks:
            render_taskboard(ref_date)
        with tab_docs:
            render_documents()
        with tab_mail:
            render_email_review("tab")

# Top-level chat_input docks to the bottom of the page and keeps the newest message in view
user_input = st.chat_input("Hỏi về tài liệu, yêu cầu đối soát hoặc soạn email…")
if user_input and user_input.strip():
    queue_query(user_input.strip())
    st.rerun()