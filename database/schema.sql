-- ==============================================================================
-- WorkspaceAI - MySQL 8.4 Database Schema DDL
-- CSC10014 Track C - Intelligent Document Workspace with Evidence Grounding
-- Character Set: utf8mb4 | Collation: utf8mb4_unicode_ci | Engine: InnoDB
-- ==============================================================================

CREATE DATABASE IF NOT EXISTS `workspace_ai` 
    DEFAULT CHARACTER SET utf8mb4 
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE `workspace_ai`;

CREATE TABLE IF NOT EXISTS `users` (
    `user_id` CHAR(36) COLLATE utf8mb4_bin NOT NULL,
    `email` VARCHAR(254) COLLATE utf8mb4_0900_as_ci NOT NULL,
    `display_name` VARCHAR(255) NOT NULL,
    `password_hash` VARCHAR(255) NULL,
    `email_verified_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`user_id`),
    UNIQUE KEY `uq_users_email` (`email`)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `workspaces` (
    `workspace_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `name` VARCHAR(255) NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`workspace_id`)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `workspace_members` (
    `workspace_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `user_id` CHAR(36) COLLATE utf8mb4_bin NOT NULL,
    `role` ENUM('owner', 'editor', 'viewer') NOT NULL,
    `joined_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`workspace_id`, `user_id`),
    KEY `idx_workspace_members_user` (`user_id`, `workspace_id`),
    CONSTRAINT `fk_member_workspace` FOREIGN KEY (`workspace_id`)
        REFERENCES `workspaces` (`workspace_id`) ON DELETE CASCADE,
    CONSTRAINT `fk_member_user` FOREIGN KEY (`user_id`)
        REFERENCES `users` (`user_id`) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ------------------------------------------------------------------------------
