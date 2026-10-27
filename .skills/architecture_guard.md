# CSC10014 WorkspaceAI — Layered Architecture Rules

## Folder Responsibilities
- `backend/core/`: Schemas (Pydantic), Config, and Guardrails (Prompt-injection & XML wrapping).
- `backend/algorithms/`: Pure deterministic Python R2 algorithms (Reconciliation, Citation Verifier, Email FSM). NEVER put LLM calls here.
- `backend/repositories/`: Data access for PDF/CSV and BM25/Vector indexing.
- `backend/providers/`: LLM wrappers (Ollama/Gemini/Mock).
- `backend/services/`: Business workflows and Router slot-filling gate.
- `backend/api/`: FastAPI route handlers only.

## AI Assistant Guidelines
- Keep routes thin; business logic belongs in `services/` or `algorithms/`.
- Edit only the specific layer requested by the user. Do NOT touch other layers.
- Output only modified code functions/diffs.