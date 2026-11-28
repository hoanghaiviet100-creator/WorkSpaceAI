"""Isolated ASGI contract tests. All model responses/faults are SIMULATED."""
import hashlib
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.core.config import settings
from backend.providers.embedding_provider import EmbeddingProvider
from backend.providers.llm_provider import LLMProvider
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services.qa_service import qa_service

MODEL='qwen3.5:9b-q4_K_M'
F3_MODEL='qwen2.5:7b'
EMBED='qwen3-embedding:0.6b'
DOC='generation-contract.txt'
TEXT='TCP provides reliable and ordered delivery of data between devices.'

def structured_answer():
    return {'thinking':'Public source-based explanation.','answer':TEXT,'citations':[{'claim':TEXT,'evidence_id':'REQUEST_EVIDENCE_1','excerpt':TEXT}]}

class OllamaStub:
    kind='success'
    def __init__(self):self.calls=[]
    def response(self,request,status=200,body=None,content=None):
        return httpx.Response(status,json=body,content=content,request=request) if content is not None else httpx.Response(status,json=body,request=request)
    def get(self,url,**kwargs):
        request=httpx.Request('GET',url)
        self.calls.append({'method':'GET','path':request.url.path,'host':request.url.host})
        kind=self.kind
        if kind=='inventory_connect':raise httpx.ConnectError('private connect failure',request=request)
        if kind=='inventory_timeout':raise httpx.ReadTimeout('private timeout',request=request)
        if kind.startswith('inventory_http_'):return self.response(request,int(kind.rsplit('_',1)[1]),{'error':'private upstream'})
        if kind=='inventory_invalid_json':return self.response(request,content=b'{')
        if kind=='inventory_invalid_shape':return self.response(request,body={'models':None})
        names={'missing_qwen':['qwen2.5:3b'], 'missing_embedding':[EMBED], 'missing_other':['unrelated:latest'], 'missing_f3':[F3_MODEL,EMBED],
               'email_missing':['qwen2.5:3b']}.get(kind,[MODEL,EMBED])
        return self.response(request,body={'models':[{'name':name} for name in names]})
    def post(self,url,**kwargs):
        request=httpx.Request('POST',url)
        payload=kwargs.get('json',{})
        self.calls.append({'method':'POST','path':request.url.path,'host':request.url.host,'model':payload.get('model'),'think':payload.get('think'),'format':payload.get('format')})
        refs=re.findall(r'ev_[0-9a-f]{16}_\d+',json.dumps(payload))
        eid=refs[0] if refs else 'NO_REFERENCE'
        if request.url.host!='ollama.f1-fix.invalid':
            text=json.dumps(structured_answer()) if payload.get('generationConfig',{}).get('responseMimeType') else TEXT
            return self.response(request,body={'candidates':[{'content':{'parts':[{'text':text.replace('REQUEST_EVIDENCE_1',eid)}]}}]})
        kind=self.kind
        if kind=='generate_timeout':raise httpx.ReadTimeout('private unknown inference outcome',request=request)
        if kind=='generate_connect':raise httpx.ConnectError('private connect failure',request=request)
        if kind.startswith('generate_http_'):return self.response(request,int(kind.rsplit('_',1)[1]),{'error':'private provider response'})
        if kind=='generate_invalid_json':return self.response(request,content=b'{')
        raw=json.dumps(structured_answer()) if payload.get('format')=='json' else TEXT
        malformed={
            'qa_non_json':'not a JSON answer','qa_empty_object':'{}',
            'qa_empty_answer':json.dumps({'answer':'','citations':structured_answer()['citations']}),
            'qa_null_answer':json.dumps({'answer':None,'citations':structured_answer()['citations']}),
            'qa_empty_citations':json.dumps({'answer':TEXT,'citations':[]}),
            'qa_bad_citations':json.dumps({'answer':TEXT,'citations':['invalid']}),
            'qa_missing_excerpt':json.dumps({'answer':TEXT,'citations':[{'doc_id':DOC,'page':1,'line_start':1,'line_end':1}]}),
            'qa_invalid_coordinate':json.dumps({'answer':TEXT,'citations':[dict(structured_answer()['citations'][0],page='not-a-page')]}),
        }
        raw=malformed.get(kind,raw)
        if kind=='qa_legitimate_abstain':raw=json.dumps(dict(answer='Insufficient evidence.',abstain=True,citations=[]))
        if kind=='generate_fix01_inline_thinking':
            inline='<think>SIMULATED_PRIVATE_INLINE</think>'
            raw=json.dumps(dict(structured_answer(),thinking=inline)) if payload.get('format')=='json' else inline+TEXT
        if kind=='email_missing':raw='SUBJECT: Existing email behavior\nBODY: Existing email draft body.'
        body={'model':payload.get('model'),'done':True,'response':raw.replace('REQUEST_EVIDENCE_1',eid),
              'thinking':'SIMULATED_PRIVATE_NATIVE_REASONING_MUST_NEVER_LEAK'}
        if kind=='generate_fix01_length':body['done_reason']='length'
        if kind=='generate_empty':body['response']=''
        if kind=='generate_whitespace':body['response']='  \n '
        if kind=='generate_non_string':body['response']=['invalid']
        if kind=='generate_model_mismatch':body['model']=EMBED
        if kind=='generate_missing_model':body.pop('model')
        if kind=='generate_incomplete':body['done']=False
        if kind=='generate_error_envelope':body['error']='private server error'
        return self.response(request,body=body)

