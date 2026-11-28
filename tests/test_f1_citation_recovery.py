"""F1-CITATION-01A: fixed offline inputs; citation integrity, not entailment.

M2 retains all direct citation-integrity assertions. API expectations additionally
require support, preserve submitted locators, and redact rejected factual text.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.algorithms.citation_verifier import CitationClaim, verify_citations
from backend.core.config import settings
from backend.core.schemas import DocumentChunk, GeneratedClaim
from backend.providers.llm_provider import GenerationError, LLMProvider
from backend.services.qa_service import QAService, align_claim_to_chunks

qa_module = importlib.import_module('backend.services.qa_service')
A1 = 'The report requires exactly 12 pages.'
A2 = 'The permit is not approved.'
A3 = 'The result is -10 units and x < 0.'
A4 = 'Alice pays Bob.'


def chunk(doc='A.pdf', page=1, text=None, start=1, version='v1', name=None, digest=None):
    text = text if text is not None else '\n'.join([A1, A2, A3, A4])
    return DocumentChunk(chunk_id=f'{doc}-{page}-{start}', doc_id=doc, doc_name=name or doc,
                         page_number=page, start_line=start, end_line=start + len(text.splitlines()) - 1,
                         text=text, score=1.0, doc_version=version,
                         doc_hash=digest if digest is not None else hashlib.sha256(text.encode()).hexdigest())


def claim(quote=A1, text=None, doc='A.pdf', page=1, start=1, end=1, **extra):
    return GeneratedClaim(claim_text=text or quote, cited_doc_id=doc, cited_page=page,
                          cited_start_line=start, cited_end_line=end, evidence_quote=quote, **extra)


def legacy_lookup(chunks):
    lookup = {}
    for c in chunks:
        key = (c.doc_id, c.page_number)
        entry = lookup.setdefault(key, dict(text='', total_lines=0, doc_version=c.doc_version,
                                           doc_hash=c.doc_hash, line_map={}))
        for offset, line in enumerate(c.text.splitlines()):
            entry['line_map'][c.start_line + offset] = line
        entry['text'] = '\n'.join(entry['line_map'][i] for i in sorted(entry['line_map']))
        entry['total_lines'] = max(entry['line_map'])
    return lookup


@pytest.fixture
def fixed(monkeypatch):
    monkeypatch.setattr(settings, 'llm_provider', 'ollama')
    # B is a separate trusted source with different provenance.
    chunks = [chunk(), chunk('B.pdf', page=2, text='Beta produces exactly 20 units.', version='v2')]
    class Fixed:
        def run(self, claims, source=None, retrieved=None, selected=None, **kwargs):
            source = chunks if source is None else source
            retrieved = source if retrieved is None else retrieved
            repo = SimpleNamespace(chunks=source, dense_available=False,
                search=lambda *a, **k: retrieved, build_page_lookup=lambda: legacy_lookup(source))
            provider = SimpleNamespace(generate_grounded_qa=lambda *a, **k: [c.model_copy(deep=True) for c in claims])
            qa = object.__new__(QAService)
            qa.repository, qa.provider = repo, provider
            result = qa.answer_question('What page count is required?',
                selected_doc_ids=selected if selected is not None else list({c.doc_id for c in retrieved}), **kwargs)
            path = os.getenv('CITATION_TEST_EVIDENCE')
            if path:
                with Path(path).open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(dict(input=[c.model_dump() for c in claims], result=result),
                        default=lambda o: o.model_dump(), ensure_ascii=False) + '\n')
            return result

        def parse(self, citations, answer='Fixed answer.', thinking='Public explanation.'):
            provider = LLMProvider()
            monkeypatch.setattr(provider, '_call_f1_generation', lambda *a, **k: json.dumps(
                dict(answer=answer, citations=citations, thinking=thinking)))
            return provider.generate_grounded_qa('What page count is required?', chunks)
    return Fixed()


def assert_abstained(result, quotes=None, reason=None):
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert result['validated_claims'] == [] and result['citations'] == []
    assert result['grounding_score'] == 0.0
    assert not result.get('thinking')
    if quotes is not None:
        assert len(result['hallucination_flags']) == len(quotes)
        assert all(not c.claim_text and not c.evidence_quote for c in result['hallucination_flags'])
    if reason:
        assert result['hallucination_flags'][0].verification_status == reason


def assert_accepted(result, original, source, start, end):
    assert result['status'] == 'ANSWER_VERIFIED'
    assert result['hallucination_flags'] == []
    assert len(result['validated_claims']) == 1
    actual = result['validated_claims'][0]
    assert actual.claim_text == original.claim_text and actual.evidence_quote == original.evidence_quote
    assert (actual.cited_doc_id, actual.cited_page, actual.cited_start_line, actual.cited_end_line) == (
        source.doc_id, source.page_number, start, end)
    assert (actual.doc_version, actual.doc_hash) == (source.doc_version, source.doc_hash)
    assert actual.verification_status == 'VERIFIED_EXACT' and actual.match_score == 1.0
    assert actual.evidence_span['matched_span'] == actual.matched_span
    assert result['citations'] == [f'{source.doc_id} (Trang {source.page_number}, Dòng {start}-{end})']


def test_ac01_ac02_all_fabrications_abstain_preserving_reasons(fixed):
    quotes = ['zzzz quantum nebula yyyy', 'unrelated fabricated galaxy wwww']
    result = fixed.run([claim(q, text='Rejected assertion.') for q in quotes])
    assert_abstained(result, quotes)
    assert len(result['hallucination_flags']) == 2


def test_ac03_parser_does_not_default_unknown_identity(fixed):
    # Keep the service identity assertions; the new provider rejects legacy coordinates earlier.
    with pytest.raises(GenerationError, match='^GENERATION_INVALID_RESPONSE$'):
        fixed.parse([dict(doc_id='Ghost.pdf', page=99, line_start=1, line_end=1, excerpt=A1)])
    parsed = [claim(doc='Ghost.pdf', page=99)]
    assert parsed[0].cited_doc_id == 'Ghost.pdf' and parsed[0].cited_page == 99
    assert parsed[0].doc_hash is None and parsed[0].doc_version is None
    assert_abstained(fixed.run(parsed), [A1], 'INVALID_DOC_ID')


def test_ac04_wrong_document_does_not_borrow_quote(fixed):
    assert_abstained(fixed.run([claim(doc='B.pdf', page=2)]), [A1])


def test_ac04_unselected_source_not_authorized(fixed):
    a, b = chunk(), chunk('B.pdf', text='Distinct forbidden source quotation.')
    result = fixed.run([claim(b.text, doc=b.doc_id)], source=[a, b], retrieved=[a], selected=['A.pdf'])
    assert_abstained(result, [b.text], 'INVALID_DOC_ID')


def test_ac05_algorithm_recovery_remains_but_api_preserves_submitted_locator(fixed):
    source = chunk()
    original = claim(page=99, start=99, end=99)
    direct = verify_citations([original], legacy_lookup([source]), strict=True, allow_locator_correction=True)
    assert direct.validated_claims[0].cited_page == 1
    assert_abstained(fixed.run([original], source=[source]), [A1], 'INVALID_SOURCE_PAGE')
    assert original.cited_page == 99 and original.cited_start_line == 99


def test_ac06_known_identity_survives_duplicate_quote_and_retrieval_order(fixed):
    a, b = chunk(text=A1), chunk('B.pdf', text=A1, version='v2')
    original = claim()
    assert_accepted(fixed.run([original], source=[a, b], retrieved=[b, a]), original, a, 1, 1)


def test_ac06_ambiguous_same_document_recovery_abstains(fixed):
    a = chunk(text=A1)
    duplicate = chunk(page=2, text=A1, digest=a.doc_hash)
    assert_abstained(fixed.run([claim(page=99, start=99, end=99)], source=[a, duplicate]), [A1], 'INVALID_SOURCE_PAGE')


def test_ac06_valid_duplicate_location_is_preserved(fixed):
    a = chunk(text=A1)
    duplicate = chunk(page=2, text=A1, digest=a.doc_hash)
    original = claim(page=2)
    assert_accepted(fixed.run([original], source=[a, duplicate]), original, duplicate, 1, 1)


@pytest.mark.parametrize('quote', [
    'The report requires exactly 99 pages.', 'The permit is approved.',
    'The result is 10 units and x < 0.', 'The result is -10 units and x > 0.',
    'The result is -10 units and x <= 0.', 'Bob pays Alice.',
])
def test_ac07_ac08_modified_quotes_are_never_replaced_or_fuzzy_accepted(fixed, quote):
    original = claim(quote)
    aligned = align_claim_to_chunks(original, [chunk()])
    assert aligned.evidence_quote == quote
    assert_abstained(fixed.run([original]), [quote], 'UNGROUNDED_QUOTE')


@pytest.mark.parametrize('field,value,reason', [
    ('doc_hash', 'wrong-hash', 'HASH_MISMATCH'),
    ('doc_version', 'v999', 'VERSION_MISMATCH'),
])
def test_ac09_conflicting_claim_provenance_is_not_overwritten(fixed, field, value, reason):
    assert_abstained(fixed.run([claim(**{field: value})]), [A1], reason)


@pytest.mark.parametrize('field', ['doc_hash', 'doc_version'])
def test_ac09_missing_trusted_provenance_abstains(fixed, field):
    source = chunk()
    setattr(source, field, '')
    assert_abstained(fixed.run([claim()], source=[source]), [A1], 'MISSING_PROVENANCE')


def test_ac09_conflicting_source_provenance_abstains(fixed):
    a = chunk(text=A1)
    conflicting = chunk(page=2, text='Another page.', digest='conflicting-source-hash')
    assert_abstained(fixed.run([claim()], source=[a, conflicting]), [A1], 'CONFLICTING_PROVENANCE')


def test_ac09_strict_verifier_checks_supplied_span_not_whole_page():
    source = chunk()
    c = CitationClaim(claim_text=A4, cited_doc_id='A.pdf', cited_page=1, evidence_quote=A4,
                      cited_start_line=1, cited_end_line=1)
    result = verify_citations([c], legacy_lookup([source]), strict=True)
    assert not result.validated_claims
    assert result.hallucination_flags[0].verification_status == 'UNGROUNDED_QUOTE'


def test_ac09_sparse_lines_cannot_be_joined_into_fake_contiguous_span(fixed):
    a = chunk(text=A1)
    later = chunk(text=A2, start=3, digest=a.doc_hash)
    quote = A1 + '\n' + A2
    assert_abstained(fixed.run([claim(quote, start=1, end=3)], source=[a, later]), [quote])


def test_ac10_rejected_claim_and_explanation_are_separate(fixed):
    bad = claim('quantum fabricated zzzz', text='REJECTED CLAIM', thinking='REJECTED EXPLANATION')
    good = claim(thinking='Accepted source explanation.')
    result = fixed.run([bad, good])
    assert result['status'] == 'ANSWER_VERIFIED'
    assert [c.claim_text for c in result['validated_claims']] == [A1]
    assert [c.claim_text for c in result['hallucination_flags']] == ['']
    assert result['citations'] == ['A.pdf (Trang 1, Dòng 1-1)']
    assert result['thinking'] is None
    assert all(c.thinking is None for c in result['validated_claims'])
    assert result['grounding_score'] == 0.5


def test_ac10_shared_provider_explanation_is_omitted_when_any_claim_rejected(fixed):
    # Scripted service candidates retain the same mixed-claim/redaction assertions.
    # A malformed binding batch is rejected by the provider and is tested separately.
    parsed = [claim(text=A1, thinking='Shared explanation containing REJECTED CLAIM'),
              claim('quantum zzzz', text='REJECTED CLAIM', doc='Ghost.pdf',
                    thinking='Shared explanation containing REJECTED CLAIM')]
    result = fixed.run(parsed)
    assert [c.claim_text for c in result['validated_claims']] == [A1]
    assert result['thinking'] is None and result['validated_claims'][0].thinking is None


def test_ac11_single_line_quote_and_public_explanation_remain_valid(fixed):
    source = chunk(text=A1)
    original = claim(thinking='Public source explanation.')
    result = fixed.run([original], source=[source])
    assert_accepted(result, original, source, 1, 1)
    assert result['thinking'] is None
    assert result['validated_claims'][0].thinking is None


def test_ac09_whitespace_only_correction_preserves_original_evidence(fixed):
    source = chunk(text=A1 + '\n' + A2)
    original = claim(A1 + '  \n  ' + A2, end=2)
    result = fixed.run([original], source=[source])
    assert_accepted(result, original, source, 1, 2)
    assert result['validated_claims'][0].matched_span == source.text


def test_ac03_canonical_alias_is_unique_and_ambiguous_alias_rejected(fixed):
    a = chunk(name='Shared.pdf')
    b = chunk('B.pdf', name='Shared.pdf', text='Beta source text.')
    assert_abstained(fixed.run([claim(doc='Shared.pdf')], source=[a, b]), [A1], 'AMBIGUOUS_DOC_ID')
    original = claim(doc='a')
    assert_accepted(fixed.run([original], source=[a]), original, a, 1, 1)


def test_ac13_legacy_fuzzy_verifier_remains_available():
    c = CitationClaim(claim_text='Legacy example', cited_doc_id='legacy', cited_page=1,
                      evidence_quote='The report requires exactly 99 pages.')
    result = verify_citations([c], {('legacy', 1): A1})
    assert result.validated_claims[0].verification_status == 'VERIFIED_FUZZY'


def test_closed_c03_valid_quote_does_not_prove_false_assertion(fixed, record_property):
    original = claim(text='The report requires exactly 99 pages.')
    result = fixed.run([original])
    assert_abstained(result, [A1], 'BOUND_VALUE_CONTRADICTION')
    record_property('semantic_verdict', 'M2_C03_BOUND_NUMERICAL_CONTRADICTION_BLOCKED')


def test_insufficient_evidence_and_empty_selection_do_not_generate(fixed):
    assert_abstained(fixed.run([], retrieved=[], selected=['A.pdf']))
    result = fixed.run([claim()], selected=[])
    assert result['status'] == 'ABSTAINED_NO_SOURCE_SELECTED'
    assert not result['citations'] and not result['validated_claims']


def test_ac02_verifier_rejection_is_authoritative_even_at_strict_threshold(fixed):
    assert_abstained(fixed.run([claim('fabricated nebula zzzz')], theta_match=1.0), ['fabricated nebula zzzz'])


def test_ac09_inconsistent_chunk_line_metadata_is_not_trusted(fixed):
    source = chunk(text=A1)
    source.end_line = 2
    assert_abstained(fixed.run([claim()], source=[source]), [A1], 'CONFLICTING_PROVENANCE')


@pytest.mark.parametrize('source_text,quote', [
    ('The result is -10 units.', '10 units.'),
    ('The result is +10 units.', '10 units.'),
    ('The value is 30.00 units.', 'The value is 30.0'),
    ('The value is 30.5 units.', 'The value is 30'),
    ('The condition is x <= 0.', 'The condition is x <'),
    ('The condition is x >= 0.', 'The condition is x >'),
])
def test_ac07_ac08_quote_edges_do_not_split_numeric_or_operator_tokens(fixed, source_text, quote):
    assert_abstained(fixed.run([claim(quote)], source=[chunk(text=source_text)]), [quote], 'UNGROUNDED_QUOTE')


@pytest.mark.parametrize('source_text,quote,start,end', [
    ('The result is −10 units.', '10 units.', 1, 1),
    ('The result is − 10 units.', '10 units.', 1, 1),
    ('The result is −\u00a010 units.', '10 units.', 1, 1),
    ('The result is −\u202f10 units.', '10 units.', 1, 1),
    ('The result is - 10 units.', '10 units.', 1, 1),
    ('The result is + 10 units.', '10 units.', 1, 1),
    ('The result is －10 units.', '10 units.', 1, 1),
    ('The result is ﹣ 10 units.', '10 units.', 1, 1),
    ('The result is ＋10 units.', '10 units.', 1, 1),
    ('The result is ± 10 units.', '10 units.', 1, 1),
    ('The result is −１０ units.', '１０ units.', 1, 1),
    ('The result is −١٠ units.', '١٠ units.', 1, 1),
    ('The result is −1\u00a0234,50 units.', '234,50 units.', 1, 1),
    ('The result is 1\u202f234.50 units.', '234.50 units.', 1, 1),
    ("The result is 1'234.50 units.", '234.50 units.', 1, 1),
    ('The result is 1’234.50 units.', '234.50 units.', 1, 1),
    ('The result is ١٠٫٥ units.', 'The result is ١٠', 1, 1),
    ('The result is １２，５ units.', 'The result is １２', 1, 1),
    ('The rate is 10 ٪.', 'The rate is 10', 1, 1),
    ('The rate is 10 %.', 'The rate is 10', 1, 1),
    ('The result is 1e−3 units.', '3 units.', 1, 1),
    ('The result is 1e− 3 units.', 'The result is 1', 1, 1),
    ('The result is .5 units.', '5 units.', 1, 1),
    ('The result is −.5 units.', '5 units.', 1, 1),
    ('The result is −½ units.', '½ units.', 1, 1),
    ('The result is −¹⁰ units.', '¹⁰ units.', 1, 1),
    ('The result is 10⁻³ units.', 'The result is 10', 1, 1),
    ('The result is −\n10 units.', '10 units.', 2, 2),
    ('The condition is x <\u0338 0.', 'The condition is x <', 1, 1),
])
def test_fix01_boundary_truncated_unicode_numbers_and_operators_rejected(fixed, source_text, quote, start, end):
    source = chunk(text=source_text)
    original = claim(quote, start=start, end=end)
    before = original.model_dump()
    direct = verify_citations([original], legacy_lookup([source]), strict=True, allow_locator_correction=True)
    assert direct.validated_claims == [] and direct.grounding_score == 0.0
    assert direct.hallucination_flags[0].verification_status == 'UNGROUNDED_QUOTE'
    assert direct.hallucination_flags[0].evidence_quote == quote
    assert_abstained(fixed.run([original], source=[source]), [quote], 'UNGROUNDED_QUOTE')
    assert original.model_dump() == before


@pytest.mark.parametrize('source_text,quote', [
    ('The permit is unapproved.', 'approved.'),
    ('The permit is reapproved.', 'approved.'),
    ('The approvals remain pending.', 'approval'),
    ('The token is _approved.', 'approved.'),
    ('The token is foo‿approved.', 'approved.'),
    ('Học sinh được duyệt.', 'ọc sinh được duyệt.'),
    ('Tài liệu hợp lệ.', 'ợp lệ.'),
    ('Tài liệu được duyệt.', 'Tài liệu được duyệ'),
    ('Từ ma\u0301 được ghi.', 'ma'),
    ('Từ ma\u0301 được ghi.', '\u0301'),
    ('Từ a\u0301p dụng.', 'p dụng.'),
])
def test_fix01_boundary_partial_unicode_words_rejected(fixed, source_text, quote):
    source = chunk(text=source_text)
    original = claim(quote)
    direct = verify_citations([original], legacy_lookup([source]), strict=True, allow_locator_correction=True)
    assert direct.validated_claims == [] and direct.grounding_score == 0.0
    assert direct.hallucination_flags[0].verification_status == 'UNGROUNDED_QUOTE'
    assert direct.hallucination_flags[0].evidence_quote == quote
    assert_abstained(fixed.run([original], source=[source]), [quote], 'UNGROUNDED_QUOTE')


@pytest.mark.parametrize('source_text,quote', [
    ('The result is −10 units.', '−10 units.'),
    ('The result is − 10 units.', '− 10 units.'),
    ('The result is −\u00a010 units.', '−\u00a010 units.'),
    ('The result is －10 units.', '－10 units.'),
    ('The result is ﹣ 10 units.', '﹣ 10 units.'),
    ('The result is ＋10 units.', '＋10 units.'),
    ('The result is ± 10 units.', '± 10 units.'),
    ('The result is −1\u202f234,50 units.', '−1\u202f234,50 units.'),
    ("The result is 1'234.50 units.", "1'234.50 units."),
    ('The result is ١٠٫٥ units.', '١٠٫٥ units.'),
    ('The result is −１０ units.', '−１０ units.'),
    ('The rate is 10 ٪.', '10 ٪.'),
    ('The result is 1e−3 units.', '1e−3 units.'),
    ('The result is .5 units.', '.5 units.'),
    ('The result is −½ units.', '−½ units.'),
    ('The result is 10⁻³ units.', '10⁻³ units.'),
    ('The condition is x <\u0338 0.', 'x <\u0338 0.'),
    ('The permit is approved.', 'approved.'),
    ('Tài liệu hợp lệ.', 'hợp lệ.'),
    ('Học sinh được duyệt.', 'Học sinh'),
    ('A cafe\u0301 serves tea.', 'cafe\u0301'),
    ('Ta\u0300i lie\u0323\u0302u ho\u031b\u0323p le\u0323\u0302.', 'ho\u031b\u0323p le\u0323\u0302.'),
])
def test_fix01_boundary_complete_unicode_quotes_preserve_evidence_and_provenance(fixed, source_text, quote):
    source = chunk(text=source_text)
    original = claim(quote)
    direct = verify_citations([original], legacy_lookup([source]), strict=True, allow_locator_correction=True)
    assert direct.validated_claims[0].matched_span == quote
    # Lexical integrity is retained; bounded support requires the whole span.
    assert_abstained(fixed.run([original], source=[source]), [quote], 'PARTIAL_CITATION_CONTEXT')
    whole = claim(source.text)
    assert_accepted(fixed.run([whole], source=[source]), whole, source, 1, 1)


def test_fix01_boundary_unicode_whitespace_and_unique_locator_correction(fixed):
    source = chunk(text='The result is −\n10 units.')
    original = claim('−  10 units.', page=99, start=99, end=99)
    direct = verify_citations([original], legacy_lookup([source]), strict=True, allow_locator_correction=True)
    assert direct.validated_claims[0].matched_span == '−\n10 units.'
    assert_abstained(fixed.run([original], source=[source]), [original.evidence_quote], 'INVALID_SOURCE_PAGE')
    assert original.evidence_quote == '−  10 units.' and original.cited_page == 99


def test_fix01_boundary_whole_words_do_not_assert_contextual_entailment(fixed):
    # Direct lexical checks still accept whole words. The integrated output
    # gate rejects the assertion because its quote omitted source negation.
    for text, quote in [('The permit is not approved.', 'approved.'),
                        ('Tài liệu không hợp lệ.', 'hợp lệ.')]:
        source = chunk(text=text)
        original = claim(quote)
        direct = verify_citations([original], legacy_lookup([source]), strict=True)
        assert direct.validated_claims[0].verification_status == 'VERIFIED_EXACT'
        assert_abstained(fixed.run([original], source=[source]), [quote], 'PARTIAL_CITATION_CONTEXT')


def test_fix01_boundary_legacy_exact_substring_behavior_is_unchanged():
    for text, quote in [('The permit is unapproved.', 'approved.'),
                        ('The result is −10 units.', '10 units.')]:
        original = CitationClaim(claim_text='Legacy boundary behavior.', cited_doc_id='legacy',
                                 cited_page=1, evidence_quote=quote)
        result = verify_citations([original], {('legacy', 1): text})
        assert result.validated_claims[0].verification_status == 'VERIFIED_EXACT'
