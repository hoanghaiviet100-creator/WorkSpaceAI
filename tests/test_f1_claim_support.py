"""Offline support core: real bounded proofs, separately labelled scripted semantics."""
from dataclasses import FrozenInstanceError, asdict, replace
import json
import os
from pathlib import Path

import pytest

from backend.algorithms.f1_claim_support import (
    Atom, CompositionCondition, DocumentIdentity, Evidence, EvidenceLedger, ParentClaim, Proof, Quantity,
    SourceFact, SupportStatus as S, audit_ledger, check_proof, fingerprint,
)
from backend.providers.f1_claim_support_provider import ScriptedSemanticVerifier
from backend.services.f1_claim_support_service import ClaimSupportController

GOLD = json.loads((Path(__file__).parent / 'fixtures/f1_claim_support_gold.json').read_text(encoding='utf-8'))


def ledger_from(case):
    records = tuple(Evidence(**r) for r in case['evidence'])
    facts = tuple(SourceFact(f['fact_id'], f['evidence_id'], f['line'], Quantity(**f['quantity'])) for f in case.get('facts', []))
    return EvidenceLedger(case['context_id'], tuple(dict.fromkeys(e.doc_id for e in records)), records,
        facts, tuple(CompositionCondition(**c) for c in case.get('conditions', [])),
        case.get('context_complete', True), case.get('conflict_groups', ()),
        tuple(DocumentIdentity(**d) for d in case['documents']))


def deterministic(case):
    ledger = ledger_from(case)
    p = case['proof']
    proof = Proof(p['operation'], p['fact_ids'], Quantity(**p['goal']), p['condition_id'])
    text = proof.goal.declaration()
    atom = Atom('a1', text, 0, len(text), tuple(e.evidence_id for e in ledger.evidence), proof)
    return ledger, ParentClaim(case['id'], ledger.context_id, text, (atom,))


def semantic(case):
    ledger = ledger_from(case)
    atoms, labels, cursor, parts = [], [], 0, []
    for index, data in enumerate(case['atoms']):
        if index: cursor += len(case['joiner'])
        atom = Atom('a'+str(index+1), data['text'], cursor, cursor+len(data['text']), data['evidence_ids'])
        atoms.append(atom); labels.append((atom.claim_id, data['mock_label'])); parts.append(data['text'])
        cursor = atom.end
    explanation = None
    if case.get('explanation'):
        d = case['explanation']; explanation = Atom('explanation', d['text'], 0, len(d['text']), d['evidence_ids'])
        labels.append(('explanation', d['mock_label']))
    parent = ParentClaim(case['id'], ledger.context_id, case['joiner'].join(parts), atoms, explanation)
    return ledger, parent, ScriptedSemanticVerifier(labels=labels)


def observe(case, result):
    path = os.getenv('CITATION_TEST_EVIDENCE')
    if path:
        with Path(path).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(case=case['id'], execution_kind=case['execution_kind'],
                real_model_accuracy='UNMEASURED', decision=asdict(result)), ensure_ascii=False) + '\n')


@pytest.mark.parametrize('case', GOLD['deterministic_cases'], ids=lambda c:c['id'])
def test_actual_bounded_proofs(case):
    ledger, parent = deterministic(case)
    before = asdict(ledger), asdict(parent)
    adapter = ScriptedSemanticVerifier('entailment')
    result = ClaimSupportController(adapter).verify(parent, ledger)
    observe(case, result)
    assert result.status.value == case['expected_status']
    assert (result.claim_id, result.context_id, result.original_text) == (parent.claim_id, ledger.context_id, parent.text)
    assert not result.simulated and not result.production_semantic_authorized and adapter.calls == 0
    assert set(result.evidence_ids) <= {e.evidence_id for e in ledger.evidence}
    assert (result.supported_text == parent.text) == (result.status == S.SUPPORTED)
    if result.status in (S.SUPPORTED, S.CONTRADICTED):
        assert result.checked_proof is not None and result.checked_proof.fact_ids == parent.atoms[0].proof.fact_ids
    assert (asdict(ledger), asdict(parent)) == before


