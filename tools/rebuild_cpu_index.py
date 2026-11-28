"""Rebuild a separate encoder index using hash-verified original documents."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def rebuild(source, originals, destination):
    from backend.core.schemas import DocumentMetadata
    from backend.providers.embedding_provider import embedding_provider
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.services.document_service import DocumentService
    from backend.services.f1_session_store import save, location
    if os.getenv('F1_EMBEDDING_BACKEND')!='fastembed_cpu': raise ValueError('CPU encoder must be configured')
    source=Path(source).resolve();destination=Path(destination).resolve()
    os.environ['F1_STORE_PATH']=str(destination)
    target=location()
    if source==target.resolve() or target.exists(): raise ValueError('Destination exists; choose a new versioned index')
    data=json.loads(source.read_text(encoding='utf-8'))
    known={}
    for directory in originals:
        for path in Path(directory).rglob('*'):
            if path.is_file() and path.stat().st_size<=25*1024**2:
                known[hashlib.sha256(path.read_bytes()).hexdigest()]=path
    missing=[d['doc_id'] for d in data['documents'] if d['file_hash'] not in known]
    if missing: raise ValueError('Missing original documents; old index was preserved: '+', '.join(missing))
    repo=WorkspaceRepository(embedding_provider.get_embed_fn()); service=DocumentService(repo)
    for row in data['documents']:
        doc=DocumentMetadata.model_validate(row); content=known[doc.file_hash].read_bytes()
        if doc.file_type=='csv': raise ValueError('Re-upload structured CSV documents through their original workflow')
        pages=service.parse_pdf_pages(doc.doc_name,content) if doc.file_type=='pdf' else service.parse_text_pages(content)
        chunks=[chunk for page,text in pages for chunk in service.build_page_chunks(doc.doc_id,doc.doc_name,page,text,doc.version_id,doc.file_hash)]
        repo.add_document(doc,chunks)
    save(repo)
    print(json.dumps(dict(index_id=embedding_provider.index_id,path=str(target),documents=len(repo.documents),chunks=len(repo.chunks))))
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--originals',action='append',required=True);parser.add_argument('--destination',required=True)
    args=parser.parse_args();rebuild(args.source,args.originals,args.destination)
