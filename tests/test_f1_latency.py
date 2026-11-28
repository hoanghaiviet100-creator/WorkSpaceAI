"""Tool correctness only. Synthetic clock values here are never performance results."""
from contextlib import ExitStack
import csv
import json
from types import SimpleNamespace

import pytest

from benchmarks.f1_latency import observer, run, verify
from benchmarks.f1_latency.common import stats


def test_percentiles_and_empty_population():
    samples = list(range(1, 101))  # mathematical unit inputs, not a latency run
    result = stats(samples)
    assert result["mean_ms"] == 50.5
    assert result["p50_ms"] == 50.5
    assert result["p95_ms"] == pytest.approx(95.05)
    assert result["p99_ms"] == pytest.approx(99.01)
    assert result == verify.distribution(samples)
    assert stats([])["p99_ms"] is None
    with pytest.raises(ValueError):
        stats([float("nan")])


def test_stage_uses_finally_and_preserves_exception_identity(monkeypatch):
    original_error = RuntimeError("unit error")

    def failing():
        raise original_error

    ticks = iter((1.0, 2.0, 2.125))
    monkeypatch.setattr(observer, "perf_counter", lambda: next(ticks))
    trace = {"clock": 0, "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        with pytest.raises(RuntimeError) as observed:
            observer.timed(failing, "test_stage")()
    finally:
        observer.CURRENT.reset(token)
    assert observed.value is original_error
    assert trace["spans"][0]["ms"] == 125  # injected clock, not a measured backend latency
    assert trace["spans"][0]["error_type"] == "RuntimeError"


def test_http_clock_stops_after_complete_body(monkeypatch):
    finished_reading = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            finished_reading.append(True)
            return b'{"status":"ANSWER_VERIFIED","route":"QA_FLOW"}'

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    ticks = iter((1.0, 1.5, 1.6))

    def clock():
        value = next(ticks)
        if value > 1:
            assert finished_reading
        return value

    monkeypatch.setattr(run.urllib.request, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(run, "perf_counter", clock)
    row, parsed, body = run.fetch("http://unit.invalid", "/api/chat", 5, {"query": "unit"})
    assert row["completed_response_ms"] == 500  # injected clock
    assert row["outcome"] == "success" and parsed["status"] == "ANSWER_VERIFIED" and body


def test_timeout_is_not_a_completed_latency(monkeypatch):
    class Opener:
        def open(self, *_args, **_kwargs):
            raise TimeoutError()

    monkeypatch.setattr(run.urllib.request, "build_opener", lambda *_: Opener())
    row, _, body = run.fetch("http://unit.invalid", "/api/chat", 1, {"query": "unit"})
    assert row["outcome"] == "timeout" and row["completed_response_ms"] == "" and body is None
    summary = run.aggregate([dict(row, request_id="unit", phase="measured", scenario="unit")], {}, [{"scenario": "unit"}])
    assert summary["completed_measured"] == 0
    assert summary["groups"]["all_scenarios"]["completed_http"]["p50_ms"] is None


def test_preindexed_document_hash_must_match():
    case = {"scenario": "unit", "request": {"query": "Unit question", "selected_doc_ids": ["actual-id"]},
            "documents": [{"doc_id": "actual-id", "file_hash": "a" * 64, "version_id": "v1", "source_reference": "unit.pdf"}],
            "expected_statuses": ["ANSWER_VERIFIED"]}
    docs = [{"doc_id": "actual-id", "file_hash": "b" * 64, "version_id": "v1", "chunk_count": 1}]
    with pytest.raises(ValueError, match="changed"):
        run.validate_cases({"schema_version": 1, "source_provenance": "unit fixture", "cases": [case]}, docs)


def test_real_router_and_qa_response_is_unchanged_with_observer(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import chat_routes
    from backend.core.config import settings
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.services.document_service import DocumentService
    from backend.services.qa_service import QAService
    import numpy as np

    monkeypatch.setattr(settings, "llm_provider", "mock")  # only this unit test; no performance run
    repo = WorkspaceRepository(embed_fn=lambda texts: np.array([[1., 0., 0.]] * len(texts)))
    qa = QAService(repository=repo)
    monkeypatch.setattr(chat_routes, "qa_service", qa)
    result = DocumentService(repo).ingest_file("unit.txt", b"An Lam training starts at 08:20.\nThe room is B204.")
    payload = {"query": "An Lam training starts at what time?", "selected_doc_ids": [result["document"].doc_id]}
    app = FastAPI()
    app.include_router(chat_routes.router)
    with TestClient(app) as client:
        baseline = client.post("/api/chat", json=payload)
    traced = FastAPI()
    traced.include_router(chat_routes.router)
    trace_path = tmp_path / "backend.jsonl"
    traced.add_middleware(observer.TraceMiddleware, path=trace_path)
    with ExitStack() as stack:
        observer.install(stack)
        with TestClient(traced) as client:
            response = client.post("/api/chat", json=payload, headers={"X-F1-Benchmark-ID": "unit"})
    assert response.status_code == baseline.status_code == 200
    assert response.content == baseline.content
    # The observer preserves M2 abstention for unverified mock prose.
    assert response.json()["status"] == "ABSTAINED_INSUFFICIENT_EVIDENCE"
    trace = json.loads(trace_path.read_text())
    stages = {s["stage"] for s in trace["spans"]}
    assert {"retrieval_search", "llm_generation", "citation_match", "claim_alignment"} <= stages
    assert not stages & {"citation_verification", "semantic_review", "llm_support", "retrieval_fallback"}
    assert "deterministic_fallback_used" in run.trace_errors(trace, {})
    assert "no_real_provider_output" in run.trace_errors(trace, {})
    assert trace["backend_completed_ms"] >= 0
    assert "An Lam" not in trace_path.read_text()  # no document or answer text in telemetry


def test_stage_populations_do_not_turn_missing_llm_into_zero():
    rows = [{"request_id": "w", "phase": "warmup", "scenario": "unit", "outcome": "success", "completed_response_ms": 9999},
            {"request_id": "m", "phase": "measured", "scenario": "unit", "outcome": "success", "completed_response_ms": 25}]
    trace = {"request_id": "m", "backend_completed_ms": 20,
             "spans": [{"stage": "retrieval_search", "ms": 2}, {"stage": "retrieval_search", "ms": 3}]}
    result = run.aggregate(rows, {"m": trace}, [{"scenario": "unit", "requires_stages": ["retrieval_search"]}])
    assert result["groups"]["all_scenarios"]["completed_http"]["mean_ms"] == 25
    assert result["stage_ms"]["retrieval_search"]["mean_ms"] == 5
    assert result["stage_ms"]["llm_generation"]["n"] == 0
    assert result["stage_ms"]["llm_generation"]["mean_ms"] is None


def test_missing_runtime_cannot_emit_numbers_or_pass(tmp_path, monkeypatch):
    target = tmp_path / "blocked"
    paths = []

    def unavailable(_base, path, *_args):
        paths.append(path)
        return {"outcome": "transport_error", "error_type": "ConnectionRefusedError"}, None, None

    monkeypatch.setattr(run, "fetch", unavailable)
    monkeypatch.setattr(run, "provenance", lambda: {"test_only": True})
    monkeypatch.setattr(run.sys, "argv", ["run", "--base-url", "http://unit.invalid",
                                         "--output", str(target), "--preflight-only"])
    assert run.main() == 2
    assert paths == ["/__f1_latency/metadata", "/api/documents"]
    assert list(csv.DictReader((target / "measured.csv").open())) == []
    report = verify.audit(target)
    assert report["integrity"] == "PASS" and report["verdict"] == "NEEDS_EVIDENCE"
    summary = json.loads((target / "aggregate.json").read_text())
    summary["groups"]["all_scenarios"]["completed_http"]["p95_ms"] = 0
    (target / "aggregate.json").write_text(json.dumps(summary))
    assert verify.audit(target)["integrity"] == "FAIL"


def test_server_metadata_is_read_only_and_excludes_credentials(tmp_path, monkeypatch):
    """Controlled metadata responses only; no inference or performance evidence."""
    import httpx
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend import main as backend
    from backend.core.config import settings
    from benchmarks.f1_latency import server

    application = FastAPI()
    monkeypatch.setattr(backend, "app", application)
    monkeypatch.setattr(server, "provenance", lambda: {"commit": "a" * 40, "branch": "unit", "hardware": {}})
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "gemini_api_key", "private-unit-credential")
    monkeypatch.setenv("F1_LATENCY_TRACE", str(tmp_path / "trace.jsonl"))
    monkeypatch.delenv("F1_LATENCY_SOURCE_MANIFEST", raising=False)
    requests = []

    class ProviderClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, url):
            requests.append(url)
            data = {"version": "unit", "models": [{"name": "unit-model", "digest": "unit-digest", "secret": "do-not-copy"}]}
            return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "Client", ProviderClient)
    original_model = settings.ollama_model
    with TestClient(server.create_app()) as client:
        response = client.get("/__f1_latency/metadata")
    assert response.status_code == 200
    assert response.json()["request_schema"]["properties"]["query"]["type"] == "string"
    assert response.json()["model_inventory"]["tags"][0]["digest"] == "unit-digest"
    assert len(requests) == 3 and all("/api/" in url for url in requests)
    assert "private-unit-credential" not in response.text and "do-not-copy" not in response.text
    assert settings.ollama_model == original_model


