"""Provider and vector-cache contract tests; all HTTP responses are explicit test doubles."""
import json

import httpx
import numpy as np
import pytest

from backend.core.config import settings
from backend.providers.embedding_provider import EmbeddingError, EmbeddingProvider
from backend.repositories.workspace_repository import WorkspaceRepository, create_ollama_embed_fn
from backend.services.document_service import DocumentService


MODEL = "qwen3-embedding:0.6b"


class OllamaStub:
    def __init__(self, dimension=3, digest="digest-v1", model=MODEL):
        self.dimension, self.digest, self.model = dimension, digest, model
        self.requests = []
        self.failure = None

    def __call__(self, request):
        self.requests.append(request)
        if self.failure:
            return self.failure(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": self.model, "digest": self.digest}]})
        assert request.url.path == "/api/embed"
        payload = json.loads(request.content)
        assert payload["model"] == self.model
        assert payload["truncate"] is False
        return httpx.Response(200, json={
            "model": self.model,
            "embeddings": [[3., 4.] + [0.] * (self.dimension - 2) for _ in payload["input"]],
        })

    def provider(self):
        return EmbeddingProvider(self.model, base_url="http://ollama.test:11434",
                                 transport=httpx.MockTransport(self))

    def inputs(self):
        return [json.loads(r.content)["input"] for r in self.requests if r.url.path == "/api/embed"]


def test_success_discovers_dimension_and_applies_query_format_and_l2():
    stub = OllamaStub(dimension=7)
    provider = stub.provider()
    assert callable(provider.get_embed_fn()) and stub.requests == []
    docs = provider.embed_texts(["TCP delivers ordered data.", "UDP is connectionless."])
    query = provider.embed_queries(["How does TCP work?"])
    assert docs.shape == (2, 7) and query.shape == (1, 7)
    assert docs.dtype == query.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(docs, axis=1), 1.)
    np.testing.assert_allclose(np.linalg.norm(query, axis=1), 1.)
    assert provider.dimension == 7 and provider.model_digest == stub.digest
    assert provider.using_ollama and not provider.using_hash_fallback
    assert not hasattr(provider, "_hash_vectorizer")
    assert stub.inputs()[1] == ["TCP delivers ordered data.", "UDP is connectionless."]
    assert stub.inputs()[2] == [f"Instruct: {provider.query_instruction}\nQuery:How does TCP work?"]
    assert provider.embed_texts([]).shape == (0, 7)


@pytest.mark.parametrize("exception,code", [
    (httpx.ReadTimeout, "EMBEDDING_TIMEOUT"),
    (httpx.ConnectTimeout, "EMBEDDING_TIMEOUT"),
    (httpx.ConnectError, "EMBEDDING_PROVIDER_FAILURE"),
])
@pytest.mark.parametrize("after_load", [False, True])
def test_transport_failure_never_falls_back(exception, code, after_load):
    stub = OllamaStub()
    provider = stub.provider()
    if after_load:
        provider.load_model()

    def fail(request):
        assert request.extensions["timeout"]["connect"] == 2.
        assert request.extensions["timeout"]["read"] == settings.ollama_embed_timeout
        raise exception("simulated failure", request=request)

    stub.failure = fail
    with pytest.raises(EmbeddingError, match=code):
        provider.embed_texts(["document"])
    assert not provider.using_hash_fallback and not provider.is_available


@pytest.mark.parametrize("status", [404, 500])
def test_http_failure_is_explicit(status):
    stub = OllamaStub()
    stub.failure = lambda request: httpx.Response(status, json={"error": "model unavailable"})
    code = "MODEL_MISSING" if status == 404 else "PROVIDER_FAILURE"
    with pytest.raises(EmbeddingError, match=code):
        stub.provider().embed_queries(["query"])


def test_missing_model_inventory_has_pull_instruction():
    provider = EmbeddingProvider(MODEL, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"models": []})))
    with pytest.raises(EmbeddingError, match=f"ollama pull {MODEL}"):
        provider.embed_texts(["document"])


