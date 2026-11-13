"""NVIDIA NIM HTTP contract and real F2/UI integration; no live key/model."""
import json
import os
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from streamlit.proto.TextInput_pb2 import TextInput
from streamlit.testing.v1 import AppTest

from backend.core.config import settings
from backend.core.f2_study_schemas import SourceRef, StudySourceSelection
from backend.providers.f2_nvidia_nim_provider import NvidiaNimFlashcardProvider, NvidiaNimQuizProvider
from backend.providers.f2_study_provider import MAX_STUDY_RESPONSE_BYTES, StudyEvidence, StudyProviderError
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services.f2_flashcard_service import F2FlashcardService
from backend.services.f2_practice_service import F2PracticeService, PracticeAccessContext, PracticeError
from backend.services.f2_quiz_service import F2QuizService
from backend.services.f2_source_service import F2SourceService, SourceAccessContext


KEY = "nvapi-unit-test-not-a-real-credential"
MODEL = "vendor/test-model"
TEXT = "Cache: Fast temporary memory.\nRAM: Volatile working storage."
APP = Path(__file__).resolve().parents[1] / "frontend/f2_manual_app.py"


def inner(kind="quiz", **changes):
    if kind == "quiz":
        item = {"question": "Khái niệm nào được mô tả sau đây?\nFast temporary memory.",
            "options": [{"option_id": "A", "text": "Cache"}, {"option_id": "B", "text": "RAM"}],
            "correct_option_id": "A", "explanation": "Theo đoạn nguồn, Cache: Fast temporary memory.",
            "source_ids": ["S1"], **changes}
        return json.dumps({"questions": [item]}, ensure_ascii=False)
    return json.dumps({"cards": [{"front": "Cache là gì?", "back": "Fast temporary memory.",
        "source_ids": ["S1"], **changes}]}, ensure_ascii=False)


def reply(raw=None, reason="stop", **message_changes):
    return {"choices": [{"finish_reason": reason, "message": {
        "role": "assistant", "content": inner() if raw is None else raw, **message_changes}}]}


def evidence():
    return (StudyEvidence("S1", "definition", SourceRef(doc_id="lesson", doc_version="v1", doc_hash="a" * 64,
        page_number=1, chunk_id="c1", start_line=1, end_line=1, evidence_quote="Cache: Fast temporary memory.")),)


@pytest.mark.parametrize("provider_type,kind", [(NvidiaNimQuizProvider, "quiz"), (NvidiaNimFlashcardProvider, "flashcards")])
def test_nim_fixed_endpoint_bearer_auth_documented_payload_timeouts_and_no_eager_request(provider_type, kind):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=reply(inner(kind)))
    provider = provider_type(KEY, MODEL, transport=httpx.MockTransport(handler))
    assert requests == []
    assert provider.generate(evidence(), 10) == inner(kind)
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST" and str(request.url) == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert "x-goog-api-key" not in request.headers and KEY not in str(request.url) and KEY not in repr(provider)
    payload = json.loads(request.content)
    assert payload["model"] == MODEL and payload["stream"] is False and payload["max_tokens"] == 4096
    assert "response_format" not in payload  # not assumed supported by every hosted model
    assert KEY not in json.dumps(payload)
    assert request.extensions["timeout"]["connect"] == 2 and request.extensions["timeout"]["read"] == 60
    prompt = payload["messages"][0]["content"]
    assert "<untrusted_document_data" in prompt and "[Dòng 1] Cache:" in prompt
    assert "Giới hạn của phiên thử Q05" in prompt and "Không dịch" in prompt


@pytest.mark.parametrize("key", [None, "", "   ", "your_nvidia_api_key_here", "Bearer secret", "key\nvalue"])
def test_invalid_nim_key_is_rejected_without_network(key):
    with pytest.raises(StudyProviderError) as error:
        NvidiaNimQuizProvider(key)
    assert error.value.code == "PROVIDER_NOT_CONFIGURED"


@pytest.mark.parametrize("model", [None, "", "https://host/model", "../model", "model name", "a/b/c"])
def test_invalid_model_is_rejected_before_request(model):
    with pytest.raises(StudyProviderError) as error:
        NvidiaNimQuizProvider(KEY, model)
    assert error.value.code == "PROVIDER_CONFIGURATION_INVALID"


