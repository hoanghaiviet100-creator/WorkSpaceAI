"""Q06 grading, reveal boundaries, scoped state and source freshness."""
import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.algorithms.f2_quiz_grading import QuizGradingError, grade_single_choice
from backend.core.f2_practice_schemas import (
    FlashcardBackView, FlashcardFrontView, QuizAnswer, QuizPracticeResult, QuizPracticeView, QuizSubmission,
)
from backend.core.f2_study_schemas import StudySourceSelection
from backend.core.schemas import DocumentChunk, DocumentMetadata
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services.f2_flashcard_service import F2FlashcardService
from backend.services.f2_practice_service import F2PracticeService, PracticeAccessContext, PracticeError
from backend.services.f2_quiz_service import F2QuizService
from backend.services.f2_source_service import F2SourceService, SourceAccessContext


TEXT = "Cache: Fast temporary memory.\nRAM: Volatile working storage.\nCPU: A processor executing instructions."


def context(learner="learner-1", workspace="workspace-1", allowed=frozenset({"lecture"})):
    return PracticeAccessContext(learner, SourceAccessContext(workspace, allowed))


CONTEXT = context()


class Repository:
    def __init__(self):
        self.documents = {"lecture": DocumentMetadata(
            doc_id="lecture", doc_name="lecture.txt", file_type="txt", page_count=1,
            chunk_count=1, total_lines=3, file_hash="a" * 64, version_id="v1", uploaded_at="today",
        )}
        self.chunks = [DocumentChunk(
            doc_id="lecture", doc_name="lecture.txt", chunk_id="chunk-1", page_number=1,
            start_line=1, end_line=3, text=TEXT, doc_version="v1", doc_hash="a" * 64,
        )]
        self.reads = []

    def get_document_chunks(self, doc_id):
        self.reads.append(doc_id)
        return self.chunks


def setup(study_format="quiz", count=3):
    repo = Repository()
    prepared = F2SourceService(repo).prepare_sources(StudySourceSelection(
        selected_doc_ids=["lecture"], study_format=study_format, requested_count=count,
    ), context=CONTEXT.sources)
    value = (F2QuizService().generate_quiz(prepared).quiz if study_format == "quiz"
             else F2FlashcardService().generate_flashcards(prepared).deck)
    assert value is not None
    repo.reads.clear()
    return repo, value, F2PracticeService(repo)


def answers(quiz, *, correct=True):
    return QuizSubmission(answers=tuple(QuizAnswer(question_id=q.question_id,
        option_id=q.correct_option_id if correct else next(o.option_id for o in q.options if o.option_id != q.correct_option_id))
        for q in quiz.questions))


def assert_hidden(view):
    forbidden = {"correct_option_id", "explanation", "source_refs", "evidence_quote", "back",
                 "resource_digest", "source_snapshot_digest", "quiz", "deck", "submission"}
    def inspect(value):
        if isinstance(value, dict):
            assert not forbidden & value.keys()
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    inspect(json.loads(view.model_dump_json()))


def test_quiz_start_and_get_expose_only_questions_options_and_progress():
    repo, quiz, service = setup()
    with patch("socket.create_connection", side_effect=AssertionError("no network")), patch("smtplib.SMTP", side_effect=AssertionError("no email")):
        view = service.start_quiz(quiz, context=CONTEXT)
        again = service.get_quiz(view.session_id, context=CONTEXT)
    assert view == again
    assert view.status == "IN_PROGRESS" and view.actual_count == 3
    assert view.questions[0].question == quiz.questions[0].question
    assert view.questions[0].options == quiz.questions[0].options
    assert_hidden(view)
    assert len(repo.reads) == 4  # two fresh source reads per successful operation


def test_result_cannot_be_read_before_submit_and_failure_does_not_change_state():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    before = service.sessions.get(view.session_id)
    with pytest.raises(PracticeError) as error:
        service.get_quiz_result(view.session_id, context=CONTEXT)
    assert error.value.code == "NOT_SUBMITTED"
    assert service.sessions.get(view.session_id) == before
    assert_hidden(service.get_quiz(view.session_id, context=CONTEXT))


