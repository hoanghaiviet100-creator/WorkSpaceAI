import os
from dataclasses import dataclass


@dataclass
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    retrieval_min_score: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.35"))
    citation_verify_threshold: float = float(os.getenv("CITATION_VERIFY_THRESHOLD", "0.75"))
    email_dispatch_mode: str = os.getenv("EMAIL_DISPATCH_MODE", "local_mock")


settings = Settings()
