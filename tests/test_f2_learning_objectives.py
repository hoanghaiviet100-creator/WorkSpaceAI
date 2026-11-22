"""R3/R4/R6/R7/R8 PDF -> goals -> controlled LLM HTTP -> Q05 -> Q06.

HTTP responses are explicit evaluation candidates, not a live model run or
human review. The same provider/parser/validator/practice pipeline serves all
three topics and both formats; only the source and response candidates vary.
"""
from copy import deepcopy
from dataclasses import asdict
import json

import httpx
import pytest

from backend.algorithms.f2_content_support import (
    CARD_CLOZE_PREFIX, QUIZ_CLOZE_PREFIX, build_learning_objectives,
    validate_flashcard_content_support, validate_quiz_content_support,
)
from backend.algorithms.f2_source_extraction import extract_contextual_study_spans, extract_study_spans
from backend.algorithms.f2_study_validation import validate_quiz_support
from backend.core.f2_study_schemas import QuizSet, StudySourceSelection
from backend.core.f2_practice_schemas import QuizSubmission
from backend.providers.f2_gemini_provider import GeminiFlashcardProvider, GeminiQuizProvider
from backend.providers.f2_source_content_provider import SourceContentProvider, build_source_content_prompt
from backend.providers.f2_study_provider import StudyEvidence
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services.f2_flashcard_service import F2FlashcardService
from backend.services.f2_practice_service import F2PracticeService, PracticeAccessContext, PracticeError
from backend.services.f2_quiz_service import F2QuizService
from backend.services.f2_source_service import F2SourceService, SourceAccessContext
from backend.services.f2_study_validation_service import F2StudyValidationService
from f2_learning_samples import FIXTURES, samples


TOPICS = ("concepts", "procedure", "rules")
HEADINGS = {"concepts": "Concepts: Processing models", "procedure": "Procedure: Sample intake", "rules": "Rule: Cold-chain intake"}


def pipeline(topic="rules", study_format="quiz", transform=None):
    repository = WorkspaceRepository()
    ingestion = DocumentService(repository)
    path = FIXTURES / (topic + ".pdf")
    document = ingestion.ingest_file(path.name, path.read_bytes())["document"]
    context = SourceAccessContext("pdf-evaluation", frozenset({document.doc_id}))
    selection = StudySourceSelection(selected_doc_ids=[document.doc_id], study_format=study_format,
        requested_count=5 if study_format == "quiz" else 3)
    prepared = F2SourceService(repository).prepare_sources(selection, context=context)
    source_id = next(f"S{i}" for i, p in enumerate(prepared.passages, 1)
        if p.text.startswith(HEADINGS[topic] + "\n"))
    quiz, cards = samples(topic, source_id)
    payload = quiz if study_format == "quiz" else cards
    if transform:
        transform(payload)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"role": "model",
            "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]})
    provider_type = GeminiQuizProvider if study_format == "quiz" else GeminiFlashcardProvider
    provider = SourceContentProvider(provider_type("unit-test-not-real-key", transport=httpx.MockTransport(handler)), study_format)
    generated = (F2QuizService(provider).generate_quiz(prepared) if study_format == "quiz"
                 else F2FlashcardService(provider).generate_flashcards(prepared))
    resource = generated.quiz if study_format == "quiz" else generated.deck
    assert resource is not None
    validator = F2StudyValidationService(repository)
    validate = validator.validate_quiz if study_format == "quiz" else validator.validate_flashcards
    receipt = validate(resource, workspace_id=context.workspace_id, context=context)
    return repository, context, prepared, generated, resource, receipt, calls