@pytest.mark.parametrize("correct,score", [(True, 100.0), (False, 0.0)])
def test_submit_reveals_keys_explanations_sources_and_correct_score(correct, score):
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    result = service.submit_quiz(view.session_id, answers(quiz, correct=correct), context=CONTEXT)
    assert result.score_percent == score
    assert result.total_count == result.answered_count == 3
    assert result.correct_count == (3 if correct else 0)
    assert all(item.is_correct == correct for item in result.items)
    for q, item in zip(quiz.questions, result.items, strict=True):
        assert item.correct_option_id == q.correct_option_id
        assert item.explanation == q.explanation and item.source_refs == q.source_refs
        assert all(ref.verification_status == "UNVERIFIED" for ref in item.source_refs)
    assert service.get_quiz(view.session_id, context=CONTEXT).status == "SUBMITTED"
    assert_hidden(service.get_quiz(view.session_id, context=CONTEXT))
    assert service.get_quiz_result(view.session_id, context=CONTEXT) == result


def test_partial_and_unanswered_grading_uses_actual_count_instead_of_requested_ten():
    repo, quiz, service = setup(count=10)
    view = service.start_quiz(quiz, context=CONTEXT)
    assert view.requested_count == 10 and view.actual_count == 3
    first, second = quiz.questions[:2]
    wrong = next(o.option_id for o in second.options if o.option_id != second.correct_option_id)
    submission = QuizSubmission(answers=(QuizAnswer(question_id=second.question_id, option_id=wrong),
                                       QuizAnswer(question_id=first.question_id, option_id=first.correct_option_id)))
    result = service.submit_quiz(view.session_id, submission, context=CONTEXT)
    assert (result.total_count, result.answered_count, result.correct_count, result.score_percent) == (3, 2, 1, 33.33)
    assert [i.question_id for i in result.items] == [q.question_id for q in quiz.questions]
    assert result.items[2].selected_option_id is None and not result.items[2].is_correct


def test_empty_submission_is_explicit_unanswered_attempt_and_scores_zero():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    result = service.submit_quiz(view.session_id, {"answers": []}, context=CONTEXT)
    assert result.answered_count == result.correct_count == 0 and result.score_percent == 0
    assert len(result.items) == 3 and all(i.selected_option_id is None for i in result.items)


def test_same_submission_retry_is_idempotent_even_when_answer_order_changes():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    submission = answers(quiz)
    first = service.submit_quiz(view.session_id, submission, context=CONTEXT)
    before = service.sessions.get(view.session_id)
    second = service.submit_quiz(view.session_id, QuizSubmission(answers=tuple(reversed(submission.answers))), context=CONTEXT)
    assert first == second and service.sessions.get(view.session_id) == before


def test_changed_submission_cannot_overwrite_a_submitted_attempt():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    first = service.submit_quiz(view.session_id, answers(quiz), context=CONTEXT)
    with pytest.raises(PracticeError) as error:
        service.submit_quiz(view.session_id, answers(quiz, correct=False), context=CONTEXT)
    assert error.value.code == "ALREADY_SUBMITTED"
    assert service.get_quiz_result(view.session_id, context=CONTEXT) == first
    fresh = service.start_quiz(quiz, context=CONTEXT)
    assert fresh.session_id != view.session_id and fresh.status == "IN_PROGRESS"


@pytest.mark.parametrize("payload,code", [
    ({"answers": [{"question_id": "unknown", "option_id": "A"}]}, "UNKNOWN_QUESTION"),
    ({"answers": [{"question_id": "q1", "option_id": "unknown"}]}, "UNKNOWN_OPTION"),
    ({"answers": [{"question_id": "Q1", "option_id": "A"}]}, "UNKNOWN_QUESTION"),
    ({"answers": [{"question_id": "q1", "option_id": "a"}]}, "UNKNOWN_OPTION"),
    ({"answers": [{"question_id": "q1", "option_id": "A"}, {"question_id": "q1", "option_id": "B"}]}, "INVALID_SUBMISSION"),
    ({"answers": [{"question_id": "q1", "option_id": ["A", "B"]}]}, "INVALID_SUBMISSION"),
    ({"answers": [{"question_id": "q1", "option_id": True}]}, "INVALID_SUBMISSION"),
    ({"answers": [{"question_id": " q1", "option_id": "A"}]}, "INVALID_SUBMISSION"),
    ({"answers": [], "correct_option_id": "A"}, "INVALID_SUBMISSION"),
    ({"answers": [], "verified": True}, "INVALID_SUBMISSION"),
    ({"answers": [], "score_percent": 100}, "INVALID_SUBMISSION"),
    ({"answers": "q1:A"}, "INVALID_SUBMISSION"),
])
def test_invalid_submissions_do_not_reveal_answers_or_mutate_session(payload, code):
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    before = service.sessions.get(view.session_id)
    with pytest.raises(PracticeError) as error:
        service.submit_quiz(view.session_id, payload, context=CONTEXT)
    assert error.value.code == code
    assert service.sessions.get(view.session_id) == before
    assert_hidden(service.get_quiz(view.session_id, context=CONTEXT))


