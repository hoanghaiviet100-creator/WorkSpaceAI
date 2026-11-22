-- ==============================================================================
-- WorkspaceAI v2.5 - Local-First SQLite Database Schema DDL
-- CSC10014 Track C - Intelligent Document Workspace with Evidence Grounding
-- Zero-Config Embedded Database (workspace_ai.db)
-- ==============================================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------------------------
-- 1. Table: documents (Metadata của tài liệu tải lên hoặc nạp sẵn)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT NOT NULL PRIMARY KEY,
    doc_name TEXT NOT NULL,
    file_type TEXT NOT NULL DEFAULT 'pdf',
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    file_hash TEXT NOT NULL UNIQUE,
    version_id TEXT NOT NULL DEFAULT 'v1',
    total_pages INTEGER NOT NULL DEFAULT 1,
    total_lines INTEGER NOT NULL DEFAULT 0,
    total_chunks INTEGER NOT NULL DEFAULT 0,
    is_selected INTEGER NOT NULL DEFAULT 1,
    storage_path TEXT NULL,
    mime_type TEXT NOT NULL DEFAULT 'application/pdf',
    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_name ON documents(doc_name);
CREATE INDEX IF NOT EXISTS idx_documents_is_selected ON documents(is_selected);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents(uploaded_at);

