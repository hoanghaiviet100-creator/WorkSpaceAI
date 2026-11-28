"""Ollama semantic embeddings. Provider failures never produce substitute vectors."""
import os
import hashlib
import json
from threading import RLock
from typing import Callable, List, Optional

import httpx
import numpy as np

from backend.core.config import settings


class EmbeddingError(RuntimeError):
    """An actionable embedding failure, propagated through ingestion/retrieval."""


def validate_vectors(vectors, rows: int, dimension: Optional[int] = None) -> np.ndarray:
    """Reject invalid vectors before caching, indexing or computing similarities."""
    try:
        raw = np.asarray(vectors)
        if raw.dtype.kind not in "fiu":
            raise ValueError("expected numeric vectors")
        arr = raw.astype(np.float32)
    except (TypeError, ValueError, OverflowError) as exc:
        raise EmbeddingError("EMBEDDING_INVALID_RESPONSE: expected a rectangular numeric matrix") from exc
    if arr.ndim != 2 or arr.shape[0] != rows or arr.shape[1] == 0:
        raise EmbeddingError(f"EMBEDDING_INVALID_RESPONSE: expected {rows} nonempty vectors, got {arr.shape}")
    if dimension is not None and arr.shape[1] != dimension:
        raise EmbeddingError(f"EMBEDDING_DIMENSION_MISMATCH: expected {dimension}, got {arr.shape[1]}; rebuild the embedding index")
    norms = np.linalg.norm(arr.astype(np.float64), axis=1, keepdims=True)
    if not np.isfinite(arr).all() or not np.isfinite(norms).all() or np.any(norms <= 1e-12):
        raise EmbeddingError("EMBEDDING_INVALID_VECTOR: vectors must be finite and nonzero")
    return (arr / norms).astype(np.float32)