def test_unsafe_copied_submission_is_revalidated():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    submission = answers(quiz).model_copy(update={"answers": (QuizAnswer(question_id="q1", option_id="A").model_copy(update={"option_id": True}),)})
    with pytest.raises(PracticeError) as error:
        service.submit_quiz(view.session_id, submission, context=CONTEXT)
    assert error.value.code == "INVALID_SUBMISSION"
    assert service.sessions.get(view.session_id).submission is None


@pytest.mark.parametrize("kind", ["quiz", "flashcards"])
@pytest.mark.parametrize("other_context", [context(learner="another"), context(workspace="other-workspace")])
def test_sessions_are_bound_to_backend_learner_and_workspace_before_source_reads(kind, other_context):
    repo, value, service = setup(kind)
    view = service.start_quiz(value, context=CONTEXT) if kind == "quiz" else service.start_flashcards(value, context=CONTEXT)
    repo.reads.clear()
    get = service.get_quiz if kind == "quiz" else service.get_flashcard
    with pytest.raises(PracticeError) as error:
        get(view.session_id, context=other_context)
    assert error.value.code == "SESSION_NOT_FOUND" and repo.reads == []


@pytest.mark.parametrize("session_id", ["missing", "", "  ", 42, None])
def test_invalid_or_missing_session_id_returns_generic_not_found(session_id):
    repo, quiz, service = setup()
    with pytest.raises(PracticeError) as error:
        service.get_quiz(session_id, context=CONTEXT)
    assert error.value.code == "SESSION_NOT_FOUND" and repo.reads == []


def test_session_format_cannot_be_switched_to_another_operation():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    with pytest.raises(PracticeError) as error:
        service.get_flashcard(view.session_id, context=CONTEXT)
    assert error.value.code == "SESSION_NOT_FOUND"


@pytest.mark.parametrize("bad_context", [None, {"learner_id": "learner-1", "workspace_id": "workspace-1"}])
def test_client_context_dict_or_missing_context_is_not_backend_authority(bad_context):
    repo, quiz, service = setup()
    with pytest.raises(PracticeError) as error:
        service.start_quiz(quiz, context=bad_context)
    assert error.value.code == "INVALID_CONTEXT" and repo.reads == []


def test_tampered_backend_context_is_reconstructed():
    repo, quiz, service = setup()
    bad = context()
    object.__setattr__(bad.sources, "allowed_doc_ids", ["lecture"])
    with pytest.raises(PracticeError) as error:
        service.start_quiz(quiz, context=bad)
    assert error.value.code == "INVALID_CONTEXT" and repo.reads == []


@pytest.mark.parametrize("kind", ["quiz", "flashcards"])
def test_review_required_resources_cannot_start_practice(kind):
    repo, value, service = setup(kind)
    if kind == "quiz":
        entry = value.questions[0].model_copy(update={"explanation": "Unproven explanation."})
        value = value.model_copy(update={"questions": (entry,)})
    else:
        entry = value.cards[0].model_copy(update={"back": "Unproven answer."})
        value = value.model_copy(update={"cards": (entry,)})
    with patch.object(service.sessions, "create") as create:
        with pytest.raises(PracticeError) as error:
            (service.start_quiz if kind == "quiz" else service.start_flashcards)(value, context=CONTEXT)
        assert error.value.code == "RESOURCE_NOT_READY"
        create.assert_not_called()


def test_forged_receipt_field_and_invalid_resource_cannot_start_session():
    repo, quiz, service = setup()
    with pytest.raises(PracticeError) as error:
        service.start_quiz({**quiz.model_dump(), "release_ready": True}, context=CONTEXT)
    assert error.value.code == "INVALID_RESOURCE" and repo.reads == []


def test_wrong_key_rejected_by_q05_cannot_start_practice():
    repo, quiz, service = setup()
    first = quiz.questions[0]
    wrong = next(o.option_id for o in first.options if o.option_id != first.correct_option_id)
    bad = quiz.model_copy(update={"questions": (first.model_copy(update={"correct_option_id": wrong}),)})
    with patch.object(service.sessions, "create") as create:
        with pytest.raises(PracticeError) as error:
            service.start_quiz(bad, context=CONTEXT)
        assert error.value.code == "RESOURCE_NOT_READY"
        create.assert_not_called()


