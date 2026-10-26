# WorkspaceAI — Engineering Skeleton (CSC10014 / 2026)

**Track C: Intelligent Document Workspace with Cross-Document Reconciliation & Human-Approved Email Actions**

This repository provides a runnable, modular local engineering skeleton aligned with the **CSC10014 Computational Thinking** reference architecture:
`REQUEST -> UNDERSTAND -> ROUTE -> RETRIEVE / COMPUTE -> REASON -> VERIFY -> RESPOND / ACT`

## Quick Start (Local Execution)

1. **Create a virtual environment & install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Choose LLM_PROVIDER=mock (0-setup test), ollama (100% local), or gemini (free cloud API)
   ```

3. **Run unit tests for R2 Deterministic Algorithms & R7 Safeguards:**
   ```bash
   pytest -v
   ```

4. **Start the FastAPI Backend (`http://localhost:8000`):**
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

5. **Start the Streamlit Workspace UI (`http://localhost:8501`):**
   ```bash
   streamlit run frontend/app.py
   ```
