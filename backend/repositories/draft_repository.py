"""
backend/repositories/draft_repository.py
R3 Data Access Layer for Email Drafts.

Stores EmailDraftRecord (and legacy EmailDraftPayload) objects in-memory with CRUD operations:
- save()
- get()
- list_by_workspace()
- list_all()
- delete()
- clear()

Automatically sets UUID primary keys and audit timestamps.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import uuid
from uuid import UUID

from backend.core.schemas import EmailDraftPayload, EmailDraftRecord


class DraftRepository:
    """
    R3 Data Access Layer for Email Drafts:
    Stores pending, approved, sent, and failed drafts in memory with full audit tracking.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    def save(self, draft: Union[EmailDraftRecord, EmailDraftPayload, Any]) -> Any:
        """
        Stores or updates an email draft record.
        Automatically generates a UUID id if missing and populates audit_timestamp.
        """
        # Assign UUID if missing on EmailDraftRecord
        if hasattr(draft, "id") and getattr(draft, "id", None) is None:
            draft.id = uuid.uuid4()
        elif isinstance(draft, dict) and not draft.get("id") and not draft.get("draft_id"):
            draft["id"] = uuid.uuid4()

        # Update or set audit_timestamp
        if hasattr(draft, "audit_timestamp") and not getattr(draft, "audit_timestamp", None):
            draft.audit_timestamp = datetime.now(timezone.utc)

        # Resolve primary key (id for EmailDraftRecord, draft_id for legacy EmailDraftPayload)
        key = str(getattr(draft, "id", None) or getattr(draft, "draft_id", ""))
        if not key:
            # Fallback to generated uuid
            generated_id = uuid.uuid4()
            if hasattr(draft, "id"):
                draft.id = generated_id
            key = str(generated_id)

        self._store[key] = draft
        return draft

    def get(self, draft_id: Union[UUID, str]) -> Optional[Any]:
        """Retrieves an email draft by its unique id or draft_id string."""
        return self._store.get(str(draft_id))

    def list_by_workspace(self, workspace_id: Union[UUID, str]) -> List[Any]:
        """Returns all email draft records belonging to a given workspace_id."""
        target_ws = str(workspace_id)
        return [
            d for d in self._store.values()
            if str(getattr(d, "workspace_id", None) or (d.get("workspace_id") if isinstance(d, dict) else "")) == target_ws
        ]

    def list_all(self) -> List[Any]:
        """Returns all currently stored drafts."""
        return list(self._store.values())

    def delete(self, draft_id: Union[UUID, str]) -> bool:
        """Removes a draft by id. Returns True if removed, False if not found."""
        key = str(draft_id)
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear(self) -> None:
        """Clears all drafts from in-memory storage."""
        self._store.clear()


# Singleton instance for application access
draft_repository = DraftRepository()
