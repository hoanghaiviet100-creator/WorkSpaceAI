"""Author review and explicitly chosen verified subsets; never approve by flag."""
from dataclasses import dataclass
from uuid import uuid4

from pydantic import ValidationError

from backend.algorithms.f2_quiz_grading import QuizGradingError, grade_single_choice
from backend.core.f2_practice_schemas import LearnerQuizQuestion, QuizSubmission
from backend.core.f2_quiz_preview_schemas import DraftQuizFeedback, DraftQuizPreview, DraftQuizResult
from backend.core.f2_study_schemas import FlashcardDeck, QuizSet
from backend.core.f2_validation_schemas import StudyValidationResult
from backend.services.f2_source_service import SourceAccessContext, StudySourceRepository
from backend.services.f2_study_validation_service import F2StudyValidationService


class StudyDraftError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class StudyDraftReview:
    resource: QuizSet | FlashcardDeck
    validation: StudyValidationResult

    @property
    def verified_item_ids(self) -> tuple[str, ...]:
        # Global warnings/errors prevent subset release too. A new review is
        # always run by verified_subset(), never accept this receipt as input.
        if self.validation.issues or self.validation.structure_status != "VALID":
            return ()
        return tuple(item.item_id for item in self.validation.items
            if item.source_status == "MATCHED" and item.support_status == "SUPPORTED" and not item.issues)


class F2StudyDraftService:
    def __init__(self, repository: StudySourceRepository):
        self.validator = F2StudyValidationService(repository)

    def review(self, resource: QuizSet | FlashcardDeck, *, context: SourceAccessContext) -> StudyDraftReview:
        try:
            if not isinstance(context, SourceAccessContext):
                raise ValueError("backend context required")
            context = SourceAccessContext(context.workspace_id, context.allowed_doc_ids)
        except (ValueError, AttributeError) as error:
            raise StudyDraftError("INVALID_CONTEXT", "Thiếu phạm vi nguồn hợp lệ do backend cung cấp.") from error
        try:
            if not isinstance(resource, (QuizSet, FlashcardDeck)):
                raise ValueError("resource required")
            checked = type(resource).model_validate(resource)
        except (ValidationError, ValueError) as error:
            raise StudyDraftError("INVALID_DRAFT", "Bản nháp không có cấu trúc hợp lệ; hãy tạo lại.") from error
        method = self.validator.validate_quiz if isinstance(checked, QuizSet) else self.validator.validate_flashcards
        receipt = method(checked, workspace_id=context.workspace_id, context=context)
        return StudyDraftReview(checked, receipt)

    def verified_subset(self, resource: QuizSet | FlashcardDeck, *, context: SourceAccessContext) -> QuizSet | FlashcardDeck:
        review = self.review(resource, context=context)
        allowed = set(review.verified_item_ids)
        if not allowed:
            raise StudyDraftError("NO_VERIFIED_ITEMS", "Chưa có mục đủ điều kiện luyện tập; hãy xem các lý do cần review.")
        checked = review.resource
        if isinstance(checked, QuizSet):
            return QuizSet(quiz_set_id=str(uuid4()), selection=checked.selection,
                questions=tuple(q for q in checked.questions if q.question_id in allowed))
        return FlashcardDeck(deck_id=str(uuid4()), selection=checked.selection,
            cards=tuple(c for c in checked.cards if c.card_id in allowed))

    def preview_quiz(self, resource: QuizSet, *, context: SourceAccessContext,
                     submission: QuizSubmission | None = None) -> DraftQuizPreview:
        """Interactive author preview, never a Q06 session or verification flag.

        Re-read sources on every call including submission/result. Review-only
        semantic support is allowed under the UNVERIFIED_DRAFT label; rejected
        content, global warnings and unavailable/mismatched sources are blocked.
        """
        if not isinstance(resource, QuizSet):
            raise StudyDraftError("QUIZ_REQUIRED", "Chế độ làm thử này cần bản nháp Quiz.")
        review = self.review(resource, context=context)
        receipt = review.validation
        if (receipt.status == "REJECTED" or receipt.issues or receipt.structure_status != "VALID"
            or not receipt.items or any(i.source_status != "MATCHED" for i in receipt.items)
            or any(issue.code == "MATH_REASONING_DEFERRED" for i in receipt.items for issue in i.issues)):
            raise StudyDraftError("DRAFT_PREVIEW_BLOCKED", "Không thể làm thử: bản nháp hoặc nguồn hiện tại có lỗi. Hãy xem lý do review.")
        quiz = review.resource
        result = None
        if submission is not None:
            try:
                checked = QuizSubmission.model_validate(submission)
                grade = grade_single_choice(
                    tuple((q.question_id, tuple(o.option_id for o in q.options), q.correct_option_id) for q in quiz.questions),
                    tuple((a.question_id, a.option_id) for a in checked.answers),
                )
            except (ValidationError, QuizGradingError, ValueError) as error:
                raise StudyDraftError("INVALID_DRAFT_SUBMISSION", "Lựa chọn không hợp lệ cho bản nháp hiện tại.") from error
            result = DraftQuizResult(total_count=grade.total_count, answered_count=grade.answered_count,
                matching_count=grade.correct_count, match_percent=grade.score_percent,
                items=tuple(DraftQuizFeedback(question_id=q.question_id,
                    selected_option_id=item.selected_option_id, proposed_option_id=item.correct_option_id,
                    matches_proposed=item.is_correct, explanation=q.explanation, source_refs=q.source_refs)
                    for q, item in zip(quiz.questions, grade.items, strict=True)))
        return DraftQuizPreview(quiz_set_id=quiz.quiz_set_id, requested_count=quiz.selection.requested_count,
            actual_count=len(quiz.questions), result=result,
            questions=tuple(LearnerQuizQuestion(question_id=q.question_id, question=q.question, options=q.options)
                            for q in quiz.questions))