@pytest.mark.parametrize("topic", TOPICS)
@pytest.mark.parametrize("study_format", ("quiz", "flashcards"))
def test_same_pipeline_three_real_text_pdfs_generates_and_verifies_both_formats(topic, study_format):
    repository, context, prepared, generated, resource, receipt, calls = pipeline(topic, study_format)
    assert len(calls) == 1 and generated.status == "COMPLETE"
    assert receipt.release_ready and receipt.method == "EXTRACTIVE_STUDY_V2"
    items = resource.questions if study_format == "quiz" else resource.cards
    assert len(items) == (5 if study_format == "quiz" else 3)
    prompts = [i.question if study_format == "quiz" else i.front for i in items]
    assert sum(p.startswith("Hiểu:") for p in prompts) >= 1
    assert sum(p.startswith("Vận dụng:") for p in prompts) >= 1
    if study_format == "quiz":
        assert [p.split(":", 1)[0] for p in prompts] == ["Nhớ", "Hiểu", "Hiểu", "Vận dụng", "Vận dụng"]
    else:
        assert all(len(i.back.split()) <= 60 for i in items)
    chunks = repository.get_document_chunks(prepared.selection.selected_doc_ids[0])
    for item in items:
        for ref in item.source_refs:
            chunk = next(c for c in chunks if c.chunk_id == ref.chunk_id)
            assert ref.page_number == 1 and ref.doc_hash == repository.documents[ref.doc_id].file_hash
            assert ref.evidence_quote == "\n".join(chunk.text.splitlines()[ref.start_line - chunk.start_line:ref.end_line - chunk.start_line + 1])
            assert ref.verification_status == "UNVERIFIED"
    service = F2PracticeService(repository)
    access = PracticeAccessContext("fixture-learner", context)
    if study_format == "quiz":
        view = service.start_quiz(resource, context=access)
        public = view.model_dump_json()
        assert "correct_option_id" not in public and "explanation" not in public and "source_refs" not in public
        assert "evidence_quote" not in public
        result = service.submit_quiz(view.session_id, QuizSubmission(answers=[
            {"question_id": q.question_id, "option_id": q.correct_option_id} for q in resource.questions]), context=access)
        assert result.correct_count == result.total_count == 5
        assert all(i.source_refs and i.explanation for i in result.items)
    else:
        view = service.start_flashcards(resource, context=access)
        for index in range(3):
            assert "back" not in view.model_dump() and "source_refs" not in view.model_dump()
            back = service.flip_flashcard(view.session_id, card_id=view.card_id, context=access)
            assert back.back == resource.cards[index].back and back.source_refs
            if index < 2:
                view = service.move_flashcard(view.session_id, "next", card_id=view.card_id, context=access)


@pytest.mark.parametrize("topic", TOPICS)
def test_q02_shared_objectives_and_heading_context_are_identical_for_quiz_and_cards(topic):
    _, _, quiz_sources, _, _, _, quiz_calls = pipeline(topic)
    _, _, card_sources, _, _, _, card_calls = pipeline(topic, "flashcards")
    assert quiz_sources.learning_objectives == card_sources.learning_objectives
    assert quiz_sources.learning_objectives
    for sources, calls in ((quiz_sources, quiz_calls), (card_sources, card_calls)):
        body = json.loads(calls[0].content)
        prompt = body["contents"][0]["parts"][0]["text"]
        assert "learning_objectives" in prompt and "Cloze là style riêng" in prompt
        for goal in sources.learning_objectives:
            assert goal.title in prompt and all(source_id in prompt for source_id in goal.source_ids)


def test_pdf_fixture_demonstrates_original_q02_heading_detachment_and_context_fix():
    repository, _, prepared, _, _, _, _ = pipeline("procedure")
    chunk = repository.chunks[0]
    old = extract_study_spans(chunk.text)
    procedure = next(p for p in old if p.kind.value == "procedure")
    assert "Sample intake" not in procedure.text
    context = next(p for p in extract_contextual_study_spans(chunk.text) if p.text.startswith("Procedure: Sample intake\n"))
    assert context.start_line == 1 and context.end_line == 6
    assert context.text == "\n".join(chunk.text.splitlines()[:6])
    assert prepared.learning_objectives[0].kind == "procedure"


def test_fnd04_old_template_gate_abstained_but_new_rule_proof_accepts_novel_data():
    _, _, prepared, _, quiz, receipt, _ = pipeline()
    item = quiz.questions[3]
    quote = item.source_refs[0].evidence_quote
    assert "7 C" not in quote and "9 C" not in quote  # new scenario data, source supplies rule at 8 C
    sources = (("S1", quote),)
    old = validate_quiz_support(item.question, tuple((o.option_id, o.text) for o in item.options), item.correct_option_id,
        item.explanation, sources, sources)
    assert old.status == "REVIEW_REQUIRED"
    assert receipt.items[3].support_status == "SUPPORTED"


@pytest.mark.parametrize("question", [
    "Vận dụng: This function returns true. What should the user do?",
    QUIZ_CLOZE_PREFIX + "\nTo use this function, you must include the [___] header file.",
])
def test_missing_this_function_subject_is_held_for_review(question):
    quote = '• Reads characters into a string.\n• To use this function, you must include the <string> header file.'
    result = validate_quiz_content_support(question, (("A", "<string>"), ("B", "<fstream>")), "A",
        "Theo đoạn nguồn: To use this function, you must include the <string> header file.", (("S1", quote),), (("S1", quote),))
    assert result.status == "REVIEW_REQUIRED" and result.code == "MISSING_SUBJECT"


