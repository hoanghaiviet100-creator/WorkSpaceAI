"""Serve the upstream hybrid index using only chunks WorkspaceAI selected."""

import hashlib
from threading import Lock

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.dependencies import SessionDep
from modules.chunks.models import Chunk
from modules.documents.models import Document, DocumentStatus, DocumentType
from modules.embedding.active import active_index, require_active_index
from modules.embedding.choose import lock_chosen
from modules.workspaces.models import Workspace
from shared.search import retrieve
from worker.ingestion.chunking import Passage
from worker.ingestion.indexing import embed_passages, replace_chunks

router = APIRouter()
index_lock = Lock()


class SourceChunk(BaseModel):
    id: str
    text: str
    start: int
    end: int


class SourceDocument(BaseModel):
    id: str
    title: str
    chunks: list[SourceChunk]


class SearchRequest(BaseModel):
    workspace: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    query: str = Field(min_length=1, max_length=8000)
    limit: int = Field(ge=1, le=20)
    documents: list[SourceDocument] = Field(min_length=1)


@router.post("/workspaceai/search", include_in_schema=False)
def search(request: SearchRequest, session: SessionDep):
    with index_lock:
        if active_index(session) is None:
            lock_chosen(session, None)
        index = require_active_index(session)
        name = f"workspaceai-index:{request.workspace}"
        workspace = session.scalar(select(Workspace).where(Workspace.name == name))
        if workspace is None:
            workspace = Workspace(name=name)
            session.add(workspace)
            session.flush()

        existing = {d.document_metadata["id"]: d for d in workspace.documents if d.document_metadata}
        selected = {}
        for source in request.documents:
            revision = hashlib.sha256(source.model_dump_json().encode()).hexdigest()
            document = existing.pop(source.id, None)
            if document is None:
                document = Document(workspace_id=workspace.id, title=source.title, document_type=DocumentType.NOTE)
                session.add(document)
                session.flush()
            if document.content_hash != revision:
                passages = [Passage(c.text, c.start, c.end) for c in source.chunks]
                replace_chunks(session, document, index, passages, embed_passages(index, passages))
                document.title = source.title
                document.content_hash = revision
                document.document_metadata = {"id": source.id, "chunks": [c.id for c in source.chunks]}
                document.status = DocumentStatus.READY
            selected[document.id] = document.document_metadata
        for document in existing.values():
            session.delete(document)
        session.flush()

        hits = retrieve(session, workspace.id, request.query, request.limit, document_ids=list(selected))
        positions = dict(session.execute(select(Chunk.id, Chunk.position).where(
            Chunk.id.in_([hit.chunk_id for hit in hits]),
        )).all())
        result = [{
            "document_id": selected[hit.document_id]["id"],
            "chunk_id": selected[hit.document_id]["chunks"][positions[hit.chunk_id]],
            "score": hit.score,
        } for hit in hits]
        session.commit()
        return {"hits": result}
