"""
backend/Retrieval_R3.py
Backward-compatible forwarding stub for backend.repositories.workspace_repository.
Preserves legacy imports without maintaining duplicate indexing code.
"""
from backend.repositories.workspace_repository import (
    HybridWorkspaceIndex,
    WorkspaceRepository,
    workspace_repository,
)

__all__ = [
    "HybridWorkspaceIndex",
    "WorkspaceRepository",
    "workspace_repository",
]
