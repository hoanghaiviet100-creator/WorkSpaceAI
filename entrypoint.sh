#!/bin/bash
set -e
case "${1:-api}" in
    test) exec python verify.py ;;
    api) exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 ;;
    ui) exec streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true ;;
    *) exec "$@" ;;
esac