@pytest.mark.parametrize("status,code", [
    (401, "PROVIDER_AUTH_FAILED"), (403, "PROVIDER_AUTH_FAILED"), (404, "PROVIDER_MODEL_NOT_FOUND"),
    (429, "PROVIDER_RATE_LIMITED"), (422, "PROVIDER_REQUEST_REJECTED"),
    (500, "PROVIDER_UNAVAILABLE"), (302, "PROVIDER_REQUEST_REJECTED"),
    (202, "PROVIDER_RESPONSE_PENDING"), (204, "PROVIDER_RESPONSE_INVALID"),
])
def test_http_errors_pending_or_redirect_do_not_echo_key_retry_poll_or_fallback(status, code):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=KEY, headers={"location": "https://example.invalid/leak"})
    with pytest.raises(StudyProviderError) as error:
        NvidiaNimQuizProvider(KEY, MODEL, transport=httpx.MockTransport(handler)).generate(evidence(), 1)
    assert error.value.code == code and KEY not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("data,code", [
    ({}, "PROVIDER_RESPONSE_INVALID"),
    ({"choices": []}, "PROVIDER_RESPONSE_INVALID"),
    ({"choices": [reply()["choices"][0]] * 2}, "PROVIDER_RESPONSE_INVALID"),
    ({"choices": [None]}, "PROVIDER_RESPONSE_INVALID"),
    (reply(reason="length"), "PROVIDER_RESPONSE_INCOMPLETE"),
    (reply(reason=None), "PROVIDER_RESPONSE_INCOMPLETE"),
    (reply(reason="content_filter"), "PROVIDER_BLOCKED"),
    (reply(refusal="refused"), "PROVIDER_BLOCKED"),
    (reply(tool_calls=[{"function": "unexpected"}]), "PROVIDER_RESPONSE_INVALID"),
    (reply(function_call={"name": "unexpected"}), "PROVIDER_RESPONSE_INVALID"),
    (reply(content=[]), "PROVIDER_RESPONSE_INVALID"),
    (reply(content=" "), "PROVIDER_RESPONSE_INVALID"),
    (reply(role="user"), "PROVIDER_RESPONSE_INVALID"),
])
def test_only_one_complete_assistant_text_response_is_usable(data, code):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=data))
    with pytest.raises(StudyProviderError) as error:
        NvidiaNimQuizProvider(KEY, MODEL, transport=transport).generate(evidence(), 1)
    assert error.value.code == code


@pytest.mark.parametrize("exception,code", [(httpx.ReadTimeout, "PROVIDER_TIMEOUT"), (httpx.ConnectError, "PROVIDER_UNAVAILABLE")])
def test_transport_errors_are_sanitized(exception, code):
    def handler(request):
        raise exception(KEY, request=request)
    with pytest.raises(StudyProviderError) as error:
        NvidiaNimQuizProvider(KEY, MODEL, transport=httpx.MockTransport(handler)).generate(evidence(), 1)
    assert error.value.code == code and KEY not in str(error.value)


def test_response_cap_and_invalid_outer_json_fail_closed():
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"x" * (MAX_STUDY_RESPONSE_BYTES + 1)
    for data, code in [(httpx.Response(200, stream=Stream()), "PROVIDER_RESPONSE_TOO_LARGE"),
                       (httpx.Response(200, text="not json"), "PROVIDER_RESPONSE_INVALID")]:
        transport = httpx.MockTransport(lambda request: data)
        with pytest.raises(StudyProviderError) as error:
            NvidiaNimQuizProvider(KEY, MODEL, transport=transport).generate(evidence(), 1)
        assert error.value.code == code


def prepared(kind):
    repo = WorkspaceRepository()
    ingestion = DocumentService(repo)
    doc = ingestion.ingest_file("lesson.txt", TEXT.encode())["document"]
    other = ingestion.ingest_file("other.txt", b"UNSELECTED_SENTINEL: Content that must not be transmitted.")["document"]
    context = PracticeAccessContext("learner", SourceAccessContext("workspace", frozenset({doc.doc_id, other.doc_id})))
    sources = F2SourceService(repo).prepare_sources(StudySourceSelection(
        selected_doc_ids=[doc.doc_id], study_format=kind, requested_count=1), context=context.sources)
    return repo, context, sources


@pytest.mark.parametrize("kind", ["quiz", "flashcards"])
def test_real_selected_sources_to_nim_adapter_q05_q06_and_no_unselected_content(kind):
    repo, context, sources = prepared(kind)
    def handler(request):
        assert "UNSELECTED_SENTINEL" not in request.content.decode()
        return httpx.Response(200, json=reply(inner(kind)))
    provider_type = NvidiaNimQuizProvider if kind == "quiz" else NvidiaNimFlashcardProvider
    provider = provider_type(KEY, MODEL, transport=httpx.MockTransport(handler))
    practice = F2PracticeService(repo)
    if kind == "quiz":
        result = F2QuizService(provider).generate_quiz(sources)
        view = practice.start_quiz(result.quiz, context=context)
    else:
        result = F2FlashcardService(provider).generate_flashcards(sources)
        view = practice.start_flashcards(result.deck, context=context)
    assert result.provider_name == "nvidia_nim" and result.status == "COMPLETE"
    assert view.actual_count == 1
    assert "source_refs" not in view.model_dump_json() and "correct_option_id" not in view.model_dump_json()