def test_start_snapshots_resource_independently_of_original_model_instance():
    repo, quiz, service = setup()
    expected_question = quiz.questions[0].question
    view = service.start_quiz(quiz, context=CONTEXT)
    object.__setattr__(quiz.questions[0], "question", "Changed external object.")
    assert service.get_quiz(view.session_id, context=CONTEXT).questions[0].question == expected_question


@pytest.mark.parametrize("operation", ["submit", "result", "flip"])
def test_other_learner_cannot_submit_or_reveal_private_session(operation):
    kind = "flashcards" if operation == "flip" else "quiz"
    repo, value, service = setup(kind)
    view = service.start_flashcards(value, context=CONTEXT) if kind == "flashcards" else service.start_quiz(value, context=CONTEXT)
    if operation == "result":
        service.submit_quiz(view.session_id, answers(value), context=CONTEXT)
    before = service.sessions.get(view.session_id)
    repo.reads.clear()
    with pytest.raises(PracticeError) as error:
        if operation == "submit":
            service.submit_quiz(view.session_id, answers(value), context=context(learner="other"))
        elif operation == "result":
            service.get_quiz_result(view.session_id, context=context(learner="other"))
        else:
            service.flip_flashcard(view.session_id, card_id=view.card_id, context=context(learner="other"))
    assert error.value.code == "SESSION_NOT_FOUND" and repo.reads == []
    assert service.sessions.get(view.session_id) == before


def test_idempotent_submission_retry_still_checks_current_sources():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    submission = answers(quiz)
    service.submit_quiz(view.session_id, submission, context=CONTEXT)
    before = service.sessions.get(view.session_id)
    repo.documents.clear()
    with pytest.raises(PracticeError) as error:
        service.submit_quiz(view.session_id, submission, context=CONTEXT)
    assert error.value.code == "RESOURCE_NOT_READY"
    assert service.sessions.get(view.session_id) == before


@pytest.mark.parametrize("operation", ["quiz_get", "submit", "result", "card_get", "flip", "move"])
def test_every_successful_read_action_requires_current_sources_and_failed_action_keeps_state(operation):
    kind = "flashcards" if operation in {"card_get", "flip", "move"} else "quiz"
    repo, value, service = setup(kind)
    view = service.start_quiz(value, context=CONTEXT) if kind == "quiz" else service.start_flashcards(value, context=CONTEXT)
    if operation == "result":
        service.submit_quiz(view.session_id, answers(value), context=CONTEXT)
    before = service.sessions.get(view.session_id)
    repo.chunks[0].text = repo.chunks[0].text.replace("Fast", "Slow")
    calls = {
        "quiz_get": lambda: service.get_quiz(view.session_id, context=CONTEXT),
        "submit": lambda: service.submit_quiz(view.session_id, answers(value), context=CONTEXT),
        "result": lambda: service.get_quiz_result(view.session_id, context=CONTEXT),
        "card_get": lambda: service.get_flashcard(view.session_id, context=CONTEXT),
        "flip": lambda: service.flip_flashcard(view.session_id, card_id=view.card_id, context=CONTEXT),
        "move": lambda: service.move_flashcard(view.session_id, "next", card_id=view.card_id, context=CONTEXT),
    }
    with pytest.raises(PracticeError) as error:
        calls[operation]()
    assert error.value.code == "RESOURCE_NOT_READY"
    assert service.sessions.get(view.session_id) == before


def test_uncited_source_change_invalidates_pinned_session_even_when_item_still_supported():
    repo, deck, service = setup("flashcards", count=1)
    view = service.start_flashcards(deck, context=CONTEXT)
    repo.chunks[0].text = repo.chunks[0].text.replace("Volatile", "Persistent")
    with pytest.raises(PracticeError) as error:
        service.flip_flashcard(view.session_id, card_id=view.card_id, context=CONTEXT)
    assert error.value.code == "SOURCE_CHANGED"
    assert service.sessions.get(view.session_id).revealed is False


def test_internal_resource_tamper_is_caught_by_original_digest_before_reveal():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    stored = service.sessions.get(view.session_id)
    changed = quiz.model_copy(update={"quiz_set_id": "changed-id"})
    service.sessions.replace(replace(stored, quiz=changed))
    with pytest.raises(PracticeError) as error:
        service.submit_quiz(view.session_id, answers(quiz), context=CONTEXT)
    assert error.value.code == "RESOURCE_CHANGED"
    assert service.sessions.get(view.session_id).submission is None