@pytest.mark.parametrize("study_format", ("quiz", "flashcards"))
def test_cloze_complete_bullet_with_subject_is_independent_of_learning_mode(study_format):
    quote = '• The std::getline function reads characters from a stream.\n• The std::getline function requires the <string> header file.'
    context = 'The std::getline function requires the [___] header file.'
    sources = (("S1", quote),)
    if study_format == "quiz":
        result = validate_quiz_content_support(QUIZ_CLOZE_PREFIX + "\n" + context,
            (("A", "<string>"), ("B", "<fstream>")), "A",
            "Theo đoạn nguồn: " + context.replace("[___]", "<string>"), sources, sources)
    else:
        result = validate_flashcard_content_support(CARD_CLOZE_PREFIX + "\n" + context, "<string>", sources, sources)
    assert result.status == "SUPPORTED"
    assert validate_quiz_content_support(QUIZ_CLOZE_PREFIX + "\nrequires the [___] header file.",
        (("A", "<string>"), ("B", "<fstream>")), "A", "partial", sources, sources).status == "REVIEW_REQUIRED"


@pytest.mark.parametrize("case", ("missing_data", "missing_unit", "wrong_condition", "two_answers", "locator_only"))
def test_review_negative_cases_with_real_pdf_and_valid_source_locators(case):
    def transform(payload):
        if case == "missing_data":
            payload["questions"][3]["question"] = payload["questions"][3]["question"].replace("; seal = intact", "")
        elif case == "missing_unit":
            payload["questions"][3]["question"] = payload["questions"][3]["question"].replace("7 C", "7")
        elif case == "wrong_condition":
            payload["questions"][3]["explanation"] = payload["questions"][3]["explanation"].replace(" and seal is intact", "")
        elif case == "two_answers":
            payload["questions"][1]["options"][1]["text"] = "temperature <= 8 C and seal = intact"
        else:
            payload["questions"][3]["source_ids"] = ["S1"]  # true heading locator, no supporting rule
    repository, context, _, _, quiz, receipt, _ = pipeline(transform=transform)
    assert receipt.status == "REVIEW_REQUIRED" and not receipt.release_ready
    index = 1 if case == "two_answers" else 3
    assert receipt.items[index].source_status == "MATCHED" and receipt.items[index].support_status == "REVIEW_REQUIRED"
    with pytest.raises(PracticeError):
        F2PracticeService(repository).start_quiz(quiz, context=PracticeAccessContext("fixture-learner", context))


@pytest.mark.parametrize("temperature,expected", [("8", "Accept"), ("8.01", "Reject"), ("-2", "Accept")])
def test_rule_boundary_and_new_values_use_comparisons_without_arithmetic_solver(temperature, expected):
    def transform(payload):
        item = payload["questions"][3]
        item["question"] = item["question"].replace("7 C", temperature + " C")
        rule = ('If temperature is at most 8 C and seal is intact, then choose "Accept".' if expected == "Accept"
                else 'If temperature is above 8 C, then choose "Reject".')
        item["correct_option_id"] = "A" if expected == "Accept" else "B"
        item["explanation"] = f'Dữ kiện: temperature = {temperature} C; seal = intact.\nÁp dụng: {rule}\nKết luận: {expected}.'
    _, _, _, _, _, receipt, _ = pipeline(transform=transform)
    assert receipt.release_ready


def test_question_and_flashcard_wrong_condition_both_stay_review():
    def transform(payload):
        payload["cards"][2]["back"] = payload["cards"][2]["back"].replace(" and seal is intact", "")
    _, _, _, _, _, receipt, _ = pipeline(study_format="flashcards", transform=transform)
    assert receipt.status == "REVIEW_REQUIRED"


def test_cloze_is_explicit_style_and_learning_style_targets_five_and_three():
    _, _, prepared, _, _, _, _ = pipeline()
    evidence = tuple(StudyEvidence(f"S{i}", p.kind.value, p.source_ref) for i, p in enumerate(prepared.passages, 1))
    quiz = build_source_content_prompt(evidence, 5, "quiz")
    cards = build_source_content_prompt(evidence, 3, "flashcards")
    assert "1 nhớ, 2 hiểu, 2 vận dụng" in quiz and "1 nhớ, 1 hiểu, 1 vận dụng" in cards
    assert "ưu tiên dạng điền nguyên văn" not in quiz + cards
    assert "ưu tiên dạng điền nguyên văn" in build_source_content_prompt(evidence, 5, "quiz", style="cloze")
    assert "Điền nguyên văn theo đoạn trích:" in build_source_content_prompt(evidence, 5, "quiz", style="cloze")


