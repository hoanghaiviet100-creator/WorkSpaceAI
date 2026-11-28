"""Final-completion regressions; controlled inputs, never model output."""
import hashlib
import json
import logging
import re

import pytest

from backend.algorithms.f1_claim_support import bounded_conflict, source_assertions
from backend.core.config import settings
from backend.core.schemas import DocumentChunk
from backend.providers.llm_provider import LLMProvider, GenerationError, _bind_f1_citation


def source(text='A unique source assertion.'):
    return DocumentChunk(chunk_id='controlled:7',doc_id='controlled.pdf',doc_name='controlled.pdf',text=text,
        start_line=10,end_line=10+len(text.splitlines())-1,page_number=7,doc_version='v1',
        doc_hash=hashlib.sha256(text.encode()).hexdigest(),score=1)


@pytest.mark.parametrize('labels',[
    ('Presentation notice | Trang 3','Presentation notice | Trang 24'),
    ('Study material | Page 7 of 30','Study material | Page 8 of 30'),
    ('Trang 5','Trang 6'),('Page 7 / 20','Page 9 / 20'),
])
def test_presentation_page_labels_are_not_conflicting_assertions(labels):
    assert bounded_conflict(labels) is False


@pytest.mark.parametrize('facts',[
    ('Report K requires exactly 9 pages.','Report K requires exactly 10 pages.'),
    ('Permit P is approved.','Permit P is not approved.'),
    ('A [north]: mass = 4 kg.','A [north]: mass = 5 kg.'),
    ('Only if approved, K requires 9 pages.','Only if approved, K requires 10 pages.'),
    ('K may require 9 pages.','K may require 10 pages.'),
    ('The experiment starts on page 3.','The experiment starts on page 4.'),
    ('Report K requires 9 pages | Page 3','Report K requires 10 pages | Page 4'),
    ('See Page 2','See Page 3'),
])
def test_genuine_numeric_and_negative_conflicts_survive(facts):
    assert bounded_conflict(facts) is True


def test_scope_qualifications_modality_and_original_text_are_preserved():
    texts=('A [north]: mass = 4 kg.','A [south]: mass = 5 kg.',
           'If P is approved, K may require 9 pages. | Page 3')
    assert not bounded_conflict(texts)
    assert source_assertions(texts[-1])==('If P is approved, K may require 9 pages. | Page 3',)


@pytest.mark.parametrize('kind,expected',[
    ('unknown','UNKNOWN_EVIDENCE_ID'),('empty','EMPTY_EXCERPT'),('whitespace','EMPTY_EXCERPT'),
    ('nonexact','NON_EXACT_EXCERPT'),('ambiguous','AMBIGUOUS_OCCURRENCE'),
    ('metadata','INVALID_SOURCE_METADATA'),('malformed','MALFORMED_RESPONSE'),
    ('excerpt_type','MALFORMED_RESPONSE'),('claim','MALFORMED_RESPONSE'),
])
def test_binding_failure_has_safe_branch_diagnostic(kind,expected,caplog):
    marker='PRIVATE_SENTINEL_DO_NOT_LOG'
    s=source(marker+' unique assertion.')
    c=dict(evidence_id='ev_allowed',claim=marker,excerpt=s.text)
    if kind=='unknown':c['evidence_id']=marker
    if kind=='empty':c['excerpt']=''
    if kind=='whitespace':c['excerpt']=' \n '
    if kind=='nonexact':c['excerpt']=marker+' changed'
    if kind=='ambiguous':s=source(marker+' '+marker);c['excerpt']=marker
    if kind=='metadata':s=s.model_copy(update={'end_line':999})
    if kind=='malformed':c['doc_id']=marker
    if kind=='excerpt_type':c['excerpt']=123
    if kind=='claim':c['claim']=''
    with caplog.at_level(logging.WARNING):
        with pytest.raises(GenerationError,match='^GENERATION_INVALID_RESPONSE$') as raised:
            _bind_f1_citation(c,{'ev_allowed':s},marker)
    assert raised.value.diagnostic_reason==expected
    records=[r for r in caplog.records if getattr(r,'event',None)=='f1_evidence_validation']
    assert len(records)==1 and records[0].reason==expected
    assert marker not in caplog.text
    assert marker not in str(raised.value) and marker not in repr(vars(raised.value))


@pytest.mark.parametrize('response',['bad JSON','[]','{"answer":"x","citations":[]}',
    '{"answer":"x","citations":{},"thinking":"PRIVATE_SENTINEL"}'])
def test_malformed_proposal_is_diagnosed_without_private_text(monkeypatch,caplog,response):
    monkeypatch.setattr(settings,'llm_provider','ollama')
    monkeypatch.setattr(LLMProvider,'_call_f1_generation',lambda *a,**k:response)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(GenerationError,match='^GENERATION_INVALID_RESPONSE$') as raised:
            LLMProvider().generate_grounded_qa('controlled question',[source()])
    assert raised.value.diagnostic_reason=='MALFORMED_RESPONSE'
    assert 'PRIVATE_SENTINEL' not in caplog.text
