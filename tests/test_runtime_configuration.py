import json
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.main import app
from backend.services import runtime_service
from backend.providers.llm_provider import llm_provider


TEST_KEY = "test-key-not-a-real-credential-6194"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "offline_only", False)
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "gemini_model", "retired-model")
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(runtime_service, "ENV_PATH", tmp_path / ".env")


def model_list(*names):
    return httpx.Response(200, json={"models": [{"name": "models/" + name, "supportedGenerationMethods": ["generateContent"]} for name in names]})


def test_runtime_status_never_returns_a_key():
    settings.gemini_api_key = TEST_KEY
    status = TestClient(app).get("/api/runtime").json()
    assert status["gemini_configured"] is True
    assert status["engine_mode"] == "offline"
    assert TEST_KEY not in json.dumps(status)


def test_invalid_key_is_not_saved_or_echoed():
    response = TestClient(app).post("/api/runtime/gemini", json={"api_key": "short"})
    assert response.status_code == 400
    assert "short" not in response.text
    assert not runtime_service.ENV_PATH.exists()
    assert settings.llm_provider == "mock"


def test_cross_origin_configuration_is_rejected():
    response = TestClient(app).post("/api/runtime/gemini", headers={"Origin": "https://untrusted.example"}, json={"api_key": TEST_KEY})
    assert response.status_code == 403
    assert not runtime_service.ENV_PATH.exists()


def test_model_discovery_uses_header_and_saves_only_after_validation():
    with patch.object(runtime_service.httpx, "get", return_value=model_list("gemini-3.5-flash-lite")) as get:
        result = runtime_service.configure_gemini(TEST_KEY)
    assert get.call_args.kwargs["headers"]["x-goog-api-key"] == TEST_KEY
    assert TEST_KEY not in get.call_args.args[0]
    assert result["engine_mode"] == "gemini"
    assert result["model"] == "gemini-3.5-flash-lite"
    assert TEST_KEY not in json.dumps(result)
    assert "LLM_PROVIDER=\"gemini\"" in runtime_service.ENV_PATH.read_text()


def test_model_discovery_avoids_image_only_models():
    with patch.object(runtime_service.httpx, "get", return_value=model_list("gemini-image-preview", "gemini-3.5-flash-lite")):
        result = runtime_service.configure_gemini(TEST_KEY, False)
    assert result["model"] == "gemini-3.5-flash-lite"
    assert not runtime_service.ENV_PATH.exists()


def test_credential_validation_failure_preserves_previous_configuration():
    settings.gemini_api_key = "previous-key-not-a-real-credential"
    runtime_service.ENV_PATH.write_text("# Keep this\nOTHER_SETTING=unchanged\n")
    with patch.object(runtime_service.httpx, "get", return_value=httpx.Response(403)):
        with pytest.raises(ValueError):
            runtime_service.configure_gemini(TEST_KEY)
    assert settings.gemini_api_key.startswith("previous-key")
    assert runtime_service.ENV_PATH.read_text() == "# Keep this\nOTHER_SETTING=unchanged\n"


def test_network_error_contains_no_credential():
    with patch.object(runtime_service.httpx, "get", side_effect=httpx.ConnectError(TEST_KEY)):
        response = TestClient(app).post("/api/runtime/gemini", json={"api_key": TEST_KEY})
    assert response.status_code == 400
    assert TEST_KEY not in response.text
    assert settings.llm_provider == "mock"


def test_persistence_preserves_other_env_values_and_comments():
    runtime_service.ENV_PATH.write_text("# Original comment\nOTHER_SETTING=keep-me\nGEMINI_API_KEY=old\n")
    with patch.object(runtime_service.httpx, "get", return_value=model_list("gemini-3.5-flash-lite")):
        runtime_service.configure_gemini(TEST_KEY)
    content = runtime_service.ENV_PATH.read_text()
    assert "# Original comment" in content
    assert "OTHER_SETTING=keep-me" in content
    assert "GEMINI_API_KEY=old" not in content
    assert content.count("GEMINI_API_KEY=") == 1


def test_saved_key_can_be_reused_without_returning_it():
    settings.gemini_api_key = TEST_KEY
    with patch.object(runtime_service.httpx, "get", return_value=model_list("gemini-3.5-flash-lite")):
        response = TestClient(app).post("/api/runtime/gemini", json={"save_locally": False})
    assert response.status_code == 200
    assert response.json()["engine_mode"] == "gemini"
    assert TEST_KEY not in response.text


def test_generation_key_is_never_in_the_request_url():
    settings.gemini_api_key = TEST_KEY
    settings.llm_provider = "gemini"
    settings.gemini_model = "gemini-3.5-flash-lite"
    with patch.object(httpx, "post", return_value=httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "answer"}]}}]})) as post:
        assert llm_provider.call_gemini("A synthetic test prompt") == "answer"
    assert TEST_KEY not in post.call_args.args[0]
    assert post.call_args.kwargs["headers"]["x-goog-api-key"] == TEST_KEY


def test_offline_mode_rejects_cloud_configuration_before_network_access():
    settings.offline_only = True
    with patch.object(httpx, "get") as get:
        response = TestClient(app).post("/api/runtime/gemini", json={"api_key": TEST_KEY})
    assert response.status_code == 409
    get.assert_not_called()
    assert not runtime_service.ENV_PATH.exists()


def test_offline_mode_blocks_generation_even_with_a_configured_key():
    settings.offline_only = True
    settings.gemini_api_key = TEST_KEY
    settings.llm_provider = "gemini"
    with patch.object(httpx, "post") as post:
        assert llm_provider.call_gemini("Do not send this document") is None
    post.assert_not_called()
    status = runtime_service.runtime_status()
    assert status["engine_mode"] == "offline"
    assert status["offline_only"] is True
