"""Local runtime configuration. Credentials never appear in status responses."""
from pathlib import Path
import json
import os
import re
import threading
from typing import Any, Dict, Optional

import httpx

from backend.core.config import settings
from backend.providers.llm_provider import llm_provider

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_settings_lock = threading.RLock()
GEMINI_QA_MODELS = ("gemini-3.5-flash-lite", "gemini-3.8-flash")


def runtime_status() -> Dict[str, Any]:
    configured = llm_provider.is_gemini_configured()
    mode = "offline" if settings.offline_only else "gemini" if settings.llm_provider == "gemini" and configured else "ollama" if settings.llm_provider == "ollama" else "offline"
    return {
        "status": "ready", "engine_mode": mode, "gemini_configured": configured,
        "offline_only": settings.offline_only,
        "model": settings.gemini_model if mode == "gemini" else settings.ollama_model if mode == "ollama" else None,
        "supported_formats": ["pdf", "txt", "md", "csv"],
        "gemini_scope": "feature1",
        "feature_engines": {"qa": mode, "tasks": "offline", "email": "ollama" if mode == "ollama" else "offline"},
        "model_options": list(GEMINI_QA_MODELS),
    }


def _save_configuration(path: Path, values: Dict[str, str]) -> None:
    """Preserve other settings, then atomically replace the local dotenv file."""
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = original.splitlines()
    remaining = dict(values)
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match.group(1) in values:
            key = match.group(1)
            lines[index] = f"{key}={json.dumps(values[key])}"
            remaining.pop(key, None)
    lines.extend(f"{key}={json.dumps(value)}" for key, value in remaining.items())
    temporary = path.with_name(path.name + ".runtime.tmp")
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def configure_gemini(api_key: Optional[str], save_locally: bool = True, model: Optional[str] = None, enable_feature1: bool = False) -> Dict[str, Any]:
    if settings.offline_only and not enable_feature1:
        raise PermissionError("Cloud AI is disabled in offline mode. No Gemini request was made.")
    model = model or (settings.gemini_model if settings.gemini_model in GEMINI_QA_MODELS else GEMINI_QA_MODELS[0])
    if model not in GEMINI_QA_MODELS:
        raise ValueError("Choose a supported Feature 1 model. No model was changed.")
    key = (api_key or settings.gemini_api_key or "").strip()
    key = re.sub(r"^(?:export\s+)?GEMINI_API_KEY\s*=\s*", "", key, flags=re.IGNORECASE).strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in {"'", '"'}:
        key = key[1:-1].strip()
    # Treat credentials as opaque; Google validates the actual key, not a guessed prefix.
    if not 20 <= len(key) <= 512 or any(not 33 <= ord(char) <= 126 for char in key):
        raise ValueError("Copy the full API key value from Google AI Studio, not its name or project ID. Do not paste the key into chat.")
    # This checks model visibility only; it does not generate content or verify free quota.
    try:
        response = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": key}, params={"pageSize": 1000},
            timeout=httpx.Timeout(15.0, connect=3.0),
        )
    except httpx.HTTPError:
        raise ValueError("Could not reach Gemini. Check your internet connection and try again.") from None
    if response.status_code != 200:
        if response.status_code == 429:
            raise ValueError("Google is limiting requests for this key. Check its quota and try again.")
        raise ValueError("Google did not accept this API key. Check the key and its API access.")
    try:
        available = [
            item["name"].removeprefix("models/") for item in response.json().get("models", [])
            if "generateContent" in item.get("supportedGenerationMethods", [])
            and isinstance(item.get("name"), str)
            and not any(word in item["name"].lower() for word in ("image", "audio", "tts", "robotics", "computer-use", "deep-research"))
        ]
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Gemini returned an unreadable model list. Try again later.") from None
    if not available:
        raise ValueError("This key has no supported text-generation model available.")
    if model not in available:
        raise ValueError("The selected model is not available to this key. Choose an accessible model; no automatic switch was made.")
    with _settings_lock:
        if save_locally:
            try:
                _save_configuration(ENV_PATH, {"GEMINI_API_KEY": key, "GEMINI_MODEL": model, "LLM_PROVIDER": "gemini", "WORKSPACE_OFFLINE_ONLY": "false"})
            except OSError:
                raise ValueError("The key could not be saved on this device. The previous configuration is unchanged.") from None
        settings.gemini_api_key = key
        settings.gemini_model = model
        settings.llm_provider = "gemini"
        settings.offline_only = False
    return {**runtime_status(), "saved_locally": save_locally}


def use_offline(save_locally: bool = True) -> Dict[str, Any]:
    with _settings_lock:
        if save_locally:
            try:
                _save_configuration(ENV_PATH, {"LLM_PROVIDER": "mock", "WORKSPACE_OFFLINE_ONLY": "true"})
            except OSError:
                raise ValueError("Offline settings could not be saved. The previous configuration is unchanged.") from None
        settings.offline_only = True
        settings.llm_provider = "mock"
    return {**runtime_status(), "saved_locally": save_locally}