def test_main_query_and_chunk_cache_are_observed_without_reembedding():
    import numpy as np
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.services.document_service import DocumentService

    calls = []

    def embed(texts):
        calls.append(list(texts))
        return np.array([[1., 0., 0.]] * len(texts))

    repo = WorkspaceRepository(embed_fn=embed)
    doc = DocumentService(repo).ingest_file("cache.txt", b"An Lam training starts at 08:20.")["document"]
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        wrapped = observer.observed_search(repo.__class__.search)
        first = wrapped(repo, "An Lam training", selected_doc_ids=[doc.doc_id])
        previous_calls = len(calls)
        second = wrapped(repo, "An Lam training", selected_doc_ids=[doc.doc_id])
    finally:
        observer.CURRENT.reset(token)
    assert first == second and len(calls) == previous_calls
    assert trace["cache_observations"][0]["query_cache_hit_observed"] is False
    assert trace["cache_observations"][1]["query_cache_hit_observed"] is True
    assert trace["cache_observations"][1]["chunk_embeddings_present_before"] == 1


@pytest.mark.parametrize("hit", [False, True], ids=["miss", "hit"])
def test_observer_legacy_cache_membership_preserves_call_and_cache_identity(hit):
    chunk = SimpleNamespace(chunk_id="chunk-1", doc_id="doc-1", doc_name="cache.txt")
    query = "legacy query"
    query_vector, chunk_vector = object(), object()
    queries = {query: query_vector} if hit else {}
    chunks = {chunk.chunk_id: chunk_vector} if hit else {}
    repo = SimpleNamespace(chunks=[chunk], _query_embeddings=queries, _chunk_embeddings=chunks,
                           _bm25=object(), dense_available=True, _embed_fn=lambda _: pytest.fail("observer embedded"))
    result = [chunk]
    calls = []

    def search(actual_repo, actual_query, *args, **kwargs):
        calls.append((actual_repo, actual_query, args, kwargs))
        assert actual_repo._query_embeddings is queries and actual_repo._chunk_embeddings is chunks
        assert (query in queries) is hit and (chunk.chunk_id in chunks) is hit
        queries[query] = query_vector
        chunks[chunk.chunk_id] = chunk_vector
        return result

    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        assert observer.observed_search(search)(repo, query, 3, selected_doc_ids=["doc-1"]) is result
    finally:
        observer.CURRENT.reset(token)
    assert calls == [(repo, query, (3,), {"selected_doc_ids": ["doc-1"]})]
    cache, = trace["cache_observations"]
    assert cache["query_present_before"] is hit
    assert cache["query_cache_hit_observed"] is hit
    assert cache["chunk_embeddings_present_before"] == int(hit)
    assert cache["query_cache_entries_after"] == cache["chunk_cache_entries_after"] == 1
    assert queries[query] is query_vector and chunks[chunk.chunk_id] is chunk_vector


