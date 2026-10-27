# CSC10014 WorkspaceAI — Project Map & Token-Saving Rules

## 1. Strict Pipeline Architecture (Never Violate)
`REQUEST -> UNDERSTAND -> ROUTE -> RETRIEVE/COMPUTE -> REASON -> VERIFY -> RESPOND/ACT`
- Never send raw requests directly to the LLM without passing through `Understanding_Guardrails.py`.
- Keep all R2 algorithms 100% deterministic pure Python in `backend/Algorithms_R2.py` (no LLM calls inside R2).

## 2. File Map (Read ONLY the file relevant to the user's task)
- `backend/schemas.py`: All Pydantic models (`UserRequest`, `DocumentChunk`, `RequirementItem`, `TaskRecord`, `EmailDraftPayload`).
- `backend/Understanding_Guardrails.py`: Prompt-injection regex, `<untrusted_document_data>` XML wrapper, email validator, `route_user_request()` (R5 & R7).
- `backend/Algorithms_R2.py`: Alg 1 (`reconcile_requirements_and_tasks`), Alg 2 (`verify_citations`), Alg 3 (`approve_and_verify_email_send` + SHA-256 hash).
- `backend/Retrieval_R3.py`: `HybridWorkspaceIndex` (PDF/TXT/CSV ingestion + BM25 & token overlap search).
- `backend/LLM_Provider_R4.py`: `LLMProvider` supporting `mock`, `ollama` (local), and `gemini` with extractive fallback.
- `backend/main.py`: FastAPI endpoints (`POST /api/chat`, `POST /api/email/approve/{draft_id}`).
- `frontend/app.py`: UI client.
- `tests/test_r2_r7_pipeline.py`: Unit tests (`unittest` / `pytest`).

## 3. Token Optimization Rules for AI Assistant
- Output ONLY diff patches or the specific modified function, NOT the entire file unless asked.
- Keep responses concise; skip generic boilerplate explanations.
- Do NOT introduce PostgreSQL, Docker, Redis, or Alembic unless explicitly requested. Use local SQLite/JSON/ChromaDB/BM25.