@pytest.fixture
def isolated_f1(monkeypatch):
    monkeypatch.setattr(settings,'llm_provider','ollama')
    monkeypatch.setattr(settings,'ollama_model',F3_MODEL)
    monkeypatch.setattr(settings,'f1_generation_model',MODEL)
    monkeypatch.setattr(settings,'f1_generation_think',True)
    monkeypatch.setattr(settings,'ollama_base_url','http://ollama.f1-fix.invalid:11434')
    monkeypatch.setattr(settings,'gemini_api_key','synthetic-gemini-key-present-for-isolation')
    monkeypatch.setattr(settings,'email_dispatch_mode','local_mock')
    embed_calls=[]
    def semantic(request):
        embed_calls.append(request.url.path)
        if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':EMBED,'digest':'synthetic-fixed-embedding-digest'}]})
        payload=json.loads(request.content)
        assert payload['model']==EMBED
        return httpx.Response(200,json={'model':EMBED,'embeddings':[[3.,4.]+[0.]*1022 for _ in payload['input']]})
    embed=EmbeddingProvider(EMBED,base_url='http://semantic.fixture:11434',transport=httpx.MockTransport(semantic))
    repo=WorkspaceRepository(embed_fn=embed.get_embed_fn())
    DocumentService(repo).ingest_file(DOC,TEXT.encode())
    provider=LLMProvider();stub=OllamaStub()
    monkeypatch.setattr(httpx,'get',stub.get)
    monkeypatch.setattr(httpx,'post',stub.post)
    monkeypatch.setattr(qa_service,'repository',repo)
    monkeypatch.setattr(qa_service,'provider',provider)
    monkeypatch.setattr(qa_service,'embed_provider',embed)
    monkeypatch.setattr(main.app.state,'f1_embedding_error',None,raising=False)
    fallback=Mock(wraps=provider.synthesize_smart_answer)
    monkeypatch.setattr(provider,'synthesize_smart_answer',fallback)
    return SimpleNamespace(client=TestClient(main.app),stub=stub,provider=provider,repo=repo,embed=embed,
                           embed_calls=embed_calls,fallback=fallback)

def observe(fixture,case,operation,response):
    event={'evidence_type':'SIMULATED','case':case,'operation':operation,'http_status':response.status_code,
           'response':response.json(),'generation_calls':fixture.stub.calls,'fallback_calls':fixture.fallback.call_count}
    path=os.getenv('F1_GENERATION_TEST_EVIDENCE')
    if path:
        with Path(path).open('a',encoding='utf-8') as stream:stream.write(json.dumps(event,ensure_ascii=False)+'\n')

