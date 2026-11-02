"""
frontend/components/evidence_viewer.py
Column 3 (Tab 1): Interactive Evidence Viewer with Physical Line Numbers and Text Highlighting.
"""
from __future__ import annotations

import streamlit as st
from frontend.state import STRETCH, esc, highlight_evidence_in_page


def render_evidence_viewer() -> None:
    """Renders the Evidence Viewer displaying full source text with line numbering and highlights."""
    ev = st.session_state.get("active_evidence")
    if not ev:
        st.info(
            "💡 **Chưa có trích dẫn nào được chọn.**\n\n"
            "Bấm vào bất kỳ nút trích dẫn `📄 [Tên tài liệu, Trang X, Dòng Y-Z]` trong câu trả lời ở khung chat "
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
    lines_label = (
        f"{ev['start_line']} - {ev['end_line']}" if ev.get("start_line") else "Toàn trang"
    )
    m2.metric("Dòng", lines_label)
    m3.metric("Khớp căn cứ", f"{ev.get('match_score', 1.0) * 100:.0f}%")

    status = ev.get("verification_status", "VERIFIED_EXACT")
    if status == "VERIFIED_EXACT":
        st.markdown(
            '<div class="verification-badge badge-verified">✅ Trích lục chính xác 100% (Exact Substring Match)</div>',
            unsafe_allow_html=True,
        )
    elif status == "VERIFIED_FUZZY":
        st.markdown(
            f'<div class="verification-badge badge-fuzzy">🔍 Trích lục tương đồng cao ({ev.get("match_score", 0.8) * 100:.0f}% Token-LCS Match)</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="verification-badge badge-flagged">⚠️ Trạng thái: {esc(status)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("**Đoạn trích làm căn cứ (Evidence Quote):**")
    st.markdown(
        f'<div class="evidence-quote">“{esc(ev.get("quote", ""))}”</div>',
        unsafe_allow_html=True,
    )

    st.markdown("**Toàn văn trang gốc (văn bản được đánh số dòng & tô sáng):**")
    page_text = ev.get("full_page_text", "")
    if page_text:
        highlighted = highlight_evidence_in_page(
            page_text, ev.get("quote", ""), ev.get("matched_span")
        )
        st.markdown(
            f'<div class="highlighted-page-view">{highlighted}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("Không có dữ liệu toàn văn trang gốc cho tài liệu này.")

    if ev.get("doc_hash"):
        st.caption(f"🔒 SHA-256 Checksum: `{ev['doc_hash']}`")
