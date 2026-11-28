"""M2 actual QA/summary paths. Scripted adapter results are SIMULATED only."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.algorithms.f1_claim_support import (
    Atom, CompositionCondition, DocumentIdentity, Evidence, EvidenceLedger, ParentClaim, Proof,
    Quantity, SourceFact, SupportStatus as S, parse_bound_proposition,
)
from backend.core.schemas import DocumentChunk, GeneratedClaim
from backend.providers.f1_claim_support_provider import QualifiedLocalNLI, ScriptedSemanticVerifier
from backend.services.f1_claim_support_service import F1SupportGate
from backend.services.qa_service import QAService, parse_summary_into_section_claims

GOLD_PATH = Path(__file__).parent/'fixtures/f1_claim_support_gold.json'
GOLD = json.loads(GOLD_PATH.read_text(encoding='utf-8'))
APPROVED_HASH = 'ad7b6cfae909db89127a14d59afcb01069583e3a8e73d70d02719aeb6df6bd39'


def record(case, kind, result, **extra):
    path = os.getenv('F1_M2_CASE_RESULTS')
    if path:
        with Path(path).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(case=case, execution_kind=kind, result=result, **extra),
                                    ensure_ascii=False, default=str)+'\n')


def chunk(text, doc='source.txt', page=1, start=1, digest=None):
    return DocumentChunk(chunk_id=f'{doc}:{page}:{start}', doc_id=doc, doc_name=doc, text=text,
        page_number=page, start_line=start, end_line=start+len(text.splitlines())-1,
        doc_version='v1', doc_hash=digest or hashlib.sha256(text.encode()).hexdigest(), score=1.0)


def claim(text, source, quote=None, thinking=None, **updates):
    return GeneratedClaim(claim_text=text, cited_doc_id=source.doc_id, cited_page=source.page_number,
        cited_start_line=source.start_line, cited_end_line=source.end_line,
        evidence_quote=source.text if quote is None else quote, doc_version=source.doc_version,
        doc_hash=source.doc_hash, thinking=thinking, **updates)


class ProbeGate(F1SupportGate):
    def verify_claims(self, claims, chunks):
        result = super().verify_claims(claims, chunks)
        self.observed = result[2]
        return result


def qa_fixture(chunks, claims=(), gate=None, proposal='Unsupported generated summary.', retrieved=None):
    qa = object.__new__(QAService)
    qa.repository = SimpleNamespace(chunks=chunks, dense_available=False,
        search=lambda *a, **kw: chunks if retrieved is None else retrieved)
    qa.provider = SimpleNamespace(generate_grounded_qa=Mock(return_value=claims),
                                  generate_summary=Mock(return_value=proposal))
    qa.support_gate = gate or ProbeGate()
    return qa


def run(qa, selected=None):
    return qa.answer_question('What does the source require?', tau_rel=0,
        selected_doc_ids=selected if selected is not None else list(dict.fromkeys(c.doc_id for c in qa.repository.chunks)))


def assert_clean(result):
    assert result.get('thinking') is None
    for c in result['validated_claims']:
        assert c.thinking is None and c.section is None
        assert c.evidence_span['support_status'] == 'SUPPORTED'
        assert c.evidence_span['chunk_ids'] and c.evidence_span['context_id']
    for c in result['hallucination_flags']:
        assert not c.claim_text and not c.evidence_quote and c.thinking is None


def semantic_input(case, gate):
    chunks = [DocumentChunk(chunk_id=e['evidence_id'], doc_id=e['doc_id'], doc_name=e['doc_id'],
        page_number=e['page'], start_line=e['line_start'], end_line=e['line_end'], text=e['text'],
        doc_version=e['doc_version'], doc_hash=e['doc_hash'], score=1.0) for e in case['evidence']]
    by_id = {e['evidence_id']: c for e,c in zip(case['evidence'], chunks)}
    # A compound assertion is one output proposition: a rejected tail cannot be
    # turned into a verified parent by returning only its first half.
    if len(case['atoms']) > 1 and len({i for a in case['atoms'] for i in a['evidence_ids']}) == 1:
        text = case['joiner'].join(a['text'] for a in case['atoms'])
        claims = [claim(text, by_id[case['atoms'][0]['evidence_ids'][0]])]
    else:
        claims = [claim(a['text'], by_id[a['evidence_ids'][0]],
            thinking=case.get('explanation', {}).get('text')) for a in case['atoms']]
    return qa_fixture(chunks, claims, gate)


def parent_status(gate):
    statuses = [d.status.value for d in gate.observed]
    for label in ('ERROR', 'CONTRADICTED', 'INSUFFICIENT_EVIDENCE'):
        if label in statuses: return label
    return 'SUPPORTED' if statuses else 'INSUFFICIENT_EVIDENCE'


def test_approved_snapshot_is_unchanged():
    assert hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest() == APPROVED_HASH


@pytest.mark.parametrize('case', GOLD['semantic_cases'], ids=lambda c:c['id'])
def test_adjudicated_main_cases_through_qa_with_hostile_mock(case):
    gate = ProbeGate.for_simulation(ScriptedSemanticVerifier('entailment'))
    qa = semantic_input(case, gate)
    result = run(qa)
    actual = parent_status(gate)
    record(case['id'], 'MOCK_ADAPTER_QA_INTEGRATION', actual,
        expected=case['expected_status'], decisions=[asdict(d) for d in gate.observed],
        api_status=result['status'], served_claims=[c.claim_text for c in result['validated_claims']])
    if case['expected_status'] != 'SUPPORTED':
        assert result['status'] != 'ANSWER_VERIFIED'
        assert actual != 'SUPPORTED'
    # Positive controls within the explicitly supported numerical/date grammar.
    elif all((p := parse_bound_proposition(a['text'])) and p.kind in ('quantity','date') for a in case['atoms']):
        assert actual == 'SUPPORTED'
        assert result['status'] == 'ANSWER_VERIFIED'
    assert_clean(result)


@pytest.mark.parametrize('case', GOLD['deterministic_cases'], ids=lambda c:c['id'])
def test_38_proofs_use_shared_production_proof_path(case):
    evidence = tuple(Evidence(**e) for e in case['evidence'])
    ledger = EvidenceLedger(case['context_id'], tuple(d['doc_id'] for d in case['documents']), evidence,
        tuple(SourceFact(f['fact_id'], f['evidence_id'], f['line'], Quantity(**f['quantity'])) for f in case['facts']),
        tuple(CompositionCondition(**c) for c in case['conditions']),
        documents=tuple(DocumentIdentity(**d) for d in case['documents']))
    p = case['proof']
    proof = Proof(p['operation'], p['fact_ids'], Quantity(**p['goal']), p['condition_id'])
    text = proof.goal.declaration()
    atom = Atom('a', text, 0, len(text), tuple(e.evidence_id for e in evidence), proof)
    result = F1SupportGate().evaluate_proof(ParentClaim('parent', ledger.context_id, text, (atom,)), ledger)
    record(case['id'], 'DETERMINISTIC_SHARED_PRODUCTION_PROOF_PATH', result.status.value, expected=case['expected_status'])
    assert result.status.value == case['expected_status']


@pytest.mark.parametrize('case', GOLD['protocol_cases'], ids=lambda c:c['mode'])
def test_protocol_faults_go_through_qa(case):
    source = chunk('Permit T has not been approved.')
    adapter = ScriptedSemanticVerifier(case['mode'])
    gate = ProbeGate.for_simulation(adapter)
    result = run(qa_fixture([source], [claim('T has not received approval.',source)], gate))
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert gate.observed[0].status == S.ERROR and adapter.calls == 1
    record('protocol:'+case['mode'], 'MOCK_ADAPTER_QA_INTEGRATION', 'ERROR')
    assert_clean(result)


@pytest.mark.parametrize('case', [c for c in GOLD['semantic_cases'] if c.get('explanation')], ids=lambda c:c['id'])
def test_two_explanation_diagnostics_cannot_inherit_even_hostile_entailment(case):
    gate = ProbeGate.for_simulation(ScriptedSemanticVerifier('entailment'))
    result = run(semantic_input(case, gate))
    assert result['status'] == 'ANSWER_VERIFIED'
    assert case['explanation']['text'] not in json.dumps(result, default=lambda x:x.model_dump(),ensure_ascii=False)
    record('explanation:'+case['id'], 'DETERMINISTIC_OUTPUT_RESTRICTION', 'REMOVED')
    assert_clean(result)


def test_wrong_citation_cannot_borrow_an_entailing_uncited_source():
    a = chunk('Report T requires exactly 7 pages.', 'a.txt')
    b = chunk('Sample U has a mass of 3 mg.', 'b.txt')
    result = run(qa_fixture([a,b], [claim('T requires 7 pages.', b)]))
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert_clean(result)


def test_compound_tail_and_section_and_rejected_content_are_not_served():
    source = chunk('Report T requires exactly 7 pages.')
    bad = claim('T requires 7 pages. and T is approved.', source,
        thinking='T is approved.', section='Approved report')
    result = run(qa_fixture([source], [bad]))
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert 'approved' not in json.dumps(result, default=lambda x:x.model_dump()).lower()
    assert_clean(result)


def test_untrusted_locator_fields_cannot_echo_rejected_assertions():
    source = chunk('Report T requires exactly 7 pages.')
    candidate = claim('T is approved.', source)
    candidate.cited_doc_id = 'T is approved.'
    candidate.doc_version = 'T is approved.'
    candidate.doc_hash = 'T is approved.'
    result = run(qa_fixture([source],[candidate]))
    assert 'T is approved.' not in json.dumps(result, default=lambda x:x.model_dump())


@pytest.mark.parametrize('adverb', ['', 'currently '])
def test_request_conflict_outside_retrieved_top_k_is_detected_without_annotations(adverb):
    a = chunk('Report T requires exactly 7 pages.', 'a.txt')
    b = chunk(f'Report T {adverb}requires exactly 8 pages.', 'b.txt')
    qa = qa_fixture([a,b], [claim('T requires 7 pages.',a)], retrieved=[a])
    result = run(qa)
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert result['hallucination_flags'][0].verification_status == 'SOURCE_CONFLICT'
    assert run(qa, ['a.txt'])['status'] == 'ANSWER_VERIFIED'


@pytest.mark.parametrize('text', [
    'Only after review, Report T requires exactly 7 pages.',
    'Report T requires exactly 7 pages only if approved.',
    'If approved:\nReport T requires exactly 7 pages.',
])
def test_qualifications_cannot_be_deleted(text):
    source = chunk(text)
    result = run(qa_fixture([source], [claim('T requires 7 pages.',source)]))
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'


def test_unknown_extraction_keeps_full_conditions_negations_and_exceptions():
    text = 'Device T may be used only after review; it must not be used outside the lab, except during approved tests.'
    source = chunk(text)
    result = run(qa_fixture([source], [claim(text,source)]))
    assert result['status'] == 'ANSWER_VERIFIED'
    assert result['validated_claims'][0].claim_text == text


def test_summary_bypass_is_replaced_with_cited_full_source_extraction():
    source = chunk('Report T requires exactly 7 pages. It has not been approved.')
    qa = qa_fixture([source], proposal='### Approval\nT is approved.\n### Finance\nT costs 99 USD.')
    candidates = parse_summary_into_section_claims(qa.provider.generate_summary(), [source])
    assert candidates[0].verification_status == 'UNVERIFIED'
    result = qa.summarize_document(source.doc_id, [source.doc_id])
    assert result['status'] == 'SUMMARY_GENERATED' and result['summary'] == source.text
    assert result['validated_claims'][0].evidence_span['support_method'] == 'deterministic_extraction'
    assert_clean(result)


def test_summary_bad_provenance_conflict_and_unselected_target_abstain():
    a = chunk('Report T requires exactly 7 pages.', 'a.txt')
    b = chunk('Report T requires exactly 8 pages.', 'b.txt')
    qa = qa_fixture([a,b])
    for result in [qa.summarize_document('a.txt',['a.txt','b.txt']), qa.summarize_document('b.txt',['a.txt'])]:
        assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE' and result['summary'] == ''
    a.doc_hash = ''
    assert qa.summarize_document('a.txt',['a.txt'])['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'


def test_partial_quote_cannot_drop_negation_from_physical_context():
    source = chunk('Permit T has not been approved.')
    result = run(qa_fixture([source], [claim('T is approved.',source,quote='approved.')]))
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'


def test_cited_whole_line_cannot_drop_a_preceding_condition_header():
    source = chunk('If approved:\nReport T requires exactly 7 pages.')
    candidate = claim('T requires 7 pages.',source,quote='Report T requires exactly 7 pages.')
    candidate.cited_start_line = candidate.cited_end_line = 2
    assert run(qa_fixture([source],[candidate]))['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'


def test_unresolved_literal_conflict_also_blocks_complete_summary_extraction():
    source = chunk('Device T is eligible. Device T is not eligible.')
    assert qa_fixture([source]).summarize_document(source.doc_id)['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'


def test_explicit_model_unavailable_fails_closed_in_actual_qa(monkeypatch):
    import backend.services.f1_claim_support_service as module
    adapter = QualifiedLocalNLI(model_path='')
    monkeypatch.setattr(module,'get_f1_semantic_verifier',lambda:adapter)
    source = chunk('Permit T has not been approved.')
    gate = ProbeGate()
    result = run(qa_fixture([source], [claim('T has not received approval.',source)],gate))
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert gate.observed[0].status == S.ERROR


def test_actual_adapter_checks_overflow_without_silent_truncation(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace())
    adapter = QualifiedLocalNLI(model_path='unused')
    adapter._model = SimpleNamespace(config=SimpleNamespace(max_position_embeddings=512))
    tokenizer = Mock(return_value={'input_ids':SimpleNamespace(shape=(1,513))})
    tokenizer.model_max_length=512
    adapter._tokenizer=tokenizer
    import backend.services.f1_claim_support_service as module
    monkeypatch.setattr(module,'get_f1_semantic_verifier',lambda:adapter)
    source = chunk('Permit T has not been approved.')
    gate = ProbeGate()
    result = run(qa_fixture([source], [claim('T has not received approval.',source)],gate))
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert gate.observed[0].reason == 'VERIFIER_CONTEXT_OVERFLOW'
    assert tokenizer.call_args.kwargs['truncation'] is False


def test_no_unqualified_mock_can_enter_default_production_path(monkeypatch):
    import backend.services.f1_claim_support_service as module
    adapter = ScriptedSemanticVerifier('entailment')
    monkeypatch.setattr(module,'get_f1_semantic_verifier',lambda:adapter)
    source = chunk('Permit T has not been approved.')
    result = run(qa_fixture([source], [claim('T has not received approval.',source)]))
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE' and adapter.calls == 0


def test_bound_disjoint_addition_passes_actual_qa_and_missing_condition_abstains():
    text = ('Team C [sprint Q]: completed = 9 task.\n'
            'Team D [sprint Q]: completed = 6 task.\n'
            'Teams C+D [sprint Q]: disjoint(Team C, Team D); attribute=completed; unit=task.')
    source = chunk(text)
    goal = 'Teams C+D [sprint Q]: completed = 15 task.'
    result = run(qa_fixture([source],[claim(goal,source)]))
    assert result['status'] == 'ANSWER_VERIFIED'
    assert result['validated_claims'][0].evidence_span['support_method'] == 'deterministic_proof'
    source = chunk('\n'.join(text.splitlines()[:2]))
    assert run(qa_fixture([source],[claim(goal,source)]))['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'


@pytest.mark.parametrize('source_text,target', [
    ('Liều được kê cho bệnh nhân Q là 3/4 viên.', 'Liều của Q là 0,75 viên.'),
    ('Tài khoản Y có số dư ghi nhận là −8 USD.', 'Y có số dư âm tám USD.'),
    ('Sample Z has a mass of 17 mg.', 'Z has a mass of 0.017 g.'),
    ("Report Z's deadline is 2027-02-17.", 'Z is due on 17 February 2027.'),
])
def test_unseen_values_and_entities_use_bound_proofs(source_text,target):
    source = chunk(source_text)
    assert run(qa_fixture([source],[claim(target,source)]))['status'] == 'ANSWER_VERIFIED'


def test_actual_adapter_timeout_discards_result_and_bounds_work(monkeypatch):
    import threading
    import backend.services.f1_claim_support_service as module
    adapter=QualifiedLocalNLI(model_path='unused',timeout_seconds=0.02)
    released=threading.Event()
    calls=[]
    def blocked(request):
        calls.append(request)
        released.wait(2)
        return ScriptedSemanticVerifier('entailment').verify(request)
    monkeypatch.setattr(adapter,'_infer',blocked)  # SIMULATED inference, real deadline/worker path.
    monkeypatch.setattr(module,'get_f1_semantic_verifier',lambda:adapter)
    source=chunk('Permit T has not been approved.')
    qa=qa_fixture([source],[claim('T has not received approval.',source)])
    try:
        for _ in range(2):
            assert run(qa)['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'
        assert len(calls)==1
    finally:
        released.set()
        adapter._worker.shutdown(wait=True)


def test_actual_adapter_malformed_logits_fail_closed_through_qa(monkeypatch):
    import sys
    from contextlib import nullcontext
    import backend.services.f1_claim_support_service as module
    fake_torch=SimpleNamespace(inference_mode=nullcontext,
        isfinite=lambda _:SimpleNamespace(all=lambda:SimpleNamespace(item=lambda:False)))
    monkeypatch.setitem(sys.modules,'torch',fake_torch)
    adapter=QualifiedLocalNLI(model_path='unused')
    model=Mock(return_value=SimpleNamespace(logits=SimpleNamespace(shape=(1,3))))
    model.config=SimpleNamespace(max_position_embeddings=512)
    tokenizer=Mock(return_value={'input_ids':SimpleNamespace(shape=(1,12))})
    tokenizer.model_max_length=512
    adapter._model,adapter._tokenizer=model,tokenizer
    monkeypatch.setattr(module,'get_f1_semantic_verifier',lambda:adapter)
    source=chunk('Permit T has not been approved.')
    gate=ProbeGate()
    result=run(qa_fixture([source],[claim('T has not received approval.',source)],gate))
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert gate.observed[0].reason=='INVALID_SEMANTIC_PROTOCOL'


def test_supported_compound_retains_all_components_and_accurate_execution_kind():
    source=chunk('Report T requires exactly 7 pages. Sample U has a mass of 3 mg.')
    text='T requires 7 pages. and U has a mass of 0.003 g.'
    result=run(qa_fixture([source],[claim(text,source)]))
    assert result['status']=='ANSWER_VERIFIED'
    output=result['validated_claims'][0]
    assert output.claim_text==text
    assert output.evidence_span['support_method']=='deterministic_compound'
    assert output.evidence_span['execution_kind']=='DETERMINISTIC'