def test_permission_revocation_blocks_existing_session_without_reading_source():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    repo.reads.clear()
    with pytest.raises(PracticeError) as error:
        service.get_quiz(view.session_id, context=context(allowed=frozenset()))
    assert error.value.code == "RESOURCE_NOT_READY" and repo.reads == []


def test_flashcard_flip_shows_back_then_hides_it_again_including_citation_quote():
    repo, deck, service = setup("flashcards")
    front = service.start_flashcards(deck, context=CONTEXT)
    assert isinstance(front, FlashcardFrontView) and front.side == "front"
    assert_hidden(front)
    back = service.flip_flashcard(front.session_id, card_id=front.card_id, context=CONTEXT)
    assert isinstance(back, FlashcardBackView) and back.side == "back"
    assert back.back == deck.cards[0].back and back.source_refs == deck.cards[0].source_refs
    assert service.get_flashcard(front.session_id, context=CONTEXT) == back
    hidden = service.flip_flashcard(front.session_id, card_id=front.card_id, context=CONTEXT)
    assert hidden == front
    assert_hidden(hidden)


def test_navigation_resets_reveal_and_visits_actual_cards_in_both_directions():
    repo, deck, service = setup("flashcards", count=10)
    front = service.start_flashcards(deck, context=CONTEXT)
    service.flip_flashcard(front.session_id, card_id=front.card_id, context=CONTEXT)
    second = service.move_flashcard(front.session_id, "next", card_id=front.card_id, context=CONTEXT)
    assert second.current_index == 1 and second.card_id == deck.cards[1].card_id
    assert second.requested_count == 10 and second.actual_count == 3
    assert_hidden(second)
    again = service.move_flashcard(front.session_id, "previous", card_id=second.card_id, context=CONTEXT)
    assert again.current_index == 0 and again.side == "front"
    assert_hidden(again)


@pytest.mark.parametrize("direction", ["previous", "invalid", None, 0])
def test_invalid_direction_and_boundary_do_not_mutate_flipped_state(direction):
    repo, deck, service = setup("flashcards")
    front = service.start_flashcards(deck, context=CONTEXT)
    back = service.flip_flashcard(front.session_id, card_id=front.card_id, context=CONTEXT)
    with pytest.raises(PracticeError) as error:
        service.move_flashcard(front.session_id, direction, card_id=front.card_id, context=CONTEXT)
    assert error.value.code == ("NAVIGATION_BOUNDARY" if direction == "previous" else "INVALID_DIRECTION")
    assert service.get_flashcard(front.session_id, context=CONTEXT) == back


def test_last_card_boundary_and_single_card_deck_do_not_wrap():
    repo, deck, service = setup("flashcards", count=1)
    view = service.start_flashcards(deck, context=CONTEXT)
    assert view.actual_count == 1
    with pytest.raises(PracticeError) as error:
        service.move_flashcard(view.session_id, "next", card_id=view.card_id, context=CONTEXT)
    assert error.value.code == "NAVIGATION_BOUNDARY"
    assert service.get_flashcard(view.session_id, context=CONTEXT) == view


@pytest.mark.parametrize("action", ["flip", "move"])
def test_stale_card_id_from_old_view_cannot_act_on_new_card(action):
    repo, deck, service = setup("flashcards")
    first = service.start_flashcards(deck, context=CONTEXT)
    second = service.move_flashcard(first.session_id, "next", card_id=first.card_id, context=CONTEXT)
    with pytest.raises(PracticeError) as error:
        if action == "flip":
            service.flip_flashcard(first.session_id, card_id=first.card_id, context=CONTEXT)
        else:
            service.move_flashcard(first.session_id, "next", card_id=first.card_id, context=CONTEXT)
    assert error.value.code == "CARD_MISMATCH"
    assert service.get_flashcard(first.session_id, context=CONTEXT) == second


def test_process_local_shared_repository_serializes_conflicting_submissions():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    second_service = F2PracticeService(repo, sessions=service.sessions)
    def submit(service, submission):
        try:
            return service.submit_quiz(view.session_id, submission, context=CONTEXT)
        except PracticeError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, target, submission) for target, submission in (
            (service, answers(quiz)), (second_service, answers(quiz, correct=False)))]
        results = [f.result() for f in futures]
    assert sum(isinstance(r, QuizPracticeResult) for r in results) == 1
    assert results.count("ALREADY_SUBMITTED") == 1
    assert service.get_quiz_result(view.session_id, context=CONTEXT) in results


