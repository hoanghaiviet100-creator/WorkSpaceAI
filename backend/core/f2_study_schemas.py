"""Structural contracts for F2 Quiz/Flashcards, independent of runtime services.

These are internal generation/study-set models, including the quiz answer key.
They do not verify factual support, live source identity or workspace access,
and must not be exposed unchanged as learner-facing API responses.
"""
from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    model_validator,
)


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("text must not be blank")
    return value  # Preserve prose and evidence verbatim, including Unicode.


def _identifier(value: str) -> str:
    _nonblank(value)
    if value != value.strip():
        raise ValueError("identifiers must not have surrounding whitespace")
    return value  # Opaque, case-sensitive identity; never resolve filename aliases.


def _ordered_sequence(value: object) -> object:
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected an ordered list or tuple")
    return value


def _unique_ids(values: Iterable[str]) -> None:
    values = tuple(values)
    if len(values) != len(set(values)):
        raise ValueError("IDs must be unique")


_Text = Annotated[StrictStr, AfterValidator(_nonblank)]
_Identifier = Annotated[StrictStr, AfterValidator(_identifier)]
_PositiveInt = Annotated[StrictInt, Field(gt=0)]
_SHA256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


class _StudyModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always"
    )


class StudyFormat(str, Enum):
    QUIZ = "quiz"
    FLASHCARDS = "flashcards"


class SourceRef(_StudyModel):
    """A claimed source locator, not a verified citation.

    Lines are inclusive and 1-based. Hashes use canonical lowercase SHA-256
    syntax; an empty legacy/demo hash must be resolved by the source layer,
    never fabricated by this contract. Quote content is preserved verbatim.
    """

    doc_id: _Identifier
    doc_version: _Identifier
    doc_hash: _SHA256
    page_number: _PositiveInt
    chunk_id: _Identifier
    start_line: _PositiveInt
    end_line: _PositiveInt
    evidence_quote: _Text
    verification_status: Literal["UNVERIFIED"] = "UNVERIFIED"

    @model_validator(mode="after")
    def _validate_line_span(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be at least start_line")
        return self


class StudySourceSelection(_StudyModel):
    """Requested source IDs/format/count; workspace authorization is external."""

    selected_doc_ids: Annotated[
        tuple[_Identifier, ...], BeforeValidator(_ordered_sequence)
    ] = Field(min_length=1)
    study_format: StudyFormat
    requested_count: _PositiveInt = 10

    @model_validator(mode="after")
    def _validate_selection(self) -> Self:
        _unique_ids(self.selected_doc_ids)
        return self


class QuizOption(_StudyModel):
    option_id: _Identifier
    text: _Text


_SourceRefs = Annotated[
    tuple[SourceRef, ...], BeforeValidator(_ordered_sequence), Field(min_length=1)
]


class QuizQuestion(_StudyModel):
    """Internal single-choice question. A well-formed key may still be wrong."""

    question_id: _Identifier
    question: _Text
    options: Annotated[
        tuple[QuizOption, ...], BeforeValidator(_ordered_sequence)
    ] = Field(min_length=2)
    correct_option_id: _Identifier
    explanation: _Text
    source_refs: _SourceRefs

    @model_validator(mode="after")
    def _validate_options_and_key(self) -> Self:
        option_ids = tuple(option.option_id for option in self.options)
        _unique_ids(option_ids)
        text_keys = {option.text.strip().casefold() for option in self.options}
        if len(text_keys) != len(self.options):
            raise ValueError("option texts must be distinct after strip/casefold")
        if self.correct_option_id not in option_ids:
            raise ValueError("correct_option_id must identify an existing option")
        return self


class Flashcard(_StudyModel):
    card_id: _Identifier
    front: _Text
    back: _Text
    source_refs: _SourceRefs


def _validate_sources(
    selection: StudySourceSelection, sources: Iterable[SourceRef]
) -> None:
    selected = set(selection.selected_doc_ids)
    snapshots: dict[str, tuple[str, str]] = {}
    for source in sources:
        if source.doc_id not in selected:
            raise ValueError("source doc_id must belong to selected_doc_ids exactly")
        snapshot = (source.doc_version, source.doc_hash)
        if source.doc_id in snapshots and snapshots[source.doc_id] != snapshot:
            raise ValueError("one document must have a consistent version/hash snapshot")
        snapshots[source.doc_id] = snapshot


class QuizSet(_StudyModel):
    """Nonempty quiz result; requested_count is not an exact result-size rule."""

    quiz_set_id: _Identifier
    selection: StudySourceSelection
    questions: Annotated[
        tuple[QuizQuestion, ...], BeforeValidator(_ordered_sequence)
    ] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_quiz_set(self) -> Self:
        if self.selection.study_format != StudyFormat.QUIZ:
            raise ValueError("QuizSet requires study_format='quiz'")
        _unique_ids(question.question_id for question in self.questions)
        _validate_sources(
            self.selection,
            (source for question in self.questions for source in question.source_refs),
        )
        return self


class FlashcardDeck(_StudyModel):
    """Nonempty card result; insufficiency messaging belongs to the service."""

    deck_id: _Identifier
    selection: StudySourceSelection
    cards: Annotated[
        tuple[Flashcard, ...], BeforeValidator(_ordered_sequence)
    ] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_deck(self) -> Self:
        if self.selection.study_format != StudyFormat.FLASHCARDS:
            raise ValueError("FlashcardDeck requires study_format='flashcards'")
        _unique_ids(card.card_id for card in self.cards)
        _validate_sources(
            self.selection,
            (source for card in self.cards for source in card.source_refs),
        )
        return self


__all__ = [
    "StudyFormat",
    "SourceRef",
    "StudySourceSelection",
    "QuizOption",
    "QuizQuestion",
    "QuizSet",
    "Flashcard",
    "FlashcardDeck",
]
