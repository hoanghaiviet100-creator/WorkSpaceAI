"""F2-Q01 structural boundaries, not generation or factual verification."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from backend.core.f2_study_schemas import (
    Flashcard,
    FlashcardDeck,
    QuizQuestion,
    QuizSet,
    SourceRef,
    StudyFormat,
    StudySourceSelection,
)


def source(**changes):
    return {
        "doc_id": "lecture-1",
        "doc_version": "v1",
        "doc_hash": "a" * 64,
        "page_number": 2,
        "chunk_id": "lecture-1:p2:c1",
        "start_line": 3,
        "end_line": 4,
        "evidence_quote": "  Phân rã chia bài toán lớn\nthành các bài toán nhỏ.  ",
        **changes,
    }


def selection(study_format="quiz", **changes):
    return {
        "selected_doc_ids": ["lecture-1"],
        "study_format": study_format,
        **changes,
    }


def question(**changes):
    return {
        "question_id": "q1",
        "question": "Phân rã là gì?",
        "options": [
            {"option_id": "A", "text": "Chia bài toán thành các phần nhỏ"},
            {"option_id": "B", "text": "Bỏ qua bài toán"},
        ],
        "correct_option_id": "A",
        "explanation": "Phân rã chia bài toán lớn thành các bài toán nhỏ.",
        "source_refs": [source()],
        **changes,
    }


def card(**changes):
    return {
        "card_id": "c1",
        "front": "Phân rã là gì?",
        "back": "Chia bài toán lớn thành các bài toán nhỏ.",
        "source_refs": [source()],
        **changes,
    }


def study_set(kind, **changes):
    if kind == "quiz":
        return QuizSet.model_validate({
            "quiz_set_id": "quiz-1", "selection": selection(),
            "questions": [question()], **changes,
        })
    return FlashcardDeck.model_validate({
        "deck_id": "deck-1", "selection": selection("flashcards"),
        "cards": [card()], **changes,
    })


@pytest.mark.parametrize("study_format", ["quiz", "flashcards"])
def test_selection_defaults_to_ten_and_preserves_exact_multi_source_ids(study_format):
    result = StudySourceSelection(**selection(
        study_format, selected_doc_ids=["lecture-1", "Lecture-1"]
    ))
    assert result.requested_count == 10
    assert result.selected_doc_ids == ("lecture-1", "Lecture-1")
    assert result.study_format == StudyFormat(study_format)


@pytest.mark.parametrize("count", [0, -1, True, False, 1.5, 10.0, "10"])
def test_selection_rejects_invalid_or_coerced_counts(count):
    with pytest.raises(ValidationError):
        StudySourceSelection(**selection(requested_count=count))


@pytest.mark.parametrize("changes", [
    {"selected_doc_ids": []}, {"selected_doc_ids": [" "]},
    {"selected_doc_ids": ["lecture-1", "lecture-1"]},
    {"selected_doc_ids": [" lecture-1"]}, {"selected_doc_ids": [True]},
    {"selected_doc_ids": {"lecture-1"}}, {"selected_doc_ids": "lecture-1"},
    {"study_format": "task"}, {"study_format": True},
])
def test_selection_rejects_invalid_source_scope_or_format(changes):
    with pytest.raises(ValidationError):
        StudySourceSelection(**selection(**changes))


@pytest.mark.parametrize("changes", [
    {"correct_option_id": "C"}, {"correct_option_id": ["A", "B"]},
    {"correct_option_id": True}, {"correct_option_id": "a"},
    {"question": " \n"}, {"explanation": " "}, {"source_refs": []},
    {"options": [{"option_id": "A", "text": "Only choice"}]},
    {"options": [{"option_id": "A", "text": ""}, {"option_id": "B", "text": "Other"}]},
    {"options": [{"option_id": "A", "text": "One"}, {"option_id": "A", "text": "Two"}]},
    {"options": [{"option_id": "A", "text": " Straße "}, {"option_id": "B", "text": "STRASSE"}]},
])
def test_question_rejects_invalid_key_options_or_content(changes):
    with pytest.raises(ValidationError):
        QuizQuestion(**question(**changes))


@pytest.mark.parametrize("missing", ["correct_option_id", "source_refs"])
def test_question_requires_answer_key_and_source(missing):
    payload = question()
    del payload[missing]
    with pytest.raises(ValidationError):
        QuizQuestion(**payload)


def test_single_choice_supports_more_than_two_options_without_fixing_count_at_four():
    payload = question()
    payload["options"].append({"option_id": "C", "text": "Gộp các bài toán"})
    payload["correct_option_id"] = "C"
    result = QuizQuestion(**payload)
    assert result.correct_option_id == result.options[2].option_id


@pytest.mark.parametrize("changes", [
    {"front": "\t"}, {"back": " \n"}, {"source_refs": []},
    {"front": 42}, {"source_refs": [source(doc_id="")]},
])
def test_flashcard_rejects_missing_content_or_provenance(changes):
    with pytest.raises(ValidationError):
        Flashcard(**card(**changes))


@pytest.mark.parametrize("changes", [
    {"doc_id": ""}, {"doc_version": " "}, {"chunk_id": " c1"},
    {"doc_hash": ""}, {"doc_hash": "a" * 63}, {"doc_hash": "g" * 64},
    {"doc_hash": "A" * 64}, {"page_number": 0}, {"page_number": True},
    {"start_line": 0}, {"end_line": 2}, {"end_line": 4.0},
    {"evidence_quote": " \n"}, {"evidence_quote": True},
])
def test_source_rejects_malformed_provenance_or_locator(changes):
    with pytest.raises(ValidationError):
        SourceRef(**source(**changes))


@pytest.mark.parametrize("missing", ["doc_id", "doc_version", "doc_hash", "chunk_id", "evidence_quote"])
def test_source_does_not_fill_missing_metadata(missing):
    payload = source()
    del payload[missing]
    with pytest.raises(ValidationError):
        SourceRef(**payload)


def test_source_round_trip_preserves_verbatim_quote_and_stays_unverified():
    ref = SourceRef(**source())
    restored = SourceRef.model_validate_json(ref.model_dump_json())
    assert restored.evidence_quote == source()["evidence_quote"]
    assert restored == ref
    assert restored.verification_status == "UNVERIFIED"


@pytest.mark.parametrize("flag", [{"verification_status": "VERIFIED_EXACT"}, {"verified": True}])
def test_provider_cannot_label_reference_as_verified(flag):
    with pytest.raises(ValidationError):
        SourceRef(**source(**flag))


@pytest.mark.parametrize("kind", ["quiz", "flashcards"])
def test_containers_allow_short_results_and_nested_json_round_trip(kind):
    result = study_set(kind)
    assert result.selection.requested_count == 10
    assert len(result.questions if kind == "quiz" else result.cards) == 1
    assert type(result).model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("kind", ["quiz", "flashcards"])
@pytest.mark.parametrize("case", ["empty", "duplicate_id", "wrong_format", "foreign_source", "case_alias", "version_conflict", "hash_conflict"])
def test_containers_reject_inconsistent_items_or_source_snapshots(kind, case):
    make = question if kind == "quiz" else card
    field = "questions" if kind == "quiz" else "cards"
    id_field = "question_id" if kind == "quiz" else "card_id"
    items = [make()]
    changes = {}
    if case == "empty":
        items = []
    elif case == "duplicate_id":
        items.append(make())
    elif case == "wrong_format":
        changes["selection"] = selection("flashcards" if kind == "quiz" else "quiz")
    elif case in ("foreign_source", "case_alias"):
        items = [make(source_refs=[source(doc_id="elsewhere" if case == "foreign_source" else "Lecture-1")])]
    else:
        ref = source(**({"doc_version": "v2"} if case == "version_conflict" else {"doc_hash": "b" * 64}))
        items.append(make(**{id_field: "second", "source_refs": [ref]}))
    with pytest.raises(ValidationError):
        study_set(kind, **{field: items, **changes})


@pytest.mark.parametrize("kind", ["quiz", "flashcards"])
def test_multi_document_result_retains_independent_source_snapshots(kind):
    make = question if kind == "quiz" else card
    field = "questions" if kind == "quiz" else "cards"
    refs = [source(), source(doc_id="lecture-2", doc_version="v3", doc_hash="b" * 64, chunk_id="l2-c1")]
    result = study_set(kind, selection=selection(kind, selected_doc_ids=["lecture-1", "lecture-2"]), **{field: [make(source_refs=refs)]})
    item = (result.questions if kind == "quiz" else result.cards)[0]
    assert [ref.doc_id for ref in item.source_refs] == ["lecture-1", "lecture-2"]
    assert item.source_refs[1].doc_version == "v3"


def test_contracts_snapshot_mutable_inputs_and_prevent_nested_mutation():
    payload = question()
    result = QuizQuestion(**payload)
    payload["options"][0]["text"] = "tampered"
    payload["source_refs"].clear()
    assert result.options[0].text == question()["options"][0]["text"]
    assert len(result.source_refs) == 1
    with pytest.raises(ValidationError):
        result.options[0].text = "tampered"
    with pytest.raises(TypeError):
        result.options[0] = result.options[1]
    with pytest.raises(ValidationError):
        result.source_refs[0].doc_hash = "b" * 64


@pytest.mark.parametrize("kind", ["quiz", "flashcards"])
def test_parent_revalidates_instances_created_with_unsafe_model_copy(kind):
    item = QuizQuestion(**question()) if kind == "quiz" else Flashcard(**card())
    invalid = item.model_copy(update={"source_refs": (SourceRef(**source()).model_copy(update={"end_line": 1}),)})
    with pytest.raises(ValidationError):
        study_set(kind, **{"questions" if kind == "quiz" else "cards": [invalid]})


def test_schema_import_adds_no_runtime_dependencies_or_external_side_effects():
    # backend.core.__init__ already imports shared config/schemas. Account for
    # that existing package behavior before checking this module's own import.
    code = """
import os
import sys
import backend.core

def audit(event, args):
    if event in ('socket.connect', 'socket.bind', 'sqlite3.connect', 'subprocess.Popen'):
        raise AssertionError(event)
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
        raise AssertionError('file write during study schema import')

before = set(sys.modules)
sys.addaudithook(audit)
from backend.core.f2_study_schemas import QuizSet
for name in set(sys.modules) - before:
    assert not name.startswith(('backend.services', 'backend.repositories', 'backend.providers', 'backend.api', 'fastapi', 'streamlit')), name
print('STUDY_CONTRACT_IMPORT_ISOLATED')
"""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STUDY_CONTRACT_IMPORT_ISOLATED" in result.stdout