@pytest.mark.parametrize('case', GOLD['semantic_cases'], ids=lambda c:c['id'])
def test_scripted_semantic_protocol_not_accuracy(case):
    ledger, parent, adapter = semantic(case)
    default = ClaimSupportController(adapter).verify(parent, ledger)
    assert default.status != S.SUPPORTED and default.supported_text is None and adapter.calls == 0
    result = ClaimSupportController.for_simulation(adapter).verify(parent, ledger)
    observe(case, result)
    assert result.status.value == case['expected_status']
    assert result.original_text == parent.text and result.context_id == ledger.context_id
    assert not result.production_semantic_authorized
    assert result.simulated or result.reason_code == 'SOURCE_CONFLICT'
    assert (result.supported_text == parent.text) == (result.status == S.SUPPORTED)
    if case.get('explanation'):
        assert result.supported_explanation is None and result.explanation_status == S.INSUFFICIENT_EVIDENCE
    if 'partial_compound' in case['id']:
        assert result.supported_text is None and len(result.atom_decisions) == 2
        assert [d.status for d in result.atom_decisions] == [S.SUPPORTED, S.INSUFFICIENT_EVIDENCE]


def test_four_status_contract_and_draft_labels():
    assert {s.value for s in S} == {'SUPPORTED','CONTRADICTED','INSUFFICIENT_EVIDENCE','ERROR'}
    assert GOLD['corpus_status'] == 'DRAFT_GOLD_PENDING_HUMAN_ADJUDICATION'
    assert GOLD['independently_reviewed'] is False and GOLD['real_model_accuracy'] == 'UNMEASURED'
    with pytest.raises(ValueError): S('CONFIDENT')


def base():
    return deterministic(next(c for c in GOLD['deterministic_cases'] if c['id'] == 'quantity_equal_en'))


def test_ledger_contracts_are_frozen_and_detached_from_lists():
    ledger, parent = base(); selected=list(ledger.selected_doc_ids); records=list(ledger.evidence)
    frozen = replace(ledger, selected_doc_ids=selected, evidence=records)
    selected.clear(); records.clear()
    assert frozen.evidence == ledger.evidence and frozen.selected_doc_ids == ledger.selected_doc_ids
    for obj, field, value in [(frozen,'context_id','other'), (frozen.evidence[0],'text','modified'),
                              (parent,'text','modified'), (parent.atoms[0],'evidence_ids',())]:
        with pytest.raises(FrozenInstanceError): setattr(obj,field,value)


@pytest.mark.parametrize('field,value', [
    ('doc_hash','invalid'),('doc_version',''),('content_fingerprint','0'*64),('text','changed'),
    ('page',0),('line_start',0),('line_end',3),('context_id','another-request'),('doc_id','unselected.txt'),
])
def test_invalid_provenance_never_authorizes(field,value):
    ledger,parent=base(); bad=replace(ledger.evidence[0],**{field:value})
    result=ClaimSupportController.for_simulation(ScriptedSemanticVerifier()).verify(parent,replace(ledger,evidence=(bad,)))
    assert result.status == S.ERROR and result.supported_text is None


def test_conflicting_overlap_and_version_fail_closed():
    ledger,parent=base(); e=ledger.evidence[0]
    for other in [replace(e,evidence_id='e2',text='Different physical line.',content_fingerprint=fingerprint('Different physical line.')),
                  replace(e,evidence_id='e2',doc_version='v2')]:
        assert ClaimSupportController().verify(parent,replace(ledger,evidence=(e,other))).status == S.ERROR


def test_source_fact_cannot_rebind_entity_value_or_scope_by_annotation():
    ledger,parent=base(); fact=ledger.facts[0]
    for field,value in [('entity','Someone else'),('scope','Elsewhere'),('value','99'),('unit','USD')]:
        altered=replace(fact,quantity=replace(fact.quantity,**{field:value}))
        assert ClaimSupportController().verify(parent,replace(ledger,facts=(altered,))).status == S.ERROR


