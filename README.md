# WorkspaceAI — Intelligent Document Workspace (CSC10014 / 2026)

**Track C: Intelligent Document Workspace with Cross-Document Reconciliation & Human-Approved Email Actions**

WorkspaceAI is an end-to-end intelligent document platform built for the **CSC10014 Computational Thinking** course at HCMUS (Ho Chi Minh University of Science). The application implements the 7-step computational pipeline:
$$\text{REQUEST} \longrightarrow \text{UNDERSTAND} \longrightarrow \text{ROUTE} \longrightarrow \text{RETRIEVE / COMPUTE} \longrightarrow \text{REASON} \longrightarrow \text{VERIFY} \longrightarrow \text{RESPOND / ACT}$$

---

## 📧 Feature 3: Context-Aware Email Reporting & Finite State Machine (FSM)

Feature 3 provides human-in-the-loop, cryptographically secured academic and progress email reporting. It is governed by a 100% pure Python standard-library Finite State Machine with SHA-256 tamper detection and duplicate-send prevention.

### FSM State Transitions
```text
  [DRAFT] ──(approve_snapshot)──> [APPROVED] ──(dispatch_email)──> [SENT] (Terminal)
     │                                │                                │
     │                                ├──(tamper detected)────────────> [DRAFT] (revocation)
     │                                ├──(auth error)─────────────────> [FAILED]
     │                                └──(network timeout)────────────> [DELIVERY_UNKNOWN]
```

- **`DRAFT`**: Initial mutable draft state created from chat or direct composition.
- **`APPROVED`**: Cryptographically locked snapshot with a canonical SHA-256 digest over the normalized tuple `(recipients, subject, body)`. Requires explicit human confirmation (`user_confirmed=True`).
- **`SENT`**: Terminal state. Message accepted by the SMTP relay. Duplicate sends are strictly prohibited (`FSMStateError`).
- **`FAILED`**: Delivery rejected due to authentication or invalid parameters (`SMTPAuthenticationError`).
- **`DELIVERY_UNKNOWN`**: Network timeout or disconnection during SMTP handoff. In accordance with **NFR-04**, automatic retries are strictly prohibited to prevent duplicate transmission.

---

### Example API Calls & Expected Responses

#### 1. Create Email Draft (`POST /api/email/draft`)
```bash
curl -X POST http://localhost:8000/api/email/draft \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "recipients": ["instructor@hcmus.edu.vn"],
    "subject": "Sprint Review Request",
    "body": "We have completed Sprint 3 deliverables.",
    "citations": ["Project_Brief.pdf (Page 2)"]
  }'
```
*Expected JSON Response (HTTP 200):*
```json
{
  "id": "e4b2c1a0-9f3e-4b2c-8d1a-0f3e4b2c8d1a",
  "workspace_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "recipients": ["instructor@hcmus.edu.vn"],
  "subject": "Sprint Review Request",
  "body": "We have completed Sprint 3 deliverables.",
  "fsm_state": "DRAFT",
  "sha256_digest": null,
  "audit_timestamp": "2026-11-11T16:00:00Z",
  "citations": ["Project_Brief.pdf (Page 2)"]
}
```

#### 2. Approve Snapshot & Lock Hash (`POST /api/email/{draft_id}/approve`)
```bash
curl -X POST http://localhost:8000/api/email/e4b2c1a0-9f3e-4b2c-8d1a-0f3e4b2c8d1a/approve \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": "instructor@hcmus.edu.vn",
    "subject": "Sprint Review Request",
    "body": "We have completed Sprint 3 deliverables.",
    "user_confirmed": true
  }'
```
*Expected JSON Response (HTTP 200):*
```json
{
  "id": "e4b2c1a0-9f3e-4b2c-8d1a-0f3e4b2c8d1a",
  "workspace_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "recipients": ["instructor@hcmus.edu.vn"],
  "subject": "Sprint Review Request",
  "body": "We have completed Sprint 3 deliverables.",
  "fsm_state": "APPROVED",
  "sha256_digest": "a3b89f2d1e4c7b8a5d6e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c",
  "audit_timestamp": "2026-11-11T16:01:00Z",
  "citations": ["Project_Brief.pdf (Page 2)"]
}
```

#### 3. Send Approved Email (`POST /api/email/{draft_id}/send`)
```bash
curl -X POST http://localhost:8000/api/email/e4b2c1a0-9f3e-4b2c-8d1a-0f3e4b2c8d1a/send
```
*Expected JSON Response (HTTP 200):*
```json
{
  "status": "SENT",
  "draft_id": "e4b2c1a0-9f3e-4b2c-8d1a-0f3e4b2c8d1a",
  "dispatch_mode": "local_mock",
  "sha256_digest": "a3b89f2d1e4c7b8a5d6e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c",
  "audit_timestamp": "2026-11-11T16:02:00Z",
  "message": "Email dispatched successfully (Local Mock Mode) to instructor@hcmus.edu.vn."
}
```

