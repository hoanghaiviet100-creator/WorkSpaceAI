"""Conservative extractive support checks; pure stdlib, no I/O or LLM judge.

Only the exact definition templates used by the offline generators are proven.
Whitespace may vary; case, negation, qualifiers and punctuation are retained.
General questions/paraphrases abstain. Literal ambiguity is not a complete
semantic contradiction detector, nor is a source assertion external truth.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from backend.algorithms.f2_definition_extraction import extract_unambiguous_definitions


@dataclass(frozen=True)
class ContentSupportDecision:
    status: Literal["SUPPORTED", "REVIEW_REQUIRED", "REJECTED"]
    code: str
    message: str


def _flat(text: str) -> str:
    return " ".join(text.split())


def _review(code: str, message: str) -> ContentSupportDecision:
    return ContentSupportDecision("REVIEW_REQUIRED", code, message)


def _local_definitions(sources: Sequence[tuple[str, str]]) -> tuple[tuple[str, str, str], ...]:
    # Parse separately so conflicts/identical-definition aliases stay visible.
    return tuple(d for source in sources for d in extract_unambiguous_definitions((source,)))


def _unambiguous(term: str, body: str, all_sources: Sequence[tuple[str, str]]) -> bool:
    # Generation dedup casefolds bodies. Validation must retain case-sensitive
    # qualifiers/units (e.g. mM versus MM) rather than hide a conflicting source.
    bodies = {b for _, t, b in _local_definitions(all_sources) if t.casefold() == term.casefold()}
    return bodies == {body} and any(
        t == term and b == body for _, t, b in extract_unambiguous_definitions(all_sources)
    )


def validate_quiz_support(
    question: str, options: Sequence[tuple[str, str]], correct_option_id: str,
    explanation: str, cited_sources: Sequence[tuple[str, str]],
    all_sources: Sequence[tuple[str, str]],
) -> ContentSupportDecision:
    """Source-relative support, independent of citation/structural validation."""
    prefix = "Khái niệm nào được mô tả sau đây? "
    stem = _flat(question)
    if not stem.startswith(prefix):
        return _review("UNSUPPORTED_QUESTION_FORM", "Câu hỏi ngoài mẫu định nghĩa cần được review về nghĩa.")
    body = stem[len(prefix):]
    candidates = [(s, t, b) for s, t, b in _local_definitions(cited_sources) if b == body]
    if not candidates:
        return _review("UNSUPPORTED_QUESTION", "Mô tả trong câu hỏi chưa được trích dẫn hỗ trợ trực tiếp.")
    _, term, body = candidates[0]
    if not _unambiguous(term, body, all_sources):
        return _review("AMBIGUOUS_DEFINITION", "Các nguồn đã chọn có định nghĩa trùng nghĩa literal hoặc khác nhau cho cùng khái niệm.")
    normalized_options = [_flat(text) for _, text in options]
    if len(normalized_options) != len(set(normalized_options)):
        return _review("AMBIGUOUS_OPTIONS", "Các lựa chọn trùng nhau sau chuẩn hóa khoảng trắng; cần review.")
    key_text = next((_flat(text) for option_id, text in options if option_id == correct_option_id), None)
    if key_text != term:
        return ContentSupportDecision("REJECTED", "WRONG_ANSWER_KEY", "Đáp án được đánh dấu không khớp khái niệm của mô tả trích dẫn.")
    eligible_terms = {t for _, t, _ in extract_unambiguous_definitions(all_sources)}
    if any(_flat(text) not in eligible_terms for _, text in options):
        return _review("UNSUPPORTED_DISTRACTOR", "Có lựa chọn chưa đối chiếu được với khái niệm rõ ràng trong nguồn.")
    if _flat(explanation) != f"Theo đoạn nguồn, {term}: {body}":
        return _review("UNSUPPORTED_EXPLANATION", "Giải thích chưa khớp đầy đủ định nghĩa nguồn; cần review.")
    option_terms = {_flat(text) for _, text in options}
    local = _local_definitions(cited_sources)
    relevant_ids = {s for s, t, b in local if t in option_terms and _unambiguous(t, b, all_sources)}
    if any(s not in relevant_ids for s, _ in cited_sources):
        return _review("IRRELEVANT_CITATION", "Có trích dẫn chưa hỗ trợ câu hỏi hoặc các khái niệm lựa chọn.")
    return ContentSupportDecision("SUPPORTED", "EXTRACTIVE_SUPPORT", "Đáp án và giải thích khớp định nghĩa được trích dẫn.")


def validate_flashcard_support(
    front: str, back: str, cited_sources: Sequence[tuple[str, str]],
    all_sources: Sequence[tuple[str, str]],
) -> ContentSupportDecision:
    local = _local_definitions(cited_sources)
    candidates = [(s, t, b) for s, t, b in local if _flat(front) == f"{t} là gì?"]
    if not candidates:
        return _review("UNSUPPORTED_FRONT", "Mặt trước ngoài mẫu hoặc không khớp khái niệm nguồn; cần review.")
    _, term, body = candidates[0]
    if not _unambiguous(term, body, all_sources):
        return _review("AMBIGUOUS_DEFINITION", "Định nghĩa chưa rõ ràng trên toàn bộ nguồn đã chọn.")
    if _flat(back) != body:
        return _review("UNSUPPORTED_ANSWER", "Mặt sau chưa khớp toàn bộ định nghĩa được trích dẫn; cần review.")
    relevant_ids = {s for s, t, b in local if t == term and b == body}
    if any(s not in relevant_ids for s, _ in cited_sources):
        return _review("IRRELEVANT_CITATION", "Có trích dẫn chưa hỗ trợ đáp án của flashcard.")
    return ContentSupportDecision("SUPPORTED", "EXTRACTIVE_SUPPORT", "Hai mặt flashcard khớp định nghĩa được trích dẫn.")