def test_isolated_repository_has_no_persistence_or_implicit_shared_sessions():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    isolated = F2PracticeService(repo)
    with pytest.raises(PracticeError) as error:
        isolated.get_quiz(view.session_id, context=CONTEXT)
    assert error.value.code == "SESSION_NOT_FOUND"


def test_learner_models_are_nested_frozen_and_roundtrippable():
    repo, quiz, service = setup()
    view = service.start_quiz(quiz, context=CONTEXT)
    assert QuizPracticeView.model_validate_json(view.model_dump_json()) == view
    with pytest.raises(ValidationError):
        view.questions[0].options[0].text = "tampered"
    result = service.submit_quiz(view.session_id, answers(quiz), context=CONTEXT)
    assert QuizPracticeResult.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError):
        result.items[0].is_correct = False


@pytest.mark.parametrize("kind", ["quiz", "flashcards"])
def test_real_two_document_ingestion_through_generation_validation_and_practice(kind):
    repo = WorkspaceRepository()
    ingestion = DocumentService(repo)
    docs = [ingestion.ingest_file(f"lesson-{i}.txt", text.encode())["document"]
            for i, text in enumerate((TEXT, "Queue: A FIFO structure.\nStack: A LIFO structure."))]
    ids = tuple(d.doc_id for d in docs)
    access = PracticeAccessContext("real-learner", SourceAccessContext("real-workspace", frozenset(ids)))
    prepared = F2SourceService(repo).prepare_sources(StudySourceSelection(
        selected_doc_ids=ids, study_format=kind, requested_count=5), context=access.sources)
    service = F2PracticeService(repo)
    if kind == "quiz":
        quiz = F2QuizService().generate_quiz(prepared).quiz
        view = service.start_quiz(quiz, context=access)
        assert_hidden(view)
        result = service.submit_quiz(view.session_id, answers(quiz), context=access)
        assert result.total_count == 5 and result.score_percent == 100
        assert {r.doc_id for item in result.items for r in item.source_refs} == set(ids)
    else:
        deck = F2FlashcardService().generate_flashcards(prepared).deck
        view = service.start_flashcards(deck, context=access)
        for i, card in enumerate(deck.cards):
            assert_hidden(view)
            back = service.flip_flashcard(view.session_id, card_id=view.card_id, context=access)
            assert back.back == card.back and back.source_refs == card.source_refs
            if i < 4:
                view = service.move_flashcard(view.session_id, "next", card_id=view.card_id, context=access)


@pytest.mark.parametrize("questions,submitted,code", [
    ((), (), "INVALID_QUIZ"),
    ((("q1", ("A",), "A"),), (), "INVALID_QUIZ"),
    ((("q1", ("A", "B"), "C"),), (), "INVALID_QUIZ"),
    ((("q1", ("A", "A"), "A"),), (), "INVALID_QUIZ"),
    ((("q1", ("A", "B"), "A"), ("q1", ("A", "B"), "B")), (), "INVALID_QUIZ"),
    ((("q1", ("A", "B"), "A"),), (("q1", "A"), ("q1", "B")), "DUPLICATE_ANSWER"),
    ((("q1", ("A", "B"), "A"),), (("q2", "A"),), "UNKNOWN_QUESTION"),
    ((("q1", ("A", "B"), "A"),), (("q1", "C"),), "UNKNOWN_OPTION"),
])
def test_grading_algorithm_rejects_invalid_keys_ids_and_repeated_answers(questions, submitted, code):
    with pytest.raises(QuizGradingError) as error:
        grade_single_choice(questions, submitted)
    assert error.value.code == code


def test_grading_algorithm_stdlib_isolation_and_purity():
    tree = ast.parse(Path("backend/algorithms/f2_quiz_grading.py").read_text(encoding="utf-8"))
    roots = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    roots |= {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert roots <= sys.stdlib_module_names
    assert not roots & {"os", "pathlib", "socket", "subprocess", "urllib", "http"}
    code = """
import sys
from backend.algorithms.f2_quiz_grading import grade_single_choice
grade = grade_single_choice((("q", ("A", "B"), "A"),), (("q", "A"),))
assert grade.score_percent == 100.0
assert not any(n in sys.modules for n in ('pydantic', 'fastapi', 'httpx', 'numpy'))
print('Q06_STDLIB_ISOLATION_PASS')
"""
    result = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Q06_STDLIB_ISOLATION_PASS" in result.stdout
