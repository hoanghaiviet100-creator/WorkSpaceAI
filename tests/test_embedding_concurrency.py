"""Deterministic encoder replacement races; fake vectors and no external services."""
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event, get_ident

import numpy as np
import pytest

from backend.providers.embedding_provider import EmbeddingError
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService


EXISTING_QUERY = "existing TCP evidence"
PENDING_QUERY = "pending TCP evidence"


class Encoder:
    def __init__(self, name, dimension, axis):
        self.index_id = name
        self.dimension = dimension
        self.vector = np.eye(dimension, dtype=np.float32)[axis]
        self.calls = []
        self.pause_kind = None
        self.entered, self.resume = Event(), Event()
        self.main_thread = get_ident()
        self.failure = None

    def _encode(self, texts, kind):
        self.calls.append((kind, tuple(texts)))
        if kind == self.pause_kind and get_ident() != self.main_thread:
            self.entered.set()
            assert self.resume.wait(5), "deadlock: encoder was not released"
        if kind == "document" and self.failure is not None:
            raise self.failure
        return np.tile(self.vector, (len(texts), 1))

    def embed_texts(self, texts):
        return self._encode(texts, "document")

    def embed_queries(self, texts):
        return self._encode(texts, "query")


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
    assert repo._bm25 is before["bm25"]
    assert repo._embedding_dimensions == before["dimensions"]
    for actual, expected in ((repo._chunk_embeddings, before["vectors"]), (repo._query_embeddings, before["queries"])):
        assert actual.keys() == expected.keys()
        for key, vector in expected.items():
            np.testing.assert_array_equal(actual[key], vector)


def assert_namespaces(repo, encoders):
    for cache in (repo._chunk_embeddings, repo._query_embeddings):
        for key, vector in cache.items():
            expected = encoders[key[0]].vector
            if key[1] == "query":
                expected = expected[None, :]
            np.testing.assert_array_equal(vector, expected, err_msg=f"vector published under wrong identity: {key[:2]}")


def prepared_repository(identity="provider"):
    old = Encoder("encoder-A", 3, 0)
    if identity == "injected":
        del old.index_id
    repo = WorkspaceRepository()
    # A legacy/lexical document legitimately has no dense vectors yet.
    DocumentService(repo).ingest_file("pending.txt", b"Pending TCP evidence with page provenance.")
    repo.set_embed_fn(old.embed_texts)
    DocumentService(repo).ingest_file("existing.txt", b"Existing TCP evidence with page provenance.")
    repo.search(EXISTING_QUERY, selected_doc_ids=["existing.txt"])
    return repo, old


def interrupted_operation(monkeypatch, operation, pause, dimension, identity="provider", failure=None, aba=False):
    repo, old = prepared_repository(identity)
    old_fn, old_space = repo._embed_fn, repo._embedding_space()
    new = Encoder("encoder-B", dimension, 1)
    if identity == "injected":
        del new.index_id
    original_stage = repo._stage_chunk_embeddings
    entered, resume = Event(), Event()
    main_thread = get_ident()

    if pause == "stage":
        def gated(*args, **kwargs):
            if get_ident() != main_thread:
                entered.set()
                assert resume.wait(5), "deadlock: stage was not released"
            return original_stage(*args, **kwargs)

        monkeypatch.setattr(repo, "_stage_chunk_embeddings", gated)
    else:
        old.pause_kind = "query" if pause == "query" else "document"
        entered, resume = old.entered, old.resume
    old.failure = failure

    def work():
        if operation == "ingestion":
            return DocumentService(repo).ingest_file("inflight-a.txt", b"New A evidence.\fSecond A page.")
        return repo.search(PENDING_QUERY, selected_doc_ids=["pending.txt"])

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(work)
        try:
            assert entered.wait(5), "deadlock: operation did not reach the requested boundary"
            repo.set_embed_fn(new.embed_texts)
            new_space = repo._embedding_space()
            # B makes progress while A is paused: no global lock across embedding I/O.
            DocumentService(repo).ingest_file("b-success.txt", b"Successful B evidence.")
            repo.search("successful B evidence", selected_doc_ids=["b-success.txt"])
            if aba:
                repo.set_embed_fn(old_fn)  # Same callable and identity, but a different generation.
            expected = snapshot(repo)
        finally:
            resume.set()
        error = future.exception(timeout=5)
    # Captured on red failures: expose the actual vector origin, not just dimensions.
    print(json.dumps({"operation": operation, "pause": pause, "identity": identity,
                      "b_dimension": dimension, "error": None if error is None else str(error),
                      "a_vectors": [v.tolist() for key, v in repo._chunk_embeddings.items() if key[0] == old_space],
                      "a_dimension": repo._embedding_dimensions.get(old_space)}))
    return repo, old, new, old_space, new_space, error, expected


