#!/bin/bash
set -e

# Support direct command execution (e.g. `docker compose run app test`)
if [ "$1" = "test" ]; then
    echo "Running WorkspaceAI test suite..."
    exec pytest -v
elif [ "$1" = "api" ]; then
    echo "Starting FastAPI backend only on port 8000..."
    exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
elif [ "$1" = "ui" ]; then
    echo "Starting Streamlit UI only on port 8501..."
    exec streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
elif [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Default: start both FastAPI (port 8000) and Streamlit (port 8501)
echo "=========================================================="
echo " Starting WorkspaceAI Intelligent Document Workspace "
echo "=========================================================="
echo "-> Starting FastAPI backend on http://0.0.0.0:8000 (API Docs: /docs)..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!

# Brief delay to allow FastAPI to bind
sleep 2

echo "-> Starting Streamlit frontend on http://0.0.0.0:8501..."
streamlit run frontend/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false &
STREAMLIT_PID=$!

# Graceful termination handler
cleanup() {
    echo "Stopping WorkspaceAI services..."
    kill -TERM "$FASTAPI_PID" 2>/dev/null || true
    kill -TERM "$STREAMLIT_PID" 2>/dev/null || true
    wait "$FASTAPI_PID" 2>/dev/null || true
    wait "$STREAMLIT_PID" 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Keep running while child processes are alive
wait -n "$FASTAPI_PID" "$STREAMLIT_PID"
cleanup
