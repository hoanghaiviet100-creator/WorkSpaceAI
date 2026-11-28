"""Controlled safety/contract tests; no model-quality claims or NLI dependency."""
import json
from types import SimpleNamespace
import pytest
from backend.algorithms.answer_language import requested_languages,language_valid,repair_preserves
from backend.algorithms.claim_evidence import select_sources
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.f1_basic_qa import BasicQA
from backend.providers.llm_provider import GenerationError

def chunks():
    repo=WorkspaceRepository()
    repo.ingest_text_document('orchid','orchid.txt',[(1,'The Orchid workshop takes place in room R207.\nThe workshop starts at 08:20.'),(2,'The logistics team prepares 32 workshop kits.\nParticipants bring laptops to practice analysing spreadsheet data.')])
    repo.ingest_text_document('pine','pine.txt',[(1,'The Pine workshop takes place in room S409.\nThe workshop starts at 10:45.')])
    return repo,repo.chunks

@pytest.mark.parametrize('query,expected',[
    ('Cho biết phòng nào?',('vi',)),('Answer in English: phòng nào?',('en',)),
    ('Trả lời bằng tiếng Việt: which room?',('vi',)),('Answer in both Vietnamese and English.',('en','vi')),
    ('Answer in Chinese: which room?',('zh',)),('Trả lời bằng tiếng Trung.',('zh',)),('请用中文回答。',('zh',)),
])
def test_requested_language(query,expected):assert requested_languages(query)==expected

@pytest.mark.parametrize('text,allowed',[
    ('Ban hậu cần chuẩn备物资准备了32套培训资料。',False),
    ('Người tham dự cần mang máy tính.',True),
    ('The label reads "准备材料".',True),('Tệp 准备.md mô tả yêu cầu.',True),
    ('Tên tác giả là 张伟.',True),('Mã kỹ thuật AB中文-42 được giữ nguyên.',True),
    ('Một lời bịa "额外事实".',False),
])
def test_only_authorized_literals_are_exempt(text,allowed):
    sources=[SimpleNamespace(doc_name='准备.md',text='Name: 张伟\nThe label reads "准备材料".\nIdentifier: AB中文-42')]
    assert language_valid(text,'vi',sources)==allowed
    assert language_valid(text,'zh',sources)

def test_claim_scoped_sources_and_nonadjacent_required_set():
    _,cs=chunks()
    assert select_sources('The Orchid workshop takes place in room R207.',[1,2],cs)==[1]
    assert select_sources('The logistics team prepares 32 workshop kits.',[1,2],cs)==[2]
    assert select_sources('Participants bring laptops to practice analysing spreadsheet data.',[1,2],cs)==[2]
    assert select_sources('The Pine workshop takes place in room S409 and the Orchid workshop takes place in room R207.',[3,1,2],cs)==[3,1]
    assert select_sources('The two opening schedules differ.',[3,1],cs)==[3,1]

def test_bilingual_shared_refs_and_new_translation_fact_rejected():
    _,cs=chunks()
    assert select_sources('The Orchid workshop takes place in room R207.',[1,2],cs,'Buổi tập huấn Orchid diễn ra tại phòng R207.')==[1]
    assert not select_sources('The Orchid workshop takes place in room R207.',[1,2],cs,'Buổi tập huấn Orchid diễn ra tại phòng R207 và chuẩn bị 32 bộ tài liệu.')

@pytest.mark.parametrize('claim',[
    'The Orchid workshop takes place in room X999.',
    'The logistics team prepares 45 workshop kits.',
    'Participants never bring laptops.',
    'The selected document requires payment of 900 dollars.',
])
def test_wrong_value_relation_or_unestablished_content_never_keeps_global_sources(claim):
    _,cs=chunks();assert select_sources(claim,[1,2,3],cs)==[]

def test_metadata_and_topics_do_not_supply_factual_values():
    _,cs=chunks();cs[1]=cs[1].model_copy(update={'doc_name':'R207-room-32-kits.txt'})
    assert select_sources('The Orchid workshop takes place in room R207.',[2],cs)==[]
    assert select_sources('The logistics team prepares 32 workshop kits.',[1],cs)==[]

class Provider:
    def __init__(self,facts,repair=None,error=None):
        self.raw=json.dumps(dict(status='answer',facts=facts),ensure_ascii=False)
        self.rep=repair;self.error=error;self.calls=0;self.repairs=0;self.metrics={}
    def generate(self,messages,*args,**kwargs):
        self.calls+=1;self.messages=messages
        if self.error:raise GenerationError(self.error)
        return self.raw
    def repair_language(self,*args,**kwargs):
        self.repairs+=1
        if isinstance(self.rep,Exception):raise self.rep
        return json.dumps(dict(texts=self.rep),ensure_ascii=False)

def vi_service(repair):
    repo=WorkspaceRepository()
    repo.ingest_text_document('manual','manual.txt',[(1,'Buổi học diễn ra tại phòng R207.'),(2,'Ban hậu cần chuẩn bị 32 bộ tài liệu tập huấn.')])
    p=Provider([dict(text='Buổi học diễn ra tại phòng R207.',sources=[1]),dict(text='Ban hậu cần chuẩn备物资准备了32套培训资料。',sources=[2])],repair)
    return repo,p,BasicQA(repo,p)