def test_conflicting_bound_quantities_cannot_be_overridden_by_mock():
    ledger,parent=base(); f=ledger.facts[0]; q=replace(f.quantity,value='99'); text=q.declaration()
    e=replace(ledger.evidence[0],evidence_id='e2',doc_id='other.txt',text=text,doc_hash=fingerprint(text),content_fingerprint=fingerprint(text))
    conflict=replace(ledger,selected_doc_ids=ledger.selected_doc_ids+(e.doc_id,),evidence=ledger.evidence+(e,),
                     facts=ledger.facts+(SourceFact('f2','e2',1,q),),
                     documents=ledger.documents+(DocumentIdentity(e.doc_id,e.doc_version,e.doc_hash),))
    adapter=ScriptedSemanticVerifier()
    result=ClaimSupportController.for_simulation(adapter).verify(parent,conflict)
    assert result.status==S.INSUFFICIENT_EVIDENCE and result.reason_code=='SOURCE_CONFLICT' and adapter.calls==0


def test_checked_contradiction_cannot_be_overridden_by_mock():
    case=next(c for c in GOLD['deterministic_cases'] if c['id']=='quantity_wrong_en')
    ledger,parent=deterministic(case); adapter=ScriptedSemanticVerifier()
    result=ClaimSupportController.for_simulation(adapter).verify(parent,ledger)
    assert result.status==S.CONTRADICTED and adapter.calls==0


@pytest.mark.parametrize('mutation', ['duplicate_fact','unknown_fact','wrong_entity','wrong_scope','wrong_unit','unknown_operation','wrong_text'])
def test_proof_binding_cannot_be_relaxed(mutation):
    ledger,parent=base(); atom=parent.atoms[0]; p=atom.proof
    if mutation=='duplicate_fact': p=replace(p,fact_ids=('f1','f1'))
    if mutation=='unknown_fact': p=replace(p,fact_ids=('absent',))
    if mutation=='wrong_entity': p=replace(p,goal=replace(p.goal,entity='Elsewhere'))
    if mutation=='wrong_scope': p=replace(p,goal=replace(p.goal,scope='other'))
    if mutation=='wrong_unit': p=replace(p,goal=replace(p.goal,attribute='dose',unit='tablet'))
    if mutation=='unknown_operation': p=replace(p,operation='eval')
    text=p.goal.declaration() if mutation!='wrong_text' else 'Completely different natural-language assertion.'
    atom=replace(atom,proof=p,text=text,end=len(text)); parent=replace(parent,text=text,atoms=(atom,))
    adapter=ScriptedSemanticVerifier(); result=ClaimSupportController.for_simulation(adapter).verify(parent,ledger)
    assert result.status!=S.SUPPORTED and adapter.calls==0


def test_composition_conditions_must_be_source_bound_and_complete():
    case=next(c for c in GOLD['deterministic_cases'] if c['id']=='sum_en'); ledger,parent=deterministic(case)
    c=ledger.conditions[0]; atom=parent.atoms[0]
    for altered in [replace(ledger,conditions=()),replace(ledger,context_complete=False),
                    replace(ledger,conditions=(replace(c,left_entity='Unbound entity'),))]:
        assert ClaimSupportController().verify(parent,altered).status!=S.SUPPORTED
    no_condition_ref=replace(atom,evidence_ids=('e1','e2'))
    assert ClaimSupportController().verify(replace(parent,atoms=(no_condition_ref,)),ledger).status!=S.SUPPORTED


