import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Retrieval relevance threshold (tau_rel)
    retrieval_min_score: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.35"))
    tau_rel: float = float(os.getenv("TAU_REL", os.getenv("RETRIEVAL_MIN_SCORE", "0.35")))
    
    # Citation verification threshold (theta_match)
    citation_verify_threshold: float = float(os.getenv("CITATION_VERIFY_THRESHOLD", "0.75"))
    theta_match: float = float(os.getenv("THETA_MATCH", os.getenv("CITATION_VERIFY_THRESHOLD", "0.75")))
    
    # Gmail SMTP Real Email Configuration
    email_dispatch_mode: str = os.getenv("EMAIL_DISPATCH_MODE", "gmail_real")
    gmail_sender_email: str = os.getenv("GMAIL_SENDER_EMAIL", "")
    gmail_app_password: str = os.getenv("GMAIL_APP_PASSWORD", "")
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))


settings = Settings()

