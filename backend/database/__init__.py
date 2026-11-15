"""
backend/database/__init__.py
Database Layer for WorkspaceAI (SQLite Local-First & MySQL).
Provides Connection Management, SQLAlchemy ORM Models, and Database Initializers.
"""
from backend.database.connection import get_db, get_engine, check_db_connection, check_mysql_connection
from backend.database.models import (
    Base,
    DocumentModel,
    DocumentPageModel,
    DocumentChunkModel,
    RequirementModel,
    TaskModel,
    ReconciliationRunModel,
    ReconciledItemModel,
    ChatSessionModel,
    ChatMessageModel,
    CitationClaimModel,
    EmailDraftModel,
    EmailAuditLogModel,
)

__all__ = [
    "get_db",
    "get_engine",
    "check_db_connection",
    "check_mysql_connection",
    "Base",
    "DocumentModel",
    "DocumentPageModel",
    "DocumentChunkModel",
    "RequirementModel",
    "TaskModel",
    "ReconciliationRunModel",
    "ReconciledItemModel",
    "ChatSessionModel",
    "ChatMessageModel",
    "CitationClaimModel",
    "EmailDraftModel",
    "EmailAuditLogModel",
]
