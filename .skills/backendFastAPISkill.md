# WorkspaceAI FastAPI & Python Backend Skill (Local-First)

## Core Conventions
- Use Python 3.11+ type hints and Pydantic v2 models defined in `backend/schemas.py`.
- Keep FastAPI routes in `backend/main.py` thin; delegate all logic to `Understanding_Guardrails.py`, `Retrieval_R3.py`, `Algorithms_R2.py`, and `LLM_Provider_R4.py`.
- Storage & Indexing: Local-first only (SQLite, local JSON/CSV, rank-bm25, local ChromaDB/FAISS). Do NOT add PostgreSQL, SQLAlchemy, or Alembic.
- Outbound HTTP: Use `httpx` with explicit timeouts (`timeout=20.0`) and deterministic fallback when local Ollama or Gemini API is unreachable.

## Security & R7 Guardrails
- Always wrap document chunks in `<untrusted_document_data>` before constructing LLM prompts.
- Never allow an LLM response or router branch to send an email directly; email state transitions must go through `approve_and_verify_email_send()` with SHA-256 verification.

## Testing & Output Discipline
- Write unit tests in `tests/test_r2_r7_pipeline.py` compatible with both `unittest` and `pytest`.
- When editing code, return minimal, targeted changes without rewriting unchanged functions.