@pytest.mark.parametrize('mutation', ['tail','gap','wrong_slice','no_atoms','same_count_missing_relation'])
def test_parent_coverage_requires_exact_text_and_relationships(mutation):
    ledger,parent=base(); a=parent.atoms[0]
    if mutation=='tail': parent=replace(parent,text=parent.text+' and it is approved.')
    if mutation=='gap': parent=replace(parent,text='Only '+parent.text,atoms=(replace(a,start=5,end=a.end+5),))
    if mutation=='wrong_slice': parent=replace(parent,atoms=(replace(a,text='wrong'),))
    if mutation=='no_atoms': parent=replace(parent,atoms=())
    if mutation=='same_count_missing_relation':
        second=replace(a,claim_id='a2',start=a.end+9,end=a.end+9+len(a.text))
        parent=replace(parent,text=a.text+' because '+a.text,atoms=(a,second))
    result=ClaimSupportController.for_simulation(ScriptedSemanticVerifier()).verify(parent,ledger)
    assert result.status==S.INSUFFICIENT_EVIDENCE and result.original_text==parent.text and result.supported_text is None


@pytest.mark.parametrize('mutation',['wrong_context','duplicate_claim','unknown_evidence','duplicate_evidence','duplicate_ledger_id'])
def test_internal_identifiers_fail_closed(mutation):
    ledger,parent=base(); a=parent.atoms[0]
    if mutation=='wrong_context': parent=replace(parent,context_id='different')
    if mutation=='duplicate_claim': parent=replace(parent,atoms=(a,a))
    if mutation=='unknown_evidence': parent=replace(parent,atoms=(replace(a,evidence_ids=('unknown',)),))
    if mutation=='duplicate_evidence': parent=replace(parent,atoms=(replace(a,evidence_ids=('e1','e1')),))
    if mutation=='duplicate_ledger_id': ledger=replace(ledger,evidence=ledger.evidence*2)
    assert ClaimSupportController().verify(parent,ledger).status==S.ERROR


def test_unverified_explanation_is_omitted_without_losing_valid_parent():
    ledger,parent=base(); text='The report has been approved.'
    parent=replace(parent,explanation=Atom('explanation',text,0,len(text),('e1',)))
    result=ClaimSupportController(ScriptedSemanticVerifier()).verify(parent,ledger)
    assert result.status==S.SUPPORTED and result.supported_text==parent.text
    assert result.supported_explanation is None and result.explanation_status==S.INSUFFICIENT_EVIDENCE


def test_unqualified_backend_cannot_self_authorize():
    case=next(c for c in GOLD['semantic_cases'] if c['id']=='paraphrase_en')
    ledger,parent,adapter=semantic(case); adapter.qualified=True; adapter.confidence=1.0
    normal=ClaimSupportController(adapter).verify(parent,ledger)
    simulated=ClaimSupportController.for_simulation(adapter).verify(parent,ledger)
    assert normal.status==S.INSUFFICIENT_EVIDENCE and simulated.status==S.SUPPORTED
    assert simulated.simulated and not simulated.production_semantic_authorized and adapter.calls==1
    with pytest.raises(ValueError): replace(simulated,production_semantic_authorized=True)


def test_always_abstain_fails_positive_controls():
    positives=[c for c in GOLD['semantic_cases'] if c['expected_status']=='SUPPORTED']
    assert positives
    accepted=0
    for case in positives:
        ledger,parent,_=semantic(case)
        result=ClaimSupportController.for_simulation(ScriptedSemanticVerifier('neutral')).verify(parent,ledger)
        accepted += result.status==S.SUPPORTED
    assert accepted==0  # An abstain-only candidate fails every scripted positive expectation.
    ledger,parent=base()
    assert ClaimSupportController().verify(parent,ledger).status==S.SUPPORTED  # Actual proof positive.


def test_proof_execution_performs_no_file_or_network_io(monkeypatch):
    ledger,parent=base()
    def forbidden(*args,**kwargs): raise AssertionError('unexpected I/O')
    monkeypatch.setattr('builtins.open',forbidden)
    assert ClaimSupportController().verify(parent,ledger).status==S.SUPPORTED


def test_mutable_values_cannot_hide_in_evidence_or_quantities():
    ledger,parent=base(); e=ledger.evidence[0]; q=ledger.facts[0].quantity
    for field in ('text','doc_id','doc_hash','content_fingerprint'):
        with pytest.raises(TypeError): replace(e,**{field:['mutable']})
    with pytest.raises(TypeError): replace(q,unit=['mg'])
    with pytest.raises(TypeError): replace(ledger,evidence=({'text':'mutable'},))
    with pytest.raises(TypeError): replace(parent,atoms=({'text':'mutable'},))


