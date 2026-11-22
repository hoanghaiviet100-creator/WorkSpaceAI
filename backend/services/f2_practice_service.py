"""Q06 interaction service. Context comes from a trusted backend resolver.

Q05 is rerun at every successful read/action, with the original resource and
source digests pinned to the session. Never accept a client validation receipt.
Views are explicit allowlists so evidence quotes cannot leak the answer early.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from pydantic import ValidationError

from backend.algorithms.f2_quiz_grading import QuizGrade, QuizGradingError, grade_single_choice
from backend.core.f2_practice_schemas import (
    FlashcardBackView, FlashcardFrontView, LearnerQuizQuestion, QuizAnswer,
    QuizPracticeResult, QuizPracticeView, QuizQuestionFeedback, QuizSubmission,
)
from backend.core.f2_study_schemas import FlashcardDeck, QuizSet
from backend.repositories.f2_practice_repository import (
    FlashcardPracticeSession, InMemoryPracticeRepository, QuizPracticeSession,
)
from backend.services.f2_source_service import SourceAccessContext, StudySourceRepository
from backend.services.f2_study_validation_service import F2StudyValidationService


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


@dataclass(frozen=True)
class PracticeAccessContext:
    """Server-resolved learner identity and source scope; not authentication."""
    learner_id: str
    sources: SourceAccessContext

    def __post_init__(self):
        if not _valid_id(self.learner_id) or not isinstance(self.sources, SourceAccessContext):
            raise ValueError("expected a learner identity and backend source scope")
        SourceAccessContext(self.sources.workspace_id, self.sources.allowed_doc_ids)


class PracticeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class F2PracticeService:
    def __init__(self, repository: StudySourceRepository, *, sessions: InMemoryPracticeRepository | None = None):
        self.validator = F2StudyValidationService(repository)
        self.sessions = sessions if sessions is not None else InMemoryPracticeRepository()

    @staticmethod
    def _context(context: PracticeAccessContext) -> PracticeAccessContext:
        try:
            if not isinstance(context, PracticeAccessContext):
                raise ValueError("missing context")
            sources = SourceAccessContext(context.sources.workspace_id, context.sources.allowed_doc_ids)
            return PracticeAccessContext(context.learner_id, sources)
        except (ValueError, AttributeError) as error:
            raise PracticeError("INVALID_CONTEXT", "Thiếu định danh người học hoặc phạm vi nguồn do backend cung cấp.") from error

    def _ready(self, resource, context, *, session=None):
        validate = self.validator.validate_quiz if isinstance(resource, QuizSet) else self.validator.validate_flashcards
        receipt = validate(resource, workspace_id=context.sources.workspace_id, context=context.sources)
        if session is not None and receipt.resource_digest != session.resource_digest:
            raise PracticeError("RESOURCE_CHANGED", "Học liệu của phiên đã thay đổi; hãy bắt đầu phiên mới.")
        if not receipt.release_ready:
            raise PracticeError("RESOURCE_NOT_READY", receipt.message)
        if session is not None and receipt.source_snapshot_digest != session.source_snapshot_digest:
            raise PracticeError("SOURCE_CHANGED", "Nguồn của phiên đã thay đổi; hãy tạo lại học liệu và bắt đầu phiên mới.")
        return receipt

    def _session(self, session_id, context, expected_type):
        session = self.sessions.get(session_id) if _valid_id(session_id) else None
        if (not isinstance(session, expected_type) or session.workspace_id != context.sources.workspace_id
            or session.learner_id != context.learner_id):
            raise PracticeError("SESSION_NOT_FOUND", "Không tìm thấy phiên luyện tập trong phạm vi của bạn.")
        return session

    @staticmethod
    def _quiz_view(session: QuizPracticeSession) -> QuizPracticeView:
        return QuizPracticeView(
            session_id=session.session_id, quiz_set_id=session.quiz.quiz_set_id,
            status="SUBMITTED" if session.submission is not None else "IN_PROGRESS",
            requested_count=session.quiz.selection.requested_count, actual_count=len(session.quiz.questions),
            questions=tuple(LearnerQuizQuestion(question_id=q.question_id, question=q.question, options=q.options)
                            for q in session.quiz.questions),
        )

    @staticmethod
    def _grade(quiz: QuizSet, submission: QuizSubmission) -> QuizGrade:
        try:
            return grade_single_choice(
                tuple((q.question_id, tuple(o.option_id for o in q.options), q.correct_option_id) for q in quiz.questions),
                tuple((a.question_id, a.option_id) for a in submission.answers),
            )
        except QuizGradingError as error:
            raise PracticeError(error.code, str(error)) from error

    @staticmethod
    def _quiz_result(session: QuizPracticeSession, grade: QuizGrade) -> QuizPracticeResult:
        return QuizPracticeResult(
            session_id=session.session_id, quiz_set_id=session.quiz.quiz_set_id,
            total_count=grade.total_count, answered_count=grade.answered_count,
            correct_count=grade.correct_count, score_percent=grade.score_percent,
            items=tuple(QuizQuestionFeedback(
                question_id=q.question_id, selected_option_id=item.selected_option_id,
                correct_option_id=item.correct_option_id, is_correct=item.is_correct,
                explanation=q.explanation, source_refs=q.source_refs,
            ) for q, item in zip(session.quiz.questions, grade.items, strict=True)),
        )

    def start_quiz(self, quiz: QuizSet, *, context: PracticeAccessContext) -> QuizPracticeView:
        context = self._context(context)
        try:
            quiz = QuizSet.model_validate(quiz)
        except ValidationError as error:
            raise PracticeError("INVALID_RESOURCE", "Quiz không hợp lệ; hãy tạo lại học liệu.") from error
        with self.sessions.transaction():
            receipt = self._ready(quiz, context)
            session = QuizPracticeSession(str(uuid4()), context.sources.workspace_id, context.learner_id,
                quiz, receipt.resource_digest, receipt.source_snapshot_digest)
            view = self._quiz_view(session)
            self.sessions.create(session)
            return view

    def get_quiz(self, session_id: str, *, context: PracticeAccessContext) -> QuizPracticeView:
        context = self._context(context)
        with self.sessions.transaction():
            session = self._session(session_id, context, QuizPracticeSession)
            self._ready(session.quiz, context, session=session)
            return self._quiz_view(session)

    def submit_quiz(self, session_id: str, submission: QuizSubmission, *, context: PracticeAccessContext) -> QuizPracticeResult:
        context = self._context(context)
        with self.sessions.transaction():
            session = self._session(session_id, context, QuizPracticeSession)
            try:
                submission = QuizSubmission.model_validate(submission)
            except ValidationError as error:
                raise PracticeError("INVALID_SUBMISSION", "Câu trả lời không hợp lệ; mỗi câu chỉ chọn một đáp án.") from error
            grade = self._grade(session.quiz, submission)
            # Canonicalize answer order so a reordered retry is idempotent.
            canonical = QuizSubmission(answers=tuple(QuizAnswer(question_id=a.question_id, option_id=a.selected_option_id)
                for a in grade.items if a.selected_option_id is not None))
            if session.submission is not None and canonical != session.submission:
                raise PracticeError("ALREADY_SUBMITTED", "Phiên đã nộp bài; hãy bắt đầu phiên mới để làm lại.")
            self._ready(session.quiz, context, session=session)
            updated = replace(session, submission=canonical)
            result = self._quiz_result(updated, grade)
            self.sessions.replace(updated)
            return result

    def get_quiz_result(self, session_id: str, *, context: PracticeAccessContext) -> QuizPracticeResult:
        context = self._context(context)
        with self.sessions.transaction():
            session = self._session(session_id, context, QuizPracticeSession)
            if session.submission is None:
                raise PracticeError("NOT_SUBMITTED", "Hãy nộp câu trả lời trước khi xem đáp án và giải thích.")
            self._ready(session.quiz, context, session=session)
            return self._quiz_result(session, self._grade(session.quiz, session.submission))

    @staticmethod
    def _card_view(session: FlashcardPracticeSession) -> FlashcardFrontView | FlashcardBackView:
        card = session.deck.cards[session.current_index]
        data = dict(session_id=session.session_id, deck_id=session.deck.deck_id,
            requested_count=session.deck.selection.requested_count, actual_count=len(session.deck.cards),
            current_index=session.current_index, card_id=card.card_id, front=card.front)
        if session.revealed:
            return FlashcardBackView(**data, back=card.back, source_refs=card.source_refs)
        return FlashcardFrontView(**data)

    def start_flashcards(self, deck: FlashcardDeck, *, context: PracticeAccessContext) -> FlashcardFrontView:
        context = self._context(context)
        try:
            deck = FlashcardDeck.model_validate(deck)
        except ValidationError as error:
            raise PracticeError("INVALID_RESOURCE", "Bộ flashcard không hợp lệ; hãy tạo lại học liệu.") from error
        with self.sessions.transaction():
            receipt = self._ready(deck, context)
            session = FlashcardPracticeSession(str(uuid4()), context.sources.workspace_id, context.learner_id,
                deck, receipt.resource_digest, receipt.source_snapshot_digest)
            view = self._card_view(session)
            self.sessions.create(session)
            return view

    def get_flashcard(self, session_id: str, *, context: PracticeAccessContext) -> FlashcardFrontView | FlashcardBackView:
        context = self._context(context)
        with self.sessions.transaction():
            session = self._session(session_id, context, FlashcardPracticeSession)
            self._ready(session.deck, context, session=session)
            return self._card_view(session)

    @staticmethod
    def _check_card(session: FlashcardPracticeSession, card_id: str):
        if not _valid_id(card_id) or card_id != session.deck.cards[session.current_index].card_id:
            raise PracticeError("CARD_MISMATCH", "Thẻ hiện tại đã thay đổi; hãy tải lại trước khi thao tác.")

    def flip_flashcard(self, session_id: str, *, card_id: str, context: PracticeAccessContext) -> FlashcardFrontView | FlashcardBackView:
        context = self._context(context)
        with self.sessions.transaction():
            session = self._session(session_id, context, FlashcardPracticeSession)
            self._check_card(session, card_id)
            self._ready(session.deck, context, session=session)
            updated = replace(session, revealed=not session.revealed)
            view = self._card_view(updated)
            self.sessions.replace(updated)
            return view

    def move_flashcard(self, session_id: str, direction: str, *, card_id: str, context: PracticeAccessContext) -> FlashcardFrontView:
        context = self._context(context)
        with self.sessions.transaction():
            session = self._session(session_id, context, FlashcardPracticeSession)
            self._check_card(session, card_id)
            if direction not in ("next", "previous"):
                raise PracticeError("INVALID_DIRECTION", "Chỉ có thể chuyển tới thẻ trước hoặc thẻ tiếp theo.")
            index = session.current_index + (1 if direction == "next" else -1)
            if index < 0 or index >= len(session.deck.cards):
                raise PracticeError("NAVIGATION_BOUNDARY", "Đã tới đầu hoặc cuối bộ flashcard.")
            self._ready(session.deck, context, session=session)
            updated = replace(session, current_index=index, revealed=False)
            view = self._card_view(updated)
            self.sessions.replace(updated)
            return view
