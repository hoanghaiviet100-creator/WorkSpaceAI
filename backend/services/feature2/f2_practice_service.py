"""Q06 interaction service. Context comes from a trusted backend resolver.

Q05 is rerun at every successful read/action, with the original resource and
source digests pinned to the session. Never accept a client validation receipt.
Views are explicit allowlists so evidence quotes cannot leak the answer early.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random
import unicodedata
from uuid import uuid4

from pydantic import ValidationError

from backend.algorithms.feature2.f2_quiz_grading import QuizGrade, QuizGradingError, grade_single_choice
from backend.core.feature2.f2_practice_schemas import (
    FlashcardBackView, FlashcardFrontView, LearnerQuizQuestion, QuizAnswer,
    QuizPracticeResult, QuizPracticeView, QuizQuestionFeedback, QuizSubmission,
)
from backend.core.feature2.f2_study_schemas import FlashcardDeck, QuizSet
from backend.repositories.feature2.f2_practice_repository import (
    FlashcardPracticeSession, InMemoryPracticeRepository, QuizPracticeSession,
)
from backend.services.feature2.f2_source_service import SourceAccessContext, StudySourceRepository
from backend.services.feature2.f2_study_validation_service import F2StudyValidationService


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

    def _ready(self, resource, context, *, session=None, allow_draft=False):
        validate = self.validator.validate_quiz if isinstance(resource, QuizSet) else self.validator.validate_flashcards
        receipt = validate(resource, workspace_id=context.sources.workspace_id, context=context.sources)
        if session is not None and receipt.resource_digest != session.resource_digest:
            raise PracticeError("RESOURCE_CHANGED", "Học liệu của phiên đã thay đổi; hãy bắt đầu phiên mới.")
        if not receipt.release_ready and not (
            (session.draft if session is not None else allow_draft) and receipt.draft_preview_ready
        ):
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
        # Stable within a session, with answer positions spread across single-choice questions.
        rng = Random(session.option_seed)
        positions: dict[int, list[int]] = {}
        questions = []
        for question in session.quiz.questions:
            options = list(question.options)
            rng.shuffle(options)
            if question.kind == "single":
                count = len(options)
                if not positions.get(count):
                    positions[count] = rng.sample(range(count), count)
                correct = next(index for index, option in enumerate(options)
                               if option.option_id == question.correct_option_id)
                options.insert(positions[count].pop(), options.pop(correct))
            questions.append(LearnerQuizQuestion(
                question_id=question.question_id, question=question.question,
                options=tuple(options), kind=question.kind,
            ))
        return QuizPracticeView(
            session_id=session.session_id, quiz_set_id=session.quiz.quiz_set_id,
            status="SUBMITTED" if session.submission is not None else "IN_PROGRESS",
            requested_count=session.quiz.selection.requested_count, actual_count=len(session.quiz.questions),
            questions=tuple(questions),
        )

    @staticmethod
    def _grade(quiz: QuizSet, submission: QuizSubmission) -> QuizGrade:
        if any(answer.option_id is None for answer in submission.answers):
            raise PracticeError("INVALID_ANSWER", "Mỗi câu hỏi cần một lựa chọn.")
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

    @classmethod
    def _submission_result(cls, session, submission):
        if all(question.kind == "single" for question in session.quiz.questions):
            grade = cls._grade(session.quiz, submission)
            canonical = QuizSubmission(answers=tuple(
                QuizAnswer(question_id=item.question_id, option_id=item.selected_option_id)
                for item in grade.items if item.selected_option_id is not None
            ))
            return canonical, cls._quiz_result(session, grade)

        answers = {answer.question_id: answer for answer in submission.answers}
        if not answers.keys() <= {question.question_id for question in session.quiz.questions}:
            raise PracticeError("UNKNOWN_QUESTION", "Có câu trả lời không thuộc Quiz này.")
        feedback = []
        canonical = []

        def normalize(text):
            return " ".join(unicodedata.normalize("NFKC", text).casefold().split()).rstrip(".!?")

        for question in session.quiz.questions:
            answer = answers.get(question.question_id)
            keys = (question.correct_option_id, *question.extra_keys)
            written = question.kind in ("blank", "short")
            selected = ()
            submitted_text = None
            correct = False
            if answer and written and answer.text is not None:
                submitted_text = " ".join(answer.text.split())
                if not submitted_text:
                    raise PracticeError("INVALID_ANSWER", "Câu trả lời không được để trống.")
                correct = normalize(submitted_text) in {normalize(key) for key in keys}
                canonical.append(QuizAnswer(question_id=question.question_id, text=submitted_text))
            elif answer and not written:
                selected = answer.option_ids if question.kind == "multiple" else ((answer.option_id,) if answer.option_id else ())
                if (not selected or len(set(selected)) != len(selected)
                        or not set(selected) <= {option.option_id for option in question.options}):
                    raise PracticeError("INVALID_ANSWER", "Lựa chọn không hợp lệ cho câu hỏi này.")
                selected = tuple(sorted(selected))
                correct = set(selected) == set(keys)
                canonical.append(QuizAnswer(
                    question_id=question.question_id,
                    **({"option_ids": selected} if question.kind == "multiple" else {"option_id": selected[0]}),
                ))
            elif answer:
                raise PracticeError("INVALID_ANSWER", "Cần nhập câu trả lời bằng văn bản.")
            feedback.append(QuizQuestionFeedback(
                question_id=question.question_id, selected_option_id=selected[0] if selected else None,
                correct_option_id=keys[0] if not written else None, is_correct=correct,
                explanation=question.explanation, source_refs=question.source_refs,
                selected_option_ids=selected, correct_option_ids=keys if not written else (),
                expected_text=keys[0] if written else None, submitted_text=submitted_text,
            ))
        correct_count = sum(item.is_correct for item in feedback)
        return QuizSubmission(answers=tuple(canonical)), QuizPracticeResult(
            session_id=session.session_id, quiz_set_id=session.quiz.quiz_set_id, total_count=len(feedback),
            answered_count=len(canonical), correct_count=correct_count,
            score_percent=round(100 * correct_count / len(feedback), 2), items=tuple(feedback),
        )

    def start_quiz(self, quiz: QuizSet, *, context: PracticeAccessContext, allow_draft: bool = False) -> QuizPracticeView:
        context = self._context(context)
        try:
            quiz = QuizSet.model_validate(quiz)
        except ValidationError as error:
            raise PracticeError("INVALID_RESOURCE", "Quiz không hợp lệ; hãy tạo lại học liệu.") from error
        with self.sessions.transaction():
            receipt = self._ready(quiz, context, allow_draft=allow_draft)
            session = QuizPracticeSession(str(uuid4()), context.sources.workspace_id, context.learner_id,
                quiz, receipt.resource_digest, receipt.source_snapshot_digest, draft=not receipt.release_ready)
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
            canonical, result = self._submission_result(session, submission)
            if session.submission is not None and canonical != session.submission:
                raise PracticeError("ALREADY_SUBMITTED", "Phiên đã nộp bài; hãy bắt đầu phiên mới để làm lại.")
            self._ready(session.quiz, context, session=session)
            updated = replace(session, submission=canonical)
            self.sessions.replace(updated)
            return result

    def check_quiz_answer(self, session_id: str, submission: QuizSubmission, *, context: PracticeAccessContext):
        context = self._context(context)
        with self.sessions.transaction():
            session = self._session(session_id, context, QuizPracticeSession)
            if session.submission is not None:
                raise PracticeError("ALREADY_SUBMITTED", "This quiz has already been submitted.")
            if len(submission.answers) != 1:
                raise PracticeError("INVALID_ANSWER", "Provide exactly one answer.")
            self._ready(session.quiz, context, session=session)
            _, result = self._submission_result(session, submission)
            question_id = submission.answers[0].question_id
            return next(item for item in result.items if item.question_id == question_id)

    def get_quiz_result(self, session_id: str, *, context: PracticeAccessContext) -> QuizPracticeResult:
        context = self._context(context)
        with self.sessions.transaction():
            session = self._session(session_id, context, QuizPracticeSession)
            if session.submission is None:
                raise PracticeError("NOT_SUBMITTED", "Hãy nộp câu trả lời trước khi xem đáp án và giải thích.")
            self._ready(session.quiz, context, session=session)
            return self._submission_result(session, session.submission)[1]

    @staticmethod
    def _card_view(session: FlashcardPracticeSession) -> FlashcardFrontView | FlashcardBackView:
        card = session.deck.cards[session.current_index]
        data = dict(session_id=session.session_id, deck_id=session.deck.deck_id,
            requested_count=session.deck.selection.requested_count, actual_count=len(session.deck.cards),
            current_index=session.current_index, card_id=card.card_id, front=card.front)
        if session.revealed:
            return FlashcardBackView(**data, back=card.back, source_refs=card.source_refs)
        return FlashcardFrontView(**data)

    def start_flashcards(self, deck: FlashcardDeck, *, context: PracticeAccessContext, allow_draft: bool = False) -> FlashcardFrontView:
        context = self._context(context)
        try:
            deck = FlashcardDeck.model_validate(deck)
        except ValidationError as error:
            raise PracticeError("INVALID_RESOURCE", "Bộ flashcard không hợp lệ; hãy tạo lại học liệu.") from error
        with self.sessions.transaction():
            receipt = self._ready(deck, context, allow_draft=allow_draft)
            session = FlashcardPracticeSession(str(uuid4()), context.sources.workspace_id, context.learner_id,
                deck, receipt.resource_digest, receipt.source_snapshot_digest, draft=not receipt.release_ready)
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
