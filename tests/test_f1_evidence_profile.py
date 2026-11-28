"""Controlled safety regression. Scripted NLI is never actual-model quality."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from backend.core.schemas import DocumentChunk,DocumentMetadata,GeneratedClaim
from backend.algorithms.f1_claim_support import fingerprint
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.f1_evidence_profile_service import F1EvidenceProfileService,EvidenceProfileError

def fixture(text='The filter permits water transfer.',other=None):
    repo=WorkspaceRepository()
    for name,source in [('source.txt',text),('context.txt',other)]:
        if source is None:continue
        digest=fingerprint(source)
        repo.chunks.append(DocumentChunk(chunk_id=name,doc_id=name,doc_name=name,text=source,
            page_number=1,start_line=1,end_line=len(source.splitlines()),doc_version='v1',doc_hash=digest))
        repo.documents[name]=DocumentMetadata(doc_id=name,doc_name=name,file_type='txt',
            file_hash=digest,version_id='v1',is_selected=True)
    repo._rebuild_index();c=repo.chunks[0]
    claim=GeneratedClaim(claim_text=text,evidence_quote=text,cited_doc_id=c.doc_id,cited_page=1,
        cited_start_line=1,cited_end_line=c.end_line,doc_version='v1',doc_hash=c.doc_hash)
    return repo,claim

def entail(context,items,evidence):return {i.claim_id:'SUPPORTED' for i in items}

def test_exact_citation_does_not_authorize_wrong_entity():
    repo,claim=fixture('Hemoglobin carries oxygen.')
    claim.claim_text='Chlorophyll carries oxygen.'
    gate=F1EvidenceProfileService(repo)
    with patch.object(gate,'_nli',side_effect=AssertionError('No inference should bypass identity guard')):
        result=gate.verify_claims([claim],['source.txt'])
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'

@pytest.mark.parametrize('patch_value',[dict(doc_hash='0'*64),dict(doc_version='stale'),dict(cited_doc_id='missing.txt')])
def test_invalid_provenance_cannot_fallback(patch_value):
    repo,claim=fixture();gate=F1EvidenceProfileService(repo)
    with patch.object(gate,'_nli',side_effect=AssertionError('Invalid citation reached NLI')):
        result=gate.verify_claims([claim.model_copy(update=patch_value)],['source.txt'])
    assert result['status']!='SOURCE_SUPPORTED' and not result['citations']

def test_whole_support_cannot_override_unsupported_atom():
    repo,claim=fixture('Heating increases motion. Faster motion raises temperature.')
    gate=F1EvidenceProfileService(repo)
    def partial(context,items,evidence):
        return {i.claim_id:'INSUFFICIENT_EVIDENCE' if i.claim_id=='support:atom:1' else 'SUPPORTED' for i in items}
    with patch.object(gate,'_nli',side_effect=partial):result=gate.verify_claims([claim],['source.txt'])
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'

def test_unresolved_detected_contradiction_blocks_and_retains_evidence():
    repo,claim=fixture(other='The filter prevents water transfer.')
    gate=F1EvidenceProfileService(repo)
    def contradiction(context,items,evidence):
        return {i.claim_id:'CONTRADICTED' if i.claim_id.startswith('competing:') else 'SUPPORTED' for i in items}
    with patch.object(gate,'_nli',side_effect=contradiction):result=gate.verify_claims([claim],list(repo.documents))
    row=result['verification']['claims'][0]
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert row['disposition']=='INSUFFICIENT_CONFLICT_COVERAGE'
    assert any(e['verdict']=='UNRESOLVED_SIGNAL' and e['citations'] for e in row['competing_evidence'])

def test_timeout_is_execution_error_and_lock_drains_without_fallback():
    repo,claim=fixture();gate=F1EvidenceProfileService(repo)
    with patch.object(gate,'_nli',side_effect=TimeoutError('VERIFIER_TIMEOUT')):
        with pytest.raises(EvidenceProfileError,match='VERIFIER_TIMEOUT'):gate.verify_claims([claim],['source.txt'])
    with patch.object(gate,'_nli',side_effect=entail):result=gate.verify_claims([claim],['source.txt'])
    assert result['status']=='SOURCE_SUPPORTED'

def test_retrieval_searches_entire_selected_scope_and_discloses_incomplete_coverage():
    repo,claim=fixture(other='The appendix describes equipment.')
    gate=F1EvidenceProfileService(repo)
    with patch.object(gate,'_nli',side_effect=entail),patch.object(repo,'search',return_value=[]) as search:
        result=gate.verify_claims([claim],None)
    assert all(set(call.kwargs['selected_doc_ids'])==set(repo.documents) for call in search.call_args_list)
    assert result['verification']['coverage']=='INCOMPLETE' and result['verification']['limitations']
    assert result['status']=='SOURCE_SUPPORTED' and result['validated_claims']==[]

def test_request_owned_adapter_is_drained_each_time():
    repo,claim=fixture();owned=[]
    class ControlledAdapter:
        def __init__(self):
            owned.append(self);self.drained=False
            self._worker=SimpleNamespace(shutdown=lambda wait:setattr(self,'drained',True))
        def warmup(self):pass
        def verify(self,request):
            return dict(context_id=request.context_id,decisions=[dict(claim_id=i.claim_id,
                context_id=request.context_id,label='entailment',evidence_ids=list(i.evidence_ids)) for i in request.items])
    with patch('backend.services.f1_evidence_profile_service.QualifiedLocalNLI',ControlledAdapter):
        for _ in range(2):
            assert F1EvidenceProfileService(repo).verify_claims([claim],['source.txt'])['status']=='SOURCE_SUPPORTED'
    assert len(owned)==2 and all(a.drained for a in owned)
