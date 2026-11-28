import os
from typing import Any, Dict
from backend.core.config import settings
from backend.providers.llm_provider import llm_provider


class RuntimeService:
    def get_status(self) -> Dict[str, Any]:
        offline_only = os.getenv("WORKSPACE_OFFLINE_ONLY", "false").lower() == "true"
        provider = settings.llm_provider.lower()
        if offline_only:
            engine_mode = "offline"
            model = None
        elif provider == "ollama":
            engine_mode = "ollama"
            model = settings.f1_generation_model
        elif provider == "gemini":
            engine_mode = "gemini"
            model = settings.gemini_model
        else:
            engine_mode = "offline"
            model = None

        return {
            "status": "ready",
            "engine_mode": engine_mode,
            "gemini_configured": llm_provider.is_gemini_configured(),
            "model": model,
            "saved_locally": True,
            "offline_only": offline_only,
            "gemini_scope": "feature1",
            "model_options": [settings.f1_generation_model, "gemini-flash-lite-latest"],
            "provider_options": [
                {
                    "id": "ollama",
                    "model": settings.f1_generation_model,
                    "configured": llm_provider.is_ollama_online(),
                },
                {
                    "id": "gemini",
                    "model": settings.gemini_model,
                    "configured": llm_provider.is_gemini_configured(),
                },
            ],
        }

    def select_provider(self, provider: str) -> Dict[str, Any]:
        offline_only = os.getenv("WORKSPACE_OFFLINE_ONLY", "false").lower() == "true"
        if not offline_only and provider in ("ollama", "gemini", "mock", "offline"):
            settings.llm_provider = provider
        return self.get_status()

    def configure_gemini(self, api_key: str) -> Dict[str, Any]:
        offline_only = os.getenv("WORKSPACE_OFFLINE_ONLY", "false").lower() == "true"
        if offline_only:
            raise PermissionError("Offline mode only - cloud configuration is disabled.")
        settings.gemini_api_key = api_key
        settings.llm_provider = "gemini"
        return self.get_status()


runtime_service = RuntimeService()
