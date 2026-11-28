"""Controlled F1 boundary/integration tests; scripted proposals are not real model output."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import json
import re
from threading import Barrier
from types import SimpleNamespace

import pytest

from backend.core.config import settings
from backend.core.schemas import DocumentChunk
from backend.providers.llm_provider import GenerationError, LLMProvider
from backend.services.qa_service import QAService

IDS = r'=== EVIDENCE_ID: (ev_[0-9a-f]{16}_\d+) ==='

def ids(prompt):
    return re.findall(IDS, prompt)

def chunk(text='Report K requires exactly 9 pages.', start=37, doc='A.pdf', page=4):
    return DocumentChunk(chunk_id=f'{doc}:{page}:{start}',doc_id=doc,doc_name=doc,text=text,
        start_line=start,end_line=start+len(text.splitlines())-1,page_number=page,
        doc_version='v3',doc_hash=hashlib.sha256((doc+text).encode()).hexdigest(),score=1)

def citation(eid, text, claim=None):
    return dict(evidence_id=eid,claim=text if claim is None else claim,excerpt=text)

@pytest.fixture
def boundary(monkeypatch):
    monkeypatch.setattr(settings,'llm_provider','ollama')
    provider=LLMProvider()
    def run(chunks, factory, query='What is supported?'):
        def generate(prompt,**kwargs):
            return json.dumps(dict(answer='Candidate answer.',citations=factory(ids(prompt))))
        monkeypatch.setattr(provider,'_call_f1_generation',generate)
        return provider.generate_grounded_qa(query,chunks)
    return SimpleNamespace(provider=provider,run=run)

def test_single_line_binding_uses_absolute_page_line_and_trusted_provenance(boundary):
    source=chunk()
    result,=boundary.run([source],lambda keys:[citation(keys[0],source.text)])
    assert (result.cited_doc_id,result.cited_page,result.cited_start_line,result.cited_end_line)==('A.pdf',4,37,37)
    assert (result.doc_version,result.doc_hash)==(source.doc_version,source.doc_hash)
    assert result.evidence_quote==source.text and result.claim_text==source.text
    assert result.verification_status=='UNVERIFIED'

def test_multiline_offset_is_not_chunk_relative_line_number(boundary):
    source=chunk('Header\nFirst fact.\nSecond fact.\nTail',start=91,page=8)
    result,=boundary.run([source],lambda keys:[citation(keys[0],'First fact.\nSecond fact.')])
    assert (result.cited_page,result.cited_start_line,result.cited_end_line)==(8,92,93)
    assert result.evidence_quote=='First fact.\nSecond fact.'

@pytest.mark.parametrize('mutation',[
    'unknown','cross_document','empty','whitespace','ambiguous_same_line','ambiguous_other_line',
    'wrong_excerpt','legacy_doc','legacy_page','legacy_line','legacy_version','legacy_hash','missing_claim','extra_field',
])
def test_invalid_binding_is_rejected_without_search_or_salvage(boundary,mutation):
    a=chunk('Unique alpha fact.');b=chunk('Distinct beta fact.',doc='B.pdf')
    if mutation=='ambiguous_same_line':a=chunk('Echo. Echo.')
    if mutation=='ambiguous_other_line':a=chunk('Echo.\nEcho.')
    def proposals(keys):
        c=citation(keys[0],a.text)
        if mutation=='unknown':c['evidence_id']='ev_deadbeefdeadbeef_99'
        elif mutation=='cross_document':c['excerpt']=b.text
        elif mutation=='empty':c['excerpt']=''
        elif mutation=='whitespace':c['excerpt']=' \n '
        elif mutation.startswith('ambiguous'):c['excerpt']='Echo.'
        elif mutation=='wrong_excerpt':c['excerpt']='unique alpha fact.'
        elif mutation.startswith('legacy_'):
            key={'legacy_doc':'doc_id','legacy_page':'page','legacy_line':'line_end','legacy_version':'doc_version','legacy_hash':'doc_hash'}[mutation]
            c[key]=2 if key in {'page','line_end'} else 'forged'
        elif mutation=='missing_claim':c.pop('claim')
        elif mutation=='extra_field':c['statement']='extra'
        return [citation(keys[0],a.text),c]
    with pytest.raises(GenerationError,match='^GENERATION_INVALID_RESPONSE$'):
        boundary.run([a,b],proposals)

@pytest.mark.parametrize('field,value',[('end_line',99),('start_line',0),('doc_hash',''),('doc_version','')])
def test_invalid_source_metadata_is_not_repaired(boundary,field,value):
    source=chunk().model_copy(update={field:value})
    with pytest.raises(GenerationError,match='^GENERATION_INVALID_RESPONSE$'):
        boundary.run([source],lambda keys:[citation(keys[0],source.text)])

def test_stale_id_is_rejected_in_later_request(boundary):
    source=chunk();previous=[]
    boundary.run([source],lambda keys:(previous.extend(keys) or [citation(keys[0],source.text)]))
    with pytest.raises(GenerationError,match='^GENERATION_INVALID_RESPONSE$'):
        boundary.run([source],lambda keys:[citation(previous[0],source.text)])

@pytest.mark.parametrize('swap',[False,True])
def test_concurrent_request_maps_do_not_cross_bind(monkeypatch,swap):
    monkeypatch.setattr(settings,'llm_provider','ollama')
    provider=LLMProvider();barrier=Barrier(2);seen={}
    def generate(prompt,**kwargs):
        name='alpha' if 'REQUEST_ALPHA' in prompt else 'beta'
        seen[name]=ids(prompt)[0];barrier.wait(timeout=5)
        chosen=seen[('beta' if name=='alpha' else 'alpha') if swap else name]
        return json.dumps(dict(answer='Candidate.',citations=[citation(chosen,'Same source fact.')]))
    monkeypatch.setattr(LLMProvider,'_call_f1_generation',lambda self,prompt,**kwargs:generate(prompt,**kwargs))
    def worker(name):
        try:
            claims=provider.generate_grounded_qa('REQUEST_'+name.upper(),[chunk('Same source fact.',doc=name+'.pdf')])
            return claims[0].cited_doc_id
        except GenerationError:
            return 'REJECTED'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,['alpha','beta']))
    assert seen['alpha']!=seen['beta']
    assert results==(['REJECTED','REJECTED'] if swap else ['alpha.pdf','beta.pdf'])
    assert not vars(provider)

def test_request_snapshot_is_not_mutated_during_generation(boundary,monkeypatch):
    source=chunk();original=source.text
    def generate(prompt,**kwargs):
        source.text='Changed after prompt.';source.start_line=1;source.doc_hash='changed'
        return json.dumps(dict(answer='Candidate.',citations=[citation(ids(prompt)[0],original)]))
    monkeypatch.setattr(boundary.provider,'_call_f1_generation',generate)
    result,=boundary.provider.generate_grounded_qa('Question',[source])
    assert result.cited_start_line==37 and result.evidence_quote==original and result.doc_hash!='changed'

@pytest.mark.parametrize('abstain,citations,accepted',[(True,[],True),(False,[],False),('true',[],False),(True,['invalid'],False)])
def test_only_explicit_valid_abstention_has_empty_claims(boundary,monkeypatch,abstain,citations,accepted):
    monkeypatch.setattr(boundary.provider,'_call_f1_generation',lambda *a,**k:json.dumps(dict(answer='Insufficient evidence.',abstain=abstain,citations=citations)))
    if accepted:assert boundary.provider.generate_grounded_qa('Question',[chunk()])==[]
    else:
        with pytest.raises(GenerationError,match='^GENERATION_INVALID_RESPONSE$'):
            boundary.provider.generate_grounded_qa('Question',[chunk()])

def controlled_qa(monkeypatch,query,claim_text,abstain=False):
    monkeypatch.setattr(settings,'llm_provider','ollama')
    source=chunk();provider=LLMProvider()
    def generate(prompt,**kwargs):
        return json.dumps(dict(answer='Insufficient evidence.' if abstain else claim_text,abstain=abstain,
            citations=[] if abstain else [citation(ids(prompt)[0],source.text,claim_text)]))
    monkeypatch.setattr(provider,'_call_f1_generation',generate)
    qa=object.__new__(QAService)
    qa.repository=SimpleNamespace(chunks=[source],dense_available=False,search=lambda *a,**k:[source])
    qa.provider=provider
    return qa.answer_question(query,selected_doc_ids=[source.doc_id],tau_rel=0)

def test_controlled_legitimate_abstention_retains_service_semantics(monkeypatch):
    result=controlled_qa(monkeypatch,'What is supported?','',abstain=True)
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert result['validated_claims']==[] and result['citations']==[]

def test_valid_binding_does_not_grant_unsupported_claim(monkeypatch):
    result=controlled_qa(monkeypatch,'Is K approved?','Report K is approved.')
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert not result['validated_claims'] and result['hallucination_flags']

def test_controlled_r5_rejection_occurs_after_valid_citation_and_support(monkeypatch):
    module=importlib.import_module('backend.services.qa_service');original=module._covers_compound_request;observed=[]
    def coverage(query,claims):
        result=original(query,claims)
        observed.append(dict(validated=len(claims),coverage=result,claims=[c.model_dump() for c in claims]))
        return result
    monkeypatch.setattr(module,'_covers_compound_request',coverage)
    result=controlled_qa(monkeypatch,'Is "K requires 9 pages and K is approved" supported?','Report K requires exactly 9 pages.')
    assert observed[0]['validated']==1 and observed[0]['coverage'] is False
    assert observed[0]['claims'][0]['verification_status']=='VERIFIED_EXACT'
    assert observed[0]['claims'][0]['evidence_span']['support_status']=='SUPPORTED'
    assert observed[0]['claims'][0]['cited_start_line']==37
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE' and not result['validated_claims']

def test_atomic_positive_remains_verified_with_binding(monkeypatch):
    result=controlled_qa(monkeypatch,'How many pages does K require?','Report K requires exactly 9 pages.')
    assert result['status']=='ANSWER_VERIFIED' and len(result['validated_claims'])==1


def test_raw_source_text_is_separate_from_display_labels():
    from backend.providers.prompts import build_qa_prompt
    source=chunk('Giấy phép P chưa được phê duyệt.',start=37,page=4)
    prompt=build_qa_prompt('Question',[source],evidence_ids=['ev_0000000000000000_1'])
    assert '<source_text>\n'+source.text+'\n</source_text>' in prompt
    assert '[Dòng 37]' in prompt
    raw=prompt.split('<source_text>\n',1)[1].split('\n</source_text>',1)[0]
    assert raw==source.text and '[Dòng' not in raw