def test_verified_deterministic_explanation_is_retained():
    ledger,parent=base(); a=replace(parent.atoms[0],claim_id='explanation')
    result=ClaimSupportController().verify(replace(parent,explanation=a),ledger)
    assert result.status==S.SUPPORTED and result.supported_explanation==a.text
    assert result.explanation_status==S.SUPPORTED and not result.simulated


def test_complete_two_atom_conjunction_is_supported_without_count_based_coverage():
    ledger,parent=base(); a=parent.atoms[0]; b=replace(a,claim_id='a2',start=a.end+5,end=a.end+5+len(a.text))
    parent=replace(parent,text=a.text+' and '+a.text,atoms=(a,b))
    result=ClaimSupportController().verify(parent,ledger)
    assert result.status==S.SUPPORTED and result.supported_text==parent.text and len(result.atom_decisions)==2


def test_request_local_records_cannot_be_reused_in_another_context():
    ledger,parent=base()
    other=replace(ledger,context_id='other-request')
    assert ClaimSupportController().verify(replace(parent,context_id='other-request'),other).status==S.ERROR


def test_trusted_document_identity_rejects_self_asserted_hash():
    ledger,parent=base()
    bad=replace(ledger.evidence[0],doc_hash='0'*64)
    assert ClaimSupportController().verify(parent,replace(ledger,evidence=(bad,))).status==S.ERROR


@pytest.mark.parametrize('mutation',['missing','duplicate','version','unselected'])
def test_invalid_document_manifest_cannot_authorize(mutation):
    ledger,parent=base(); d=ledger.documents[0]
    if mutation=='missing': docs=()
    if mutation=='duplicate': docs=(d,d)
    if mutation=='version': docs=(replace(d,doc_version='v999'),)
    if mutation=='unselected': docs=(replace(d,doc_id='unselected.txt'),)
    result=ClaimSupportController().verify(parent,replace(ledger,documents=docs))
    assert result.status==S.ERROR and result.supported_text is None


def fix01_ledger(total='99', *, values=('12', '8'), total_changes=None, condition_changes=None):
    """Fixed selected synthetic sources; no model, extraction or repository reads."""
    quantities = [Quantity('A', 'S', 'completed', values[0], 'task'),
                  Quantity('B', 'S', 'completed', values[1], 'task')]
    condition = CompositionCondition('d1', 'e3', 1, 'A', 'B', 'AB', 'S')
    if condition_changes:
        condition = replace(condition, **condition_changes)
    records = []
    facts = []
    for index, q in enumerate(quantities, 1):
        text = q.declaration()
        records.append(Evidence('fix01', 'e'+str(index), 'source'+str(index)+'.txt', 'v1',
                                fingerprint(text), 1, 1, 1, text, fingerprint(text)))
        facts.append(SourceFact('f'+str(index), 'e'+str(index), 1, q))
    text = condition.declaration()
    records.append(Evidence('fix01', 'e3', 'condition.txt', 'v1', fingerprint(text), 1, 1, 1, text, fingerprint(text)))
    if total is not None:
        q = Quantity('AB', 'S', 'completed', total, 'task')
        if total_changes:
            q = replace(q, **total_changes)
        text = q.declaration()
        records.append(Evidence('fix01', 'e4', 'total.txt', 'v1', fingerprint(text), 1, 1, 1, text, fingerprint(text)))
        facts.append(SourceFact('f_total', 'e4', 1, q))
    return EvidenceLedger('fix01', tuple(e.doc_id for e in records), tuple(records), tuple(facts), (condition,),
        documents=tuple(DocumentIdentity(e.doc_id, e.doc_version, e.doc_hash) for e in records))


