"""Explicitly unverified author-preview DTOs, separate from Q06 practice."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from backend.core.f2_practice_schemas import LearnerQuizQuestion
from backend.core.f2_study_schemas import SourceRef


class _PreviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class DraftQuizFeedback(_PreviewModel):
    question_id: StrictStr
    selected_option_id: StrictStr | None
    proposed_option_id: StrictStr
    matches_proposed: StrictBool
    explanation: StrictStr
    source_refs: tuple[SourceRef, ...]


class DraftQuizResult(_PreviewModel):
    total_count: Annotated[StrictInt, Field(gt=0)]
    answered_count: Annotated[StrictInt, Field(ge=0)]
    matching_count: Annotated[StrictInt, Field(ge=0)]
    match_percent: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    items: tuple[DraftQuizFeedback, ...]


class DraftQuizPreview(_PreviewModel):
    status: Literal["UNVERIFIED_DRAFT"] = "UNVERIFIED_DRAFT"
    quiz_set_id: StrictStr
    requested_count: Annotated[StrictInt, Field(gt=0)]
    actual_count: Annotated[StrictInt, Field(gt=0)]
    questions: tuple[LearnerQuizQuestion, ...]
    result: DraftQuizResult | None = None
