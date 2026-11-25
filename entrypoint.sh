#!/bin/bash
set -e

# Support direct command execution (e.g. `docker compose run app test`)
if [ "$1" = "test" ]; then
    echo "Running WorkspaceAI test suite..."
    exec pytest -v
elif [ "$1" = "api" ]; then
    echo "Starting FastAPI backend on port 8000..."
    exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
elif [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Default: start FastAPI backend on port 8000
echo "=========================================================="
echo " Starting WorkspaceAI FastAPI Backend (Port 8000) "
echo "=========================================================="
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
