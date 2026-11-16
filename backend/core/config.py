import os
from dataclasses import dataclass
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    ollama_embed_model: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    
    # Retrieval relevance threshold (tau_rel)
    retrieval_min_score: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.35"))
    tau_rel: float = float(os.getenv("TAU_REL", os.getenv("RETRIEVAL_MIN_SCORE", "0.35")))
    dense_tau_rel: float = float(os.getenv("DENSE_TAU_REL", "0.35"))
    bm25_tau_rel: float = float(os.getenv("BM25_TAU_REL", "0.35"))
    
    # Citation verification threshold (theta_match)
    citation_verify_threshold: float = float(os.getenv("CITATION_VERIFY_THRESHOLD", "0.75"))
    theta_match: float = float(os.getenv("THETA_MATCH", os.getenv("CITATION_VERIFY_THRESHOLD", "0.75")))
    
    # Gmail SMTP Real Email Configuration
    email_dispatch_mode: str = os.getenv("EMAIL_DISPATCH_MODE", "gmail_real")
    gmail_sender_email: str = os.getenv("GMAIL_SENDER_EMAIL", "")
    gmail_app_password: str = os.getenv("GMAIL_APP_PASSWORD", "")
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))

    # Database Configuration (SQLite default for Local-First Zero-Config, MySQL optional)
    database_type: str = os.getenv("DATABASE_TYPE", "sqlite")
    sqlite_db_path: str = os.getenv("SQLITE_DB_PATH", "workspace_ai.db")

    # Optional MySQL Database Configuration
    mysql_host: str = os.getenv("MYSQL_HOST", "localhost")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "workspace_ai")
    mysql_pool_size: int = int(os.getenv("MYSQL_POOL_SIZE", "10"))
    mysql_pool_recycle: int = int(os.getenv("MYSQL_POOL_RECYCLE", "3600"))

    @property
    def db_url(self) -> str:
        """Returns active database connection URL (SQLite or MySQL)."""
        if self.database_type.lower() == "mysql":
            pwd = f":{self.mysql_password}" if self.mysql_password else ""
            return f"mysql+pymysql://{self.mysql_user}{pwd}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        return f"sqlite:///{self.sqlite_db_path}"

    @property
    def mysql_url(self) -> str:
        """Backward-compatible alias for db_url."""
        return self.db_url



settings = Settings()

