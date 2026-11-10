import json
from uuid import uuid4
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.main import app
from backend.providers.llm_provider import llm_provider, GeminiRequestError
from backend.services import runtime_service

KEY = "synthetic-gemini-key-never-sent-6194"
MODEL = "gemini-3.5-flash-lite"
QUOTE = "The report deadline is November 20, 2026."


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "offline_only", False)
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", KEY)
    monkeypatch.setattr(settings, "gemini_model", MODEL)
    monkeypatch.setattr(settings, "dense_tau_rel", 0.0)
    monkeypatch.setattr(settings, "bm25_tau_rel", 0.0)
    monkeypatch.setattr(runtime_service, "ENV_PATH", tmp_path / ".env")


@pytest.fixture
def workspace():
    client = TestClient(app)
    headers = {"X-Workspace-ID": str(uuid4())}
    for name, text in (("alpha.txt", QUOTE), ("beta.txt", "Confidential excluded content BETA-6194.")):
        response = client.post("/api/documents/upload", headers=headers, files={"file": (name, text.encode(), "text/plain")})
        assert response.status_code == 200
    return client, headers


def response_text(text):
    return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]})


def grounded_output(extra=None):
    claims = [{"claim": "The deadline is November 20.", "doc_id": "alpha.txt", "page": 1, "line_start": 1, "line_end": 1, "excerpt": QUOTE}]
    if extra:
        claims.append(extra)
    return response_text(json.dumps({"answer": "The deadline is November 20.", "citations": claims}))


