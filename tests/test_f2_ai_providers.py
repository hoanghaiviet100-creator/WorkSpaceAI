"""Gemini wire protocol and UI integration. HTTP is simulated only in tests."""
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.proto.TextInput_pb2 import TextInput

from backend.core.config import settings
from backend.core.f2_study_schemas import SourceRef, StudySourceSelection
from backend.providers.f2_gemini_provider import GeminiFlashcardProvider, GeminiQuizProvider
from backend.providers.f2_study_provider import MAX_STUDY_RESPONSE_BYTES, StudyEvidence, StudyProviderError
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services.f2_flashcard_service import F2FlashcardService
from backend.services.f2_practice_service import F2PracticeService, PracticeAccessContext, PracticeError
from backend.services.f2_quiz_service import F2QuizService
from backend.services.f2_source_service import F2SourceService, SourceAccessContext


KEY = "unit-test-key-not-a-real-credential"
MODEL = "gemini-test-model"
TEXT = "Cache: Fast temporary memory.\nRAM: Volatile working storage."
APP = Path(__file__).resolve().parents[1] / "frontend/f2_manual_app.py"


def draft(study_format="quiz", **changes):
    if study_format == "quiz":
        return {"question": "Khái niệm nào được mô tả sau đây?\nFast temporary memory.",
            "options": [{"option_id": "A", "text": "Cache"}, {"option_id": "B", "text": "RAM"}],
            "correct_option_id": "A", "explanation": "Theo đoạn nguồn, Cache: Fast temporary memory.",
            "source_ids": ["S1"], **changes}
    return {"front": "Cache là gì?", "back": "Fast temporary memory.", "source_ids": ["S1"], **changes}


def inner(study_format="quiz", **changes):
    return json.dumps({"questions" if study_format == "quiz" else "cards": [draft(study_format, **changes)]}, ensure_ascii=False)


def response(raw=None, reason="STOP"):
    return {"candidates": [{"finishReason": reason, "content": {"role": "model", "parts": [{"text": inner() if raw is None else raw}]}}]}


def evidence():
    return (StudyEvidence("S1", "definition", SourceRef(doc_id="lecture", doc_version="v1", doc_hash="a" * 64,
        page_number=1, chunk_id="chunk-1", start_line=1, end_line=1, evidence_quote="Cache: Fast temporary memory.")),)


@pytest.mark.parametrize("provider_type,study_format,root", [
    (GeminiQuizProvider, "quiz", "questions"), (GeminiFlashcardProvider, "flashcards", "cards"),
])
def test_gemini_fixed_origin_header_json_schema_timeouts_and_original_wire_output(provider_type, study_format, root):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response(inner(study_format)))
    provider = provider_type(KEY, MODEL, transport=httpx.MockTransport(handler))
    assert requests == []  # configuration does not call the network
    raw = provider.generate(evidence(), 10)
    assert raw == inner(study_format)
    request = requests[0]
    assert len(requests) == 1 and request.method == "POST"
    assert str(request.url) == f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    assert request.headers["x-goog-api-key"] == KEY
    assert KEY not in str(request.url) and KEY not in repr(provider)
    payload = json.loads(request.content)
    assert KEY not in json.dumps(payload)
    config = payload["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"]["required"] == [root]
    assert config["responseJsonSchema"]["additionalProperties"] is False
    assert request.extensions["timeout"]["read"] == 60 and request.extensions["timeout"]["connect"] == 2
    prompt = payload["contents"][0]["parts"][0]["text"]
    assert "<untrusted_document_data" in prompt and "[Dòng 1] Cache: Fast temporary memory." in prompt
    assert "Giới hạn của phiên thử Q05" in prompt and "Không dịch" in prompt


@pytest.mark.parametrize("key", [None, "", "  ", "your_gemini_api_key_here", "key\nvalue", "key value"])
def test_missing_or_invalid_key_is_rejected_before_network(key):
    with pytest.raises(StudyProviderError) as error:
        GeminiQuizProvider(key)
    assert error.value.code == "PROVIDER_NOT_CONFIGURED"
    assert str(key) not in str(error.value) or key in (None, "")


@pytest.mark.parametrize("model", [None, "", "model name", "models/gemini", "gemini?key=secret", "../model"])
def test_model_cannot_modify_api_origin_path_or_auth(model):
    with pytest.raises(StudyProviderError) as error:
        GeminiQuizProvider(KEY, model)
    assert error.value.code == "PROVIDER_CONFIGURATION_INVALID"