@pytest.fixture
def observer_cache_repository():
    import numpy as np
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.services.document_service import DocumentService

    calls = []

    def embed(texts):
        calls.append(list(texts))
        return np.array([[1., 0., 0.]] * len(texts))

    repo = WorkspaceRepository(embed_fn=embed)
    DocumentService(repo).ingest_file("cache.txt", b"An Lam training starts at 08:20.")
    return repo, calls


@pytest.mark.parametrize("stale", ["legacy", "other-space", "wrong-role", "none-value"])
def test_observer_p0_cache_miss_ignores_unusable_entries(observer_cache_repository, stale):
    import numpy as np

    repo, calls = observer_cache_repository
    query = "An Lam training"
    chunk = repo.chunks[0]
    space = repo._embedding_space()
    repo._chunk_embeddings.clear()
    query_key = (space, "query", query)
    chunk_key = repo._chunk_embedding_key(chunk, space)
    if stale == "legacy":
        query_key, chunk_key = query, chunk.chunk_id
    elif stale == "other-space":
        query_key = ("old-space", "query", query)
        chunk_key = repo._chunk_embedding_key(chunk, "old-space")
    elif stale == "wrong-role":
        query_key = (space, "document", query)
        chunk_key = (space, "query", *chunk_key[2:])
    # A None query value is a miss even when its key belongs to the active space.
    repo._query_embeddings[query_key] = None if stale == "none-value" else np.ones((1, 3))
    if stale != "none-value":
        repo._chunk_embeddings[chunk_key] = np.ones(3)
    old_queries, old_chunks = dict(repo._query_embeddings), dict(repo._chunk_embeddings)
    query_cache, chunk_cache = repo._query_embeddings, repo._chunk_embeddings
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        wrapped = observer.observed_search(type(repo).search)
        previous_calls = len(calls)
        first = wrapped(repo, query, selected_doc_ids=[chunk.doc_id])
        assert len(calls) == previous_calls + 2  # real test-double query and document embedding
        second = wrapped(repo, query, selected_doc_ids=[chunk.doc_id])
    finally:
        observer.CURRENT.reset(token)
    assert first == second and len(calls) == previous_calls + 2
    cold, warm = trace["cache_observations"]
    assert cold["query_present_before"] is cold["query_cache_hit_observed"] is False
    assert cold["chunk_embeddings_present_before"] == 0
    assert warm["query_present_before"] is warm["query_cache_hit_observed"] is True
    assert warm["chunk_embeddings_present_before"] == 1
    assert repo._query_embeddings is query_cache and repo._chunk_embeddings is chunk_cache
    for key, value in old_queries.items():
        if value is not None:
            assert query_cache[key] is value
    assert all(chunk_cache[key] is value for key, value in old_chunks.items())


