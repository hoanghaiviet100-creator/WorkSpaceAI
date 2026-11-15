"""
backend/database/models.py
SQLAlchemy 2.0 ORM Models for WorkspaceAI running on SQLite (Local-First) & MySQL.
Maps 1:1 with database/schema.sql and database/schema_sqlite.sql.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional

try:
    from sqlalchemy import (
        BigInteger,
        Boolean,
        Column,
        Date as SqlDate,
        DateTime as SqlDateTime,
        Enum as SqlEnum,
        Float,
        ForeignKey,
        Index,
        Integer,
        JSON,
        Numeric,
        String,
        Text,
        text,
    )
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

    class DeclarativeBase:  # type: ignore
        pass

    def mapped_column(*args, **kwargs):  # type: ignore
        return None


if HAS_SQLALCHEMY:
    class Base(DeclarativeBase):
        """Root Declarative Base for WorkspaceAI Relational ORM (SQLite / MySQL)."""
        pass

    # --------------------------------------------------------------------------
    # 1. Documents (Metadata tài liệu nguồn)
    # --------------------------------------------------------------------------
    class DocumentModel(Base):
        __tablename__ = "documents"

        doc_id: Mapped[str] = mapped_column(String(100), primary_key=True)
        doc_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
        file_type: Mapped[str] = mapped_column(String(20), default="pdf", nullable=False)
        file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
        file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
        version_id: Mapped[str] = mapped_column(String(20), default="v1", nullable=False)
        total_pages: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
        total_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        is_selected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
        storage_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
        mime_type: Mapped[str] = mapped_column(String(100), default="application/pdf", nullable=False)
        uploaded_at: Mapped[datetime] = mapped_column(SqlDateTime, default=datetime.utcnow, nullable=False)
        updated_at: Mapped[datetime] = mapped_column(
            SqlDateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
        )

        # Relationships
        pages: Mapped[List["DocumentPageModel"]] = relationship(
            "DocumentPageModel", back_populates="document", cascade="all, delete-orphan"
        )
        chunks: Mapped[List["DocumentChunkModel"]] = relationship(
            "DocumentChunkModel", back_populates="document", cascade="all, delete-orphan"
        )
        requirements: Mapped[List["RequirementModel"]] = relationship(
            "RequirementModel", back_populates="source_document"
        )

    # --------------------------------------------------------------------------
    # 2. Document Pages (Toàn văn theo từng trang phục vụ đối soát & highlight)
    # --------------------------------------------------------------------------
    class DocumentPageModel(Base):
        __tablename__ = "document_pages"

        page_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
        doc_id: Mapped[str] = mapped_column(
            String(100), ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False, index=True
        )
        page_number: Mapped[int] = mapped_column(Integer, nullable=False)
        line_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        raw_text: Mapped[str] = mapped_column(Text, nullable=False)
        page_hash: Mapped[str] = mapped_column(String(64), nullable=False)
        created_at: Mapped[datetime] = mapped_column(SqlDateTime, default=datetime.utcnow, nullable=False)

        document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="pages")

    # --------------------------------------------------------------------------
    # 3. Document Chunks (Phục vụ BM25 & Hybrid Vector RAG)
    # --------------------------------------------------------------------------
    class DocumentChunkModel(Base):
        __tablename__ = "document_chunks"

        chunk_id: Mapped[str] = mapped_column(String(120), primary_key=True)
        doc_id: Mapped[str] = mapped_column(
            String(100), ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False, index=True
        )
        doc_name: Mapped[str] = mapped_column(String(255), nullable=False)
        page_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
        start_line: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
        end_line: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
        section_header: Mapped[str] = mapped_column(String(255), default="General", nullable=False)
        text: Mapped[str] = mapped_column(Text, nullable=False)
        chunk_hash: Mapped[str] = mapped_column(String(64), nullable=False)
        token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        doc_version: Mapped[str] = mapped_column(String(20), default="v1", nullable=False)
        embedding: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
        created_at: Mapped[datetime] = mapped_column(SqlDateTime, default=datetime.utcnow, nullable=False)

        document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="chunks")

    # --------------------------------------------------------------------------
    # 4. Requirements (Danh mục yêu cầu/tiêu chí từ đề bài)
    # --------------------------------------------------------------------------
    class RequirementModel(Base):
        __tablename__ = "requirements"

        req_id: Mapped[str] = mapped_column(String(50), primary_key=True)
        doc_id: Mapped[Optional[str]] = mapped_column(
            String(100), ForeignKey("documents.doc_id", ondelete="SET NULL"), nullable=True, index=True
        )
        title: Mapped[str] = mapped_column(String(255), nullable=False)
        description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
        keywords: Mapped[List[str]] = mapped_column(JSON, nullable=False)
        official_deadline: Mapped[Optional[date]] = mapped_column(SqlDate, nullable=True, index=True)
        mandatory_flag: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
        source_ref: Mapped[str] = mapped_column(String(255), nullable=False)
        created_at: Mapped[datetime] = mapped_column(SqlDateTime, default=datetime.utcnow, nullable=False)
        updated_at: Mapped[datetime] = mapped_column(
            SqlDateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
        )

        source_document: Mapped[Optional["DocumentModel"]] = relationship(
            "DocumentModel", back_populates="requirements"
        )
        tasks: Mapped[List["TaskModel"]] = relationship("TaskModel", back_populates="requirement")

    # --------------------------------------------------------------------------
    # 5. Tasks (Bảng công việc Kanban của nhóm)
    # --------------------------------------------------------------------------
    class TaskModel(Base):
        __tablename__ = "tasks"

        task_id: Mapped[str] = mapped_column(String(50), primary_key=True)
        mapped_req_id: Mapped[Optional[str]] = mapped_column(
            String(50), ForeignKey("requirements.req_id", ondelete="SET NULL"), nullable=True, index=True
        )
        title: Mapped[str] = mapped_column(String(255), nullable=False)
        owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
        status: Mapped[str] = mapped_column(
            SqlEnum("TODO", "IN_PROGRESS", "REVIEW", "DONE", name="task_status_enum"),
            default="IN_PROGRESS",
            nullable=False,
            index=True,
        )
        logged_deadline: Mapped[Optional[date]] = mapped_column(SqlDate, nullable=True, index=True)
        completion_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0.00, nullable=False)
        source_ref: Mapped[str] = mapped_column(String(255), default="team_tasks.csv", nullable=False)
        created_at: Mapped[datetime] = mapped_column(SqlDateTime, default=datetime.utcnow, nullable=False)
        updated_at: Mapped[datetime] = mapped_column(
            SqlDateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
        )

        requirement: Mapped[Optional["RequirementModel"]] = relationship(
            "RequirementModel", back_populates="tasks"
        )

    # --------------------------------------------------------------------------
    # 6. Reconciliation Runs (Lịch sử đối soát tiến độ)
    # --------------------------------------------------------------------------
    class ReconciliationRunModel(Base):
        __tablename__ = "reconciliation_runs"

        run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
        reference_date: Mapped[date] = mapped_column(SqlDate, nullable=False, index=True)
        coverage_ratio: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0000, nullable=False)
        total_requirements: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        covered_requirements: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        overdue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        conflict_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        executed_at: Mapped[datetime] = mapped_column(
            SqlDateTime, default=datetime.utcnow, nullable=False, index=True
        )

        items: Mapped[List["ReconciledItemModel"]] = relationship(
            "ReconciledItemModel", back_populates="run", cascade="all, delete-orphan"
        )

    # --------------------------------------------------------------------------
    # 7. Reconciled Items (Chi tiết đánh giá từng Requirement)
    # --------------------------------------------------------------------------
    class ReconciledItemModel(Base):
        __tablename__ = "reconciled_items"

        id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
        run_id: Mapped[str] = mapped_column(
            String(64), ForeignKey("reconciliation_runs.run_id", ondelete="CASCADE"), nullable=False, index=True
        )
        req_id: Mapped[str] = mapped_column(
            String(50), ForeignKey("requirements.req_id", ondelete="CASCADE"), nullable=False, index=True
        )
        state: Mapped[str] = mapped_column(
            SqlEnum(
                "FULLY_COVERED",
                "PARTIALLY_COVERED",
                "NOT_COVERED",
                "OVERDUE",
                "DEADLINE_CONFLICT",
                name="recon_item_state_enum",
            ),
            nullable=False,
            index=True,
        )
        risk_level: Mapped[str] = mapped_column(
            SqlEnum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="recon_risk_level_enum"),
            default="LOW",
            nullable=False,
            index=True,
        )
        avg_completion: Mapped[float] = mapped_column(Numeric(5, 2), default=0.00, nullable=False)
        days_remaining: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        owners: Mapped[List[str]] = mapped_column(JSON, nullable=False)
        date_conflicts: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, nullable=False)
        citations: Mapped[List[str]] = mapped_column(JSON, nullable=False)

        run: Mapped["ReconciliationRunModel"] = relationship("ReconciliationRunModel", back_populates="items")
        requirement: Mapped["RequirementModel"] = relationship("RequirementModel")

    # --------------------------------------------------------------------------
    # 8. Chat Sessions & Messages (Lịch sử hội thoại)
    # --------------------------------------------------------------------------
    class ChatSessionModel(Base):
        __tablename__ = "chat_sessions"

        session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
        session_name: Mapped[str] = mapped_column(String(255), default="Phiên làm việc mới", nullable=False)
        active_mode: Mapped[str] = mapped_column(
            SqlEnum("offline", "ollama", "gemini", name="chat_ai_mode_enum"),
            default="gemini",
            nullable=False,
        )
        created_at: Mapped[datetime] = mapped_column(SqlDateTime, default=datetime.utcnow, nullable=False)
        updated_at: Mapped[datetime] = mapped_column(
            SqlDateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True
        )

        messages: Mapped[List["ChatMessageModel"]] = relationship(
            "ChatMessageModel", back_populates="session", cascade="all, delete-orphan"
        )
        drafts: Mapped[List["EmailDraftModel"]] = relationship("EmailDraftModel", back_populates="session")

    class ChatMessageModel(Base):
        __tablename__ = "chat_messages"

        message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
        session_id: Mapped[str] = mapped_column(
            String(64), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True
        )
        role: Mapped[str] = mapped_column(
            SqlEnum("user", "assistant", "system", name="chat_role_enum"), nullable=False
        )
        content: Mapped[str] = mapped_column(Text, nullable=False)
        route_type: Mapped[str] = mapped_column(String(50), default="QA_FLOW", nullable=False, index=True)
        grounding_score: Mapped[float] = mapped_column(Numeric(4, 3), default=0.000, nullable=False)
        selected_docs: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
        citations: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
        created_at: Mapped[datetime] = mapped_column(
            SqlDateTime, default=datetime.utcnow, nullable=False, index=True
        )

        session: Mapped["ChatSessionModel"] = relationship("ChatSessionModel", back_populates="messages")
        claims: Mapped[List["CitationClaimModel"]] = relationship(
            "CitationClaimModel", back_populates="message", cascade="all, delete-orphan"
        )

    # --------------------------------------------------------------------------
    # 9. Citation Claims (Audit Log kiểm định trích dẫn)
    # --------------------------------------------------------------------------
    class CitationClaimModel(Base):
        __tablename__ = "citation_claims"

        claim_id: Mapped[str] = mapped_column(String(64), primary_key=True)
        message_id: Mapped[str] = mapped_column(
            String(64), ForeignKey("chat_messages.message_id", ondelete="CASCADE"), nullable=False, index=True
        )
        claim_text: Mapped[str] = mapped_column(Text, nullable=False)
        cited_doc_id: Mapped[str] = mapped_column(
            String(100), ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False
        )
        cited_page: Mapped[int] = mapped_column(Integer, nullable=False)
        cited_start_line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        cited_end_line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        evidence_quote: Mapped[str] = mapped_column(Text, nullable=False)
        verification_status: Mapped[str] = mapped_column(
            SqlEnum(
                "VERIFIED_EXACT",
                "VERIFIED_SUBSTRING",
                "VERIFIED_TOKEN_LCS",
                "VERIFIED_FUZZY",
                "UNGROUNDED_QUOTE",
                "HALLUCINATED_CLAIM",
                "OUT_OF_BOUNDS",
                name="verification_status_enum",
            ),
            default="UNGROUNDED_QUOTE",
            nullable=False,
            index=True,
        )
        match_score: Mapped[float] = mapped_column(Numeric(4, 3), default=0.000, nullable=False)
        matched_span: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
        doc_version: Mapped[str] = mapped_column(String(20), default="v1", nullable=False)
        doc_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
        verified_at: Mapped[datetime] = mapped_column(SqlDateTime, default=datetime.utcnow, nullable=False)

        message: Mapped["ChatMessageModel"] = relationship("ChatMessageModel", back_populates="claims")

    # --------------------------------------------------------------------------
    # 10. Email Drafts & Audit Logs (Email FSM & Tamper Protection)
    # --------------------------------------------------------------------------
    class EmailDraftModel(Base):
        __tablename__ = "email_drafts"

        draft_id: Mapped[str] = mapped_column(String(64), primary_key=True)
        session_id: Mapped[Optional[str]] = mapped_column(
            String(64), ForeignKey("chat_sessions.session_id", ondelete="SET NULL"), nullable=True
        )
        recipient_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
        subject: Mapped[str] = mapped_column(String(500), nullable=False)
        body: Mapped[str] = mapped_column(Text, nullable=False)
        attachment_ids: Mapped[List[str]] = mapped_column(JSON, nullable=False)
        citations: Mapped[List[str]] = mapped_column(JSON, nullable=False)
        current_state: Mapped[str] = mapped_column(
            SqlEnum(
                "IDLE",
                "AWAITING_CLARIFICATION",
                "PENDING_APPROVAL",
                "APPROVED",
                "SENT",
                "FAILED_RETRYABLE",
                name="email_state_enum",
            ),
            default="PENDING_APPROVAL",
            nullable=False,
            index=True,
        )
        payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
        hmac_signature: Mapped[str] = mapped_column(String(128), nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            SqlDateTime, default=datetime.utcnow, nullable=False, index=True
        )
        updated_at: Mapped[datetime] = mapped_column(
            SqlDateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
        )
        sent_at: Mapped[Optional[datetime]] = mapped_column(SqlDateTime, nullable=True)

        session: Mapped[Optional["ChatSessionModel"]] = relationship("ChatSessionModel", back_populates="drafts")
        audit_logs: Mapped[List["EmailAuditLogModel"]] = relationship(
            "EmailAuditLogModel", back_populates="draft", cascade="all, delete-orphan"
        )

    class EmailAuditLogModel(Base):
        __tablename__ = "email_audit_logs"

        log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
        draft_id: Mapped[str] = mapped_column(
            String(64), ForeignKey("email_drafts.draft_id", ondelete="CASCADE"), nullable=False, index=True
        )
        from_state: Mapped[str] = mapped_column(String(50), nullable=False)
        to_state: Mapped[str] = mapped_column(String(50), nullable=False)
        trigger_event: Mapped[str] = mapped_column(String(100), nullable=False)
        actor: Mapped[str] = mapped_column(String(100), default="system", nullable=False)
        is_tampered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
        details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
        recorded_at: Mapped[datetime] = mapped_column(SqlDateTime, default=datetime.utcnow, nullable=False)

        draft: Mapped["EmailDraftModel"] = relationship("EmailDraftModel", back_populates="audit_logs")

else:
    # Fallback placeholder models when SQLAlchemy is not installed
    class Base:  # type: ignore
        pass

    class DocumentModel: pass
    class DocumentPageModel: pass
    class DocumentChunkModel: pass
    class RequirementModel: pass
    class TaskModel: pass
    class ReconciliationRunModel: pass
    class ReconciledItemModel: pass
    class ChatSessionModel: pass
    class ChatMessageModel: pass
    class CitationClaimModel: pass
    class EmailDraftModel: pass
    class EmailAuditLogModel: pass
