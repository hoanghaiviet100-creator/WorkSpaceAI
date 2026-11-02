# WorkspaceAI Backend & RAG Optimization Skill (FastAPI + Hybrid RAG + Qwen2.5:7b)

## 1. Backend & API Conventions
- **Pydantic Models**: Use Python 3.11+ type hints and Pydantic v2 schemas defined in `backend/core/schemas.py`.
- **Thin Route Handlers**: Keep FastAPI routes in `backend/api/` thin; delegate business logic strictly to `backend/services/` and deterministic algorithms to `backend/algorithms/`.
- **Local-First Storage**: Local in-memory dictionary / JSON / CSV, rank-bm25, and dense NumPy embeddings. Never introduce PostgreSQL, SQLAlchemy, or Alembic.
- **R7 Security Guardrails**:
  - Always enclose document chunks in `<untrusted_document_data>` before constructing LLM prompts.
  - Never allow LLM or router branches to dispatch emails directly; state transitions must go through `approve_and_verify_email_send()` with SHA-256 payload verification.
- **Outbound HTTP**: Use `httpx` with explicit timeouts (`timeout=60.0`, `connect=2.0`) and deterministic fallback when local Ollama or Gemini API is unreachable.

## 2. RAG & Ollama Qwen2.5-7B Optimization
- **Line-Numbered Chunking**:
  Before prompt injection, format every physical line with an explicit label:
  ```text
  === TÀI LIỆU: {doc_id} | TÊN: {title} | TRANG: {page_number} | DÒNG: {line_start}-{line_end} ===
  [Dòng 10] Nội dung dòng 10 trích xuất nguyên văn...
  [Dòng 11] Nội dung dòng 11 tiếp theo...
  ```
- **Ollama Invocations (`/api/generate`)**:
  - Model: `settings.ollama_model` (`qwen2.5:7b`).
  - Options: `{"num_ctx": 8192, "temperature": 0.1, "top_p": 0.85, "repeat_penalty": 1.1}`.
  - Format: `"format": "json"` to enforce structured JSON output.
- **JSON Schema Output**:
  ```json
  {
    "answer": "Câu trả lời chi tiết bằng tiếng Việt, cuối mỗi ý gắn [doc_id, Trang X, Dòng Y-Z]...",
    "citations": [
      {
        "doc_id": "Project_Brief.pdf",
        "page": 6,
        "line_start": 1,
        "line_end": 2,
        "excerpt": "Trích nguyên văn 100% câu chữ từ tài liệu gốc làm bằng chứng..."
      }
    ]
  }
  ```
- **Verification Flow**:
  1. Parse JSON safely (handling optional markdown code blocks ````json ... ````).
  2. Align candidate claims against retrieved chunk text using `align_claim_to_chunks()`.
  3. Pass through `verify_citations()` in `backend/algorithms/citation_verifier.py`.
  4. If all claims fail verification, abstain with `ABSTAINED_INSUFFICIENT_EVIDENCE`.