@pytest.mark.parametrize("change", ["generation", "encoder", "provider-index"])
def test_observer_p0_namespace_change_is_a_miss_then_a_hit(observer_cache_repository, change):
    import numpy as np

    repo, calls = observer_cache_repository
    query = "An Lam training"
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        wrapped = observer.observed_search(type(repo).search)
        wrapped(repo, query)
        wrapped(repo, query)
        old_queries, old_chunks = dict(repo._query_embeddings), dict(repo._chunk_embeddings)
        old_space = repo._embedding_space()
        if change == "generation":
            repo.set_embed_fn(repo._embed_fn)
        elif change == "provider-index":
            repo._embed_fn.index_id = "changed-model-digest-dimension-policy"
        else:
            def new_embed(texts):
                calls.append(list(texts))
                return np.array([[1., 0., 0., 0., 0.]] * len(texts))

            repo.set_embed_fn(new_embed)
        assert repo._embedding_space() != old_space
        previous_calls = len(calls)
        first = wrapped(repo, query)
        assert len(calls) == previous_calls + 2
        second = wrapped(repo, query)
    finally:
        observer.CURRENT.reset(token)
    assert first == second and len(calls) == previous_calls + 2
    assert [c["query_cache_hit_observed"] for c in trace["cache_observations"]] == [False, True, False, True]
    assert [c["chunk_embeddings_present_before"] for c in trace["cache_observations"]] == [1, 1, 0, 1]
    assert all(repo._query_embeddings[key] is value for key, value in old_queries.items())
    assert all(repo._chunk_embeddings[key] is value for key, value in old_chunks.items())


