"""Single-choice grading over trusted keys; pure stdlib and no I/O."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


class QuizGradingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GradedAnswer:
    question_id: str
    selected_option_id: str | None
    correct_option_id: str
    is_correct: bool


@dataclass(frozen=True)
class QuizGrade:
    items: tuple[GradedAnswer, ...]

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def answered_count(self) -> int:
        return sum(item.selected_option_id is not None for item in self.items)

    @property
    def correct_count(self) -> int:
        return sum(item.is_correct for item in self.items)

    @property
    def score_percent(self) -> float:
        return round(100 * self.correct_count / self.total_count, 2)


def _identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def grade_single_choice(
    questions: Sequence[tuple[str, Sequence[str], str]],
    answers: Sequence[tuple[str, str]],
) -> QuizGrade:
    """Grade in question order, using actual count; omitted answers are wrong.

    questions contains (question_id, option_ids, correct_option_id). Reject
    unknown IDs and repeated answers instead of guessing or overwriting them.
    The caller verifies source support and controls when the key is revealed.
    """
    if not questions:
        raise QuizGradingError("INVALID_QUIZ", "Quiz phải có ít nhất một câu hỏi.")
    keys = {}
    for question_id, option_ids, correct_id in questions:
        if (not _identifier(question_id) or question_id in keys
            or not isinstance(option_ids, (list, tuple)) or len(option_ids) < 2
            or any(not _identifier(option_id) for option_id in option_ids)
            or len(set(option_ids)) != len(option_ids) or not _identifier(correct_id)
            or correct_id not in option_ids):
            raise QuizGradingError("INVALID_QUIZ", "Định danh câu hỏi/lựa chọn hoặc đáp án nội bộ không hợp lệ.")
        keys[question_id] = (tuple(option_ids), correct_id)
    selected = {}
    for question_id, option_id in answers:
        if not _identifier(question_id) or question_id not in keys:
            raise QuizGradingError("UNKNOWN_QUESTION", "Có câu trả lời không thuộc Quiz này.")
        if question_id in selected:
            raise QuizGradingError("DUPLICATE_ANSWER", "Mỗi câu hỏi chỉ nhận một lựa chọn.")
        if not _identifier(option_id) or option_id not in keys[question_id][0]:
            raise QuizGradingError("UNKNOWN_OPTION", "Lựa chọn trả lời không thuộc câu hỏi tương ứng.")
        selected[question_id] = option_id
    return QuizGrade(tuple(
        GradedAnswer(question_id, selected.get(question_id), correct_id, selected.get(question_id) == correct_id)
        for question_id, (_, correct_id) in keys.items()
    ))
