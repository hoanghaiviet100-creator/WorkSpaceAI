"""Q06 learner projections: keys/quotes only after submit, backs after flip."""
from __future__ import annotations

from typing import Annotated, Literal
from typing_extensions import Self

from pydantic import (
    AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field,
    StrictBool, StrictInt, StrictStr, model_validator,
)

from backend.core.feature2.f2_study_schemas import QuizOption, SourceRef


def _identifier(value: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError("expected an exact nonblank identifier")
    return value


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected nonblank text")
    return value


def _ordered(value: object) -> object:
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected an ordered list or tuple")
    return value


_ID = Annotated[StrictStr, AfterValidator(_identifier)]
_Text = Annotated[StrictStr, AfterValidator(_nonblank)]
_Count = Annotated[StrictInt, Field(gt=0)]
_Nonnegative = Annotated[StrictInt, Field(ge=0)]
_Refs = Annotated[tuple[SourceRef, ...], BeforeValidator(_ordered), Field(min_length=1)]


class _PracticeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class QuizAnswer(_PracticeModel):
    question_id: _ID
    option_id: _ID | None = None
    option_ids: tuple[_ID, ...] = ()
    text: Annotated[StrictStr, Field(min_length=1, max_length=500)] | None = None

    @model_validator(mode="after")
    def _one_form(self) -> Self:
        if sum((self.option_id is not None, bool(self.option_ids), self.text is not None)) != 1:
            raise ValueError("provide exactly one answer form")
        return self


class QuizSubmission(_PracticeModel):
    answers: Annotated[tuple[QuizAnswer, ...], BeforeValidator(_ordered)] = ()

    @model_validator(mode="after")
    def _unique_answers(self) -> Self:
        ids = [answer.question_id for answer in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("one answer per question is required")
        return self


class LearnerQuizQuestion(_PracticeModel):
    question_id: _ID
    question: _Text
    options: Annotated[tuple[QuizOption, ...], BeforeValidator(_ordered)]
    kind: Literal["single", "multiple", "blank", "short"] = "single"


class QuizPracticeView(_PracticeModel):
    session_id: _ID
    quiz_set_id: _ID
    status: Literal["IN_PROGRESS", "SUBMITTED"]
    requested_count: _Count
    actual_count: _Count
    questions: Annotated[tuple[LearnerQuizQuestion, ...], BeforeValidator(_ordered), Field(min_length=1)]


class QuizQuestionFeedback(_PracticeModel):
    question_id: _ID
    selected_option_id: _ID | None
    correct_option_id: _ID | None
    is_correct: StrictBool
    explanation: _Text
    source_refs: _Refs
    correct_option_ids: tuple[_ID, ...] = ()
    selected_option_ids: tuple[_ID, ...] = ()
    expected_text: str | None = None
    submitted_text: str | None = None


class QuizPracticeResult(_PracticeModel):
    session_id: _ID
    quiz_set_id: _ID
    total_count: _Count
    answered_count: _Nonnegative
    correct_count: _Nonnegative
    score_percent: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    items: Annotated[tuple[QuizQuestionFeedback, ...], BeforeValidator(_ordered), Field(min_length=1)]


class FlashcardFrontView(_PracticeModel):
    session_id: _ID
    deck_id: _ID
    requested_count: _Count
    actual_count: _Count
    current_index: _Nonnegative  # zero-based, unlike source line/page numbers
    card_id: _ID
    front: _Text
    side: Literal["front"] = "front"


class FlashcardBackView(FlashcardFrontView):
    side: Literal["back"] = "back"
    back: _Text
    source_refs: _Refs
