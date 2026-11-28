"""Isolated atomic library snapshots; derived vector caches retain encoder identity."""
import json
import os
import threading
from pathlib import Path
import numpy as np
from backend.core.schemas import DocumentChunk, DocumentMetadata

_lock = threading.RLock()

def location():
    name = os.getenv('F1_STORE_PATH')
    if not name: return None
    path=Path(name)
    if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu':
        from backend.providers.embedding_provider import embedding_provider
        return path.parent/'indexes'/embedding_provider.index_id.replace(':','-')/path.name
    return path

def save(repository):
    path = location()
    if not path:
        return
    with _lock, repository._embedding_lock:
        data = dict(format=1, documents=[d.model_dump() for d in repository.documents.values()],
            chunks=[c.model_dump() for c in repository.chunks],
            dimensions=repository._embedding_dimensions,
            embeddings=[dict(key=list(k), value=np.asarray(v).tolist()) for k,v in repository._chunk_embeddings.items()])
        if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu':
            from backend.providers.embedding_provider import embedding_provider
            data['encoder_identity']=embedding_provider.index_identity
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        temporary.replace(path)

def load(repository):
    path = location()
    if not path or not path.exists():
        return
    with _lock:
        data=json.loads(path.read_text(encoding='utf-8'))
        if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu':
            from backend.providers.embedding_provider import embedding_provider
            if data.get('encoder_identity')!=embedding_provider.index_identity:
                raise ValueError('Encoder identity mismatch; rebuild from original documents')
        if data.get('format') != 1:
            raise ValueError('Unsupported library format')
        documents={d.doc_id:d for d in map(DocumentMetadata.model_validate,data['documents'])}
        chunks=list(map(DocumentChunk.model_validate,data['chunks']))
        if any(c.doc_id not in documents or c.doc_hash != documents[c.doc_id].file_hash or c.doc_version != documents[c.doc_id].version_id for c in chunks):
            raise ValueError('Library provenance mismatch')
        repository.documents=documents; repository.chunks=chunks
        repository._chunk_embeddings={tuple(row['key']):np.asarray(row['value'],dtype=np.float32) for row in data['embeddings']}
        repository._embedding_dimensions=data['dimensions']; repository._rebuild_index()


def retain_original(content):
    import hashlib
    base=Path(os.environ['F1_STORE_PATH']).parent/'originals'
    base.mkdir(parents=True,exist_ok=True)
    target=base/hashlib.sha256(content).hexdigest()
    try:
        with target.open('xb') as handle: handle.write(content)
    except FileExistsError:
        if target.read_bytes()!=content: raise ValueError('Original document hash collision')