-- ------------------------------------------------------------------------------
-- 2. Table: document_pages (Nội dung thô theo từng trang phục vụ đối soát & highlight)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_pages (
    page_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    line_count INTEGER NOT NULL DEFAULT 0,
    raw_text TEXT NOT NULL,
    page_hash TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (doc_id, page_number),
    FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_page_lookup ON document_pages(doc_id, page_number);

-- ------------------------------------------------------------------------------
-- 3. Table: document_chunks (Đoạn chunking vật lý phục vụ BM25 & Hybrid Vector RAG)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id TEXT NOT NULL PRIMARY KEY,
    doc_id TEXT NOT NULL,
    doc_name TEXT NOT NULL,
    page_number INTEGER NOT NULL DEFAULT 1,
    start_line INTEGER NOT NULL DEFAULT 1,
    end_line INTEGER NOT NULL DEFAULT 1,
    section_header TEXT NOT NULL DEFAULT 'General',
    text TEXT NOT NULL,
    chunk_hash TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    doc_version TEXT NOT NULL DEFAULT 'v1',
    embedding TEXT NULL, -- Vector JSON array
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_locator ON document_chunks(doc_id, page_number, start_line, end_line);

-- ------------------------------------------------------------------------------
-- 4. Table: requirements (Danh mục yêu cầu/tiêu chí từ đề bài hoặc bóc tách tự động)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS requirements (
    req_id TEXT NOT NULL PRIMARY KEY,
    doc_id TEXT NULL,
    title TEXT NOT NULL,
    description TEXT NULL,
    keywords TEXT NOT NULL, -- JSON array
    official_deadline DATE NULL,
    mandatory_flag INTEGER NOT NULL DEFAULT 1,
    source_ref TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_req_doc_id ON requirements(doc_id);
CREATE INDEX IF NOT EXISTS idx_req_deadline ON requirements(official_deadline);
CREATE INDEX IF NOT EXISTS idx_req_mandatory ON requirements(mandatory_flag);

-- ------------------------------------------------------------------------------
-- 5. Table: tasks (Bảng công việc Kanban của nhóm)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT NOT NULL PRIMARY KEY,
    mapped_req_id TEXT NULL,
    title TEXT NOT NULL,
    owner TEXT NULL,
    status TEXT NOT NULL DEFAULT 'IN_PROGRESS' CHECK (status IN ('TODO', 'IN_PROGRESS', 'REVIEW', 'DONE')),
    logged_deadline DATE NULL,
    completion_pct REAL NOT NULL DEFAULT 0.00 CHECK (completion_pct >= 0.00 AND completion_pct <= 100.00),
    source_ref TEXT NOT NULL DEFAULT 'team_tasks.csv',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mapped_req_id) REFERENCES requirements (req_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_req_id ON tasks(mapped_req_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(logged_deadline);

-- ------------------------------------------------------------------------------
-- 6. Table: reconciliation_runs (Nhật ký các lần chạy đối soát tiến độ & mâu thuẫn)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reconciliation_runs (
    run_id TEXT NOT NULL PRIMARY KEY,
    reference_date DATE NOT NULL,
    coverage_ratio REAL NOT NULL DEFAULT 0.0000,
    total_requirements INTEGER NOT NULL DEFAULT 0,
    covered_requirements INTEGER NOT NULL DEFAULT 0,
    overdue_count INTEGER NOT NULL DEFAULT 0,
    conflict_count INTEGER NOT NULL DEFAULT 0,
    executed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_recon_exec_at ON reconciliation_runs(executed_at);
CREATE INDEX IF NOT EXISTS idx_recon_ref_date ON reconciliation_runs(reference_date);

-- ------------------------------------------------------------------------------
-- 7. Table: reconciled_items (Chi tiết kết quả đánh giá cho từng Requirement)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reconciled_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    req_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('FULLY_COVERED', 'PARTIALLY_COVERED', 'NOT_COVERED', 'OVERDUE', 'DEADLINE_CONFLICT')),
    risk_level TEXT NOT NULL DEFAULT 'LOW' CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    avg_completion REAL NOT NULL DEFAULT 0.00,
    days_remaining INTEGER NULL,
    owners TEXT NOT NULL, -- JSON array
    date_conflicts TEXT NOT NULL, -- JSON array
    citations TEXT NOT NULL, -- JSON array
    FOREIGN KEY (run_id) REFERENCES reconciliation_runs (run_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (req_id) REFERENCES requirements (req_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_recon_items_run ON reconciled_items(run_id);
CREATE INDEX IF NOT EXISTS idx_recon_items_req ON reconciled_items(req_id);
CREATE INDEX IF NOT EXISTS idx_recon_items_risk ON reconciled_items(risk_level);
CREATE INDEX IF NOT EXISTS idx_recon_items_state ON reconciled_items(state);

-- ------------------------------------------------------------------------------
-- 8. Table: chat_sessions (Phiên hội thoại trao đổi của người dùng)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT NOT NULL PRIMARY KEY,
    session_name TEXT NOT NULL DEFAULT 'Phiên làm việc mới',
    active_mode TEXT NOT NULL DEFAULT 'gemini' CHECK (active_mode IN ('offline', 'ollama', 'gemini')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_session_updated ON chat_sessions(updated_at);

-- ------------------------------------------------------------------------------
-- 9. Table: chat_messages (Từng lượt trao đổi câu hỏi & phản hồi trả lời)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT NOT NULL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    route_type TEXT NOT NULL DEFAULT 'QA_FLOW',
    grounding_score REAL NOT NULL DEFAULT 0.000,
    selected_docs TEXT NULL, -- JSON array
    citations TEXT NULL, -- JSON array
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_msg_session_time ON chat_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_msg_route ON chat_messages(route_type);

-- ------------------------------------------------------------------------------
-- 10. Table: citation_claims (Nhật ký xác thực tính trung thực của từng câu phát biểu)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS citation_claims (
    claim_id TEXT NOT NULL PRIMARY KEY,
    message_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    cited_doc_id TEXT NOT NULL,
    cited_page INTEGER NOT NULL,
    cited_start_line INTEGER NULL,
    cited_end_line INTEGER NULL,
    evidence_quote TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'UNGROUNDED_QUOTE' CHECK (verification_status IN (
        'VERIFIED_EXACT', 'VERIFIED_SUBSTRING', 'VERIFIED_TOKEN_LCS', 
        'VERIFIED_FUZZY', 'UNGROUNDED_QUOTE', 'HALLUCINATED_CLAIM', 'OUT_OF_BOUNDS'
    )),
    match_score REAL NOT NULL DEFAULT 0.000,
    matched_span TEXT NULL,
    doc_version TEXT NOT NULL DEFAULT 'v1',
    doc_hash TEXT NOT NULL DEFAULT '',
    verified_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES chat_messages (message_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (cited_doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_claims_message ON citation_claims(message_id);
CREATE INDEX IF NOT EXISTS idx_claims_doc_page ON citation_claims(cited_doc_id, cited_page);
CREATE INDEX IF NOT EXISTS idx_claims_status ON citation_claims(verification_status);

-- ------------------------------------------------------------------------------
-- 11. Table: email_drafts (Bản nháp email được sinh kèm mã bảo vệ HMAC Tamper-Proof)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_drafts (
    draft_id TEXT NOT NULL PRIMARY KEY,
    session_id TEXT NULL,
    recipient_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    attachment_ids TEXT NOT NULL, -- JSON array
    citations TEXT NOT NULL, -- JSON array
    current_state TEXT NOT NULL DEFAULT 'PENDING_APPROVAL' CHECK (current_state IN (
        'IDLE', 'AWAITING_CLARIFICATION', 'PENDING_APPROVAL', 'APPROVED', 'SENT', 'FAILED_RETRYABLE'
    )),
    payload_hash TEXT NOT NULL,
    hmac_signature TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_email_state ON email_drafts(current_state);
CREATE INDEX IF NOT EXISTS idx_email_recipient ON email_drafts(recipient_email);
CREATE INDEX IF NOT EXISTS idx_email_created_at ON email_drafts(created_at);

-- ------------------------------------------------------------------------------
-- 12. Table: email_audit_logs (Audit Log bất biến ghi nhận mọi bước chuyển trạng thái FSM)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    trigger_event TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    is_tampered INTEGER NOT NULL DEFAULT 0,
    details TEXT NULL, -- JSON object
    recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (draft_id) REFERENCES email_drafts (draft_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audit_draft_time ON email_audit_logs(draft_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_audit_tampered ON email_audit_logs(is_tampered);
