"""Opt-in real Ollama evidence, using only synthetic documents and an isolated index.

PowerShell: $env:RUN_OLLAMA_EMBEDDING_SMOKE='1'; python -m pytest -s -q tests/test_embedding_ollama_runtime.py
Set OLLAMA_BASE_URL to the reachable endpoint before starting Python.
"""
import json
import os

import httpx
import numpy as np
import pytest

from backend.providers.embedding_provider import embedding_provider
from backend.repositories.workspace_repository import WorkspaceRepository, create_ollama_embed_fn
from backend.services.document_service import DocumentService


@pytest.mark.skipif(os.getenv("RUN_OLLAMA_EMBEDDING_SMOKE") != "1", reason="requires real Ollama; explicitly opt in")
def test_real_document_ingestion_and_query_use_qwen3(monkeypatch):
    calls = []

    class RecordingTransport(httpx.BaseTransport):
        def handle_request(self, request):
            # Every response comes from the real server, with no replacement vectors.
            with httpx.HTTPTransport() as transport:
                response = transport.handle_request(request)
                response.read()
            if request.url.path == "/api/embed":
                data = response.json()
                calls.append({
                    "request": json.loads(request.content), "response_model": data.get("model"),
                    "shape": list(np.asarray(data.get("embeddings")).shape),
                    "keys": list(data),
                })
            return response

    provider = embedding_provider
    assert provider.model_name == "qwen3-embedding:0.6b"
    monkeypatch.setattr(provider, "_transport", RecordingTransport())
    repo = WorkspaceRepository(embed_fn=create_ollama_embed_fn())
    service = DocumentService(repo)
    document = "TCP provides reliable and ordered delivery of data between devices."
    result = service.ingest_file("synthetic-qwen3.txt", document.encode())
    query = "How does TCP deliver data?"
    hits = repo.search(query, selected_doc_ids=[result["document"].doc_id])
    assert hits and hits[0].doc_id == "synthetic-qwen3.txt"
    assert provider.using_ollama and not provider.using_hash_fallback
    assert provider.dimension == 1024  # observed for the official 0.6b tag, never forced in production
    assert all(call["request"]["model"] == call["response_model"] == provider.model_name for call in calls)
    assert all(call["shape"][1] == provider.dimension for call in calls)
    assert any(call["request"]["input"] == [document] for call in calls)
    assert any(call["request"]["input"] == [f"Instruct: {provider.query_instruction}\nQuery:{query}"] for call in calls)
    for vector in repo._chunk_embeddings.values():
        assert vector.shape == (1024,) and np.isfinite(vector).all()
        np.testing.assert_allclose(np.linalg.norm(vector), 1., atol=1e-6)
    for vector in repo._query_embeddings.values():
        assert vector.shape == (1, 1024) and np.isfinite(vector).all()
        np.testing.assert_allclose(np.linalg.norm(vector), 1., atol=1e-6)
    calls_before = len(calls)
    repo.search(query, selected_doc_ids=["synthetic-qwen3.txt"])
    assert len(calls) == calls_before
    print("QWEN3_RUNTIME_EVIDENCE=" + json.dumps({
        "model": provider.model_name, "digest": provider.model_digest,
        "dimension": provider.dimension, "index_id": provider.index_id,
        "using_ollama": provider.using_ollama, "using_hash_fallback": provider.using_hash_fallback,
        "document_vectors": len(repo._chunk_embeddings), "query_vectors": len(repo._query_embeddings),
        "embed_calls": calls, "cached_repeat_embed_calls": len(calls) - calls_before,
        "retrieved_doc_id": hits[0].doc_id,
    }, ensure_ascii=False))
