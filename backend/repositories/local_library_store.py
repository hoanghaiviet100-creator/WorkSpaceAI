"""Durable document metadata and evidence for the single-process local app."""
import json
import os
from pathlib import Path
import tempfile

from backend.core.schemas import DocumentChunk, DocumentMetadata
from backend.repositories.workspace_repository import WorkspaceRepository


class LocalLibraryStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def restore(self, repository: WorkspaceRepository) -> bool:
        """Validate the complete snapshot before replacing the in-memory library."""
        if not self.path.exists():
            return False
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("Unsupported saved document library version.")
        documents = [DocumentMetadata.model_validate(row) for row in data["documents"]]
        chunks = [DocumentChunk.model_validate(row) for row in data["chunks"]]
        by_id = {doc.doc_id: doc for doc in documents}
        if len(by_id) != len(documents) or any(chunk.doc_id not in by_id for chunk in chunks):
            raise ValueError("The saved document library has inconsistent document IDs.")
        repository.documents = by_id
        repository.chunks = chunks
        repository._rebuild_index()
        return True

    def save(self, repository: WorkspaceRepository) -> None:
        """Replace atomically so an interrupted write cannot truncate the last good copy."""
        data = {
            "version": 1,
            "documents": [doc.model_dump(mode="json") for doc in repository.documents.values()],
            "chunks": [chunk.model_dump(mode="json") for chunk in repository.chunks],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, suffix=".tmp", delete=False
            ) as handle:
                temporary = Path(handle.name)
                json.dump(data, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
