"""Find additional notebook passages using the private research service."""

import logging
import math
import os

import httpx

from backend.core.schemas import DocumentChunk
from backend.repositories.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)


class ResearchIndex:
    def __init__(self, workspace_id: str, repository: WorkspaceRepository):
        self.workspace_id = workspace_id
        self.repository = repository

    def search(self, query: str, top_k: int, selected_ids: list[str] | None) -> list[DocumentChunk]:
        url = os.getenv("WORKSPACE_RESEARCH_URL")
        if not url or not query.strip() or top_k < 1:
            return []
        if selected_ids is None:
            selected_ids = self.repository.get_selected_doc_ids() or list(self.repository.documents)
        originals = {}
        for source in selected_ids:
            for chunk in self.repository.get_document_chunks(source):
                if chunk.text.strip():
                    originals.setdefault(chunk.doc_id, {})[chunk.chunk_id] = chunk
        if not originals:
            return []
        documents = [{
            "id": doc_id,
            "title": next(iter(chunks.values())).doc_name,
            "chunks": [{"id": c.chunk_id, "text": c.text, "start": c.start_line, "end": c.end_line}
                       for c in chunks.values()],
        } for doc_id, chunks in originals.items()]
        try:
            with httpx.Client(timeout=httpx.Timeout(30, connect=2), trust_env=False) as client:
                response = client.post(url, json={
                    "workspace": self.workspace_id, "query": query, "limit": min(top_k, 20), "documents": documents,
                }).raise_for_status()
            hits = []
            seen = set()
            for row in response.json()["hits"]:
                key = (row["document_id"], row["chunk_id"])
                chunk = originals.get(key[0], {}).get(key[1])
                score = float(row["score"])
                if chunk is not None and key not in seen and math.isfinite(score) and 0 < score <= 1:
                    hits.append(chunk.model_copy(update={"score": score, "dense_score": score}))
                    seen.add(key)
            return hits[:top_k]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            logger.warning("Research index unavailable (%s); continuing with notebook search", type(error).__name__)
            return []