@pytest.mark.parametrize("body", [
    "not json", "[]", '{"error":"failed"}', '{}',
    json.dumps({"model": "other", "embeddings": [[1, 2, 3]]}),
    json.dumps({"model": MODEL, "embeddings": []}),
    json.dumps({"model": MODEL, "embeddings": [[1, 2], [1]]}),
    json.dumps({"model": MODEL, "embeddings": [[0, 0, 0]]}),
    json.dumps({"model": MODEL, "embeddings": [[float("nan"), 1, 2]]}),
    json.dumps({"model": MODEL, "embeddings": [[float("inf"), 1, 2]]}),
    json.dumps({"model": MODEL, "embeddings": [[True, False]]}),
    json.dumps({"model": MODEL, "embeddings": [["1", "2"]]}),
    json.dumps({"model": MODEL, "embeddings": [1, 2, 3]}),
])
def test_malformed_response_is_rejected(body):
    stub = OllamaStub()
    provider = stub.provider()
    provider.load_model()
    stub.failure = lambda request: (
        httpx.Response(200, json={"models": [{"name": MODEL, "digest": stub.digest}]})
        if request.url.path == "/api/tags" else httpx.Response(200, content=body.encode()))
    with pytest.raises(EmbeddingError, match="EMBEDDING_INVALID"):
        provider.embed_texts(["document"])


def test_document_query_dimension_mismatch_is_rejected():
    stub = OllamaStub()
    provider = stub.provider()
    provider.embed_texts(["document"])
    stub.dimension = 4
    with pytest.raises(EmbeddingError, match="DIMENSION_MISMATCH: expected 3, got 4"):
        provider.embed_queries(["query"])


def test_model_digest_change_requires_new_provider_and_index():
    stub = OllamaStub()
    provider = stub.provider()
    provider.load_model()
    stub.digest = "digest-v2"
    with pytest.raises(EmbeddingError, match="MODEL_CHANGED"):
        provider.embed_texts(["document"])


@pytest.mark.parametrize("change", ["model", "digest", "dimension", "instruction"])
def test_cache_identity_covers_model_version_dimension_instruction(change):
    original = OllamaStub().provider().index_id
    stub = OllamaStub(dimension=5 if change == "dimension" else 3,
                      digest="new-digest" if change == "digest" else "digest-v1",
                      model="other-embedding:version" if change == "model" else MODEL)
    provider = stub.provider()
    if change == "instruction":
        provider.query_instruction = "Retrieve relevant workspace evidence"
    assert provider.index_id != original


def test_ingestion_and_retrieval_use_same_provider_and_ignore_legacy_cache():
    stub = OllamaStub(dimension=8)
    provider = stub.provider()
    repo = WorkspaceRepository(embed_fn=provider.get_embed_fn())
    service = DocumentService(repo)
    result = service.ingest_file("tcp.txt", b"TCP delivers ordered reliable data.")
    chunk = repo.chunks[0]
    # Baseline cache entries lack model/digest/policy and must never be reused.
    repo._chunk_embeddings[chunk.chunk_id] = np.ones(384)
    repo._query_embeddings["How does TCP work?"] = np.ones((1, 384))
    hits = repo.search("How does TCP work?", selected_doc_ids=[result["document"].doc_id])
    assert hits and hits[0].doc_id == "tcp.txt"
    assert stub.inputs()[1] == [chunk.text]  # ingestion really embedded the document
    assert stub.inputs()[2][0].startswith("Instruct:")
    requests = len(stub.requests)
    repo.search("How does TCP work?", selected_doc_ids=["tcp.txt"])
    assert [request.url.path for request in stub.requests[requests:]] == ["/api/tags"]
    assert len(repo._chunk_embeddings[chunk.chunk_id]) == 384  # old cache preserved
    assert repo.search("query", selected_doc_ids=[]) == []