-- 1. Table: documents (Metadata của tài liệu tải lên hoặc nạp sẵn)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `documents` (
    `workspace_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `doc_id` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
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
    `source_url` TEXT NULL,
    `headings` JSON NULL,
    `mime_type` VARCHAR(100) NOT NULL DEFAULT 'application/pdf',
    `uploaded_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `archived_at` DATETIME NULL,
    PRIMARY KEY (`workspace_id`, `doc_id`),
    UNIQUE KEY `uq_documents_file_hash` (`workspace_id`, `file_hash`),
    KEY `idx_documents_uploaded_at` (`workspace_id`, `uploaded_at`),
    CONSTRAINT `fk_document_workspace` FOREIGN KEY (`workspace_id`)
        REFERENCES `workspaces` (`workspace_id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 2. Table: document_pages (Nội dung thô theo từng trang phục vụ đối soát & highlight)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `document_pages` (
    `page_id` BIGINT UNSIGNED AUTO_INCREMENT,
    `workspace_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `doc_id` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    `page_number` INT UNSIGNED NOT NULL,
    `line_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `raw_text` MEDIUMTEXT NOT NULL COMMENT 'Toàn văn bản của trang giữ nguyên xuống dòng',
    `page_hash` CHAR(64) NOT NULL COMMENT 'SHA-256 checksum từng trang',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`page_id`),
    UNIQUE KEY `uq_doc_page` (`workspace_id`, `doc_id`, `page_number`),
    CONSTRAINT `chk_page_number` CHECK (`page_number` > 0),
    CONSTRAINT `fk_page_document` FOREIGN KEY (`workspace_id`, `doc_id`)
        REFERENCES `documents` (`workspace_id`, `doc_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 3. Table: document_chunks (Đoạn chunking vật lý phục vụ BM25 & Hybrid Vector RAG)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `document_chunks` (
    `workspace_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `chunk_id` VARCHAR(300) COLLATE utf8mb4_bin NOT NULL,
    `doc_id` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    `doc_name` VARCHAR(255) NOT NULL,
    `page_number` INT UNSIGNED NOT NULL DEFAULT 1,
    `start_line` INT UNSIGNED NOT NULL DEFAULT 1,
    `end_line` INT UNSIGNED NOT NULL DEFAULT 1,
    `section_header` VARCHAR(255) NOT NULL DEFAULT 'General',
    `text` MEDIUMTEXT NOT NULL COMMENT 'Nội dung chunk phục vụ retrieval và sinh trích dẫn',
    `chunk_hash` CHAR(64) NOT NULL,
    `token_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `doc_version` VARCHAR(20) NOT NULL DEFAULT 'v1',
    `embedding` JSON NULL COMMENT 'Vector lưu dưới dạng JSON mảng float',
    `embedding_encoder` VARCHAR(255) NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`workspace_id`, `chunk_id`),
    KEY `idx_chunks_locator` (`workspace_id`, `doc_id`, `page_number`, `start_line`, `end_line`),
    FULLTEXT KEY `ft_chunks_text_header` (`text`, `section_header`) /*!50100 WITH PARSER `ngram` */,
    CONSTRAINT `chk_chunk_lines` CHECK (`start_line` > 0 AND `end_line` >= `start_line`),
    CONSTRAINT `fk_chunk_page` FOREIGN KEY (`workspace_id`, `doc_id`, `page_number`)
        REFERENCES `document_pages` (`workspace_id`, `doc_id`, `page_number`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 4. Table: chat_sessions (Phiên hội thoại trao đổi của người dùng)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `chat_sessions` (
    `workspace_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `session_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `session_name` VARCHAR(255) NOT NULL DEFAULT 'Phiên làm việc mới',
    `active_mode` ENUM('offline', 'ollama', 'gemini') NOT NULL DEFAULT 'gemini',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`workspace_id`, `session_id`),
    KEY `idx_chat_session_updated` (`workspace_id`, `updated_at`),
    CONSTRAINT `fk_chat_session_workspace` FOREIGN KEY (`workspace_id`)
        REFERENCES `workspaces` (`workspace_id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 5. Table: chat_messages (Từng lượt trao đổi câu hỏi & phản hồi trả lời)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `chat_messages` (
    `workspace_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `message_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `session_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `role` ENUM('user', 'assistant', 'system') NOT NULL,
    `content` MEDIUMTEXT NOT NULL,
    `route_type` VARCHAR(50) NOT NULL DEFAULT 'QA_FLOW',
    `grounding_score` DECIMAL(4,3) NOT NULL DEFAULT 0.000,
    `selected_docs` JSON NULL COMMENT 'Mảng doc_id được lọc tại lượt hỏi này',
    `citations` JSON NULL COMMENT 'Mảng trích dẫn thô đính kèm',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`workspace_id`, `message_id`),
    KEY `idx_chat_msg_session_time` (`workspace_id`, `session_id`, `created_at`, `message_id`),
    CONSTRAINT `fk_chat_msg_session` FOREIGN KEY (`workspace_id`, `session_id`)
        REFERENCES `chat_sessions` (`workspace_id`, `session_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 6. Table: citation_claims (Nhật ký xác thực tính trung thực của từng câu phát biểu)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `citation_claims` (
    `workspace_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `claim_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `message_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `claim_text` TEXT NOT NULL,
    `cited_doc_id` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
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
    `semantic_status` ENUM('SUPPORTED', 'CONTRADICTED', 'INSUFFICIENT', 'UNAVAILABLE') NULL,
    `match_score` DECIMAL(4,3) NOT NULL DEFAULT 0.000,
    `matched_span` TEXT NULL,
    `doc_version` VARCHAR(20) NOT NULL DEFAULT 'v1',
    `doc_hash` CHAR(64) NOT NULL DEFAULT '',
    `verified_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`workspace_id`, `claim_id`),
    KEY `idx_claims_message` (`workspace_id`, `message_id`),
    KEY `idx_claims_doc_page` (`workspace_id`, `cited_doc_id`, `cited_page`),
    CONSTRAINT `chk_citation_lines` CHECK (
        (`cited_start_line` IS NULL AND `cited_end_line` IS NULL)
        OR (`cited_start_line` IS NOT NULL AND `cited_end_line` IS NOT NULL
            AND `cited_start_line` > 0 AND `cited_end_line` >= `cited_start_line`)
    ),
    CONSTRAINT `fk_claims_message` FOREIGN KEY (`workspace_id`, `message_id`)
        REFERENCES `chat_messages` (`workspace_id`, `message_id`) ON DELETE CASCADE,
    CONSTRAINT `fk_claim_page` FOREIGN KEY (`workspace_id`, `cited_doc_id`, `cited_page`)
        REFERENCES `document_pages` (`workspace_id`, `doc_id`, `page_number`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 7. Table: email_drafts (Bản nháp và dấu kiểm tra nội dung đã duyệt)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `email_drafts` (
    `workspace_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `draft_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `session_id` VARCHAR(64) COLLATE utf8mb4_bin NULL,
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
        'FAILED_RETRYABLE',
        'DRAFT',
        'FAILED',
        'DELIVERY_UNKNOWN'
    ) NOT NULL DEFAULT 'PENDING_APPROVAL',
    `payload_hash` CHAR(64) NULL COMMENT 'SHA-256 của nội dung được duyệt',
    `hmac_signature` VARCHAR(128) NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `sent_at` DATETIME NULL,
    PRIMARY KEY (`workspace_id`, `draft_id`),
    KEY `idx_email_created_at` (`workspace_id`, `created_at`),
    CONSTRAINT `fk_email_workspace` FOREIGN KEY (`workspace_id`)
        REFERENCES `workspaces` (`workspace_id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_email_session` FOREIGN KEY (`workspace_id`, `session_id`)
        REFERENCES `chat_sessions` (`workspace_id`, `session_id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 8. Table: email_audit_logs (Nhật ký chuyển trạng thái của bản nháp)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `email_audit_logs` (
    `log_id` BIGINT UNSIGNED AUTO_INCREMENT,
    `workspace_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `draft_id` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    `from_state` VARCHAR(50) NOT NULL,
    `to_state` VARCHAR(50) NOT NULL,
    `trigger_event` VARCHAR(100) NOT NULL,
    `actor` VARCHAR(100) NOT NULL DEFAULT 'system' COMMENT 'user_ui, system_agent, cron',
    `is_tampered` BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Bật cờ nếu phát hiện hash/HMAC không khớp',
    `details` JSON NULL,
    `recorded_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`log_id`),
    KEY `idx_audit_draft_time` (`workspace_id`, `draft_id`, `recorded_at`),
    CONSTRAINT `fk_audit_draft_id` FOREIGN KEY (`workspace_id`, `draft_id`)
        REFERENCES `email_drafts` (`workspace_id`, `draft_id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