def test_gemini_is_called_once_with_only_selected_document_evidence(workspace):
    client, headers = workspace
    with patch.object(httpx, "post", return_value=grounded_output()) as post:
        result = client.post("/api/chat", headers=headers, json={"query": "What is the report deadline?", "selected_doc_ids": ["alpha.txt"]})
    assert result.status_code == 200
    assert result.json()["status"] == "ANSWER_VERIFIED"
    assert all(c["cited_doc_id"] == "alpha.txt" for c in result.json()["validated_claims"])
    assert post.call_count == 1
    assert post.call_args.args[0].endswith(f"/{MODEL}:generateContent")
    assert KEY not in post.call_args.args[0]
    payload = json.dumps(post.call_args.kwargs["json"])
    assert QUOTE in payload
    assert "BETA-6194" not in payload
    assert "<untrusted_document_data>" in payload
    assert post.call_args.kwargs["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_summary_verifies_generated_citations_instead_of_marking_everything_verified(workspace):
    client, headers = workspace
    unsupported = {"claim": "Invented deadline", "doc_id": "alpha.txt", "page": 1, "line_start": 1, "line_end": 1, "excerpt": "The deadline is December 31, 2030 and cannot be changed."}
    with patch.object(httpx, "post", return_value=grounded_output(unsupported)) as post:
        result = client.post("/api/chat", headers=headers, json={"query": "Summarize alpha.txt", "selected_doc_ids": ["alpha.txt"]})
    assert post.call_count == 1
    body = result.json()
    assert body["status"] == "SUMMARY_GENERATED"
    assert len(body["validated_claims"]) == 1
    assert len(body["hallucination_flags"]) == 1
    assert "Invented deadline" not in body["summary"]
    assert body["grounding_score"] < 1.0


def test_tasks_email_and_empty_selection_never_call_gemini(workspace):
    client, headers = workspace
    with patch.object(httpx, "post") as post:
        report = client.post("/api/chat", headers=headers, json={"query": "Reconcile requirements and tasks", "selected_doc_ids": ["alpha.txt"]})
        draft = client.post("/api/chat", headers=headers, json={"query": "Draft an email about the report", "recipient_email": "test@example.org", "selected_doc_ids": ["alpha.txt"]})
        empty = client.post("/api/chat", headers=headers, json={"query": "What is the deadline?", "selected_doc_ids": []})
        assert llm_provider.call_gemini("Email prompt", feature="email") is None
        assert llm_provider.call_gemini("Task prompt", feature="tasks") is None
    post.assert_not_called()
    assert report.json()["route"] == "RECONCILE_FLOW"
    assert draft.json()["status"] == "PENDING_APPROVAL"
    assert empty.json()["status"] == "ABSTAINED_NO_SOURCE_SELECTED"
    status = runtime_service.runtime_status()
    assert status["feature_engines"] == {"qa": "gemini", "tasks": "offline", "email": "offline"}
    assert status["gemini_scope"] == "feature1"


def test_saved_key_does_not_enable_calls_when_another_engine_is_selected():
    settings.llm_provider = "mock"
    with patch.object(httpx, "post") as post:
        assert llm_provider.call_gemini("Do not send") is None
    post.assert_not_called()


@pytest.mark.parametrize("code", [429, 404, 403, 503])
def test_quota_and_access_errors_never_retry_or_switch_models(workspace, code):
    client, headers = workspace
    with patch.object(httpx, "post", return_value=httpx.Response(code, text=KEY)) as post:
        result = client.post("/api/chat", headers=headers, json={"query": "What is the report deadline?", "selected_doc_ids": ["alpha.txt"]})
    assert post.call_count == 1
    assert result.status_code == 503
    assert KEY not in result.text
    assert "validated_claims" not in result.json()


def test_missing_citations_do_not_get_replaced_with_a_fabricated_quote(workspace):
    client, headers = workspace
    with patch.object(httpx, "post", return_value=response_text('{"answer":"An unsupported answer"}')) as post:
        result = client.post("/api/chat", headers=headers, json={"query": "What is the report deadline?", "selected_doc_ids": ["alpha.txt"]})
    assert post.call_count == 1
    assert result.status_code == 503


def test_connect_can_explicitly_enable_only_feature1_from_offline():
    settings.offline_only = True
    settings.llm_provider = "mock"
    models = httpx.Response(200, json={"models": [{"name": "models/" + MODEL, "supportedGenerationMethods": ["generateContent"]}]})
    with patch.object(httpx, "get", return_value=models), patch.object(httpx, "post") as post:
        response = TestClient(app).post("/api/runtime/gemini", json={"api_key": KEY, "model": MODEL, "enable_feature1": True, "save_locally": True})
    post.assert_not_called()
    assert response.status_code == 200
    assert response.json()["feature_engines"] == {"qa": "gemini", "tasks": "offline", "email": "offline"}
    assert not response.json()["offline_only"]
    assert KEY not in response.text
    assert 'WORKSPACE_OFFLINE_ONLY="false"' in runtime_service.ENV_PATH.read_text()


def test_unavailable_model_preserves_current_configuration():
    settings.offline_only = True
    settings.llm_provider = "mock"
    models = httpx.Response(200, json={"models": [{"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]}]})
    with patch.object(httpx, "get", return_value=models):
        with pytest.raises(ValueError, match="no automatic switch"):
            runtime_service.configure_gemini(KEY, model=MODEL, enable_feature1=True)
    assert settings.offline_only and settings.llm_provider == "mock"
    assert not runtime_service.ENV_PATH.exists()


def test_offline_switch_blocks_cloud_immediately_and_is_local_only():
    client = TestClient(app)
    denied = client.post("/api/runtime/offline", headers={"Origin": "https://other.example"}, json={})
    assert denied.status_code == 403
    response = client.post("/api/runtime/offline", json={"save_locally": True})
    assert response.json()["offline_only"]
    assert response.json()["feature_engines"]["qa"] == "offline"
    with patch.object(httpx, "post") as post:
        assert llm_provider.call_gemini("Do not send") is None
    post.assert_not_called()
    assert 'WORKSPACE_OFFLINE_ONLY="true"' in runtime_service.ENV_PATH.read_text()


@pytest.mark.parametrize("pasted", [f'"{KEY}"', f"'{KEY}'", f'GEMINI_API_KEY="{KEY}"', f"export GEMINI_API_KEY='{KEY}'"])
def test_pasted_key_wrappers_are_normalized_without_exposing_credentials(pasted):
    models = httpx.Response(200, json={"models": [{"name": "models/" + MODEL, "supportedGenerationMethods": ["generateContent"]}]})
    with patch.object(httpx, "get", return_value=models) as get:
        result = runtime_service.configure_gemini(pasted, False, MODEL)
    assert get.call_args.kwargs["headers"]["x-goog-api-key"] == KEY
    assert result["engine_mode"] == "gemini"
    assert KEY not in json.dumps(result)
