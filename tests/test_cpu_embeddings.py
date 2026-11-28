import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from backend.providers.cpu_embedding_provider import CPUEmbeddingProvider
from backend.providers.embedding_provider import EmbeddingError
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.f1_basic_qa import BasicQA
from backend.services.answer_messages import failure_message, vietnamese


def manifest(tmp_path):
    weights=tmp_path/'model.onnx'; weights.write_bytes(b'pinned test bytes')
    spec=dict(versions={},files={'model.onnx':hashlib.sha256(weights.read_bytes()).hexdigest()},dimension=3,
        model='controlled',query_prefix='Instruct: retrieve\nQuery:',document_prefix='',pooling='last')
    path=tmp_path/'encoder.json';path.write_text(json.dumps(spec))
    return path


def test_encoder_identity_changes_for_every_vector_policy(tmp_path):
    path=manifest(tmp_path); p=CPUEmbeddingProvider(path);identity=p.index_id
    for field,value in [('pooling','mean'),('query_prefix','query: '),('dimension',4)]:
        spec=json.loads(path.read_text());spec[field]=value;path.write_text(json.dumps(spec))
        with pytest.raises(EmbeddingError,match='MODEL_CHANGED'): p.verify_index(identity)
        assert CPUEmbeddingProvider(path).index_id!=identity


def test_modified_artifact_fails_before_cached_vector_use(tmp_path):
    p=CPUEmbeddingProvider(manifest(tmp_path)); identity=p.index_id
    (tmp_path/'model.onnx').write_bytes(b'modified artifact')
    with pytest.raises(EmbeddingError,match='hash mismatch'): p.verify_index(identity)


def test_cpu_provider_never_calls_ollama(tmp_path,monkeypatch):
    p=CPUEmbeddingProvider(manifest(tmp_path));seen=[]
    monkeypatch.setattr(p,'_exchange',lambda payload: seen.append(payload) or np.array([[1.,0.,0.]],dtype=np.float32))
    p.embed_texts(['source']);p.embed_queries(['question'])
    assert seen==[dict(texts=['source'],purpose='document'),dict(texts=['question'],purpose='query')]
    assert not p.using_ollama


def test_cpu_store_is_separate_and_old_index_unchanged(tmp_path,monkeypatch):
    import backend.providers.embedding_provider as module
    # The providers package also exports the provider instance; import the module explicitly.
    import importlib
    module=importlib.import_module('backend.providers.embedding_provider')
    from backend.services.f1_session_store import location,save,load
    p=CPUEmbeddingProvider(manifest(tmp_path));monkeypatch.setattr(module,'embedding_provider',p)
    old=tmp_path/'library.json';old.write_text('old Ollama vector snapshot')
    monkeypatch.setenv('F1_STORE_PATH',str(old));monkeypatch.setenv('F1_EMBEDDING_BACKEND','fastembed_cpu')
    repo=WorkspaceRepository();repo.ingest_text_document('doc','doc.txt',[(1,'Original source.')]);save(repo)
    assert old.read_text()=='old Ollama vector snapshot'
    assert location()!=old and p.index_id.replace(':','-') in str(location())
    copied=WorkspaceRepository();load(copied);assert copied.chunks[0].text=='Original source.'
    data=json.loads(location().read_text());data['encoder_identity']['pooling']='mean';location().write_text(json.dumps(data))
    with pytest.raises(ValueError,match='identity mismatch'):load(WorkspaceRepository())


class Provider:
    metrics={}
    def __init__(self,reply):self.reply=json.dumps(reply)
    def generate(self,*a,**k):return self.reply


def test_atomic_structured_citations_map_to_distinct_pages():
    repo=WorkspaceRepository();repo.ingest_text_document('doc','doc.txt',[(1,'The room is A112.'),(2,'Bring a laptop.')])
    service=BasicQA(repo,Provider(dict(status='answer',facts=[dict(text='The room is A112.',sources=[1]),dict(text='Bring a laptop.',sources=[2])])))
    result=service.answer_question('Summarize location and preparation.',['doc'])
    assert [(c['cited_page'],c['claim_text']) for c in result['validated_claims']]==[(1,'The room is A112. [1]'),(2,'Bring a laptop. [2]')]


def test_structured_boundary_abstention_is_normal():
    repo=WorkspaceRepository();repo.ingest_text_document('doc','doc.txt',[(1,'Another workshop.')])
    result=BasicQA(repo,Provider(dict(status='insufficient_evidence',facts=[]))).answer_question('Where is Cedar?',['doc'])
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'


@pytest.mark.parametrize('query,vi',[('Cần chuẩn bị gì?',True),('Trả lời bằng tiếng Anh: cần gì?',False),('Answer in Vietnamese: where?',True),('Where is the workshop?',False)])
def test_requested_language_and_natural_errors(query,vi):
    assert vietnamese(query)==vi
    message=failure_message(query,'GENERATION_INVALID_RESPONSE')
    assert 'GENERATION_' not in message and 'runtime' not in message