#### 4. Query Audit Log (`GET /api/email/audit-log`)
```bash
curl -X GET "http://localhost:8000/api/email/audit-log?workspace_id=9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
```
*Expected JSON Response (HTTP 200, PII-redacted):*
```json
[
  {
    "id": "e4b2c1a0-9f3e-4b2c-8d1a-0f3e4b2c8d1a",
    "draft_id": "e4b2c1a0-9f3e-4b2c-8d1a-0f3e4b2c8d1a",
    "workspace_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "fsm_state": "SENT",
    "state": "SENT",
    "sha256_digest": "a3b89f2d1e4c7b8a5d6e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c",
    "audit_timestamp": "2026-11-11T16:02:00Z"
  }
]
```

---

## 🧪 Running the Test Suite Locally

### Single-Command Feature 3 Test Suite
To run the Feature 3 unit and integration test suite:
```bash
python -m unittest tests/test_feature3_email_backend.py
```
Or using the Makefile target:
```bash
make test
```

### Full Single-Touch Verification Suite (`verify.py`)
To run the automated 3-step verification (AST Syntax Check, R2 Stdlib Purity Gate, Pytest Suite):
```bash
python verify.py
```

---

## 🚀 Quick Start with Docker (Recommended)

You can run the entire WorkspaceAI platform (React UI + FastAPI Backend + Local Ollama LLM) with a single command without installing Python dependencies locally.

### 1. Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/) installed and running.

### 2. Configure Environment (Optional)
```bash
cp .env.example .env
# Default settings work out-of-the-box (uses local Ollama or fallback smart synthesizer)
```

### 3. Build & Run
```bash
docker compose up --build -d
```

Once started:
- 🌐 **Interactive Web UI (React):** [http://localhost:8501](http://localhost:8501)
- 📖 **API Docs & Swagger UI (FastAPI):** [http://localhost:8001/docs](http://localhost:8001/docs)
- 🦙 **Ollama LLM Engine:** [http://localhost:11434](http://localhost:11434)

---

### Docker data and stopping

React is served at http://localhost:8501. `/api` requests are forwarded to FastAPI inside Docker. Ports are bound to this computer only.

Backend document libraries persist in `./.workspace_data` on the host; back up this folder. Ollama models persist in the `workspaceai_ollama_models` volume. UI conversations and boards use browser local storage: keep the same browser profile and URL. Data from `http://127.0.0.1:5174` is not automatically transferred to `http://localhost:8501`.

Stop without deleting data: `docker compose down`. Start again: `docker compose up -d`. Do not use `down --volumes` unless you intend to delete model storage. Keep original documents as backups.

To use the 1.5B model, set `OLLAMA_MODEL=qwen2.5:1.5b` in `.env`, pull that exact model, and recreate app with `docker compose up -d`. No Node.js, Python or Ollama installation is needed on the host.

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

### 3. Start Services
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
| **Feature 3: Context-Aware Email Assistant** | 100% Pure stdlib Finite State Machine (`DRAFT` $\to$ `APPROVED` $\to$ `SENT`), canonical SHA-256 draft integrity lock, duplicate-send prevention, Gmail SMTP TLS dispatch with NFR-04 unknown delivery protection | `backend/algorithms/email_state_machine.py`<br>`backend/services/email_service.py`<br>`backend/api/email_routes.py` |
| **Safeguards & Guardrails** | Prompt injection detection ($R_7$), recipient validation, untrusted context framing | `backend/core/guardrails.py`<br>`backend/services/router_service.py` |

For detailed architectural specification, see [`WORKSPACEAI_PROJECT_ARCHITECTURE_AND_STATUS_REPORT.md`](WORKSPACEAI_PROJECT_ARCHITECTURE_AND_STATUS_REPORT.md).



### NVIDIA laptop profile

The Ollama service requests NVIDIA GPU access (requires a working Docker Desktop WSL2 GPU setup). It limits CPU to 4 cores, host memory to 10 GB, parallel requests to one and loaded models to one; queue limit is four. Models unload after 60 seconds idle. Backend generation uses a 4096-token context, up to 1024 output tokens (2048 for detailed Q&A) and four CPU threads. These are resource controls, not GPU wattage or hardware temperature limits. Do not interpret a successful short test as a hardware safety guarantee.

Qwen2.5 7B downloads about 4.7 GB; keep disk headroom for Docker. Stop model use immediately with `docker compose stop ollama`; restart with `docker compose up -d ollama`. Check loaded GPU placement with `docker compose exec ollama ollama ps`. Keep the same browser origin for existing UI history.
