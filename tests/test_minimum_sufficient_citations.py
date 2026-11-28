"""Contract and mapping checks; controlled outputs are not semantic quality evidence."""
import json
import pytest
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.f1_basic_qa import BasicQA
from backend.vendor.surfsense.prompt import prompting
from backend.providers.f1_basic_provider import ANSWER_SCHEMA

class FixedProvider:
    metrics={}
    def __init__(self,facts,status='answer'):
        self.response=json.dumps(dict(status=status,facts=facts));self.calls=0
    def generate(self,messages,*args):
        self.calls+=1;self.messages=messages;return self.response

def run(facts,query='Compare the selected records.',status='answer',selection=None):
    repo=WorkspaceRepository()
    repo.ingest_text_document('orchid','orchid.txt',[(1,'Orchid opens on 7 June at 08:20.'),(2,'Orchid requires a badge for entry.')])
    repo.ingest_text_document('pine','pine.txt',[(1,'Pine opens on 9 June at 16:45.')])
    repo.ingest_text_document('outside','outside.txt',[(1,'Private unrelated record.')])
    provider=FixedProvider(facts,status)
    result=BasicQA(repo,provider).answer_question(query,['orchid','pine'] if selection is None else selection)
    return result,provider

@pytest.mark.parametrize('fact,labels',[
    ('Orchid opens on 7 June at 08:20.',[1]),
    ('Entry to Orchid requires a badge.',[2]),
    ('Pine opens on 9 June at 16:45.',[3]),
])
def test_each_assertion_keeps_only_its_supplied_passage(fact,labels):
    result,provider=run([dict(text=fact,sources=labels)])
    assert len(result['citations'])==1
    assert result['citations'][0]['source_id']==labels[0]
    assert provider.calls==1
    assert result['semantic_verified'] is False

def test_different_assertions_do_not_inherit_each_others_sources():
    result,_=run([dict(text='Orchid opens at 08:20.',sources=[1]),dict(text='A badge is required for entry.',sources=[2])])
    assert result['answer'].split('\n\n')==['Orchid opens at 08:20. [citation:1]','A badge is required for entry. [citation:2]']

def test_genuinely_joint_evidence_is_not_truncated_or_sorted_by_position():
    result,_=run([dict(text='The two opening schedules differ.',sources=[3,1])])
    assert result['answer'].endswith('[citation:3][citation:1]')
    assert {c['cited_doc_id'] for c in result['validated_claims']}=={'orchid','pine'}

def test_equivalent_bilingual_statements_share_the_same_evidence():
    result,provider=run([dict(text='Entry requires a badge.',translation='Cần có thẻ để vào cửa.',sources=[2])],query='Answer in both Vietnamese and English: what is required for entry?')
    assert result['answer'].count('[citation:2]')==2
    assert len(result['citations'])==1 and provider.calls==1

def test_separate_source_statements_keep_all_required_citations():
    result,_=run([dict(text='Orchid opens at 08:20.',sources=[1]),dict(text='Pine opens at 16:45.',sources=[3])])
    assert {c['source_id'] for c in result['citations']}=={1,3}

def test_abstention_and_boundary_do_not_fabricate_evidence():
    result,p=run([],status='insufficient_evidence',query='What is the insurance charge?')
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE' and not result['citations'] and p.calls==1
    result,p=run([],selection=[])
    assert result['status']=='ABSTAINED_NO_SOURCE_SELECTED' and p.calls==0

def test_model_contract_describes_claim_specific_sufficiency_without_source_cap():
    prompt=prompting.load('backend.vendor.surfsense','capable')
    assert 'minimum sufficient evidence for THAT assertion' in prompt
    assert 'shared document, topic or retrieval match does not justify a citation' in prompt
    assert 'Keep multiple citations when genuinely necessary' in prompt
    assert 'Modified from' not in prompt
    sources=ANSWER_SCHEMA['properties']['facts']['items']['properties']['sources']
    assert 'maxItems' not in sources