class EmbeddingProvider:
    """One model/digest/dimension and L2 policy for documents and instructed queries."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.model_name = model_name or settings.ollama_embed_model
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.query_instruction = settings.ollama_embed_query_instruction
        self.timeout = httpx.Timeout(settings.ollama_embed_timeout, connect=2.0)
        self.batch_size = settings.ollama_embed_batch_size
        self.dimension: Optional[int] = None
        self.model_digest: Optional[str] = None
        self._index_identity = None
        self.is_available = False
        self.using_ollama = False
        self.using_hash_fallback = False
        self._transport = transport
        self._lock = RLock()
        if self.batch_size < 1 or settings.ollama_embed_timeout <= 0:
            raise EmbeddingError("EMBEDDING_INVALID_CONFIG: batch size and timeout must be positive")

    def _request(self, method: str, path: str, payload=None):
        if method == "POST" and os.getenv("F1_SESSION_B", "false").lower() == "true":
            from backend.services.f1_session_runtime import admit_embedding
            admit_embedding()
            payload = dict(payload, keep_alive="10m")
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport, trust_env=False) as client:
                response = client.request(method, self.base_url + path, json=payload)
            if response.status_code == 404:
                raise EmbeddingError(f"EMBEDDING_MODEL_MISSING: run ollama pull {self.model_name} on {self.base_url}")
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise EmbeddingError(f"EMBEDDING_TIMEOUT: Ollama {self.model_name} at {self.base_url}") from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"EMBEDDING_PROVIDER_FAILURE: Ollama {self.model_name} at {self.base_url}: {exc}") from exc
        except ValueError as exc:
            raise EmbeddingError("EMBEDDING_INVALID_RESPONSE: Ollama returned invalid JSON") from exc
        if not isinstance(data, dict) or data.get("error"):
            raise EmbeddingError("EMBEDDING_INVALID_RESPONSE: Ollama returned an error or non-object response")
        return data

    def _digest(self) -> str:
        models = self._request("GET", "/api/tags").get("models")
        if not isinstance(models, list) or any(not isinstance(m, dict) for m in models):
            raise EmbeddingError("EMBEDDING_INVALID_RESPONSE: missing model inventory")
        model = next((m for m in models if m.get("name") == self.model_name), None)
        if model is None:
            raise EmbeddingError(f"EMBEDDING_MODEL_MISSING: run ollama pull {self.model_name} on {self.base_url}")
        digest = model.get("digest")
        if not isinstance(digest, str) or not digest:
            raise EmbeddingError("EMBEDDING_INVALID_RESPONSE: missing model digest")
        return digest

    def _assert_digest(self, expected: str) -> None:
        if self._digest() != expected:
            raise EmbeddingError("EMBEDDING_MODEL_CHANGED: model digest changed; restart provider and stage a new index")

    def _assert_index_identity(self) -> None:
        if self._index_policy() != self._index_identity:
            raise EmbeddingError("EMBEDDING_MODEL_CHANGED: active embedding identity or policy changed")

    def verify_index(self, expected_index_id: str) -> None:
        """Verify the live digest before cached vectors are used; never adopt a new identity."""
        with self._lock:
            try:
                self.load_model()
                self._assert_index_identity()
                if self.index_id != expected_index_id:
                    raise EmbeddingError("EMBEDDING_MODEL_CHANGED: active embedding index changed")
                self._assert_digest(self._index_identity["digest"])
                self.is_available = self.using_ollama = True
            except EmbeddingError:
                self.is_available = False
                raise

    def _encode_batch(self, texts: List[str], dimension: Optional[int]) -> np.ndarray:
        data = self._request("POST", "/api/embed", {
            "model": self.model_name, "input": texts, "truncate": False,
        })
        if data.get("model") != self.model_name:
            raise EmbeddingError("EMBEDDING_INVALID_RESPONSE: response model does not match requested model")
        return validate_vectors(data.get("embeddings"), len(texts), dimension)

    def load_model(self) -> bool:
        """Resolve the installed digest and discover dimension from a real embedding."""
        with self._lock:
            if self._index_identity is None:
                digest = self._digest()
                probe = self._encode_batch(["WorkspaceAI embedding dimension probe"], None)
                self._assert_digest(digest)
                self.dimension = probe.shape[1]
                self.model_digest = digest
                self._index_identity = self._index_policy()
                self.is_available = self.using_ollama = True
        return True

    def _embed(self, texts: List[str]) -> np.ndarray:
        with self._lock:
            try:
                self.load_model()
                self._assert_index_identity()
                if not texts:
                    return np.empty((0, self.dimension), dtype=np.float32)
                if any(not isinstance(t, str) or not t.strip() for t in texts):
                    raise EmbeddingError("EMBEDDING_INVALID_INPUT: texts must be nonempty strings")
                self._assert_digest(self._index_identity["digest"])
                batches = [self._encode_batch(texts[i:i + self.batch_size], self.dimension)
                           for i in range(0, len(texts), self.batch_size)]
                self._assert_digest(self._index_identity["digest"])
                self._assert_index_identity()
                self.is_available = self.using_ollama = True
                return np.concatenate(batches)
            except EmbeddingError:
                self.is_available = False
                raise

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Documents are embedded verbatim, without query instructions."""
        return self._embed(texts)

    def embed_queries(self, texts: List[str]) -> np.ndarray:
        """Qwen3 retrieval format; the shared model/dimension/L2 policy is unchanged."""
        if any(not isinstance(t, str) or not t.strip() for t in texts):
            raise EmbeddingError("EMBEDDING_INVALID_INPUT: queries must be nonempty strings")
        return self._embed([f"Instruct: {self.query_instruction}\nQuery:{t}" for t in texts])

    def _index_policy(self) -> dict:
        return {
            "provider": "ollama", "model": self.model_name, "digest": self.model_digest,
            "dimension": self.dimension, "normalization": "l2-float32-v1",
            "document_format": "raw-v1", "query_format": "qwen3-instruct-query-v1",
            "instruction": self.query_instruction, "truncate": False,
        }

    @property
    def index_identity(self) -> dict:
        """Recorded identity/policy of this index; callers receive an independent copy."""
        self.load_model()
        return dict(self._index_identity)

    @property
    def index_id(self) -> str:
        self.load_model()
        policy = json.dumps(self._index_identity, sort_keys=True)
        return "ollama:" + hashlib.sha256(policy.encode("utf-8")).hexdigest()

    def get_embed_fn(self) -> Callable[[List[str]], np.ndarray]:
        """Return a lazy callable; imports and dependency injection do no network I/O."""
        return self.embed_texts


if os.getenv("F1_EMBEDDING_BACKEND", "ollama") == "fastembed_cpu":
    from backend.providers.cpu_embedding_provider import CPUEmbeddingProvider
    embedding_provider = CPUEmbeddingProvider()
else:
    embedding_provider = EmbeddingProvider()
