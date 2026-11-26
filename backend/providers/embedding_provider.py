"""
backend/providers/embedding_provider.py
R3 Dense Embedding Provider with CPU FastEmbed (ONNX) & Subword Hash Fallback.

Architecture Rules:
- Reserves GPU/VRAM for generative LLMs by running lightweight multilingual
  embeddings (intfloat/multilingual-e5-small quantized ONNX) on CPU via FastEmbed.
- Respects E5 query/passage prefixes ("query: " / "passage: ") automatically.
- Offline-safe & resilient fallback: Includes a 384-dimensional Character N-gram +
  Subword Hash Vectorizer using pure NumPy and Python hashlib.
- Decoupled from Repository: WorkspaceRepository does NOT import this file directly;
  the service layer injects the embed_fn.
"""
import hashlib
import os
import re
import threading
from typing import Any, Callable, List, Optional
import numpy as np

from backend.core.config import settings


class SubwordHashVectorizer:
    """
    Deterministic 384-dimensional Character N-gram + Subword Feature Hasher in pure NumPy.
    Supports English and Vietnamese with zero external model dependencies.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def encode(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)

        mat = np.zeros((len(texts), self.dim), dtype=np.float32)

        for row_idx, text in enumerate(texts):
            clean = text.lower().strip()
            if not clean:
                continue

            words = re.findall(r"\w+", clean)
            features = list(words)

            # Character 3-grams and 4-grams for subword morphology
            for w in words:
                w_len = len(w)
                if w_len >= 3:
                    for i in range(w_len - 2):
                        features.append(w[i : i + 3])
                if w_len >= 4:
                    for i in range(w_len - 3):
                        features.append(w[i : i + 4])

            # Bigrams
            for i in range(len(words) - 1):
                features.append(f"{words[i]}_{words[i+1]}")

            # Hash features into signed buckets
            for feat in features:
                h = hashlib.md5(feat.encode("utf-8")).digest()
                bucket = int.from_bytes(h[:2], "little") % self.dim
                sign = 1.0 if (h[2] & 1) else -1.0
                mat[row_idx, bucket] += sign

            # L2 normalization
            norm = np.linalg.norm(mat[row_idx])
            if norm > 1e-9:
                mat[row_idx] /= norm

        return mat


def _is_offline_env() -> bool:
    """Returns True when environment flags prohibit outbound model downloads."""
    if os.getenv("WORKSPACE_OFFLINE_ONLY", "").strip().lower() == "true":
        return True
    if os.getenv("HF_HUB_OFFLINE", "").strip().lower() in ("1", "true", "yes"):
        return True
    if os.getenv("TRANSFORMERS_OFFLINE", "").strip().lower() in ("1", "true", "yes"):
        return True
    return False


class _InjectedEmbedFn:
    """Adapter exposing callable, query/passage helpers, and score calibration to WorkspaceRepository."""

    def __init__(self, provider: "EmbeddingProvider") -> None:
        self._provider = provider

    def __call__(self, texts: List[str]) -> Optional[np.ndarray]:
        return self._provider.embed_texts(texts, is_query=False)

    def embed_queries(self, texts: List[str]) -> Optional[np.ndarray]:
        return self._provider.embed_queries(texts)

    def embed_passages(self, texts: List[str]) -> Optional[np.ndarray]:
        return self._provider.embed_passages(texts)

    @property
    def score_floor(self) -> float:
        return self._provider.score_floor


class EmbeddingProvider:
    """
    Local multilingual embedding provider.
    Priority order (when EMBEDDING_BACKEND=auto):
    1. CPU FastEmbed ONNX ('intfloat/multilingual-e5-small' quantized, 384-d) — saves 100% VRAM for LLM.
    2. SentenceTransformer ('paraphrase-multilingual-MiniLM-L12-v2' 384-d).
    3. Local Ollama embedding service ('nomic-embed-text' 768-d), if explicitly configured or FastEmbed unavailable.
    4. Pure NumPy SubwordHashVectorizer (384-d) as deterministic offline fallback.
    """

    DEFAULT_FASTEMBED_MODEL = "intfloat/multilingual-e5-small"
    CUSTOM_E5_HF_SOURCE = "Xenova/multilingual-e5-small"
    CUSTOM_E5_MODEL_FILE = "onnx/model_quantized.onnx"

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        fastembed_model: Optional[str] = None,
    ) -> None:
        self.model_name = model_name
        self.fastembed_model_name = (fastembed_model or settings.fastembed_model).strip()
        self._fastembed_model: Optional[Any] = None
        self._model: Optional[Any] = None
        self._hash_vectorizer: Optional[SubwordHashVectorizer] = None
        self._load_lock = threading.Lock()
        self._load_attempted: bool = False
        self.is_available: bool = False
        self.using_fastembed: bool = False
        self.using_ollama: bool = False
        self.using_hash_fallback: bool = False

    def _is_e5_model(self) -> bool:
        if self.using_fastembed:
            return "e5" in self.fastembed_model_name.lower()
        if self._model is not None:
            return "e5" in self.model_name.lower()
        return False

    @property
    def score_floor(self) -> float:
        """Baseline cosine similarity floor for anisotropic models (e.g. E5)."""
        if self.using_fastembed and self._is_e5_model():
            return 0.70
        return 0.0

    def _prepare_texts(self, texts: List[str], *, is_query: bool) -> List[str]:
        if not self._is_e5_model():
            return texts
        prefix = "query: " if is_query else "passage: "
        prepared: List[str] = []
        for text in texts:
            stripped = text.lstrip()
            lowered = stripped.lower()
            if lowered.startswith("query:") or lowered.startswith("passage:"):
                prepared.append(text)
            else:
                prepared.append(f"{prefix}{text}")
        return prepared

    def _try_load_fastembed(self) -> bool:
        try:
            from fastembed import TextEmbedding
            from fastembed.common.model_description import ModelSource, PoolingType
        except ImportError:
            return False

        target = self.fastembed_model_name or self.DEFAULT_FASTEMBED_MODEL
        try:
            supported = {m["model"].lower() for m in TextEmbedding.list_supported_models()}
            if target.lower() not in supported and target.lower() == self.DEFAULT_FASTEMBED_MODEL.lower():
                TextEmbedding.add_custom_model(
                    model=self.DEFAULT_FASTEMBED_MODEL,
                    pooling=PoolingType.MEAN,
                    normalization=True,
                    sources=ModelSource(hf=self.CUSTOM_E5_HF_SOURCE),
                    dim=384,
                    model_file=self.CUSTOM_E5_MODEL_FILE,
                    description="Multilingual E5 Small INT8 ONNX",
                    license="mit",
                    size_in_gb=0.11,
                )

            try:
                self._fastembed_model = TextEmbedding(
                    model_name=target,
                    providers=["CPUExecutionProvider"],
                    local_files_only=True,
                )
                return True
            except Exception:
                # In offline mode or pytest without pre-cached weights, skip network downloads
                if _is_offline_env() or os.getenv("PYTEST_CURRENT_TEST"):
                    return False
                self._fastembed_model = TextEmbedding(
                    model_name=target,
                    providers=["CPUExecutionProvider"],
                )
                return True
        except Exception:
            self._fastembed_model = None
            return False

    def _try_embed_ollama(self, texts: List[str]) -> Optional[np.ndarray]:
        if not texts:
            return np.empty((0, 768), dtype=np.float32)
        try:
            import json
            import urllib.request

            payload = json.dumps({"model": settings.ollama_embed_model, "input": texts}).encode("utf-8")
            req = urllib.request.Request(
                f"{settings.ollama_base_url.rstrip('/')}/api/embed",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=20.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                embeddings = data.get("embeddings")
                if embeddings and len(embeddings) == len(texts):
                    arr = np.asarray(embeddings, dtype=np.float32)
                    norms = np.linalg.norm(arr, axis=1, keepdims=True)
                    norms = np.maximum(norms, 1e-9)
                    return arr / norms
        except Exception:
            return None
        return None

    def _try_load_sentence_transformer(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            return True
        except Exception:
            self._model = None
            return False

    def _try_probe_ollama(self) -> bool:
        try:
            probe = self._try_embed_ollama(["workspace ai test probe"])
            return probe is not None and len(probe) == 1 and probe.shape[1] > 0
        except Exception:
            return False

    def load_model(self) -> bool:
        """Initializes embedding backend according to EMBEDDING_BACKEND priority."""
        with self._load_lock:
            if self._load_attempted:
                return self.is_available

            self._load_attempted = True
            self.using_fastembed = False
            self.using_ollama = False
            self.using_hash_fallback = False
            backend = settings.embedding_backend.strip().lower()

            if backend == "hash":
                self._activate_hash_fallback()
                return True

            if backend == "ollama":
                if self._try_probe_ollama():
                    self.using_ollama = True
                    self.is_available = True
                    return True
                if self._try_load_fastembed():
                    self.using_fastembed = True
                    self.is_available = True
                    return True
                if self._try_load_sentence_transformer():
                    self.is_available = True
                    return True
                self._activate_hash_fallback()
                return True

            # Default "auto" / "fastembed": prioritize CPU FastEmbed so Ollama keeps 100% VRAM for LLM
            if self._try_load_fastembed():
                self.using_fastembed = True
                self.is_available = True
                return True

            if backend != "fastembed":
                if self._try_load_sentence_transformer():
                    self.is_available = True
                    return True
                if self._try_probe_ollama():
                    self.using_ollama = True
                    self.is_available = True
                    return True

            self._activate_hash_fallback()
            return True

    def _activate_hash_fallback(self) -> None:
        self._fastembed_model = None
        self._model = None
        self._hash_vectorizer = SubwordHashVectorizer(dim=384)
        self.is_available = True
        self.using_fastembed = False
        self.using_ollama = False
        self.using_hash_fallback = True

    def embed_texts(self, texts: List[str], *, is_query: bool = False) -> Optional[np.ndarray]:
        """
        Encodes a list of string passages or queries into unit-normalized numpy vectors.
        Always returns a valid (N, D) array.
        """
        if not texts:
            return np.empty((0, 768 if self.using_ollama else 384), dtype=np.float32)

        if not self._load_attempted:
            self.load_model()

        # 1. CPU FastEmbed ONNX
        if self.using_fastembed and self._fastembed_model is not None:
            try:
                prepared = self._prepare_texts(texts, is_query=is_query)
                vecs = list(self._fastembed_model.embed(prepared))
                arr = np.asarray(vecs, dtype=np.float32)
                if arr.ndim == 2 and len(arr) == len(texts):
                    norms = np.linalg.norm(arr, axis=1, keepdims=True)
                    norms = np.maximum(norms, 1e-9)
                    return arr / norms
            except Exception:
                pass

        # 2. Ollama embedding (if active)
        if self.using_ollama:
            vecs = self._try_embed_ollama(texts)
            if vecs is not None:
                return vecs

        # 3. SentenceTransformer (if loaded)
        if self._model is not None:
            try:
                prepared = self._prepare_texts(texts, is_query=is_query)
                embeddings = self._model.encode(
                    prepared,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                return embeddings
            except Exception:
                pass

        # 4. Robust subword hash vectorizer fallback
        if self._hash_vectorizer is None:
            self._hash_vectorizer = SubwordHashVectorizer(dim=384)
        return self._hash_vectorizer.encode(texts)

    def embed_queries(self, texts: List[str]) -> Optional[np.ndarray]:
        """Encodes search queries with query-side instruction/prefix when supported."""
        return self.embed_texts(texts, is_query=True)

    def embed_passages(self, texts: List[str]) -> Optional[np.ndarray]:
        """Encodes document chunks with passage-side instruction/prefix when supported."""
        return self.embed_texts(texts, is_query=False)

    def get_embed_fn(self) -> Optional[Callable[[List[str]], Optional[np.ndarray]]]:
        """
        Returns a lazy-loading callable adapter suitable for injection into WorkspaceRepository.
        """
        return _InjectedEmbedFn(self)


# Singleton instance
embedding_provider = EmbeddingProvider()