@pytest.mark.parametrize("field", ["text", "doc_version", "doc_hash"])
def test_observer_p0_changed_document_identity_is_a_chunk_miss(observer_cache_repository, field):
    repo, calls = observer_cache_repository
    query = "An Lam training"
    repo.search(query)
    chunk = repo.chunks[0]
    old_chunks = dict(repo._chunk_embeddings)
    setattr(chunk, field, getattr(chunk, field) + " updated")
    previous_calls = len(calls)
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        wrapped = observer.observed_search(type(repo).search)
        wrapped(repo, query)
        wrapped(repo, query)
    finally:
        observer.CURRENT.reset(token)
    cold, warm = trace["cache_observations"]
    assert cold["query_cache_hit_observed"] is warm["query_cache_hit_observed"] is True
    assert cold["chunk_embeddings_present_before"] == 0
    assert warm["chunk_embeddings_present_before"] == 1
    assert len(calls) == previous_calls + 1
    assert all(repo._chunk_embeddings[key] is value for key, value in old_chunks.items())


@pytest.mark.parametrize("path", ["empty-selection", "missing-document", "no-tokens", "dense-disabled", "no-chunks"])
def test_observer_p0_no_dense_lookup_does_not_initialize_provider(path):
    import httpx
    from backend.providers.embedding_provider import EmbeddingProvider
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.services.document_service import DocumentService

    requests = []

    def forbidden(request):
        requests.append(request)
        pytest.fail("observer initialized a lazy provider on a path with no dense lookup")

    repo = WorkspaceRepository()
    if path != "no-chunks":
        DocumentService(repo).ingest_file("cache.txt", b"An Lam training starts at 08:20.")
    provider = EmbeddingProvider(transport=httpx.MockTransport(forbidden))
    repo.set_embed_fn(provider.get_embed_fn())
    query, selected = "An Lam training", None
    if path == "empty-selection":
        selected = []
    elif path == "missing-document":
        selected = ["absent.txt"]
    elif path == "no-tokens":
        query = "!!!"
    elif path == "dense-disabled":
        repo.dense_available = False
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        result = observer.observed_search(type(repo).search)(repo, query, selected_doc_ids=selected)
    finally:
        observer.CURRENT.reset(token)
    assert bool(result) is (path == "dense-disabled")
    assert requests == [] and provider.dimension is None
    cache, = trace["cache_observations"]
    assert cache["query_cache_hit_observed"] is False
    assert cache["query_present_before"] is cache["chunk_embeddings_present_before"] is None
    assert repo._query_embeddings == repo._chunk_embeddings == {}


def test_observer_p0_lazy_provider_matches_unobserved_requests_and_results():
    import httpx
    from backend.providers.embedding_provider import EmbeddingProvider
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.services.document_service import DocumentService

    def repository(requests):
        def ollama(request):
            payload = json.loads(request.content) if request.content else None
            requests.append((request.method, request.url.path, payload))
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "unit-embedding", "digest": "unit-digest"}]})
            assert request.url.path == "/api/embed"
            return httpx.Response(200, json={"model": "unit-embedding",
                                            "embeddings": [[1., 0., 0.] for _ in payload["input"]]})

        provider = EmbeddingProvider("unit-embedding", transport=httpx.MockTransport(ollama))
        repo = WorkspaceRepository()
        DocumentService(repo).ingest_file("cache.txt", b"An Lam training starts at 08:20.")
        repo.set_embed_fn(provider.get_embed_fn())
        assert requests == [] and provider.dimension is None
        return repo

    baseline_requests, observed_requests = [], []
    baseline_repo, observed_repo = repository(baseline_requests), repository(observed_requests)
    query = "An Lam training"
    baseline = [baseline_repo.search(query), baseline_repo.search(query)]
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        wrapped = observer.observed_search(type(observed_repo).search)
        results = [wrapped(observed_repo, query), wrapped(observed_repo, query)]
    finally:
        observer.CURRENT.reset(token)
    assert results == baseline and observed_requests == baseline_requests
    assert [c["query_cache_hit_observed"] for c in trace["cache_observations"]] == [False, True]
    assert [c["chunk_embeddings_present_before"] for c in trace["cache_observations"]] == [0, 1]


