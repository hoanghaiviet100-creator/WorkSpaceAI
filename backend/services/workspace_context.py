"""Separate local document libraries for the workspace IDs used by the React app."""
from dataclasses import dataclass
from pathlib import Path
import re
from threading import RLock
from typing import Dict, Optional

from backend.repositories.workspace_repository import WorkspaceRepository, workspace_repository
from backend.repositories.draft_repository import DraftRepository, draft_repository
from backend.services.document_service import DocumentService, document_service
from backend.services.qa_service import QAService, qa_service
from backend.services.email_service import EmailService, email_service


@dataclass
class WorkspaceServices:
    repository: WorkspaceRepository
    documents: DocumentService
    qa: QAService
    drafts: DraftRepository
    email: EmailService
    is_default: bool = False


_contexts: Dict[str, WorkspaceServices] = {}
_context_lock = RLock()
_library_root: Optional[Path] = None


def configure_workspace_storage(root: Path) -> bool:
    """Enable durable libraries at app startup; direct/unit callers stay in memory."""
    global _library_root
    with _context_lock:
        restored = document_service.enable_local_storage(root / "midterm.json")
        for workspace_id, context in _contexts.items():
            if not context.is_default:
                context.documents.enable_local_storage(root / f"{workspace_id}.json")
                context.documents.save_library()
        _library_root = root
        return restored


def get_workspace_services(workspace_id: Optional[str] = None) -> WorkspaceServices:
    # Calls without a header retain the original Streamlit/API/test behavior.
    workspace_id = "midterm" if workspace_id is None else workspace_id
    if not isinstance(workspace_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", workspace_id):
        raise ValueError("Invalid workspace identifier.")
    with _context_lock:
        if workspace_id not in _contexts:
            if workspace_id == "midterm":
                _contexts[workspace_id] = WorkspaceServices(workspace_repository, document_service, qa_service, draft_repository, email_service, True)
            else:
                repository = WorkspaceRepository()
                drafts = DraftRepository()
                library_path = _library_root / f"{workspace_id}.json" if _library_root is not None else None
                _contexts[workspace_id] = WorkspaceServices(repository, DocumentService(repository, library_path), QAService(repository), drafts, EmailService(drafts, repository))
        return _contexts[workspace_id]


def resolve_workspace_services(value: object) -> WorkspaceServices:
    """Also support callers invoking a route function directly without FastAPI DI."""
    return value if isinstance(value, WorkspaceServices) else get_workspace_services(None)
