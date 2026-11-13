"""F2-Q03 internal Quiz generation from server-prepared Q02 source snapshots.

Results are structurally checked, not semantically verified or learner DTOs.
No runtime registration, persistence, authentication or answer grading here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from backend.core.f2_quiz_payload import LLMQuizQuestion
from backend.core.f2_study_schemas import QuizQuestion, QuizSet, StudyFormat, StudySourceSelection
from backend.providers.f2_quiz_provider import (
    DeterministicQuizProvider, QuizEvidence,
    QuizGenerationProvider, QuizProviderError,
)
from backend.services.f2_source_service import PreparedStudySources, SourceContentIssue
from backend.services.f2_generation_support import (
    StudyGenerationError, parse_generation_items, prepare_generation_snapshot, resolve_source_ids,
)


@dataclass(frozen=True)
class QuizGenerationIssue:
    code: str
    message: str
    question_index: int | None = None


@dataclass(frozen=True)
class QuizGenerationResult:
    workspace_id: str
    selection: StudySourceSelection
    quiz: QuizSet | None
    provider_name: str
    issues: tuple[QuizGenerationIssue, ...] = ()
    source_issues: tuple[SourceContentIssue, ...] = ()
    failed: bool = False

    @property
    def status(self) -> Literal["COMPLETE", "PARTIAL", "INSUFFICIENT_CONTENT", "ERROR"]:
        if self.failed:
            return "ERROR"
        if self.quiz is None:
            return "INSUFFICIENT_CONTENT"
        if len(self.quiz.questions) < self.selection.requested_count or self.issues or self.source_issues:
            return "PARTIAL"
        return "COMPLETE"

    @property
    def message(self) -> str:
        if self.status == "ERROR":
            return "Không tạo được Quiz hợp lệ. Vui lòng thử lại hoặc chọn nguồn khác."
        if self.quiz is None:
            return "Chưa đủ nội dung để tạo câu hỏi với các đáp án phân biệt. Vui lòng bổ sung hoặc chọn tài liệu khác."
        count = len(self.quiz.questions)
        if self.status == "PARTIAL":
            return f"Đã tạo {count}/{self.selection.requested_count} câu. Hãy xem cảnh báo hoặc bổ sung nguồn. Nội dung chưa được kiểm chứng."
        return f"Đã tạo {count} câu trắc nghiệm. Nội dung chưa được kiểm chứng."


class QuizGenerationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _parse_questions(raw: str) -> list:
    return parse_generation_items(raw, "questions")


def _snapshot(prepared: PreparedStudySources) -> tuple[StudySourceSelection, tuple[QuizEvidence, ...]]:
    try:
        return prepare_generation_snapshot(prepared, StudyFormat.QUIZ)
    except StudyGenerationError as error:
        raise QuizGenerationError(error.code, str(error)) from error


class F2QuizService:
    def __init__(
        self, provider: QuizGenerationProvider | None = None,
        *, fallback_provider: QuizGenerationProvider | None = None,
    ):
        self.provider = provider if provider is not None else DeterministicQuizProvider()
        self.fallback_provider = fallback_provider

    def generate_quiz(self, prepared: PreparedStudySources) -> QuizGenerationResult:
        """Generate internal single-choice questions, preserving exact Q02 refs.

        An optional explicitly configured fallback runs only for provider
        timeout/unavailability, never to hide malformed output or invalid items.
        """
        selection, evidence = _snapshot(prepared)
        provider = self.provider
        issues: list[QuizGenerationIssue] = []

        def result(quiz=None, *, failed=False):
            return QuizGenerationResult(
                prepared.workspace_id, selection, quiz, provider.name,
                tuple(issues), prepared.issues, failed,
            )

        if not evidence:
            issues.append(QuizGenerationIssue("INSUFFICIENT_SOURCE_CONTENT", prepared.message))
            return result()
        try:
            raw = provider.generate(evidence, selection.requested_count)
        except QuizProviderError as error:
            if self.fallback_provider is None or error.code not in ("PROVIDER_TIMEOUT", "PROVIDER_UNAVAILABLE"):
                issues.append(QuizGenerationIssue(error.code, str(error)))
                return result(failed=True)
            issues.append(QuizGenerationIssue("FALLBACK_USED", "Dịch vụ chính không khả dụng; đã dùng chế độ sinh câu hỏi dự phòng."))
            provider = self.fallback_provider
            try:
                raw = provider.generate(evidence, selection.requested_count)
            except Exception:
                issues.append(QuizGenerationIssue("FALLBACK_FAILED", "Chế độ dự phòng không tạo được câu hỏi."))
                return result(failed=True)
        except Exception:
            issues.append(QuizGenerationIssue("PROVIDER_FAILED", "Dịch vụ sinh Quiz gặp lỗi; vui lòng thử lại."))
            return result(failed=True)
        try:
            drafts = _parse_questions(raw)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            issues.append(QuizGenerationIssue("INVALID_PROVIDER_OUTPUT", "Phản hồi sinh Quiz không hợp lệ; đã dừng sử dụng phản hồi này."))
            return result(failed=True)
        if not drafts:
            issues.append(QuizGenerationIssue("INSUFFICIENT_GENERATABLE_CONTENT", "Chưa đủ nội dung để tạo câu hỏi phân biệt; hãy bổ sung hoặc chọn tài liệu khác."))
            return result()
        by_id = {item.source_id: item.source_ref for item in evidence}
        questions: list[QuizQuestion] = []
        seen = set()
        for index, draft in enumerate(drafts, 1):
            if len(questions) == selection.requested_count:
                issues.append(QuizGenerationIssue("EXCESS_ITEMS_IGNORED", "Đã bỏ các câu vượt quá số lượng yêu cầu.", index))
                break
            try:
                item = LLMQuizQuestion.model_validate(draft)
                question = QuizQuestion(
                    question_id=f"q{len(questions) + 1}",
                    question=item.question, options=item.options,
                    correct_option_id=item.correct_option_id, explanation=item.explanation,
                    source_refs=resolve_source_ids(list(item.source_ids), by_id),
                )
                key = " ".join(question.question.split()).casefold()
                if key in seen:
                    issues.append(QuizGenerationIssue("DUPLICATE_QUESTION", "Đã bỏ câu hỏi trùng nội dung.", index))
                    continue
                seen.add(key)
                questions.append(question)
            except (ValidationError, ValueError, TypeError):
                issues.append(QuizGenerationIssue("INVALID_QUESTION", "Đã bỏ câu hỏi thiếu nội dung, đáp án hoặc nguồn hợp lệ.", index))
        if not questions:
            issues.append(QuizGenerationIssue("NO_VALID_QUESTIONS", "Không có câu hỏi nào qua kiểm tra cấu trúc và snapshot nguồn."))
            return result(failed=True)
        quiz = QuizSet(quiz_set_id=str(uuid4()), selection=selection, questions=tuple(questions))
        if len(questions) < selection.requested_count:
            issues.append(QuizGenerationIssue("FEWER_QUESTIONS_THAN_REQUESTED", "Số câu hợp lệ ít hơn yêu cầu; không sinh bù thông tin thiếu."))
        return result(quiz)


__all__ = ["QuizGenerationIssue", "QuizGenerationResult", "QuizGenerationError", "F2QuizService"]