def test_exactly_one_wording_repair_with_unchanged_facts_and_refs():
    repo,p,s=vi_service(['Ban hậu cần chuẩn bị 32 bộ tài liệu tập huấn.'])
    result=s.answer_question('Cho biết phòng học và số bộ tài liệu.',['manual'])
    assert p.calls==1 and p.repairs==1
    assert '32 bộ tài liệu' in result['answer'] and '准备' not in result['answer']
    assert [r['source_id'] for r in result['citations']]==[1,2]
    assert result['model_metrics']['language_repair']['attempts']==1
    assert result['model_metrics']['language_repair']['outcome']=='validated'
    assert 'Response language: Vietnamese' in p.messages[0].content

@pytest.mark.parametrize('repair',[
    ['Ban hậu cần chuẩn bị 99 bộ tài liệu tập huấn.'],
    ['Ban hậu cần chuẩn备物资准备了32套培训资料。'],
    ['Ban hậu cần chuẩn bị 32 bộ tài liệu và cung cấp bữa trưa.'],
    [],None,
])
def test_failed_repair_drops_only_affected_claim_and_never_repeats(repair):
    _,p,s=vi_service(repair);r=s.answer_question('Cho biết phòng học và số bộ tài liệu.',['manual'])
    assert p.repairs==1 and p.calls==1
    assert 'R207' in r['answer'] and '32' not in r['answer'] and '准备' not in r['answer']
    assert len(r['citations'])==1

@pytest.mark.parametrize('error',['GENERATION_TIMEOUT','GENERATION_PROVIDER_FAILURE','RESOURCE_LIMIT','MODEL_LOAD_TIMEOUT'])
def test_initial_error_does_not_trigger_repair(error):
    _,p,s=vi_service([]);p.error=error
    with pytest.raises(GenerationError):s.answer_question('Cho biết thông tin.',['manual'])
    assert p.calls==1 and p.repairs==0

def test_repair_transport_failure_follows_existing_error_path_without_retry():
    _,p,s=vi_service(GenerationError('GENERATION_TIMEOUT'))
    with pytest.raises(GenerationError):s.answer_question('Cho biết thông tin.',['manual'])
    assert p.repairs==1 and p.calls==1

@pytest.mark.parametrize('sources',[None,'1',[999],[],{'global':[1,2]}])
def test_malformed_binding_is_claim_local(sources):
    repo,_=chunks();p=Provider([dict(text='The workshop starts at 08:20.',sources=[1]),dict(text='An unsupported assertion.',sources=sources)])
    r=BasicQA(repo,p).answer_question('What does the document establish?',['orchid'])
    assert '08:20' in r['answer'] and 'unsupported assertion' not in r['answer']
    assert len(r['citations'])==1 and p.repairs==0

def test_source_identity_mismatch_is_local():
    repo=WorkspaceRepository()
    repo.ingest_text_document('orchid','orchid.txt',[(1,'The Orchid workshop takes place in room R207.')])
    repo.ingest_text_document('pine','pine.txt',[(1,'The Pine workshop takes place in room S409.')])
    repo.documents['orchid'].file_hash='0'*64
    p=Provider([dict(text='The Orchid workshop takes place in room R207.',sources=[1]),dict(text='The Pine workshop takes place in room S409.',sources=[2])])
    r=BasicQA(repo,p).answer_question('What rooms?',['orchid','pine'])
    assert 'S409' in r['answer'] and 'R207' not in r['answer']


def test_ambiguous_or_new_repair_fact_is_not_accepted():
    sources=[SimpleNamespace(text='Orchid prepares 32 kits.\nPine prepares 32 kits.')]
    assert not repair_preserves('Some text 准备32.','Orchid prepares 32 kits.',sources)

def test_nli_unavailable_has_no_effect(monkeypatch):
    import backend.providers.f1_claim_support_provider as nli
    monkeypatch.setattr(nli,'get_f1_semantic_verifier',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('unavailable')))
    _,p,s=vi_service(['Ban hậu cần chuẩn bị 32 bộ tài liệu tập huấn.'])
    assert s.answer_question('Cho biết phòng học và tài liệu.',['manual'])['citations']


def test_chinese_explicit_answer_is_permitted_with_same_room_evidence():
    _,cs=chunks()
    assert select_sources('Cedarless研讨会在R207教室举行。',[1,2],cs)==[]
    assert select_sources('Orchid研讨会在R207教室举行。',[1,2],cs)==[1]

def test_repair_has_a_thirty_second_transport_bound_and_restores_schema(monkeypatch):
    from backend.providers.f1_basic_provider import BasicProvider
    p=BasicProvider();previous=p.client.timeout
    def generate(messages,*args,**kwargs):
        assert p.client.timeout.read==30 and p.bilingual_request is False
        assert p.schema_override['properties']['texts']['maxItems']==1
        return '{"texts":[]}'
    monkeypatch.setattr(p,'generate',generate)
    assert p.repair_language([dict(language='vi',prose='32混合')],[dict(text='32 kits.')],lambda event:None,lambda:False)=='{"texts":[]}'
    assert p.client.timeout==previous and not hasattr(p,'schema_override')
    p.client.close()


def test_chinese_prose_with_a_number_is_not_misclassified_as_a_technical_id():
    sources=[SimpleNamespace(doc_name='original.txt',text='准备了32套培训资料。')]
    assert not language_valid('Ban hậu cần准备了32套培训资料。','vi',sources)