@pytest.mark.parametrize("identity", ["provider", "injected"])
@pytest.mark.parametrize("dimension", [3, 5], ids=["same-dimension", "different-dimension"])
@pytest.mark.parametrize("operation,pause", [
    ("ingestion", "stage"), ("ingestion", "embedding"),
    ("retrieval", "stage"), ("retrieval", "embedding"), ("retrieval", "query"),
])
def test_replacement_before_publication_aborts_and_preserves_valid_namespaces(monkeypatch, operation, pause, dimension, identity):
    repo, old, new, old_space, new_space, error, expected = interrupted_operation(
        monkeypatch, operation, pause, dimension, identity)
    assert_namespaces(repo, {old_space: old, new_space: new})
    assert isinstance(error, EmbeddingError), f"stale operation did not fail explicitly: {error!r}"
    assert str(error).startswith("EMBEDDING_PROVIDER_FAILURE:") and "encoder changed" in str(error)
    assert_unchanged(repo, expected)
    assert repo._embed_fn.__self__ is new
    assert "inflight-a.txt" not in repo.documents and "b-success.txt" in repo.documents


@pytest.mark.parametrize("dimension", [3, 5], ids=["same-dimension", "different-dimension"])
def test_switch_back_to_encoder_a_never_reads_vectors_from_b(monkeypatch, dimension):
    repo, old, new, old_space, new_space, _, _ = interrupted_operation(
        monkeypatch, "retrieval", "stage", dimension)
    old_cache = {key: value.copy() for key, value in repo._chunk_embeddings.items() if key[0] == old_space}
    repo.set_embed_fn(old.embed_texts)
    calls = len(old.calls)
    existing = repo.search(EXISTING_QUERY, selected_doc_ids=["existing.txt"])
    assert existing and existing[0].dense_score == 1.0 and len(old.calls) == calls
    pending = repo.search(PENDING_QUERY, selected_doc_ids=["pending.txt"])
    assert pending and pending[0].dense_score == 1.0
    assert_namespaces(repo, {old_space: old, new_space: new})
    for key, vector in old_cache.items():
        np.testing.assert_array_equal(repo._chunk_embeddings[key], vector)
    assert repo._embedding_dimensions[old_space] == 3


@pytest.mark.parametrize("dimension", [3, 5])
def test_a_to_b_to_same_a_callable_before_publication_is_rejected(monkeypatch, dimension):
    repo, old, new, old_space, new_space, error, expected = interrupted_operation(
        monkeypatch, "ingestion", "stage", dimension, aba=True)
    assert isinstance(error, EmbeddingError) and "encoder changed" in str(error)
    assert_unchanged(repo, expected)
    assert_namespaces(repo, {old_space: old, new_space: new})
    assert repo._embed_fn.__self__ is old


@pytest.mark.parametrize("operation", ["ingestion", "retrieval"])
@pytest.mark.parametrize("dimension", [3, 5])
def test_failed_inflight_embedding_keeps_original_error_and_publishes_nothing(monkeypatch, operation, dimension):
    failure = EmbeddingError("EMBEDDING_TIMEOUT: deterministic test failure")
    repo, old, new, old_space, new_space, error, expected = interrupted_operation(
        monkeypatch, operation, "embedding", dimension, failure=failure)
    assert error is failure
    assert_unchanged(repo, expected)
    assert_namespaces(repo, {old_space: old, new_space: new})


def test_failed_retrieval_does_not_publish_query_vector_or_dimension():
    old = Encoder("encoder-A", 3, 0)
    repo = WorkspaceRepository()
    DocumentService(repo).ingest_file("pending.txt", b"Pending TCP evidence.")
    repo.set_embed_fn(old.embed_texts)
    failure = EmbeddingError("EMBEDDING_TIMEOUT: document embedding failed after query succeeded")
    old.failure = failure
    before = snapshot(repo)
    with pytest.raises(EmbeddingError) as caught:
        repo.search(PENDING_QUERY)
    assert caught.value is failure
    assert_unchanged(repo, before)


@pytest.mark.parametrize("dimension", [3, 5])
def test_replacement_after_publication_can_complete_consistently(monkeypatch, dimension):
    repo, old = prepared_repository()
    old_space = repo._embedding_space()
    entered, resume = Event(), Event()
    original_dot = np.dot
    main_thread = get_ident()

    def gated_dot(*args, **kwargs):
        if get_ident() != main_thread:
            entered.set()
            assert resume.wait(5), "deadlock: scoring was not released"
        return original_dot(*args, **kwargs)

    monkeypatch.setattr(np, "dot", gated_dot)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(repo.search, PENDING_QUERY, selected_doc_ids=["pending.txt"])
        try:
            assert entered.wait(5), "operation did not reach scoring after publication"
            new = Encoder("encoder-B", dimension, 1)
            repo.set_embed_fn(new.embed_texts)
            new_space = repo._embedding_space()
            repo.search("B evidence", selected_doc_ids=["pending.txt"])
        finally:
            resume.set()
        result = future.result(timeout=5)
    assert result and result[0].dense_score == 1.0
    assert_namespaces(repo, {old_space: old, new_space: new})