def test_changing_encoder_preserves_old_cache_without_mixing_vectors():
    old = OllamaStub(dimension=3).provider()
    repo = WorkspaceRepository(embed_fn=old.get_embed_fn())
    DocumentService(repo).ingest_file("doc.txt", b"TCP delivers ordered reliable data.")
    repo.search("TCP data")
    old_keys = set(repo._chunk_embeddings)
    old_queries = set(repo._query_embeddings)
    new_stub = OllamaStub(dimension=9, digest="new-model-version")
    repo.set_embed_fn(new_stub.provider().get_embed_fn())
    repo.search("TCP data")
    assert old_keys < set(repo._chunk_embeddings)
    assert old_queries < set(repo._query_embeddings)
    assert any(row.shape == (9,) for row in repo._chunk_embeddings.values())
    assert len(new_stub.inputs()) == 3  # probe, query, document


def test_ingestion_failure_does_not_publish_document_or_partial_cache():
    stub = OllamaStub()
    provider = stub.provider()
    repo = WorkspaceRepository(embed_fn=provider.get_embed_fn())
    service = DocumentService(repo)
    service.ingest_file("old.txt", b"Existing document.")
    old_chunks, old_keys = list(repo.chunks), set(repo._chunk_embeddings)
    stub.dimension = 4
    with pytest.raises(EmbeddingError, match="DIMENSION_MISMATCH"):
        service.ingest_file("new.txt", b"New document.")
    assert list(repo.documents) == ["old.txt"]
    assert repo.chunks == old_chunks and set(repo._chunk_embeddings) == old_keys


def test_retrieval_failure_is_not_silently_downgraded_to_bm25():
    stub = OllamaStub()
    repo = WorkspaceRepository(embed_fn=stub.provider().get_embed_fn())
    DocumentService(repo).ingest_file("doc.txt", b"TCP delivers ordered reliable data.")
    stub.failure = lambda request: httpx.Response(503, json={"error": "unavailable"})
    with pytest.raises(EmbeddingError, match="PROVIDER_FAILURE"):
        repo.search("TCP")
    assert repo._query_embeddings == {}


def test_repository_rejects_injected_document_query_dimension_mismatch():
    repo = WorkspaceRepository(embed_fn=lambda texts: [[1., 0., 0.] for _ in texts])
    DocumentService(repo).ingest_file("doc.txt", b"TCP data.")
    # Change output in-place without replacing the encoder identity.
    repo._embed_fn = lambda texts: [[1., 0.] for _ in texts]
    # Carry an invalid namespaced cache entry into the query's new space.
    space = repo._embedding_space()
    repo._chunk_embeddings[repo._chunk_embedding_key(repo.chunks[0], space)] = np.ones(3)
    with pytest.raises(EmbeddingError, match="DIMENSION_MISMATCH"):
        repo.search("TCP")


def test_compatibility_factory_uses_provider_singleton():
    from backend.providers.embedding_provider import embedding_provider
    assert create_ollama_embed_fn().__self__ is embedding_provider


