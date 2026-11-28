"""API contract tests; no model inference or acceptance claims."""
from unittest.mock import patch
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.core.schemas import UserRequest,RouteType
from backend.services.f1_evidence_profile_service import EvidenceProfileError
import backend.api.chat_routes as routes

def client():
    app=FastAPI();app.include_router(routes.router);return TestClient(app)

def test_profile_default_and_invalid_value():
    assert UserRequest(query='A question').verification_profile=='strict'
    with pytest.raises(ValidationError):UserRequest(query='A question',verification_profile='automatic_fallback')

def test_strict_dispatch_keeps_original_internal_call_contract():
    seen=[]
    def answer(**kwargs):seen.append(kwargs);return dict(status='ANSWER_VERIFIED')
    with patch.object(routes,'route_user_request',return_value=(RouteType.QA_FLOW,[])),patch.object(routes,'qa_service',SimpleNamespace(answer_question=answer)):
        response=client().post('/api/chat',json=dict(query='A question',selected_doc_ids=['a']))
    assert response.status_code==200
    assert seen==[dict(query='A question',selected_doc_ids=['a'],conversation_history=[])]

def test_opt_in_verifier_error_returns503_and_no_factual_fallback():
    def fail(**kwargs):raise EvidenceProfileError('VERIFIER_TIMEOUT')
    with patch.object(routes,'route_user_request',return_value=(RouteType.QA_FLOW,[])),patch.object(routes,'qa_service',SimpleNamespace(answer_question=fail)):
        response=client().post('/api/chat',json=dict(query='A question',selected_doc_ids=['a'],verification_profile='evidence_centric_v0'))
    assert response.status_code==503
    assert 'VERIFIER_TIMEOUT' in response.json()['detail'] and 'answer' not in response.json()

def test_unknown_profile_rejected_before_generation():
    response=client().post('/api/chat',json=dict(query='A question',verification_profile='source_supported_on_error'))
    assert response.status_code==422


def generation_fixture():
    from backend.core.schemas import DocumentChunk
    from backend.algorithms.f1_claim_support import fingerprint
    source='Reference heading\nThe filter permits water transfer.'
    return DocumentChunk(chunk_id='chunk-a',doc_id='a.txt',doc_name='a.txt',page_number=2,
        start_line=7,end_line=8,text=source,doc_version='v3',doc_hash=fingerprint(source))


def test_generation_ordinal_binds_exact_physical_span_without_model_quote():
    import json
    from backend.services.f1_evidence_profile_service import generate_evidence_claims
    source=generation_fixture()
    provider=SimpleNamespace(_call_f1_generation=lambda *a,**k:json.dumps(dict(abstain=False,
        citations=[dict(source_id='2',claim='The filter permits water transfer.')])) )
    claim=generate_evidence_claims(provider,'What does the filter permit?',[source])[0]
    assert claim.evidence_quote=='The filter permits water transfer.'
    assert (claim.cited_page,claim.cited_start_line,claim.cited_end_line)==(2,8,8)
    assert claim.doc_version=='v3' and claim.doc_hash==source.doc_hash


@pytest.mark.parametrize('citation',[
    dict(source_id='999',claim='A fact.'),
    dict(source_id='2',claim='A fact.',excerpt='A corrupted quote.'),
    dict(source_id=2,claim='A fact.'),
])
def test_bad_generation_mapping_never_repaired(citation):
    import json
    from backend.services.f1_evidence_profile_service import generate_evidence_claims
    from backend.providers.llm_provider import GenerationError
    provider=SimpleNamespace(_call_f1_generation=lambda *a,**k:json.dumps(dict(abstain=False,citations=[citation])))
    with pytest.raises(GenerationError):generate_evidence_claims(provider,'A question',[generation_fixture()])


def test_mapping_preserves_untrusted_claim_for_semantic_rejection():
    import json
    from backend.services.f1_evidence_profile_service import generate_evidence_claims
    text='The filter cures every disease.'
    provider=SimpleNamespace(_call_f1_generation=lambda *a,**k:json.dumps(dict(abstain=False,
        citations=[dict(source_id='2',claim=text)])))
    claim=generate_evidence_claims(provider,'A question',[generation_fixture()])[0]
    assert claim.claim_text==text and claim.evidence_quote=='The filter permits water transfer.'
    assert claim.verification_status=='UNVERIFIED'


def test_physical_span_mapping_retains_adjacent_explicit_condition():
    from backend.algorithms.f1_evidence_profile import physical_source_spans
    spans=physical_source_spans('Only under low pressure:\nThe filter permits water transfer.')
    assert all('Only under low pressure:' in quote for first,last,quote in spans if last==1)