@pytest.mark.parametrize("name,field,limit,unit,low,high", [
    ("Print dispatch", "pages", "20", "pages", "13", "21"),
    ("Archive handling", "retention", "6", "months", "2", "7"),
])
def test_unseen_rule_topics_and_predicate_names_are_data_not_fixture_specific(name, field, limit, unit, low, high):
    quote = (f'Rule: {name}\nIf {field} is at most {limit} {unit}, then choose "Routine".\n'
             f'If {field} is above {limit} {unit}, then choose "Escalate".')
    for value, answer, predicate in ((low, "Routine", "is at most"), (high, "Escalate", "is above")):
        question = f'Vận dụng: Theo quy tắc "{name}", tình huống "New-case" có dữ kiện: {field} = {value} {unit}. Kết quả nào được áp dụng?'
        explanation = f'Dữ kiện: {field} = {value} {unit}.\nÁp dụng: If {field} {predicate} {limit} {unit}, then choose "{answer}".\nKết luận: {answer}.'
        result = validate_quiz_content_support(question, (("A", "Routine"), ("B", "Escalate")),
            "A" if answer == "Routine" else "B", explanation, (("S9", quote),), (("S9", quote),))
        assert result.status == "SUPPORTED"


@pytest.mark.parametrize("extra", [
    'If temperature is at most 8 C, then choose "Reject".',
    'Unless approval is present, choose "Reject".',
    'If temperature is below 10 K, then choose "Accept".',
])
def test_conflicting_rules_unsupported_exceptions_or_mixed_units_do_not_gain_support(extra):
    _, _, _, _, quiz, _, _ = pipeline()
    item = quiz.questions[3]
    source = item.source_refs[0].evidence_quote + "\n" + extra
    result = validate_quiz_content_support(item.question, tuple((o.option_id, o.text) for o in item.options), "A",
        item.explanation, (("S1", source),), (("S1", source),))
    assert result.status == "REVIEW_REQUIRED"


def test_conflict_in_uncited_selected_context_still_blocks_procedure():
    _, _, _, _, quiz, _, _ = pipeline("procedure")
    item = quiz.questions[1]
    quote = item.source_refs[0].evidence_quote
    conflict = quote.replace("2. Assign a tracking code.", "2. Confirm the inventory entry.")
    result = validate_quiz_content_support(item.question, tuple((o.option_id, o.text) for o in item.options), "A", item.explanation,
        (("S1", quote),), (("S1", quote), ("S2", conflict)))
    assert result.status == "REVIEW_REQUIRED"


def test_other_prose_has_shared_goals_but_does_not_falsely_pass_semantic_support():
    sources = (("S1", "Plant roots transport water through several tissues."),)
    goals = build_learning_objectives(sources)
    assert goals and goals[0].kind == "source_understanding" and goals[0].source_ids == ("S1",)
    result = validate_quiz_content_support("Hiểu: Vì sao cây cần nước?", (("A", "A reason"), ("B", "Another reason")), "A",
        "An unsupported explanation.", sources, sources)
    assert result.status == "REVIEW_REQUIRED"


def test_partial_bullet_cannot_drop_its_continuation_condition():
    quote = '• The action accepts a sample\nonly when approval is present.\n• Another action rejects it.'
    result = validate_quiz_content_support(QUIZ_CLOZE_PREFIX + "\nThe action accepts a [___].",
        (("A", "sample"), ("B", "record")), "A", "Theo đoạn nguồn: The action accepts a sample.", (("S1", quote),), (("S1", quote),))
    assert result.status == "REVIEW_REQUIRED"


def test_definition_lookup_preserves_wrapped_qualifiers():
    sources = (("S1", "Gate: Requests are accepted\nonly when approval is present."), ("S2", "Queue: Requests wait for review."))
    question = 'Nhớ: Theo tài liệu, "Gate" là gì?'
    dropped = validate_quiz_content_support(question,
        (("A", "Requests are accepted"), ("B", "Requests wait for review.")), "A",
        "Theo nguồn: Gate: Requests are accepted", sources[:1], sources)
    assert dropped.status == "REVIEW_REQUIRED"
    complete = "Requests are accepted only when approval is present."
    supported = validate_quiz_content_support(question,
        (("A", complete), ("B", "Requests wait for review.")), "A", "Theo nguồn: Gate: " + complete, sources[:1], sources)
    assert supported.status == "SUPPORTED"


@pytest.mark.parametrize("line", [
    'If temperature is above 8 C, then choose "Reject".',
    'If seal is broken, then choose "Reject".',
])
def test_two_active_rules_with_same_outcome_allow_either_valid_derivation(line):
    _, _, _, _, quiz, _, _ = pipeline()
    item = quiz.questions[3]
    quote = item.source_refs[0].evidence_quote
    question = item.question.replace("7 C; seal = intact", "9 C; seal = broken")
    explanation = f'Dữ kiện: temperature = 9 C; seal = broken.\nÁp dụng: {line}\nKết luận: Reject.'
    result = validate_quiz_content_support(question, (("A", "Reject"), ("B", "Accept")), "A",
        explanation, (("S1", quote),), (("S1", quote),))
    assert result.status == "SUPPORTED"