def fix01_parent(ledger, operation='add', target='20', *, narrow_refs=False):
    goal = Quantity('AB', 'S', 'completed', target, 'task')
    proof = Proof(operation, ('f1', 'f2') if operation == 'add' else ('f_total',),
                  goal, 'd1' if operation == 'add' else None)
    refs = (('e1', 'e2', 'e3') if operation == 'add' else ('e4',)) if narrow_refs else tuple(e.evidence_id for e in ledger.evidence)
    text = goal.declaration()
    return ParentClaim('fix01_parent', ledger.context_id, text, (Atom('fix01_atom', text, 0, len(text), refs, proof),))


def fix01_check(case, ledger, parent, expected, reason=None):
    before = asdict(ledger), asdict(parent)
    audit = audit_ledger(ledger)
    proof = check_proof(parent.atoms[0], ledger)
    adapter = ScriptedSemanticVerifier('entailment')
    controller = ClaimSupportController.for_simulation(adapter)
    decision = controller.verify(parent, ledger)
    path = os.getenv('CITATION_TEST_EVIDENCE')
    if path:
        with Path(path).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(case=case, execution_kind='FIX01_ACTUAL_DETERMINISTIC',
                ledger=asdict(ledger), parent=asdict(parent), expected_status=expected,
                expected_reason=reason, audit=audit, proof=asdict(proof), decision=asdict(decision),
                real_model_accuracy='UNMEASURED'), ensure_ascii=False) + '\n')
    assert proof.status == expected and decision.status == expected
    assert decision.original_text == parent.text and decision.context_id == ledger.context_id
    assert (decision.supported_text == parent.text) == (expected == S.SUPPORTED)
    assert proof.claim_id == parent.atoms[0].claim_id and decision.claim_id == parent.claim_id
    assert not decision.simulated and not decision.production_semantic_authorized and adapter.calls == 0
    if reason == 'SOURCE_CONFLICT':
        assert audit == (S.INSUFFICIENT_EVIDENCE, 'SOURCE_CONFLICT')
        assert proof.checked_proof is None and decision.checked_proof is None
    else:
        assert audit is None
    if reason:
        assert proof.reason_code == reason and decision.reason_code == reason
    assert (asdict(ledger), asdict(parent)) == before
    return decision


@pytest.mark.parametrize('operation', ['add', 'compare'])
@pytest.mark.parametrize('target', ['20', '99'])
@pytest.mark.parametrize('narrow_refs', [False, True], ids=['all_evidence', 'selected_proof_only'])
@pytest.mark.parametrize('reverse', [False, True], ids=['source_order', 'reversed_order'])
def test_fix01_negative_conflict_is_independent_of_proof_selection(operation, target, narrow_refs, reverse):
    ledger = fix01_ledger()
    if reverse:
        ledger = replace(ledger, facts=tuple(reversed(ledger.facts)), evidence=tuple(reversed(ledger.evidence)),
                         documents=tuple(reversed(ledger.documents)))
    parent = fix01_parent(ledger, operation, target, narrow_refs=narrow_refs)
    fix01_check('conflict_'+operation+'_'+target+'_'+str(narrow_refs)+'_'+str(reverse), ledger, parent,
                S.INSUFFICIENT_EVIDENCE, 'SOURCE_CONFLICT')


@pytest.mark.parametrize('operation', ['add', 'compare'])
def test_fix01_matching_direct_total_is_supported(operation):
    ledger = fix01_ledger('20')
    decision = fix01_check('matching_'+operation, ledger, fix01_parent(ledger, operation), S.SUPPORTED)
    assert decision.checked_proof.actual_value == '20'


def test_fix01_no_direct_total_keeps_valid_addition():
    ledger = fix01_ledger(None)
    assert fix01_check('no_direct_total', ledger, fix01_parent(ledger), S.SUPPORTED).checked_proof.actual_value == '20'