def test_failed_later_batch_never_publishes_partial_ingestion():
    stub = OllamaStub()
    provider = stub.provider()
    provider.batch_size = 1
    repo = WorkspaceRepository(embed_fn=provider.get_embed_fn())
    service = DocumentService(repo)
    service.ingest_file("existing.txt", b"Existing document.")
    original_keys = set(repo._chunk_embeddings)

    def fail_second_batch(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": MODEL, "digest": stub.digest}]})
        texts = json.loads(request.content)["input"]
        if texts == ["Second page."]:
            raise httpx.ReadTimeout("second batch timeout", request=request)
        return httpx.Response(200, json={"model": MODEL, "embeddings": [[3., 4., 0.] for _ in texts]})

    stub.failure = fail_second_batch
    with pytest.raises(EmbeddingError, match="EMBEDDING_TIMEOUT"):
        service.ingest_file("two-pages.txt", b"First page.\fSecond page.")
    assert list(repo.documents) == ["existing.txt"]
    assert len(repo.chunks) == 1 and set(repo._chunk_embeddings) == original_keys


def test_changed_chunk_text_is_reembedded_even_with_same_chunk_id():
    stub = OllamaStub()
    repo = WorkspaceRepository(embed_fn=stub.provider().get_embed_fn())
    DocumentService(repo).ingest_file("doc.txt", b"Original TCP data.")
    old_keys = set(repo._chunk_embeddings)
    repo.chunks[0].text = "Updated TCP data."
    repo.search("TCP")
    assert ["Updated TCP data."] in stub.inputs()
    assert old_keys < set(repo._chunk_embeddings)


def test_no_source_abstention_does_not_call_unavailable_provider():
    from backend.services.qa_service import QAService
    stub = OllamaStub()
    repo = WorkspaceRepository(embed_fn=stub.provider().get_embed_fn())
    response = QAService(repository=repo).answer_question("TCP?", selected_doc_ids=[])
    assert response["status"] == "ABSTAINED_NO_SOURCE_SELECTED"
    assert stub.requests == []


def test_upload_api_returns_explicit_embedding_failure(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.services.document_service import document_service
    stub = OllamaStub()
    stub.failure = lambda request: httpx.Response(503, json={"error": "unavailable"})
    repo = WorkspaceRepository(embed_fn=stub.provider().get_embed_fn())
    monkeypatch.setattr(document_service, "repository", repo)
    response = TestClient(app).post("/api/documents/upload", files={"file": ("tcp.txt", b"TCP data.")})
    assert response.status_code == 503
    assert response.json() == {"detail": "EMBEDDING_PROVIDER_FAILURE: Semantic embedding is unavailable."}
    assert repo.documents == {} and repo.chunks == []
    assert repo._chunk_embeddings == repo._query_embeddings == {}


def test_chat_api_returns_503_with_embedding_error_code(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.services.qa_service import qa_service
    stub = OllamaStub()
    repo = WorkspaceRepository(embed_fn=stub.provider().get_embed_fn())
    DocumentService(repo).ingest_file("tcp.txt", b"TCP provides ordered reliable data delivery.")
    stub.failure = lambda request: httpx.Response(503, json={"error": "unavailable"})
    monkeypatch.setattr(qa_service, "repository", repo)
    response = TestClient(app).post("/api/chat", json={
        "query": "How does TCP deliver data?", "selected_doc_ids": ["tcp.txt"],
    })
    assert response.status_code == 503
    assert response.json() == {"detail": "EMBEDDING_PROVIDER_FAILURE: Semantic embedding is unavailable."}
    assert repo._query_embeddings == {}


@pytest.fixture
def semantic_api(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.services.document_service import document_service
    from backend.services.qa_service import qa_service

    stub = OllamaStub()
    provider = stub.provider()
    repo = WorkspaceRepository(embed_fn=provider.get_embed_fn())
    DocumentService(repo).ingest_file("existing.txt", b"TCP provides ordered reliable data delivery.")
    repo.search("TCP data", selected_doc_ids=["existing.txt"])
    monkeypatch.setattr(document_service, "repository", repo)
    monkeypatch.setattr(qa_service, "repository", repo)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(app.state, "f1_embedding_error", None, raising=False)
    # No lifespan here: startup has its own suite; all provider HTTP uses MockTransport.
    client = TestClient(app, raise_server_exceptions=False)
    yield client, repo, stub, provider
    client.close()


def _semantic_api_request(client, endpoint):
    if endpoint == "upload":
        return client.post("/api/documents/upload", files={"file": ("new.txt", b"First new page.\fSecond new page.")})
    if endpoint == "import":
        return client.post("/api/documents/import-url", json={"url": "https://example.test/reference", "title": "Imported"})
    return client.post("/api/chat", json={"query": "How does TCP deliver data?", "selected_doc_ids": ["existing.txt"]})


def _repository_snapshot(repo):
    return {
        "documents": {key: value.model_dump() for key, value in repo.documents.items()},
        "chunks": [chunk.model_dump() for chunk in repo.chunks],
        "vectors": {key: value.copy() for key, value in repo._chunk_embeddings.items()},
        "queries": {key: value.copy() for key, value in repo._query_embeddings.items()},
        "dimensions": dict(repo._embedding_dimensions), "bm25": repo._bm25,
    }


def _assert_repository_unchanged(repo, before):
    assert {key: value.model_dump() for key, value in repo.documents.items()} == before["documents"]
    assert [chunk.model_dump() for chunk in repo.chunks] == before["chunks"]
    assert repo._bm25 is before["bm25"] and repo._embedding_dimensions == before["dimensions"]
    for cache, expected in ((repo._chunk_embeddings, before["vectors"]), (repo._query_embeddings, before["queries"])):
        assert cache.keys() == expected.keys()
        for key, vector in expected.items():
            np.testing.assert_array_equal(cache[key], vector)


@pytest.mark.parametrize("endpoint", ["upload", "import", "chat"])
@pytest.mark.parametrize("loaded", [False, True], ids=["cold", "loaded"])
@pytest.mark.parametrize("failure,code", [
    ("read-timeout", "EMBEDDING_TIMEOUT"),
    ("connect-timeout", "EMBEDDING_TIMEOUT"),
    ("connection", "EMBEDDING_PROVIDER_FAILURE"),
    ("model-missing", "EMBEDDING_MODEL_MISSING"),
    ("http-503", "EMBEDDING_PROVIDER_FAILURE"),
])
def test_api_embedding_unavailable_is_sanitized_503_and_atomic(semantic_api, endpoint, loaded, failure, code):
    client, repo, stub, _ = semantic_api
    if not loaded:
        repo.set_embed_fn(stub.provider().get_embed_fn())
    before = _repository_snapshot(repo)
    previous_requests = len(stub.requests)

    def fail(request):
        private = "private-exception-detail http://internal-ollama:11434 Traceback"
        if failure in {"read-timeout", "connect-timeout", "connection"}:
            error = {"read-timeout": httpx.ReadTimeout, "connect-timeout": httpx.ConnectTimeout,
                     "connection": httpx.ConnectError}[failure]
            raise error(private, request=request)
        if failure == "model-missing":
            return httpx.Response(200, json={"models": []}) if request.url.path == "/api/tags" else httpx.Response(404)
        return httpx.Response(503, json={"error": private})

    stub.failure = fail
    response = _semantic_api_request(client, endpoint)
    assert len(stub.requests) > previous_requests  # The real provider path, through a fake transport, failed.
    assert response.status_code == 503
    assert response.json() == {"detail": f"{code}: Semantic embedding is unavailable."}
    assert "ollama.test" not in response.text and "private-exception-detail" not in response.text
    assert "Traceback" not in response.text and MODEL not in response.text
    _assert_repository_unchanged(repo, before)


@pytest.mark.parametrize("endpoint", ["upload", "import"])
def test_api_later_embedding_batch_failure_does_not_publish_partial_ingestion(semantic_api, endpoint):
    client, repo, stub, provider = semantic_api
    provider.batch_size = 1
    before = _repository_snapshot(repo)
    batches = []

    def second_batch_fails(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": MODEL, "digest": stub.digest}]})
        texts = json.loads(request.content)["input"]
        batches.append(texts)
        if len(batches) == 2:
            raise httpx.ReadTimeout("private second-batch failure", request=request)
        return httpx.Response(200, json={"model": MODEL, "embeddings": [[3., 4., 0.] for _ in texts]})

    stub.failure = second_batch_fails
    if endpoint == "import":
        # A long valid reference URL yields two chunks without mocking ingestion.
        response = client.post("/api/documents/import-url", json={
            "url": "https://example.test/" + "evidence/" * 140, "title": "Imported"})
    else:
        response = _semantic_api_request(client, endpoint)
    assert len(batches) == 2  # One successful vector batch preceded the failure.
    assert response.status_code == 503
    assert response.json() == {"detail": "EMBEDDING_TIMEOUT: Semantic embedding is unavailable."}
    _assert_repository_unchanged(repo, before)


@pytest.mark.parametrize("endpoint", ["upload", "import", "chat"])
def test_api_semantic_success_publishes_complete_results(semantic_api, endpoint):
    client, repo, stub, _ = semantic_api
    response = _semantic_api_request(client, endpoint)
    assert response.status_code == 200, response.text
    assert len(repo._chunk_embeddings) == len(repo.chunks)
    if endpoint == "chat":
        # Embedding success does not verify the development generator's prose.
        assert response.json()["status"] == "ABSTAINED_INSUFFICIENT_EVIDENCE"
        assert response.json()["validated_claims"] == []
        assert len(repo._query_embeddings) == 2
    else:
        body = response.json()
        assert body["status"] == "INGESTED"
        doc_id = body["document"]["doc_id"]
        assert doc_id in repo.documents
        assert len(repo.get_document_chunks(doc_id)) == body["chunks_count"] > 0
        requests = len(stub.requests)
        duplicate = _semantic_api_request(client, endpoint)
        assert duplicate.status_code == 200 and duplicate.json()["status"] == "ALREADY_EXISTS"
        assert len(stub.requests) == requests


@pytest.mark.parametrize("endpoint,method", [("upload", "ingest_file"), ("import", "import_url"), ("chat", "answer_question")])
@pytest.mark.parametrize("error_type", [RuntimeError, KeyError])
def test_api_internal_errors_remain_500_without_exception_details(semantic_api, monkeypatch, endpoint, method, error_type):
    from backend.services.document_service import document_service
    from backend.services.qa_service import qa_service

    client, repo, _, _ = semantic_api
    before = _repository_snapshot(repo)

    def fail(*_args, **_kwargs):
        raise error_type("EMBEDDING_TIMEOUT: private-internal-detail http://internal-ollama:11434 Traceback")

    service = qa_service if endpoint == "chat" else document_service
    monkeypatch.setattr(service, method, fail)
    response = _semantic_api_request(client, endpoint)
    assert response.status_code == 500
    assert "EMBEDDING_" not in response.text and "private-internal-detail" not in response.text
    assert "internal-ollama" not in response.text and "Traceback" not in response.text
    _assert_repository_unchanged(repo, before)


@pytest.mark.parametrize("code", [
    "EMBEDDING_TIMEOUT", "EMBEDDING_PROVIDER_FAILURE", "EMBEDDING_MODEL_MISSING", "EMBEDDING_NOT_READY",
    "EMBEDDING_MODEL_CHANGED", "EMBEDDING_DIMENSION_MISMATCH", "EMBEDDING_INVALID_CONFIG",
    "EMBEDDING_INVALID_INPUT", "EMBEDDING_INVALID_RESPONSE", "EMBEDDING_INVALID_VECTOR",
    "UNTRUSTED_ERROR", "EMBEDDING_TIMEOUT\nprivate", "EMBEDDING_PRIVATE_DETAIL",
])
def test_api_embedding_handler_only_exposes_known_codes(semantic_api, monkeypatch, code):
    from backend.services.qa_service import qa_service

    client, _, _, _ = semantic_api

    def fail(*_args, **_kwargs):
        raise EmbeddingError(f"{code}: private-details http://internal-ollama:11434 Traceback")

    monkeypatch.setattr(qa_service, "answer_question", fail)
    response = _semantic_api_request(client, "chat")
    expected = "EMBEDDING_PROVIDER_FAILURE" if code in {
        "UNTRUSTED_ERROR", "EMBEDDING_TIMEOUT\nprivate", "EMBEDDING_PRIVATE_DETAIL"} else code
    assert response.status_code == 503
    assert response.json() == {"detail": f"{expected}: Semantic embedding is unavailable."}


def test_api_request_validation_still_uses_400_and_422_without_embedding(semantic_api):
    client, repo, stub, _ = semantic_api
    before = _repository_snapshot(repo)
    requests = len(stub.requests)
    unsupported = client.post("/api/documents/upload", files={"file": ("unsupported.exe", b"invalid file")})
    empty = client.post("/api/documents/upload", files={"file": ("empty.txt", b"")})
    invalid_import = client.post("/api/documents/import-url", json={"url": "https://example.test"})
    assert unsupported.status_code == empty.status_code == 400
    assert invalid_import.status_code == 422
    assert len(stub.requests) == requests
    _assert_repository_unchanged(repo, before)
