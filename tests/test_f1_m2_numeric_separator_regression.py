"""M2 final P1: real deterministic QA/support gate; generation is a test fixture."""
import pytest

from backend.services.f1_claim_support_service import F1SupportGate
from test_f1_m2_integration import chunk, claim, qa_fixture, record, run


def pipeline(source_text, target, monkeypatch):
    import backend.services.f1_claim_support_service as module
    def forbidden_model():
        pytest.fail('Numeric-format decisions must not call NLI')
    monkeypatch.setattr(module, 'get_f1_semantic_verifier', forbidden_model)
    source = chunk(source_text)
    return run(qa_fixture([source], [claim(target, source)], F1SupportGate()))


AMBIGUOUS = [
    ('finding_en', 'Report R requires exactly 1,000 pages.', 'R requires exactly 1 page.'),
    ('comma_to_thousand_en', 'Report R requires exactly 1,000 pages.', 'R requires 1000 pages.'),
    ('dot_vi', 'Báo cáo R bắt buộc có đúng 1.000 trang.', 'R bắt buộc có 1 trang.'),
    ('dot_to_thousand_vi', 'Báo cáo R bắt buộc có đúng 1.000 trang.', 'R bắt buộc có 1000 trang.'),
    ('comma_vi', 'Báo cáo R bắt buộc có đúng 1,000 trang.', 'R bắt buộc có 1 trang.'),
    ('dot_en', 'Report R requires exactly 1.000 pages.', 'R requires 1 page.'),
    ('comma_nonzero_fraction_en', 'Report R requires exactly 12,500 pages.', 'R requires 12.5 pages.'),
    ('dot_nonzero_fraction_vi', 'Báo cáo R bắt buộc có đúng 12.500 trang.', 'R bắt buộc có 12,5 trang.'),
    ('ambiguous_target_en', 'Report R requires exactly 1 page.', 'R requires 1,000 pages.'),
    ('ambiguous_target_vi', 'Báo cáo R bắt buộc có đúng 1 trang.', 'R bắt buộc có 1.000 trang.'),
    ('negative_en', 'Account X has a recorded balance of −1,000 USD.', "X's balance is −1 USD."),
    ('negative_vi', 'Tài khoản X có số dư ghi nhận là −1.000 USD.', 'Số dư của X là −1 USD.'),
    ('mixed_en', 'Report R requires exactly 1,000.50 pages.', 'R requires 1000.5 pages.'),
    ('mixed_vi', 'Báo cáo R bắt buộc có đúng 1.000,50 trang.', 'R bắt buộc có 1000,5 trang.'),
    ('repeated_en', 'Report R requires exactly 1,000,000 pages.', 'R requires 1000000 pages.'),
    ('repeated_vi', 'Báo cáo R bắt buộc có đúng 1.000.000 trang.', 'R bắt buộc có 1000000 trang.'),
    ('copy_en', 'Report R requires exactly 1,000 pages.', 'Report R requires exactly 1,000 pages.'),
    ('copy_vi', 'Báo cáo R bắt buộc có đúng 1.000 trang.', 'Báo cáo R bắt buộc có đúng 1.000 trang.'),
]


@pytest.mark.parametrize('case,source_text,target', AMBIGUOUS, ids=[c[0] for c in AMBIGUOUS])
def test_ambiguous_numeric_separators_abstain_through_production_gate(case, source_text, target, monkeypatch):
    result = pipeline(source_text, target, monkeypatch)
    record('numeric_separator:'+case, 'REAL_DETERMINISTIC_QA_GATE_NO_NLI', result['status'],
        source=source_text, claim=target, expected='ABSTAINED_INSUFFICIENT_EVIDENCE',
        served_claims=[c.claim_text for c in result['validated_claims']],
        reason=[c.verification_status for c in result['hallucination_flags']])
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert result['validated_claims'] == [] and result['grounding_score'] == 0.0
    assert result['hallucination_flags'][0].verification_status == 'AMBIGUOUS_NUMBER_FORMAT'


POSITIVE = [
    ('comma_half_vi', 'Liều được kê cho bệnh nhân P là 0,5 viên.', 'Liều của P là 1/2 viên.'),
    ('dot_half_en', "Patient P's prescribed dose is 0.5 tablet.", "P's dose is 1/2 tablet."),
    ('fraction_vi', 'Liều được kê cho bệnh nhân Q là 3/4 viên.', 'Liều của Q là 0,75 viên.'),
    ('fraction_en', "Patient Q's prescribed dose is 3/4 tablet.", "Q's dose is 0.75 tablet."),
    ('unicode_negative_vi', 'Tài khoản Y có số dư ghi nhận là −8 USD.', 'Y có số dư âm tám USD.'),
    ('negative_decimal_en', 'Account Y has a recorded balance of -1.5 USD.', "Y's balance is −1.5 USD."),
    ('negative_decimal_vi', 'Tài khoản Y có số dư ghi nhận là −1,5 USD.', 'Số dư của Y là -1.5 USD.'),
    ('unit_en', 'Sample Z has a mass of 17 mg.', 'Z has a mass of 0.017 g.'),
    ('unit_vi', 'Mẫu Z có khối lượng 17 mg.', 'Khối lượng Z là 0,017 g.'),
    ('date_en', "Report Z's deadline is 2027-02-17.", 'Z is due on 17 February 2027.'),
    ('date_vi', 'Hạn nộp báo cáo Z là 2027-02-17.', 'Z đến hạn vào ngày 17 tháng 2 năm 2027.'),
]


@pytest.mark.parametrize('case,source_text,target', POSITIVE, ids=[c[0] for c in POSITIVE])
def test_existing_unambiguous_positive_controls_remain_supported(case, source_text, target, monkeypatch):
    result = pipeline(source_text, target, monkeypatch)
    record('numeric_positive:'+case, 'REAL_DETERMINISTIC_QA_GATE_NO_NLI', result['status'],
        source=source_text, claim=target, expected='ANSWER_VERIFIED')
    assert result['status'] == 'ANSWER_VERIFIED'
    assert result['validated_claims'][0].claim_text == target
    assert result['validated_claims'][0].evidence_span['execution_kind'] == 'DETERMINISTIC'


@pytest.mark.parametrize('source_text,target', [
    ('Report T requires exactly 1.5 pages.', 'T requires 15 pages.'),
    ('Báo cáo T bắt buộc có đúng 1,5 trang.', 'T bắt buộc có 15 trang.'),
])
def test_unambiguous_decimal_mismatch_is_still_a_contradiction(source_text, target, monkeypatch):
    result = pipeline(source_text, target, monkeypatch)
    assert result['status'] == 'ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert result['hallucination_flags'][0].verification_status == 'BOUND_VALUE_CONTRADICTION'
