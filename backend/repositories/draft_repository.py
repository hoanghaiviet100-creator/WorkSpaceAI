from typing import Dict, List, Optional
from backend.core.schemas import EmailDraftPayload


class DraftRepository:
    """
    R3 Data Access Layer for Email Drafts:
    Stores pending and approved email drafts in memory for human-in-the-loop review.
    """

    def __init__(self) -> None:
        self._store: Dict[str, EmailDraftPayload] = {}

    def save(self, draft: EmailDraftPayload) -> EmailDraftPayload:
        """Stores or updates an email draft."""
        self._store[draft.draft_id] = draft
        return draft

    def get(self, draft_id: str) -> Optional[EmailDraftPayload]:
        """Retrieves an email draft by its unique draft_id."""
        return self._store.get(draft_id)

    def delete(self, draft_id: str) -> bool:
        """Removes a draft by draft_id. Returns True if removed, False if not found."""
        if draft_id in self._store:
            del self._store[draft_id]
            return True
        return False

    def list_all(self) -> List[EmailDraftPayload]:
        """Returns all currently stored drafts."""
        return list(self._store.values())

    def clear(self) -> None:
        """Clears all drafts (useful for testing)."""
        self._store.clear()


# Singleton instance for application access
draft_repository = DraftRepository()
