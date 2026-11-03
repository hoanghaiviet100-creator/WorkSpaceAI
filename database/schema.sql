-- ==============================================================================
-- WorkspaceAI v2.5 - Enterprise MySQL 8.0+ Database Schema DDL
-- CSC10014 Track C - Intelligent Document Workspace with Evidence Grounding
-- Character Set: utf8mb4 | Collation: utf8mb4_unicode_ci | Engine: InnoDB
-- ==============================================================================

CREATE DATABASE IF NOT EXISTS `workspace_ai` 
    DEFAULT CHARACTER SET utf8mb4 
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE `workspace_ai`;

-- ------------------------------------------------------------------------------
-- 1. Table: documents (Metadata của tài liệu tải lên hoặc nạp sẵn)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `documents` (
    `doc_id` VARCHAR(100) NOT NULL,
    `doc_name` VARCHAR(255) NOT NULL,
    `file_type` VARCHAR(20) NOT NULL DEFAULT 'pdf',
    `file_size_bytes` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `file_hash` CHAR(64) NOT NULL COMMENT 'SHA-256 checksum chống trùng lặp nội dung',
    `version_id` VARCHAR(20) NOT NULL DEFAULT 'v1',
    `total_pages` INT UNSIGNED NOT NULL DEFAULT 1,
    `total_lines` INT UNSIGNED NOT NULL DEFAULT 0,
    `total_chunks` INT UNSIGNED NOT NULL DEFAULT 0,
    `is_selected` BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Tick chọn active trong Document Library',
    `storage_path` VARCHAR(500) NULL COMMENT 'Đường dẫn file trên disk hoặc object storage',
    `mime_type` VARCHAR(100) NOT NULL DEFAULT 'application/pdf',
    `uploaded_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`doc_id`),
    UNIQUE KEY `uq_documents_file_hash` (`file_hash`),
    KEY `idx_documents_name` (`doc_name`),
    KEY `idx_documents_is_selected` (`is_selected`),
    KEY `idx_documents_uploaded_at` (`uploaded_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 2. Table: document_pages (Nội dung thô theo từng trang phục vụ đối soát & highlight)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `document_pages` (
    `page_id` BIGINT UNSIGNED AUTO_INCREMENT,
    `doc_id` VARCHAR(100) NOT NULL,
    `page_number` INT UNSIGNED NOT NULL,
    `line_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `raw_text` MEDIUMTEXT NOT NULL COMMENT 'Toàn văn bản của trang giữ nguyên xuống dòng',
    `page_hash` CHAR(64) NOT NULL COMMENT 'SHA-256 checksum từng trang',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`page_id`),
    UNIQUE KEY `uq_doc_page` (`doc_id`, `page_number`),
    KEY `idx_page_lookup` (`doc_id`, `page_number`),
    CONSTRAINT `fk_pages_doc_id` FOREIGN KEY (`doc_id`) 
        REFERENCES `documents` (`doc_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 3. Table: document_chunks (Đoạn chunking vật lý phục vụ BM25 & Hybrid Vector RAG)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `document_chunks` (
    `chunk_id` VARCHAR(120) NOT NULL,
    `doc_id` VARCHAR(100) NOT NULL,
    `doc_name` VARCHAR(255) NOT NULL,
    `page_number` INT UNSIGNED NOT NULL DEFAULT 1,
    `start_line` INT UNSIGNED NOT NULL DEFAULT 1,
    `end_line` INT UNSIGNED NOT NULL DEFAULT 1,
    `section_header` VARCHAR(255) NOT NULL DEFAULT 'General',
    `text` MEDIUMTEXT NOT NULL COMMENT 'Nội dung chunk phục vụ retrieval và sinh trích dẫn',
    `chunk_hash` CHAR(64) NOT NULL,
    `token_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `doc_version` VARCHAR(20) NOT NULL DEFAULT 'v1',
    `embedding` JSON NULL COMMENT 'Vector 384/768-d lưu dạng JSON mảng float',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`chunk_id`),
    KEY `idx_chunks_doc_id` (`doc_id`),
    KEY `idx_chunks_locator` (`doc_id`, `page_number`, `start_line`, `end_line`),
    FULLTEXT KEY `ft_chunks_text_header` (`text`, `section_header`) /*!50100 WITH PARSER `ngram` */,
    CONSTRAINT `fk_chunks_doc_id` FOREIGN KEY (`doc_id`) 
        REFERENCES `documents` (`doc_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 4. Table: requirements (Danh mục yêu cầu/tiêu chí từ đề bài hoặc bóc tách tự động)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `requirements` (
    `req_id` VARCHAR(50) NOT NULL,
    `doc_id` VARCHAR(100) NULL COMMENT 'Tài liệu nguồn chứa requirement',
    `title` VARCHAR(255) NOT NULL,
    `description` TEXT NULL,
    `keywords` JSON NOT NULL COMMENT 'Mảng từ khóa phục vụ mapping với task',
    `official_deadline` DATE NULL COMMENT 'Hạn chót chính thức trong đề bài',
    `mandatory_flag` BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Yêu cầu bắt buộc hay tự chọn',
    `source_ref` VARCHAR(255) NOT NULL COMMENT 'Tọa độ nguồn ví dụ: Project_Brief.pdf:P6:L10-15',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`req_id`),
    KEY `idx_req_doc_id` (`doc_id`),
    KEY `idx_req_deadline` (`official_deadline`),
    KEY `idx_req_mandatory` (`mandatory_flag`),
    CONSTRAINT `fk_req_doc_id` FOREIGN KEY (`doc_id`) 
        REFERENCES `documents` (`doc_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 5. Table: tasks (Bảng công việc Kanban của nhóm)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `tasks` (
    `task_id` VARCHAR(50) NOT NULL,
    `mapped_req_id` VARCHAR(50) NULL COMMENT 'Mã yêu cầu được ánh xạ',
    `title` VARCHAR(255) NOT NULL,
    `owner` VARCHAR(100) NULL COMMENT 'Thành viên phụ trách',
    `status` ENUM('TODO', 'IN_PROGRESS', 'REVIEW', 'DONE') NOT NULL DEFAULT 'IN_PROGRESS',
    `logged_deadline` DATE NULL COMMENT 'Hạn chót nhóm tự ghi nhận',
    `completion_pct` DECIMAL(5,2) NOT NULL DEFAULT 0.00 COMMENT 'Tiến độ 0.00 - 100.00',
    `source_ref` VARCHAR(255) NOT NULL DEFAULT 'team_tasks.csv' COMMENT 'Nguồn import task',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`task_id`),
    KEY `idx_tasks_req_id` (`mapped_req_id`),
    KEY `idx_tasks_status` (`status`),
    KEY `idx_tasks_owner` (`owner`),
    KEY `idx_tasks_deadline` (`logged_deadline`),
    CONSTRAINT `chk_completion_pct` CHECK (`completion_pct` >= 0.00 AND `completion_pct` <= 100.00),
    CONSTRAINT `fk_tasks_mapped_req` FOREIGN KEY (`mapped_req_id`) 
        REFERENCES `requirements` (`req_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 6. Table: reconciliation_runs (Nhật ký các lần chạy đối soát tiến độ & mâu thuẫn)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `reconciliation_runs` (
    `run_id` VARCHAR(64) NOT NULL,
    `reference_date` DATE NOT NULL COMMENT 'Ngày mốc dùng để tính quá hạn',
    `coverage_ratio` DECIMAL(5,4) NOT NULL DEFAULT 0.0000 COMMENT 'Tỷ lệ bao phủ 0.0000 - 1.0000',
    `total_requirements` INT UNSIGNED NOT NULL DEFAULT 0,
    `covered_requirements` INT UNSIGNED NOT NULL DEFAULT 0,
    `overdue_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `conflict_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `executed_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`run_id`),
    KEY `idx_recon_exec_at` (`executed_at`),
    KEY `idx_recon_ref_date` (`reference_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 7. Table: reconciled_items (Chi tiết kết quả đánh giá cho từng Requirement)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `reconciled_items` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT,
    `run_id` VARCHAR(64) NOT NULL,
    `req_id` VARCHAR(50) NOT NULL,
    `state` ENUM('FULLY_COVERED', 'PARTIALLY_COVERED', 'NOT_COVERED', 'OVERDUE', 'DEADLINE_CONFLICT') NOT NULL,
    `risk_level` ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL') NOT NULL DEFAULT 'LOW',
    `avg_completion` DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    `days_remaining` INT NULL COMMENT 'Số ngày còn lại so với ngày mốc (có thể âm nếu quá hạn)',
    `owners` JSON NOT NULL COMMENT 'Danh sách phụ trách dạng ["Bình", "An"]',
    `date_conflicts` JSON NOT NULL COMMENT 'Danh sách mâu thuẫn ngày [doc_a, date_a, doc_b, date_b]',
    `citations` JSON NOT NULL COMMENT 'Căn cứ trích dẫn chứng minh kết luận',
    PRIMARY KEY (`id`),
    KEY `idx_recon_items_run` (`run_id`),
    KEY `idx_recon_items_req` (`req_id`),
    KEY `idx_recon_items_risk` (`risk_level`),
    KEY `idx_recon_items_state` (`state`),
    CONSTRAINT `fk_recon_items_run` FOREIGN KEY (`run_id`) 
        REFERENCES `reconciliation_runs` (`run_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_recon_items_req` FOREIGN KEY (`req_id`) 
        REFERENCES `requirements` (`req_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 8. Table: chat_sessions (Phiên hội thoại trao đổi của người dùng)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `chat_sessions` (
    `session_id` VARCHAR(64) NOT NULL,
    `session_name` VARCHAR(255) NOT NULL DEFAULT 'Phiên làm việc mới',
    `active_mode` ENUM('offline', 'ollama', 'gemini') NOT NULL DEFAULT 'gemini',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`session_id`),
    KEY `idx_chat_session_updated` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 9. Table: chat_messages (Từng lượt trao đổi câu hỏi & phản hồi trả lời)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `chat_messages` (
    `message_id` VARCHAR(64) NOT NULL,
    `session_id` VARCHAR(64) NOT NULL,
    `role` ENUM('user', 'assistant', 'system') NOT NULL,
    `content` MEDIUMTEXT NOT NULL,
    `route_type` VARCHAR(50) NOT NULL DEFAULT 'QA_FLOW',
    `grounding_score` DECIMAL(4,3) NOT NULL DEFAULT 0.000,
    `selected_docs` JSON NULL COMMENT 'Mảng doc_id được lọc tại lượt hỏi này',
    `citations` JSON NULL COMMENT 'Mảng trích dẫn thô đính kèm',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`message_id`),
    KEY `idx_chat_msg_session_time` (`session_id`, `created_at`),
    KEY `idx_chat_msg_route` (`route_type`),
    CONSTRAINT `fk_chat_msg_session` FOREIGN KEY (`session_id`) 
        REFERENCES `chat_sessions` (`session_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 10. Table: citation_claims (Nhật ký xác thực tính trung thực của từng câu phát biểu)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `citation_claims` (
    `claim_id` VARCHAR(64) NOT NULL,
    `message_id` VARCHAR(64) NOT NULL,
    `claim_text` TEXT NOT NULL,
    `cited_doc_id` VARCHAR(100) NOT NULL,
    `cited_page` INT UNSIGNED NOT NULL,
    `cited_start_line` INT UNSIGNED NULL,
    `cited_end_line` INT UNSIGNED NULL,
    `evidence_quote` TEXT NOT NULL,
    `verification_status` ENUM(
        'VERIFIED_EXACT', 
        'VERIFIED_SUBSTRING', 
        'VERIFIED_TOKEN_LCS', 
        'VERIFIED_FUZZY', 
        'UNGROUNDED_QUOTE', 
        'HALLUCINATED_CLAIM', 
        'OUT_OF_BOUNDS'
    ) NOT NULL DEFAULT 'UNGROUNDED_QUOTE',
    `match_score` DECIMAL(4,3) NOT NULL DEFAULT 0.000,
    `matched_span` TEXT NULL,
    `doc_version` VARCHAR(20) NOT NULL DEFAULT 'v1',
    `doc_hash` CHAR(64) NOT NULL DEFAULT '',
    `verified_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`claim_id`),
    KEY `idx_claims_message` (`message_id`),
    KEY `idx_claims_doc_page` (`cited_doc_id`, `cited_page`),
    KEY `idx_claims_status` (`verification_status`),
    CONSTRAINT `fk_claims_message` FOREIGN KEY (`message_id`) 
        REFERENCES `chat_messages` (`message_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_claims_doc` FOREIGN KEY (`cited_doc_id`) 
        REFERENCES `documents` (`doc_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 11. Table: email_drafts (Bản nháp email được sinh kèm mã bảo vệ HMAC Tamper-Proof)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `email_drafts` (
    `draft_id` VARCHAR(64) NOT NULL,
    `session_id` VARCHAR(64) NULL,
    `recipient_email` VARCHAR(255) NOT NULL,
    `subject` VARCHAR(500) NOT NULL,
    `body` MEDIUMTEXT NOT NULL,
    `attachment_ids` JSON NOT NULL COMMENT 'Danh sách doc_id đính kèm',
    `citations` JSON NOT NULL COMMENT 'Danh sách trích dẫn căn cứ gửi kèm',
    `current_state` ENUM(
        'IDLE', 
        'AWAITING_CLARIFICATION', 
        'PENDING_APPROVAL', 
        'APPROVED', 
        'SENT', 
        'FAILED_RETRYABLE'
    ) NOT NULL DEFAULT 'PENDING_APPROVAL',
    `payload_hash` CHAR(64) NOT NULL COMMENT 'SHA-256(recipient|subject|body)',
    `hmac_signature` VARCHAR(128) NOT NULL COMMENT 'HMAC-SHA256 signature ngăn chặn giả mạo',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `sent_at` DATETIME NULL,
    PRIMARY KEY (`draft_id`),
    KEY `idx_email_state` (`current_state`),
    KEY `idx_email_recipient` (`recipient_email`),
    KEY `idx_email_created_at` (`created_at`),
    CONSTRAINT `fk_email_session` FOREIGN KEY (`session_id`) 
        REFERENCES `chat_sessions` (`session_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 12. Table: email_audit_logs (Audit Log bất biến ghi nhận mọi bước chuyển trạng thái FSM)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `email_audit_logs` (
    `log_id` BIGINT UNSIGNED AUTO_INCREMENT,
    `draft_id` VARCHAR(64) NOT NULL,
    `from_state` VARCHAR(50) NOT NULL,
    `to_state` VARCHAR(50) NOT NULL,
    `trigger_event` VARCHAR(100) NOT NULL,
    `actor` VARCHAR(100) NOT NULL DEFAULT 'system' COMMENT 'user_ui, system_agent, cron',
    `is_tampered` BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Bật cờ nếu phát hiện hash/HMAC không khớp',
    `details` JSON NULL,
    `recorded_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`log_id`),
    KEY `idx_audit_draft_time` (`draft_id`, `recorded_at`),
    KEY `idx_audit_tampered` (`is_tampered`),
    CONSTRAINT `fk_audit_draft_id` FOREIGN KEY (`draft_id`) 
        REFERENCES `email_drafts` (`draft_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
