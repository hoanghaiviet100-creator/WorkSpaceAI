# WorkspaceAI — Intelligent Document Workspace (CSC10014 / 2026)

**Track C: Intelligent Document Workspace with Cross-Document Reconciliation & Human-Approved Email Actions**

WorkspaceAI is an end-to-end intelligent document platform built for the **CSC10014 Computational Thinking** course at HCMUS (Ho Chi Minh University of Science). The application implements the 7-step computational pipeline:
$$\text{REQUEST} \longrightarrow \text{UNDERSTAND} \longrightarrow \text{ROUTE} \longrightarrow \text{RETRIEVE / COMPUTE} \longrightarrow \text{REASON} \longrightarrow \text{VERIFY} \longrightarrow \text{RESPOND / ACT}$$

---

## 🚀 Quick Start with Docker (Recommended)

You can run the entire WorkspaceAI platform (FastAPI Backend + Streamlit UI + Local Ollama LLM) with a single command without installing Python dependencies locally.

### 1. Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/) installed and running.

### 2. Configure Environment (Optional)
```bash
cp .env.example .env
# Default settings work out-of-the-box (uses local Ollama or fallback smart synthesizer)
```

### 3. Build & Run
```bash
docker compose up --build
```

Once started:
- 🌐 **Interactive Web UI (Streamlit):** [http://localhost:8501](http://localhost:8501)
- 📖 **API Docs & Swagger UI (FastAPI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- 🦙 **Ollama LLM Engine:** [http://localhost:11434](http://localhost:11434)

### 4. Pull Local LLM Model (Optional for Ollama)
If you wish to run Qwen2.5 locally inside the Ollama container:
```bash
# Pull lightweight 1.5B model (recommended for low-RAM / laptops):
docker compose exec ollama ollama pull qwen2.5:1.5b

# Or pull full 7B model:
docker compose exec ollama ollama pull qwen2.5:7b
```
*(If no model is pulled or Ollama is offline, WorkspaceAI automatically uses its deterministic Smart Offline Synthesizer without failing).*

### 5. Run Verification Test Suite in Docker
```bash
docker compose run --rm app test
```

---

## 💻 Manual Local Setup (Without Docker)

### 1. Environment & Dependencies
```bash
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure `.env`
```bash
cp .env.example .env
```
Choose `LLM_PROVIDER`:
- `mock`: 100% offline deterministic test mode (zero setup needed)
- `ollama`: Local Qwen2.5 / Llama models via Ollama
- `gemini`: Cloud Gemini API (requires `GEMINI_API_KEY`)

### 3. Run Automated Tests (13/13 Pass)
```bash
pytest -v
```

### 4. Start Services
- **Backend (FastAPI):**
  ```bash
  uvicorn backend.main:app --reload --port 8000
  ```
- **Frontend (Streamlit):**
  ```bash
  streamlit run frontend/app.py
  ```

---

## 📂 Core Architecture & Features

| Feature | Scope & Algorithms | Core Files |
|---|---|---|
| **Feature 1: Evidence-Grounded Q&A** | Ingestion (PDF/TXT/MD), SHA-256 deduplication, Hybrid RRF retrieval (BM25 + Dense), 5-step strict Citation Verifier ($S_{verify} \ge \theta_{match}$), Table-of-Contents penalty | `backend/services/document_service.py`<br>`backend/services/qa_service.py`<br>`backend/algorithms/citation_verifier.py`<br>`backend/repositories/workspace_repository.py` |
| **Feature 2: Cross-Document Reconciliation** | Pure stdlib reconciliation: Missing Requirements ($O(N)$), Redundant Tasks ($O(M)$), Inconsistent Specs ($O(N \cdot M)$), Task Drift (Jaccard similarity) | `backend/algorithms/reconciliation.py`<br>`backend/services/reconciliation_service.py` |
| **Feature 3: Context-Aware Email Assistant** | Deterministic Finite State Machine (DRAFT $\to$ PENDING $\to$ APPROVED $\to$ DISPATCHED), SHA-256 draft integrity lock, Gmail SMTP TLS dispatch | `backend/algorithms/email_state_machine.py`<br>`backend/services/email_service.py`<br>`backend/api/email_routes.py` |
| **Safeguards & Guardrails** | Prompt injection detection ($R_7$), recipient validation, untrusted context framing | `backend/core/guardrails.py`<br>`backend/services/router_service.py` |

For detailed architectural specification, see [`WORKSPACEAI_PROJECT_ARCHITECTURE_AND_STATUS_REPORT.md`](WORKSPACEAI_PROJECT_ARCHITECTURE_AND_STATUS_REPORT.md).