@pytest.mark.parametrize("status,code", [
    (400, "PROVIDER_REQUEST_REJECTED"), (401, "PROVIDER_AUTH_FAILED"), (403, "PROVIDER_AUTH_FAILED"),
    (404, "PROVIDER_MODEL_NOT_FOUND"), (429, "PROVIDER_RATE_LIMITED"),
    (500, "PROVIDER_UNAVAILABLE"), (302, "PROVIDER_REQUEST_REJECTED"),
])
def test_http_errors_are_sanitized_without_retry_redirect_or_fallback(status, code):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"location": "https://example.invalid/leak"}, text=KEY)
    provider = GeminiQuizProvider(KEY, MODEL, transport=httpx.MockTransport(handler))
    with pytest.raises(StudyProviderError) as error:
        provider.generate(evidence(), 10)
    assert error.value.code == code and len(calls) == 1
    assert KEY not in str(error.value)


@pytest.mark.parametrize("exception,code", [(httpx.ReadTimeout, "PROVIDER_TIMEOUT"), (httpx.ConnectError, "PROVIDER_UNAVAILABLE")])
def test_transport_failures_have_recoverable_errors(exception, code):
    def handler(request):
        raise exception(KEY, request=request)
    with pytest.raises(StudyProviderError) as error:
        GeminiQuizProvider(KEY, MODEL, transport=httpx.MockTransport(handler)).generate(evidence(), 10)
    assert error.value.code == code and KEY not in str(error.value)


@pytest.mark.parametrize("data,code", [
    ({"promptFeedback": {"blockReason": "SAFETY"}}, "PROVIDER_BLOCKED"),
    (response(reason="SAFETY"), "PROVIDER_BLOCKED"),
    (response(reason="RECITATION"), "PROVIDER_BLOCKED"),
    (response(reason="MAX_TOKENS"), "PROVIDER_RESPONSE_INCOMPLETE"),
    (response(reason=None), "PROVIDER_RESPONSE_INCOMPLETE"),
    ({}, "PROVIDER_RESPONSE_INVALID"),
    ({"candidates": []}, "PROVIDER_RESPONSE_INVALID"),
    ({"candidates": [response()["candidates"][0]] * 2}, "PROVIDER_RESPONSE_INVALID"),
    ({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"functionCall": {}}]}}]}, "PROVIDER_RESPONSE_INVALID"),
    (response(raw=" "), "PROVIDER_RESPONSE_INVALID"),
])
def test_incomplete_blocked_or_malformed_outer_responses_are_never_used(data, code):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=data))
    with pytest.raises(StudyProviderError) as error:
        GeminiQuizProvider(KEY, MODEL, transport=transport).generate(evidence(), 10)
    assert error.value.code == code


def test_response_size_is_bounded_before_accumulation_and_invalid_json_is_rejected():
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"x" * (MAX_STUDY_RESPONSE_BYTES + 1)
    for reply, code in [(httpx.Response(200, stream=Stream()), "PROVIDER_RESPONSE_TOO_LARGE"),
                        (httpx.Response(200, content=b"not-json"), "PROVIDER_RESPONSE_INVALID")]:
        transport = httpx.MockTransport(lambda request: reply)
        with pytest.raises(StudyProviderError) as error:
            GeminiQuizProvider(KEY, MODEL, transport=transport).generate(evidence(), 10)
        assert error.value.code == code


def test_thought_parts_are_not_treated_as_learning_output_and_text_parts_are_joined():
    data = response()
    raw = inner()
    data["candidates"][0]["content"]["parts"] = [
        {"thought": True, "text": "private reasoning"}, {"text": raw[:20]}, {"text": raw[20:]},
    ]
    provider = GeminiQuizProvider(KEY, MODEL, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data)))
    assert provider.generate(evidence(), 1) == raw


def sources(study_format):
    repo = WorkspaceRepository()
    document = DocumentService(repo).ingest_file("lesson.txt", TEXT.encode())["document"]
    context = PracticeAccessContext("learner", SourceAccessContext("workspace", frozenset({document.doc_id})))
    prepared = F2SourceService(repo).prepare_sources(StudySourceSelection(
        selected_doc_ids=[document.doc_id], study_format=study_format, requested_count=1), context=context.sources)
    return repo, context, prepared