@pytest.mark.parametrize("kind,changes", [("quiz", {"correct_option_id": "B"}), ("flashcards", {"back": "Unsupported answer."})])
def test_q05_still_blocks_wrong_or_unsupported_nim_answers(kind, changes):
    repo, context, sources = prepared(kind)
    provider_type = NvidiaNimQuizProvider if kind == "quiz" else NvidiaNimFlashcardProvider
    provider = provider_type(KEY, MODEL, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=reply(inner(kind, **changes)))))
    practice = F2PracticeService(repo)
    with pytest.raises(PracticeError) as error:
        if kind == "quiz":
            practice.start_quiz(F2QuizService(provider).generate_quiz(sources).quiz, context=context)
        else:
            practice.start_flashcards(F2FlashcardService(provider).generate_flashcards(sources).deck, context=context)
    assert error.value.code == "RESOURCE_NOT_READY"


def test_fenced_json_is_not_repaired_and_auth_failure_is_not_offline_success():
    repo, context, sources = prepared("quiz")
    for status, data, code in [(200, reply("```json\n" + inner() + "\n```"), "INVALID_PROVIDER_OUTPUT"),
                               (403, {"error": KEY}, "PROVIDER_AUTH_FAILED")]:
        provider = NvidiaNimQuizProvider(KEY, MODEL, transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json=data)))
        result = F2QuizService(provider).generate_quiz(sources)
        assert result.status == "ERROR" and result.quiz is None and result.provider_name == "nvidia_nim"
        assert code in [issue.code for issue in result.issues]
        assert KEY not in str(result.issues)


def ui():
    at = AppTest.from_file(str(APP), default_timeout=20).run()
    runtime = at.session_state["f2_manual_runtime"]
    doc = runtime["ingestion"].ingest_file("lesson.txt", TEXT.encode())["document"]
    at.run()
    at.multiselect(key="f2_manual_selected").select(doc.doc_id).run()
    at.number_input(key="f2_manual_count").set_value(1).run()
    return at


def test_ui_nim_key_is_masked_and_never_inherited_from_gemini_field():
    with patch.dict(os.environ, {"NVIDIA_API_KEY": ""}), patch.object(settings, "gemini_api_key", ""):
        at = ui()
        at.selectbox(key="f2_manual_engine").set_value("Gemini").run()
        at.text_input(key="f2_manual_gemini_key").set_value("google-only-test-key").run()
        at.selectbox(key="f2_manual_engine").set_value("NVIDIA NIM").run()
        assert not at.exception
        assert at.text_input(key="f2_manual_nim_key").value == ""
        assert at.text_input(key="f2_manual_nim_key").proto.type == TextInput.PASSWORD
        assert at.button(key="f2_manual_generate").disabled
        at.text_input(key="f2_manual_nim_key").set_value(KEY).run()
        assert not at.button(key="f2_manual_generate").disabled
        assert any("chưa xác nhận" in item.value for item in at.caption)


@pytest.mark.parametrize("kind,status", [("quiz", 200), ("flashcards", 200), ("quiz", 403)])
def test_ui_nim_factory_model_provider_errors_and_no_hidden_fallback(kind, status):
    real_type = NvidiaNimQuizProvider if kind == "quiz" else NvidiaNimFlashcardProvider
    def factory(api_key, model):
        assert api_key == KEY
        return real_type(api_key, model, transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json=reply(inner(kind)) if status == 200 else {"error": KEY})))
    target = "NvidiaNimQuizProvider" if kind == "quiz" else "NvidiaNimFlashcardProvider"
    with patch.dict(os.environ, {"NVIDIA_API_KEY": ""}), patch(
        "frontend.components.f2_manual_panel." + target, side_effect=factory):
        at = ui()
        at.selectbox(key="f2_manual_engine").set_value("NVIDIA NIM").run()
        at.radio(key="f2_manual_format").set_value("Quiz" if kind == "quiz" else "Flashcards").run()
        at.text_input(key="f2_manual_nim_key").set_value(KEY).run()
        at.text_input(key="f2_manual_nim_model").set_value(MODEL).run()
        at.button(key="f2_manual_generate").click().run()
        assert not at.exception
        assert any(f"nvidia_nim · model yêu cầu: {MODEL}" in item.value for item in at.info)
        assert all(KEY not in item.value for item in [*at.info, *at.warning, *at.error])
        if status == 200:
            assert at.session_state["f2_manual_active"]["format"] == kind
        else:
            assert at.session_state["f2_manual_active"] is None
            assert any("NVIDIA NIM" in item.value for item in at.warning)
