# WorkspaceAI Streamlit Frontend Skill (Modular Component Architecture)

## Architecture Overview
The frontend of WorkspaceAI is built with Streamlit (>= 1.41) using a strictly modular 3-column desktop layout:
- **Column 1 (`frontend/components/sidebar_library.py`)**: Document Library & Ingestion (PDF, TXT, MD, CSV), Document selection checkboxes for scope-filtered QA, document versioning badges, and runtime engine health indicators (Ollama / Gemini / Offline).
- **Column 2 (`frontend/components/chat_panel.py`)**: Multi-turn conversational Q&A, query expansion display, grounding verification score ($S_{verify}$), clickable citation pills (`[Doc • Page • Lines]`), and Hallucination Alert flags.
- **Column 3 (`frontend/components/evidence_viewer.py`, `reconciliation_board.py`, `email_assistant.py`)**:
  - **Tab 1: Evidence Viewer**: Deep-dive original source page viewer with line-by-line numbering, full-span yellow highlighting (`mark.cite-mark`), and SHA-256 integrity indicator.
  - **Tab 2: Cross-Document Reconciliation Board (Feature 2)**: Project Brief vs. Taskboard reconciliation with progress ribbons and conflict flags.
  - **Tab 3: Email Assistant (Feature 3)**: Human-in-the-loop email staging, draft review, and SHA-256 tamper-proof approval gate.

## Modular Component Structure
```text
frontend/
├── app.py                         # Clean entrypoint (< 120 lines): layout assembly only
├── state.py                       # Centralized Streamlit session_state management
├── styles.py                      # Academic Teal CSS design system
└── components/
    ├── sidebar_library.py         # Column 1: Document management & engine settings
    ├── chat_panel.py              # Column 2: Conversational UI & citation badges
    ├── evidence_viewer.py         # Column 3 (Tab 1): Interactive line-numbered evidence viewer
    ├── reconciliation_board.py    # Column 3 (Tab 2): Kanban taskboard & cross-doc reconciliation
    └── email_assistant.py         # Column 3 (Tab 3): HITL email review & cryptographic dispatch
```

## Academic Teal Design System (`frontend/styles.py`)
- **Primary Brand Color**: Academic Teal `#0E4A5A` with subtle slate accents.
- **Focus & Selection**: `#2C8FA8` / `#0E4A5A`.
- **Status Semantic Colors**:
  - Done / Verified Exact: `#2E7D5B`
  - Doing / Verified Fuzzy: `#B7791F`
  - Overdue / Hallucination Flag: `#C0392B`
  - Todo / Pending: `#5B6B7A`
- **Evidence Highlight**: `#ffd54f` (`mark.cite-mark`) with dark slate typography `#14202B`.

## Citation Click Synchronization & Evidence Viewer
1. When a user clicks a citation button `[Doc • Trang X • Dòng Y-Z]` in `chat_panel.py`:
   - It captures `cited_doc_id`, `cited_page`, `cited_start_line`, `cited_end_line`, `evidence_quote`, and `matched_span`.
   - It sets `st.session_state["active_evidence"]` with the structured claim payload and the full page text from `workspace_repository.build_page_lookup()`.
   - It triggers `st.rerun()`.
2. In `evidence_viewer.py`:
   - Checks `st.session_state["active_evidence"]`. If present, renders the exact page with physical line numbers (`[1]`, `[2]`, ...).
   - Automatically applies the CSS class `.highlighted-page-view` and highlights the matched quote using `<mark class="cite-mark">`.
3. Hallucination Flags:
   - When claims fail verification (e.g. `UNGROUNDED_QUOTE`, `LINE_OUT_OF_RANGE`), display an expandable warning box `⚠️ Đã loại bỏ N luận điểm chưa đủ căn cứ trích lục` to maintain zero-tolerance for hallucinations.
