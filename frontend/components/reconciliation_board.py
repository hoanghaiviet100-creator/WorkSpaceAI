"""
frontend/components/reconciliation_board.py
Column 3 (Tab 2): Kanban Taskboard and Cross-Document Requirements Reconciliation (Feature 2).
"""
from __future__ import annotations

from datetime import date
from typing import List

import pandas as pd
import streamlit as st
from backend.core.schemas import TaskRecord
from backend.services.reconciliation_service import (
    get_default_requirements,
    reconciliation_service,
)
from frontend.state import (
    STATUS_OPTIONS,
    STRETCH,
    TASK_FILTERS,
    TASK_STATE_COLOR,
    TASK_STATE_LABEL,
    advance_task,
    classify_task_status,
    deadline_text,
    esc,
    next_task_id,
    set_task,
    task_state,
)


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
        for k in order
        if counts[k]
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
        st.button(
            f"Bắt đầu {tid}",
            key=f"start_{idx}",
            icon=":material/play_arrow:",
            type="tertiary",
            on_click=set_task,
            args=(idx, "IN_PROGRESS", 25.0),
        )
    elif status == "IN_PROGRESS":
        a, b, c = st.columns(3)
        a.button(
            f"+25% {tid}",
            key=f"adv_{idx}",
            icon=":material/add:",
            type="tertiary",
            on_click=advance_task,
            args=(idx,),
            **STRETCH,
        )
        b.button(
            f"Xong {tid}",
            key=f"done_{idx}",
            icon=":material/check:",
            type="tertiary",
            on_click=set_task,
            args=(idx, "COMPLETED", 100.0),
            **STRETCH,
        )
        c.button(
            f"Trả về {tid}",
            key=f"back_{idx}",
            icon=":material/undo:",
            type="tertiary",
            on_click=set_task,
            args=(idx, "TODO", 0.0),
            **STRETCH,
        )
    else:
        st.button(
            f"Mở lại {tid}",
            key=f"reopen_{idx}",
            icon=":material/replay:",
            type="tertiary",
            on_click=set_task,
            args=(idx, "IN_PROGRESS", 50.0),
        )


def render_add_task_form(ref: date) -> None:
    tasks: List[TaskRecord] = st.session_state["tasks"]
    req_ids = [r.req_id for r in st.session_state["requirements"]]
    with st.expander("Thêm công việc mới"):
        with st.form("form_add_task", clear_on_submit=True):
            title = st.text_input("Tiêu đề", placeholder="Ví dụ: Hoàn thiện báo cáo kỹ thuật")
            c1, c2 = st.columns(2)
            owner = c1.text_input("Người phụ trách")
            deadline = c2.date_input("Hạn chót", value=ref, format="DD/MM/YYYY")
            req = c1.selectbox(
                "Yêu cầu liên quan",
                [None] + req_ids,
                format_func=lambda r: "Không liên kết" if r is None else r,
            )
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
    """Renders the Kanban Taskboard and cross-document reconciliation view."""
    # Feature 2 Dynamic Requirement Extraction Button
    c_btn1, c_btn2 = st.columns([3, 2])
    with c_btn1:
        if st.button("🔄 Trích xuất Yêu cầu từ Tài liệu", icon=":material/sync:", type="secondary", **STRETCH):
            selected_docs = st.session_state.get("selected_doc_ids")
            extracted = reconciliation_service.extract_requirements(selected_docs)
            st.session_state["requirements"] = extracted
            st.session_state["flash"] = f"Đã tự động trích xuất {len(extracted)} yêu cầu từ tài liệu workspace!"
            st.rerun()
    with c_btn2:
        if st.button("Khôi phục Yêu cầu mẫu", icon=":material/restart_alt:", type="tertiary", **STRETCH):
            st.session_state["requirements"] = get_default_requirements()
            st.session_state["flash"] = "Đã khôi phục danh sách yêu cầu mẫu ban đầu."
            st.rerun()

    tasks: List[TaskRecord] = st.session_state["tasks"]

    if not tasks:
        st.info("Chưa có công việc nào. Tải tệp CSV ở Thư viện tài liệu hoặc thêm công việc bên dưới.")
    else:
        render_ribbon(tasks, ref)
        chosen = (
            st.segmented_control(
                "Lọc công việc",
                list(TASK_FILTERS),
                default="all",
                key="task_filter",
                format_func=TASK_FILTERS.get,
                label_visibility="collapsed",
                help="Việc quá hạn được tách riêng khỏi Đang làm và Chờ làm.",
            )
            or "all"
        )

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

    with st.expander(f"Yêu cầu đối soát đề bài ({len(st.session_state['requirements'])})", expanded=True):
        req_rows = [
            {
                "Mã": r.req_id,
                "Tiêu chí": r.title,
                "Hạn chót": r.official_deadline.strftime("%d/%m/%Y")
                if r.official_deadline
                else "—",
                "Bắt buộc": "Có" if r.mandatory_flag else "Không",
                "Nguồn": r.source_ref,
            }
            for r in st.session_state["requirements"]
        ]
        st.dataframe(pd.DataFrame(req_rows), hide_index=True, **STRETCH)
