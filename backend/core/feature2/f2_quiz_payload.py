"""LLM Quiz JSON contract. Valid structure is not verified knowledge."""
from typing import Annotated, Literal
from typing_extensions import Self

from pydantic import (
    AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, StrictStr, model_validator,
)

from backend.core.feature2.f2_study_schemas import QuizOption


def _text(value: str) -> str:
    if not value.strip():
        raise ValueError("expected nonblank text")
    return value


def _ordered(value: object) -> object:
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected an ordered JSON array")
    return value


_Text = Annotated[StrictStr, AfterValidator(_text)]


class LLMQuizQuestion(BaseModel):
    """Wire fields only: the server supplies question IDs and real source refs."""
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    question: _Text
    options: Annotated[tuple[QuizOption, ...], Field(max_length=4), BeforeValidator(_ordered)]
    correct_option_id: _Text
    explanation: _Text
    source_ids: Annotated[tuple[_Text, ...], Field(min_length=1), BeforeValidator(_ordered)]
    kind: Literal["single", "multiple", "blank", "short"] = "single"
    extra_keys: Annotated[tuple[_Text, ...], Field(max_length=4)] = ()

    @model_validator(mode="after")
    def _single_choice(self) -> Self:
        ids = tuple(option.option_id for option in self.options)
        texts = {" ".join(option.text.split()).casefold() for option in self.options}
        if len(set(ids)) != len(ids) or len(texts) != len(self.options):
            raise ValueError("options must have unique IDs and distinct text")
        if self.kind in ("single", "multiple") and (len(ids) < 2 or self.correct_option_id not in ids):
            raise ValueError("choice questions require options and a valid key")
        if self.kind == "multiple":
            keys = (self.correct_option_id, *self.extra_keys)
            if len(set(keys)) != len(keys) or not 2 <= len(keys) < len(ids) or any(key not in ids for key in keys):
                raise ValueError("multiple choice needs at least two correct options and one distractor")
        elif self.kind in ("blank", "short"):
            if ids or any(len(key) > 300 for key in (self.correct_option_id, *self.extra_keys)):
                raise ValueError("written answers need a brief key and no options")
            if self.kind == "blank" and self.question.count("[___]") != 1:
                raise ValueError("fill-in-the-blank needs exactly one blank")
        elif self.extra_keys:
            raise ValueError("single choice requires one key")
        if len(set(self.source_ids)) != len(self.source_ids) or any(s != s.strip() for s in self.source_ids):
            raise ValueError("source aliases must be unique and exact")
        return self


class LLMQuizPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    questions: Annotated[tuple[LLMQuizQuestion, ...], BeforeValidator(_ordered)]


def quiz_response_schema() -> dict:
    """Inline the contract as the same simple schema used by prompt and Gemini.

    Leave semantic checks, source membership and duplicate JSON keys to the
    service. Each call returns a fresh mapping, with no shared mutable schema.
    """
    schema = LLMQuizPayload.model_json_schema()
    definitions = schema.get("$defs", {})

    def inline(node):
        if isinstance(node, list):
            return [inline(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return inline(definitions[node["$ref"].rsplit("/", 1)[-1]])
        return {key: inline(value) for key, value in node.items() if key not in ("$defs", "title")}

    return inline(schema)