def test_cpu_timeout_terminates_only_cpu_worker(tmp_path,monkeypatch):
    import subprocess,sys
    from backend.services import f1_session_runtime as runtime
    monkeypatch.setattr(runtime,'enabled',lambda:False)
    p=CPUEmbeddingProvider(manifest(tmp_path),timeout=.05);p._verify_files()
    worker=subprocess.Popen([sys.executable,'-u','-c','import sys,time;sys.stdin.readline();time.sleep(30)'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    p._process=worker
    with pytest.raises(EmbeddingError,match='TIMEOUT'):p._exchange(dict(texts=['query'],purpose='query'))
    assert worker.poll() is not None and p._process is None


def test_cpu_generation_plan_is_reused_without_eviction(tmp_path,monkeypatch):
    from backend.services.f1_adaptive_memory import AdaptivePolicy,InferencePlan,FALLBACK
    from tools.resources import GIB
    snap=dict(physical_free=20*GIB,commit_free=30*GIB,gpu_free_mib=14000)
    p=AdaptivePolicy(state_path=tmp_path/'policy.json',probe=lambda:snap)
    plan=InferencePlan(FALLBACK,p.catalog[FALLBACK]['digest'],4096,768)
    monkeypatch.setenv('F1_EMBEDDING_BACKEND','fastembed_cpu')
    recover=[];monkeypatch.setattr(p,'recover',lambda **kw:recover.append(kw))
    monkeypatch.setattr(p,'residency',lambda:[])
    monkeypatch.setattr(p,'propose',lambda *a,**kw:plan)
    assert p.select()==plan
    monkeypatch.setattr(p,'residency',lambda:[dict(name=FALLBACK,context_length=4096)])
    assert p.select()==plan and len(recover)==1


def test_rebuild_requires_originals_and_preserves_old_index(tmp_path,monkeypatch):
    import importlib
    module=importlib.import_module('backend.providers.embedding_provider')
    from backend.services.document_service import DocumentService
    from tools.rebuild_cpu_index import rebuild
    original=tmp_path/'originals';original.mkdir();content=b'The approved room is A112.'
    repo=WorkspaceRepository();DocumentService(repo).ingest_file('source.txt',content)
    source=tmp_path/'old.json';source.write_text(json.dumps(dict(format=1,documents=[d.model_dump() for d in repo.documents.values()])))
    old=source.read_bytes();p=CPUEmbeddingProvider(manifest(tmp_path))
    monkeypatch.setattr(p,'_exchange',lambda payload:np.array([[1.,0.,0.]],dtype=np.float32))
    monkeypatch.setattr(module,'embedding_provider',p);monkeypatch.setenv('F1_EMBEDDING_BACKEND','fastembed_cpu')
    with pytest.raises(ValueError,match='Missing original'):rebuild(source,[original],tmp_path/'new/library.json')
    (original/'source.txt').write_bytes(content)
    target=rebuild(source,[original],tmp_path/'new/library.json')
    data=json.loads(target.read_text());assert data['encoder_identity']==p.index_identity
    assert data['documents'][0]['file_hash']==hashlib.sha256(content).hexdigest()
    assert all(row['key'][0]==p.index_id for row in data['embeddings'])
    assert source.read_bytes()==old
    with pytest.raises(ValueError,match='Destination exists'):rebuild(source,[original],tmp_path/'new/library.json')


@pytest.mark.parametrize('reason,code',[('MODEL_RESIDENCY_LOAD_FAILED','GENERATION_UNAVAILABLE'),('RESOURCE_RESERVE_VIOLATION:commit_free','RESOURCE_LIMIT')])
def test_model_load_failure_is_not_reported_as_memory_denial(monkeypatch,reason,code):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.chat_routes import router
    from backend.services.f1_basic_qa import basic_qa
    from tools.resources import AdmissionDenied
    def fail(*args,**kwargs):raise AdmissionDenied(reason)
    monkeypatch.setattr(basic_qa,'answer_question',fail)
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        text=client.post('/api/chat/stream',json=dict(query='Tóm tắt tài liệu.',selected_doc_ids=['doc'],verification_profile='academic_grounded')).text
    events=[json.loads(line[6:]) for line in text.splitlines() if line.startswith('data: ')]
    event=next(e for e in events if e['type']=='error')
    assert event['code']==code and code not in event['message']


def test_explicit_bilingual_has_two_cited_versions_in_one_generation():
    repo=WorkspaceRepository();repo.ingest_text_document('doc','doc.txt',[(1,'The room is A112.')])
    provider=Provider(dict(status='answer',facts=[dict(text='The room is A112.',translation='Phòng được chỉ định là A112.',sources=[1])]))
    result=BasicQA(repo,provider).answer_question('Answer in both English and Vietnamese: which room?',['doc'])
    assert 'The room is A112.' in result['answer'] and 'Phòng được chỉ định là A112.' in result['answer']
    assert result['answer'].count('[citation:')==2 and len(result['validated_claims'])==1


def test_explicit_bilingual_missing_translation_fails_closed():
    from backend.providers.llm_provider import GenerationError
    repo=WorkspaceRepository();repo.ingest_text_document('doc','doc.txt',[(1,'The room is A112.')])
    provider=Provider(dict(status='answer',facts=[dict(text='The room is A112.',sources=[1])]))
    with pytest.raises(GenerationError):BasicQA(repo,provider).answer_question('Trả lời song ngữ Việt Anh: phòng nào?',['doc'])


def test_total_embedding_batch_has_one_shared_deadline(tmp_path,monkeypatch):
    p=CPUEmbeddingProvider(manifest(tmp_path));seen=[]
    def exchange(payload):
        seen.append(p._deadline);return np.array([[1.,0.,0.]],dtype=np.float32)
    monkeypatch.setattr(p,'_exchange',exchange)
    p.embed_texts(['first','second'])
    assert seen[0]==seen[1] and not hasattr(p,'_deadline')
