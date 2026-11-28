"""Warm-cache digest integrity, explicit rollback and real-provider concurrency with fake HTTP."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from threading import Event, get_ident

import httpx
import numpy as np
import pytest

from backend.providers.embedding_provider import EmbeddingError, EmbeddingProvider
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService


MODEL = "qwen3-embedding:0.6b"
QUERY = "How does TCP deliver data?"


class DigestServer:
    def __init__(self, model=MODEL, digest="digest-A", dimension=3, axis=0):
        self.model, self.digest, self.dimension, self.axis = model, digest, dimension, axis
        self.requests = []
        self.failure = None
        self.before = None

    def __call__(self, request):
        self.requests.append((request.method, request.url.path))
        if self.before:
            self.before(request)
        if self.failure:
            return self.failure(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": self.model, "digest": self.digest}]})
        assert request.url.path == "/api/embed"
        payload = json.loads(request.content)
        assert payload["model"] == self.model
        vector = np.eye(self.dimension)[self.axis].tolist()
        return httpx.Response(200, json={"model": self.model, "embeddings": [vector for _ in payload["input"]]})

    def provider(self):
        return EmbeddingProvider(self.model, base_url="http://ollama.test:11434", transport=httpx.MockTransport(self))


def snapshot(repo):
    return {
        "documents": {key: value.model_dump() for key, value in repo.documents.items()},
        "chunks": [chunk.model_dump() for chunk in repo.chunks],
        "vectors": {key: value.copy() for key, value in repo._chunk_embeddings.items()},
        "queries": {key: value.copy() for key, value in repo._query_embeddings.items()},
        "dimensions": dict(repo._embedding_dimensions), "bm25": repo._bm25,
    }


def assert_unchanged(repo, before):
    assert {key: value.model_dump() for key, value in repo.documents.items()} == before["documents"]
    assert [chunk.model_dump() for chunk in repo.chunks] == before["chunks"]
    assert repo._bm25 is before["bm25"] and repo._embedding_dimensions == before["dimensions"]
    for actual, expected in ((repo._chunk_embeddings, before["vectors"]), (repo._query_embeddings, before["queries"])):
        assert actual.keys() == expected.keys()
        for key, vector in expected.items():
            np.testing.assert_array_equal(actual[key], vector)


@pytest.fixture
def warm_index():
    server = DigestServer()
    provider = server.provider()
    repo = WorkspaceRepository(embed_fn=provider.get_embed_fn())
    DocumentService(repo).ingest_file("unit.txt", b"TCP provides ordered reliable data delivery.")
    assert repo.search(QUERY)
    return server, provider, repo


def test_unchanged_warm_cache_uses_one_fresh_digest_check_and_no_embedding(warm_index):
    server, provider, repo = warm_index
    before, offset = snapshot(repo), len(server.requests)
    assert repo.search(QUERY)[0].dense_score == 1.0
    assert server.requests[offset:] == [("GET", "/api/tags")]
    assert provider.is_available and not provider.using_hash_fallback
    assert_unchanged(repo, before)


@pytest.mark.parametrize("warm", [True, False], ids=["fully-warm", "cold-query"])
def test_changed_digest_never_uses_existing_namespace_or_activates_new_index(warm_index, warm):
    server, provider, repo = warm_index
    before, identity, offset = snapshot(repo), provider.index_id, len(server.requests)
    server.digest = "digest-B"
    try:
        with pytest.raises(EmbeddingError, match="EMBEDDING_MODEL_CHANGED"):
            repo.search(QUERY if warm else "A new cold query")
    finally:
        print(json.dumps({"warm": warm, "pinned_digest": provider.model_digest,
                          "actual_digest": server.digest, "requests": server.requests[offset:]}))
    assert server.requests[offset:] == [("GET", "/api/tags")]
    assert provider.index_id == identity and provider.model_digest == "digest-A"
    assert not provider.is_available and not provider.using_hash_fallback
    assert repo.dense_available and repo._embed_fn.__self__ is provider
    assert_unchanged(repo, before)


@pytest.mark.parametrize("warm", [True, False], ids=["fully-warm", "cold-query"])
@pytest.mark.parametrize("failure,code", [
    ("read-timeout", "EMBEDDING_TIMEOUT"), ("connect-timeout", "EMBEDDING_TIMEOUT"),
    ("connection", "EMBEDDING_PROVIDER_FAILURE"), ("http-503", "EMBEDDING_PROVIDER_FAILURE"),
    ("model-missing", "EMBEDDING_MODEL_MISSING"), ("malformed", "EMBEDDING_INVALID_RESPONSE"),
    ("missing-digest", "EMBEDDING_INVALID_RESPONSE"),
])
def test_unverifiable_digest_fails_closed_even_with_full_cache(warm_index, warm, failure, code):
    server, provider, repo = warm_index
    before, offset = snapshot(repo), len(server.requests)

    def fail(request):
        assert request.method == "GET" and request.url.path == "/api/tags"
        if failure in {"read-timeout", "connect-timeout", "connection"}:
            error = {"read-timeout": httpx.ReadTimeout, "connect-timeout": httpx.ConnectTimeout,
                     "connection": httpx.ConnectError}[failure]
            raise error("controlled inventory failure", request=request)
        if failure == "http-503":
            return httpx.Response(503)
        if failure == "model-missing":
            return httpx.Response(200, json={"models": []})
        if failure == "malformed":
            return httpx.Response(200, content="invalid json")
        return httpx.Response(200, json={"models": [{"name": MODEL}]})

    server.failure = fail
    with pytest.raises(EmbeddingError, match=code):
        repo.search(QUERY if warm else "A new cold query")
    assert server.requests[offset:] == [("GET", "/api/tags")]
    assert not provider.is_available and not provider.using_hash_fallback
    assert repo.dense_available and repo._embed_fn.__self__ is provider
    assert_unchanged(repo, before)


def test_active_index_records_identity_and_policy_without_extra_inspection_http(warm_index):
    server, provider, repo = warm_index
    offset = len(server.requests)
    identity = provider.index_identity
    assert identity == {
        "provider": "ollama", "model": MODEL, "digest": "digest-A", "dimension": 3,
        "normalization": "l2-float32-v1", "document_format": "raw-v1", "query_format": "qwen3-instruct-query-v1",
        "instruction": provider.query_instruction, "truncate": False,
    }
    expected = "ollama:" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    assert provider.index_id == repo._embedding_space() == expected
    identity["digest"] = "tampered-copy"
    assert provider.index_identity["digest"] == "digest-A"
    assert server.requests[offset:] == []  # Observer metadata inspection must not add provider calls.


@pytest.mark.parametrize("field,value", [
    ("model_name", "other-model:version"), ("dimension", 5),
    ("query_instruction", "A different embedding policy"), ("model_digest", "manually-changed-digest"),
])
def test_loaded_identity_cannot_silently_change_policy_or_activate_a_new_index(warm_index, field, value):
    _, provider, repo = warm_index
    identity, record, before = provider.index_id, provider.index_identity, snapshot(repo)
    setattr(provider, field, value)
    with pytest.raises(EmbeddingError, match="EMBEDDING_MODEL_CHANGED"):
        repo.search(QUERY)
    assert provider.index_id == identity and provider.index_identity == record
    assert_unchanged(repo, before)


def test_restoring_recorded_digest_can_reuse_preserved_cache_without_reembedding(warm_index):
    server, provider, repo = warm_index
    identity, before = provider.index_id, snapshot(repo)
    server.digest = "digest-B"
    with pytest.raises(EmbeddingError, match="EMBEDDING_MODEL_CHANGED"):
        repo.search(QUERY)
    server.digest = "digest-A"
    offset = len(server.requests)
    assert repo.search(QUERY)[0].dense_score == 1.0
    assert server.requests[offset:] == [("GET", "/api/tags")]
    assert provider.index_id == identity and provider.is_available
    assert_unchanged(repo, before)


@pytest.mark.parametrize("change", ["model", "digest", "dimension", "instruction"])
def test_explicit_new_identity_remains_isolated_and_old_index_can_be_selected_again(warm_index, change):
    old_server, old, repo = warm_index
    old_space, old_state = old.index_id, snapshot(repo)
    server = DigestServer(model="other-model:version" if change == "model" else MODEL,
                          digest="digest-B" if change == "digest" else "digest-A",
                          dimension=5 if change == "dimension" else 3, axis=1)
    new = server.provider()
    if change == "instruction":
        new.query_instruction = "Another explicit query policy"
    repo.set_embed_fn(new.get_embed_fn())
    assert repo.search(QUERY)[0].dense_score == 1.0
    assert new.index_id != old_space
    assert old_state["vectors"].keys() < repo._chunk_embeddings.keys()
    assert old_state["queries"].keys() < repo._query_embeddings.keys()
    for key, vector in old_state["vectors"].items():
        np.testing.assert_array_equal(repo._chunk_embeddings[key], vector)
    repo.set_embed_fn(old.get_embed_fn())  # Explicit selection in an isolated test, never a production cutover.
    offset = len(old_server.requests)
    assert repo.search(QUERY)[0].dense_score == 1.0
    assert old_server.requests[offset:] == [("GET", "/api/tags")]
    assert repo._embedding_space() == old_space


def test_digest_change_during_new_embedding_does_not_publish_any_cache(warm_index):
    server, provider, repo = warm_index
    before = snapshot(repo)

    def change_during_embedding(request):
        if request.url.path == "/api/embed":
            server.digest = "digest-B"

    server.before = change_during_embedding
    with pytest.raises(EmbeddingError, match="EMBEDDING_MODEL_CHANGED"):
        repo.search("A new query that requires embedding")
    assert provider.model_digest == "digest-A" and not provider.is_available
    assert_unchanged(repo, before)


def test_warm_chat_digest_change_preserves_fix02_sanitized_503(warm_index, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.core.config import settings
    from backend.main import app
    from backend.services.qa_service import qa_service

    server, _, repo = warm_index
    before = snapshot(repo)
    monkeypatch.setattr(qa_service, "repository", repo)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(app.state, "f1_embedding_error", None, raising=False)
    server.digest = "digest-B"
    response = TestClient(app).post("/api/chat", json={"query": QUERY, "selected_doc_ids": ["unit.txt"]})
    assert response.status_code == 503
    assert response.json() == {"detail": "EMBEDDING_MODEL_CHANGED: Semantic embedding is unavailable."}
    assert_unchanged(repo, before)


@pytest.mark.parametrize("dimension", [3, 5], ids=["same-dimension", "different-dimension"])
def test_encoder_replacement_during_digest_check_preserves_fix03_atomicity(warm_index, dimension):
    server, old, repo = warm_index
    assert callable(getattr(old, "verify_index", None)), "no pre-cache digest verification hook exists"
    entered, resume = Event(), Event()
    main_thread = get_ident()

    def pause_inventory(request):
        if request.url.path == "/api/tags" and get_ident() != main_thread:
            entered.set()
            assert resume.wait(5), "digest request was not released"

    server.before = pause_inventory
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(repo.search, QUERY)
        try:
            assert entered.wait(5), "warm-cache operation did not verify its digest"
            new = DigestServer(model="new-model:version", digest="digest-B", dimension=dimension, axis=1).provider()
            repo.set_embed_fn(new.get_embed_fn())
            assert repo.search(QUERY)
            expected = snapshot(repo)
        finally:
            resume.set()
        error = future.exception(timeout=5)
    assert isinstance(error, EmbeddingError) and "encoder changed" in str(error)
    assert_unchanged(repo, expected)
    assert repo._embed_fn.__self__ is new


def test_digest_is_checked_before_the_first_cached_vector_is_read(warm_index):
    server, _, repo = warm_index
    verified = Event()
    server.before = lambda request: verified.set() if request.url.path == "/api/tags" else None

    class GuardedQueryCache(dict):
        def get(self, *args, **kwargs):
            assert verified.is_set(), "cached query was read before the live digest check"
            return super().get(*args, **kwargs)

    repo._query_embeddings = GuardedQueryCache(repo._query_embeddings)
    assert repo.search(QUERY)


def test_fully_cached_ingestion_still_rejects_digest_change_before_publication(warm_index):
    server, _, repo = warm_index
    before = snapshot(repo)
    server.digest = "digest-B"
    with pytest.raises(EmbeddingError, match="EMBEDDING_MODEL_CHANGED"):
        repo.add_document(repo.documents["unit.txt"], list(repo.chunks))
    assert_unchanged(repo, before)


@pytest.mark.parametrize("path", ["no-selection", "missing-document", "no-tokens"])
def test_paths_without_semantic_cache_use_do_not_contact_ollama(warm_index, path):
    server, _, repo = warm_index
    server.digest = "digest-B"
    offset = len(server.requests)
    selected = [] if path == "no-selection" else ["absent.txt"] if path == "missing-document" else None
    assert repo.search("!!!" if path == "no-tokens" else QUERY, selected_doc_ids=selected) == []
    assert server.requests[offset:] == []