COMMON_FAILURES=[
    ('missing_qwen','GENERATION_MODEL_MISSING',0),('missing_embedding','GENERATION_MODEL_MISSING',0),('missing_other','GENERATION_MODEL_MISSING',0),('missing_f3','GENERATION_MODEL_MISSING',0),
    ('inventory_connect','GENERATION_UNAVAILABLE',0),('inventory_timeout','GENERATION_TIMEOUT',0),
    ('inventory_http_400','GENERATION_PROVIDER_FAILURE',0),('inventory_http_503','GENERATION_PROVIDER_FAILURE',0),
    ('inventory_invalid_json','GENERATION_INVALID_RESPONSE',0),('inventory_invalid_shape','GENERATION_INVALID_RESPONSE',0),
    ('generate_http_400','GENERATION_PROVIDER_FAILURE',1),('generate_http_503','GENERATION_PROVIDER_FAILURE',1),
    ('generate_http_404','GENERATION_MODEL_MISSING',1),('generate_timeout','GENERATION_TIMEOUT',1),('generate_connect','GENERATION_UNAVAILABLE',1),
    ('generate_invalid_json','GENERATION_INVALID_RESPONSE',1),('generate_empty','GENERATION_INVALID_RESPONSE',1),
    ('generate_whitespace','GENERATION_INVALID_RESPONSE',1),('generate_non_string','GENERATION_INVALID_RESPONSE',1),
    ('generate_model_mismatch','GENERATION_INVALID_RESPONSE',1),('generate_missing_model','GENERATION_INVALID_RESPONSE',1),
    ('generate_incomplete','GENERATION_INVALID_RESPONSE',1),('generate_error_envelope','GENERATION_INVALID_RESPONSE',1),
    ('generate_fix01_length','GENERATION_INVALID_RESPONSE',1),('generate_fix01_inline_thinking','GENERATION_INVALID_RESPONSE',1),
]
QA_FAILURES=[(kind,'GENERATION_INVALID_RESPONSE',1) for kind in ('qa_non_json','qa_empty_object','qa_empty_answer','qa_null_answer','qa_empty_citations','qa_bad_citations','qa_missing_excerpt','qa_invalid_coordinate')]

@pytest.mark.parametrize('operation',['qa','summary'])
@pytest.mark.parametrize('case,code,attempts',COMMON_FAILURES)
def test_generation_failures_are_controlled(isolated_f1,operation,case,code,attempts):
    check_failure(isolated_f1,operation,case,code,attempts)

@pytest.mark.parametrize('case,code,attempts',QA_FAILURES)
def test_invalid_structured_qa_is_controlled(isolated_f1,case,code,attempts):
    check_failure(isolated_f1,'qa',case,code,attempts)

def check_failure(f,operation,case,code,attempts):
    f.stub.kind=case
    chunks=list(f.repo.chunks);documents=dict(f.repo.documents);index=f.embed.index_id
    vectors={k:v.copy() for k,v in f.repo._chunk_embeddings.items()}
    query='How does TCP deliver data?' if operation=='qa' else 'Summarize '+DOC
    response=f.client.post('/api/chat',json={'query':query,'selected_doc_ids':[DOC]})
    observe(f,case,operation,response)
    assert response.status_code==503,response.text
    assert response.json()=={'detail':code+': Configured generation is unavailable.'}
    assert 'ANSWER_VERIFIED' not in response.text and 'private' not in response.text
    posts=[c for c in f.stub.calls if c['method']=='POST']
    assert len(posts)==attempts
    assert all(c['host']=='ollama.f1-fix.invalid' and c['model']==MODEL for c in posts)
    assert f.fallback.call_count==0
    assert f.repo.chunks==chunks and f.repo.documents==documents and f.embed.index_id==index
    assert f.repo._chunk_embeddings.keys()==vectors.keys()
    for key,old in vectors.items():np.testing.assert_array_equal(old,f.repo._chunk_embeddings[key])
    assert not f.embed.using_hash_fallback

@pytest.mark.parametrize('operation',['qa','summary'])
def test_correct_model_succeeds_without_cloud_substitution(isolated_f1,operation):
    f=isolated_f1
    response=f.client.post('/api/chat',json={'query':'How does TCP deliver data?' if operation=='qa' else 'Summarize '+DOC,'selected_doc_ids':[DOC]})
    observe(f,'success',operation,response)
    assert response.status_code==200
    assert 'SIMULATED_PRIVATE_NATIVE_REASONING_MUST_NEVER_LEAK' not in response.text
    assert f.embed.model_name==EMBED and f.embed.dimension==1024
    assert response.json()['status']==('ANSWER_VERIFIED' if operation=='qa' else 'SUMMARY_GENERATED')
    posts=[c for c in f.stub.calls if c['method']=='POST']
    assert len(posts)==1 and posts[0]['model']==MODEL and posts[0]['host']=='ollama.f1-fix.invalid'
    assert f.fallback.call_count==0
    assert posts[0]['think'] is True
    assert posts[0]['format']==('json' if operation=='qa' else None)
    if operation=='qa':
        assert response.json()['thinking'] is None
        assert 'Public source-based explanation.' not in response.text
        claim=response.json()['validated_claims'][0]
        assert claim['evidence_quote']==TEXT and claim['verification_status']=='VERIFIED_EXACT'
        assert claim['doc_hash']==hashlib.sha256(TEXT.encode()).hexdigest()
    assert '/api/embed' in f.embed_calls