def test_observer_p0_failed_namespace_lookup_preserves_original_exception(observer_cache_repository, monkeypatch):
    repo, _ = observer_cache_repository
    error = RuntimeError("unit namespace failure")
    calls = []

    def fail():
        calls.append(True)
        raise error

    monkeypatch.setattr(repo, "_embedding_space", fail)
    before = dict(repo._chunk_embeddings)
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        with pytest.raises(RuntimeError) as caught:
            observer.observed_search(type(repo).search)(repo, "An Lam training")
    finally:
        observer.CURRENT.reset(token)
    assert caught.value is error and calls == [True]
    assert repo._query_embeddings == {}
    assert all(repo._chunk_embeddings[key] is value for key, value in before.items())
    assert trace["spans"][-1]["error_type"] == "RuntimeError"
    cache, = trace["cache_observations"]
    assert cache["query_present_before"] is cache["chunk_embeddings_present_before"] is None
    assert cache["query_cache_entries_after"] == 0 and cache["chunk_cache_entries_after"] == len(before)


def test_provider_timeout_is_visible_and_f1_fails_closed(monkeypatch):
    import httpx
    import numpy as np
    from backend.core.config import settings
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.services.document_service import DocumentService
    from backend.services.qa_service import QAService
    from backend.providers.llm_provider import GenerationError, LLMProvider

    monkeypatch.setattr(settings, "llm_provider", "ollama")  # controlled unit failure, never a benchmark
    provider = LLMProvider()
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: httpx.Response(
        200, json={"models": [{"name": settings.f1_generation_model}]}, request=httpx.Request("GET", url),
    ))

    def fail(*_args, **_kwargs):
        raise httpx.ReadTimeout("unit timeout")

    monkeypatch.setattr(httpx, "post", fail)
    repo = WorkspaceRepository(embed_fn=lambda texts: np.array([[1., 0., 0.]] * len(texts)))
    doc = DocumentService(repo).ingest_file("unit.txt", b"An Lam training starts at 08:20.")["document"]
    qa = QAService(repository=repo, provider=provider)
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        with ExitStack() as stack:
            observer.install(stack)
            with pytest.raises(GenerationError, match="^GENERATION_TIMEOUT$"):
                qa.answer_question("An Lam training starts when?", selected_doc_ids=[doc.doc_id])
    finally:
        observer.CURRENT.reset(token)
    assert any(s["stage"] == "provider_http" and s.get("error_type") == "ReadTimeout" for s in trace["spans"])
    assert any(s["stage"] == "provider_ollama" and s.get("error_type") == "GenerationError" for s in trace["spans"])
    assert not any(s["stage"] == "deterministic_fallback" for s in trace["spans"])
    assert "deterministic_fallback_used" not in run.trace_errors(trace, {})
    assert "no_real_provider_output" in run.trace_errors(trace, {})


def test_main_citation_rejection_abstains_and_observer_preserves_result(monkeypatch):
    import numpy as np
    from backend.core.schemas import GeneratedClaim
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.services.document_service import DocumentService
    from backend.services.qa_service import QAService
    from backend.providers.llm_provider import LLMProvider

    repo = WorkspaceRepository(embed_fn=lambda texts: np.array([[1., 0., 0.]] * len(texts)))
    doc = DocumentService(repo).ingest_file("unit.txt", b"An Lam training starts at 08:20.")["document"]
    provider = LLMProvider()
    claim = GeneratedClaim(claim_text="Unit unsupported statement", cited_doc_id=doc.doc_id, cited_page=1,
                           evidence_quote="zzzz entirely fabricated quantum nebula yyyyyy")
    monkeypatch.setattr(provider, "generate_grounded_qa", lambda *_args, **_kwargs: [claim.model_copy()])
    qa = QAService(repository=repo, provider=provider)
    baseline = qa.answer_question("An Lam training starts when?", selected_doc_ids=[doc.doc_id])
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        with ExitStack() as stack:
            observer.install(stack)
            result = qa.answer_question("An Lam training starts when?", selected_doc_ids=[doc.doc_id])
    finally:
        observer.CURRENT.reset(token)
    # F1-CITATION-01A: the old oracle preserved a verification bypass.
    # An observer must preserve fail-closed abstention when R2 rejects all claims.
    assert result == baseline and result["status"] == "ABSTAINED_INSUFFICIENT_EVIDENCE"
    assert result["validated_claims"] == [] and result["citations"] == []
    assert result["grounding_score"] == 0.0
    assert result["hallucination_flags"][0].evidence_quote == ""
    assert result["hallucination_flags"][0].claim_text == ""
    assert claim.evidence_quote == "zzzz entirely fabricated quantum nebula yyyyyy"
    assert trace["citation_soft_recovery_observed"] is False
    assert next(s for s in trace["spans"] if s["stage"] == "citation_match")["validated_count"] == 0