@pytest.mark.parametrize("study_format", ["quiz", "flashcards"])
def test_real_ingestion_gemini_adapter_q05_q06_integration_with_simulated_http(study_format):
    repo, context, prepared = sources(study_format)
    provider_type = GeminiQuizProvider if study_format == "quiz" else GeminiFlashcardProvider
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response(inner(study_format))))
    provider = provider_type(KEY, MODEL, transport=transport)
    generation = (F2QuizService(provider).generate_quiz(prepared) if study_format == "quiz"
                  else F2FlashcardService(provider).generate_flashcards(prepared))
    assert generation.provider_name == "gemini" and generation.status == "COMPLETE"
    practice = F2PracticeService(repo)
    view = (practice.start_quiz(generation.quiz, context=context) if study_format == "quiz"
            else practice.start_flashcards(generation.deck, context=context))
    assert view.actual_count == 1
    assert "source_refs" not in view.model_dump_json() and "correct_option_id" not in view.model_dump_json()


@pytest.mark.parametrize("study_format,changes", [
    ("quiz", {"correct_option_id": "B"}), ("flashcards", {"back": "Unsupported fabricated answer."}),
])
def test_q05_blocks_invalid_ai_support_even_with_valid_gemini_json(study_format, changes):
    repo, context, prepared = sources(study_format)
    provider_type = GeminiQuizProvider if study_format == "quiz" else GeminiFlashcardProvider
    provider = provider_type(KEY, MODEL, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response(inner(study_format, **changes)))))
    practice = F2PracticeService(repo)
    with pytest.raises(PracticeError) as error:
        if study_format == "quiz":
            practice.start_quiz(F2QuizService(provider).generate_quiz(prepared).quiz, context=context)
        else:
            practice.start_flashcards(F2FlashcardService(provider).generate_flashcards(prepared).deck, context=context)
    assert error.value.code == "RESOURCE_NOT_READY"


def test_api_auth_failure_remains_gemini_error_in_generation_without_offline_fallback():
    repo, context, prepared = sources("quiz")
    provider = GeminiQuizProvider(KEY, MODEL, transport=httpx.MockTransport(lambda request: httpx.Response(403, text=KEY)))
    result = F2QuizService(provider).generate_quiz(prepared)
    assert result.provider_name == "gemini" and result.status == "ERROR" and result.quiz is None
    assert [i.code for i in result.issues] == ["PROVIDER_AUTH_FAILED"]
    assert KEY not in str(result.issues)


def ui():
    at = AppTest.from_file(str(APP), default_timeout=20).run()
    runtime = at.session_state["f2_manual_runtime"]
    doc = runtime["ingestion"].ingest_file("lesson.txt", TEXT.encode())["document"]
    at.run()
    at.multiselect(key="f2_manual_selected").select(doc.doc_id).run()
    at.number_input(key="f2_manual_count").set_value(1).run()
    at.selectbox(key="f2_manual_engine").set_value("Gemini").run()
    assert not at.exception
    return at


def test_ui_missing_key_blocks_generation_and_password_is_not_a_validity_claim():
    with patch.object(settings, "gemini_api_key", ""):
        at = ui()
        assert at.button(key="f2_manual_generate").disabled
        assert at.text_input(key="f2_manual_gemini_key").proto.type == TextInput.PASSWORD
        at.text_input(key="f2_manual_gemini_key").set_value(KEY).run()
        assert not at.button(key="f2_manual_generate").disabled
        assert any("chưa xác nhận" in c.value for c in at.caption)


@pytest.mark.parametrize("status", [200, 403])
def test_ui_uses_selected_real_adapter_and_reports_actual_model_or_failure(status):
    def factory(api_key, model):
        return GeminiQuizProvider(api_key, model, transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json=response() if status == 200 else {"error": KEY})))
    with patch.object(settings, "gemini_api_key", ""), patch(
        "frontend.components.f2_manual_panel.GeminiQuizProvider", side_effect=factory):
        at = ui()
        at.text_input(key="f2_manual_gemini_key").set_value(KEY).run()
        at.text_input(key="f2_manual_gemini_model").set_value(MODEL).run()
        at.button(key="f2_manual_generate").click().run()
        assert not at.exception
        assert any(f"gemini · model yêu cầu: {MODEL}" in item.value for item in at.info)
        assert all(KEY not in item.value for item in [*at.info, *at.warning, *at.error])
        if status == 200:
            assert at.form
        else:
            assert not at.form and at.session_state["f2_manual_active"] is None
            assert any("API key" in item.value for item in at.warning)