@pytest.mark.parametrize('changes', [
    {'entity': 'Other'}, {'scope': 'Other'},
    {'attribute': 'pages', 'unit': 'page'}, {'attribute': 'mass', 'unit': 'kg'},
], ids=['another_entity', 'another_scope', 'another_attribute', 'another_dimension'])
def test_fix01_unrelated_direct_fact_is_not_a_conflict(changes):
    ledger = fix01_ledger(total_changes=changes)
    fix01_check('unrelated_'+next(iter(changes))+'_'+next(iter(changes.values())), ledger, fix01_parent(ledger), S.SUPPORTED)


def test_fix01_incorrect_arithmetic_without_conflict_is_contradicted():
    ledger = fix01_ledger(None)
    fix01_check('incorrect_arithmetic', ledger, fix01_parent(ledger, target='21'), S.CONTRADICTED, 'CHECKED_CONTRADICTION')


def test_fix01_missing_disjointness_cannot_derive_a_conflict_or_support_addition():
    ledger = replace(fix01_ledger(), conditions=())
    fix01_check('missing_disjointness', ledger, fix01_parent(ledger), S.INSUFFICIENT_EVIDENCE, 'MISSING_COMPOSITION_CONDITION')
    direct = fix01_parent(ledger, 'compare', '99')
    fix01_check('missing_disjointness_direct', ledger, direct, S.SUPPORTED)


@pytest.mark.parametrize('total,expected', [('0.3', S.SUPPORTED), ('0.31', S.INSUFFICIENT_EVIDENCE)])
def test_fix01_fraction_totals_use_exact_arithmetic(total, expected):
    ledger = fix01_ledger(total, values=('1/10', '1/5'))
    decision = fix01_check('fractions_'+total, ledger, fix01_parent(ledger, target='3/10'), expected,
                           'SOURCE_CONFLICT' if expected == S.INSUFFICIENT_EVIDENCE else None)
    if expected == S.SUPPORTED:
        assert decision.checked_proof.actual_value == '3/10'


def test_fix01_complete_signed_totals_are_preserved():
    ledger = fix01_ledger('−2', values=('−10', '+8'))
    decision = fix01_check('signed_total', ledger, fix01_parent(ledger, target='-2'), S.SUPPORTED)
    assert decision.checked_proof.actual_value == '-2' and '−10' in ledger.evidence[0].text


@pytest.mark.parametrize('changes', [
    {'kind': 'overlap'}, {'scope': 'Other'}, {'attribute': 'pages'},
    {'unit': 'page'}, {'left_entity': 'Missing'}, {'right_entity': 'A'},
], ids=['not_disjoint', 'wrong_scope', 'wrong_attribute', 'wrong_unit', 'missing_operand', 'same_operand'])
def test_fix01_inapplicable_conditions_do_not_create_conflicts(changes):
    ledger = fix01_ledger(condition_changes=changes)
    fix01_check('inapplicable_'+next(iter(changes)), ledger, fix01_parent(ledger, 'compare', '99'), S.SUPPORTED)


def test_fix01_no_recursive_derivation_is_introduced():
    # AB has no direct quantity. A second rule mentioning it cannot recursively
    # derive a contradiction for ABC; this audit is deliberately one step only.
    ledger = fix01_ledger(None)
    q = Quantity('ABC', 'S', 'completed', '99', 'task')
    c = CompositionCondition('d2', 'e5', 1, 'AB', 'B', 'ABC', 'S')
    extra = []
    for evidence_id, doc_id, text in [('e4', 'abc.txt', q.declaration()), ('e5', 'abc_condition.txt', c.declaration())]:
        extra.append(Evidence('fix01', evidence_id, doc_id, 'v1', fingerprint(text), 1, 1, 1, text, fingerprint(text)))
    ledger = replace(ledger, selected_doc_ids=ledger.selected_doc_ids+tuple(e.doc_id for e in extra),
        evidence=ledger.evidence+tuple(extra), facts=ledger.facts+(SourceFact('f_total', 'e4', 1, q),),
        conditions=ledger.conditions+(c,), documents=ledger.documents+tuple(DocumentIdentity(e.doc_id, e.doc_version, e.doc_hash) for e in extra))
    fix01_check('no_recursive_derivation', ledger, fix01_parent(ledger), S.SUPPORTED)