def test_main_summary_fallback_is_not_accepted_as_model_evidence(monkeypatch):
    import numpy as np
    from backend.core.config import settings
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.services.document_service import DocumentService
    from backend.services.qa_service import QAService

    monkeypatch.setattr(settings, "llm_provider", "mock")
    repo = WorkspaceRepository(embed_fn=lambda texts: np.array([[1., 0., 0.]] * len(texts)))
    doc = DocumentService(repo).ingest_file("unit.txt", b"An Lam training starts at 08:20.")["document"]
    qa = QAService(repository=repo)
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        with ExitStack() as stack:
            observer.install(stack)
            qa.answer_question("Summarize unit.txt", selected_doc_ids=[doc.doc_id])
    finally:
        observer.CURRENT.reset(token)
    assert trace["summary_fallback_observed"] is True
    assert "deterministic_summary_fallback_used" in run.trace_errors(trace, {"requires_stages": ["llm_summary"]})


def test_incomplete_body_is_never_counted_as_completion(monkeypatch):
    import http.client

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            raise http.client.IncompleteRead(b"partial", 100)

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(run.urllib.request, "build_opener", lambda *_: Opener())
    row, _, body = run.fetch("http://unit.invalid", "/api/chat", 5, {"query": "unit"})
    assert row["outcome"] == "transport_error" and row["completed_response_ms"] == "" and body is None


@pytest.mark.parametrize("native", [None, "", "SIMULATED_PRIVATE_TRACE", {"unexpected": "SIMULATED_PRIVATE_TRACE"}])
def test_observer_records_safe_native_thinking_metadata_only(native):
    import httpx

    response = httpx.Response(200, json={"model": "qwen3.5:9b-q4_K_M", "done": True,
                                        "response": "Final answer", "thinking": native})
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return response

    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    payload = {"model": "qwen3.5:9b-q4_K_M", "think": True, "format": "json"}
    try:
        result = observer.observed_post(post)("http://unit.invalid/api/generate", json=payload)
    finally:
        observer.CURRENT.reset(token)
    assert result is response and calls == [("http://unit.invalid/api/generate", {"json": payload})]
    span, = trace["spans"]
    assert span["requested_think"] is True and span["output_format"] == "json"
    assert span["thinking_present"] is (isinstance(native, str) and bool(native))
    assert span["thinking_length"] == (len(native) if isinstance(native, str) else None)
    assert "SIMULATED_PRIVATE_TRACE" not in json.dumps(trace)
    assert "Final answer" not in json.dumps(trace)


def test_observer_does_not_log_schema_or_invalid_thinking_values():
    import httpx

    private = "SIMULATED_PRIVATE_REQUEST_TEXT"
    response = httpx.Response(200, json={"model": "unit", "done": True, "response": "final"})
    trace = {"clock": observer.perf_counter(), "spans": []}
    token = observer.CURRENT.set(trace)
    try:
        result = observer.observed_post(lambda *args, **kwargs: response)(
            "http://unit.invalid/api/generate",
            json={"model": "unit", "think": {"unexpected": private}, "format": {"description": private}},
        )
    finally:
        observer.CURRENT.reset(token)
    assert result is response
    span, = trace["spans"]
    assert span["requested_think"] is None and span["output_format"] == "schema"
    assert span["thinking_present"] is False and span["thinking_length"] is None
    assert private not in json.dumps(trace)