def test_explicit_gemini_success_and_failure_are_not_offline_answers(isolated_f1,monkeypatch):
    f=isolated_f1;monkeypatch.setattr(settings,'llm_provider','gemini')
    response=f.client.post('/api/chat',json={'query':'How does TCP deliver data?','selected_doc_ids':[DOC]})
    assert response.status_code==200 and response.json()['status']=='ANSWER_VERIFIED'
    assert all(c['host']!='ollama.f1-fix.invalid' for c in f.stub.calls)
    monkeypatch.setattr(f.provider,'call_gemini',Mock(return_value=None))
    response=f.client.post('/api/chat',json={'query':'How does TCP deliver data?','selected_doc_ids':[DOC]})
    assert response.status_code==503 and response.json()['detail'].startswith('GENERATION_PROVIDER_FAILURE:')
    assert f.fallback.call_count==0

def test_mock_and_no_source_abstention_need_no_provider(isolated_f1,monkeypatch):
    f=isolated_f1
    f.stub.kind='inventory_connect'
    response=f.client.post('/api/chat',json={'query':'How does TCP deliver data?','selected_doc_ids':[]})
    assert response.status_code==200 and response.json()['status']=='ABSTAINED_NO_SOURCE_SELECTED'
    assert not f.stub.calls
    response=f.client.post('/api/chat',json={'query':'What is missing?','selected_doc_ids':['absent.txt']})
    assert response.status_code==200 and response.json()['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert not f.stub.calls
    monkeypatch.setattr(settings,'llm_provider','mock')
    response=f.client.post('/api/chat',json={'query':'How does TCP deliver data?','selected_doc_ids':[DOC]})
    assert response.status_code==200 and response.json()['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'
    response=f.client.post('/api/chat',json={'query':'Summarize '+DOC,'selected_doc_ids':[DOC]})
    assert response.status_code==200 and response.json()['status']=='SUMMARY_GENERATED'
    assert not f.stub.calls

def test_legacy_f3_email_generation_keeps_existing_contract(isolated_f1):
    f=isolated_f1;f.stub.kind='email_missing'
    subject,body=f.provider.generate_email_draft('Progress update',list(f.repo.chunks),'review@example.com')
    assert (subject,body)==('Existing email behavior','Existing email draft body.')
    assert [c['model'] for c in f.stub.calls if c['method']=='POST']==['qwen2.5:3b']

@pytest.mark.parametrize('code,expected',[
    ('GENERATION_TIMEOUT','GENERATION_TIMEOUT'),('GENERATION_PRIVATE','GENERATION_PROVIDER_FAILURE'),
    ('GENERATION_TIMEOUT\nprivate','GENERATION_PROVIDER_FAILURE'),
])
def test_generation_handler_sanitizes_error_codes(isolated_f1,monkeypatch,code,expected):
    from backend.providers.llm_provider import GenerationError
    def failed(*args,**kwargs):raise GenerationError(code)
    monkeypatch.setattr(isolated_f1.provider,'generate_grounded_qa',failed)
    response=isolated_f1.client.post('/api/chat',json={'query':'How does TCP deliver data?','selected_doc_ids':[DOC]})
    assert response.status_code==503 and response.json()=={'detail':expected+': Configured generation is unavailable.'}


def test_explicit_legitimate_model_abstention_is_http200(isolated_f1):
    f=isolated_f1;f.stub.kind='qa_legitimate_abstain'
    response=f.client.post('/api/chat',json={'query':'How does TCP deliver data?','selected_doc_ids':[DOC]})
    assert response.status_code==200
    assert response.json()['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert not response.json()['validated_claims'] and not response.json()['citations']
    assert f.fallback.call_count==0
