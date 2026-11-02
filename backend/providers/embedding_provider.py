"""
backend/providers/embedding_provider.py
R3 Dense Embedding Provider with Lazy Loading & Fallback Subword Hash Vectorizer.

Architecture Rules:
- Lazy loading: Attempts sentence_transformers if available.
- Resilient fallback: Includes a 384-dimensional Character N-gram + Subword Hash
  Vectorizer using pure NumPy and Python hashlib, ensuring Dense Cosine Similarity
  is ALWAYS active without requiring PyTorch or heavy external dependencies.
- Decoupled from Repository: WorkspaceRepository does NOT import this file directly;
  the service layer injects the embed_fn.
"""
import hashlib
import re
from typing import Any, Callable, List, Optional
import numpy as np


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


class EmbeddingProvider:
    """
    Local multilingual embedding provider.
    Prioritizes SentenceTransformer ('paraphrase-multilingual-MiniLM-L12-v2') if installed;
    seamlessly falls back to SubwordHashVectorizer (384-d) so Dense Cosine Similarity
    never fails.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2") -> None:
        self.model_name = model_name
        self._model: Optional[Any] = None
        self._hash_vectorizer: Optional[SubwordHashVectorizer] = None
        self._load_attempted: bool = False
        self.is_available: bool = False
        self.using_hash_fallback: bool = False

    def load_model(self) -> bool:
        """Attempts to import sentence_transformers or loads 384-d hash vectorizer."""
        if self._load_attempted:
            return self.is_available

        self._load_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self.is_available = True
            self.using_hash_fallback = False
            return True
        except Exception:
            # Fallback to pure NumPy Subword Hash Vectorizer (384 dimensions)
            self._model = None
            self._hash_vectorizer = SubwordHashVectorizer(dim=384)
            self.is_available = True
            self.using_hash_fallback = True
            return True

    def embed_texts(self, texts: List[str]) -> Optional[np.ndarray]:
        """
        Encodes a list of string passages into unit-normalized numpy vectors (384 dimensions).
        Always returns a valid (N, 384) array.
        """
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        if not self._load_attempted:
            self.load_model()

        if self._model is not None:
            try:
                embeddings = self._model.encode(
                    texts,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                return embeddings
            except Exception:
                pass

        # Use robust subword hash vectorizer
        if self._hash_vectorizer is None:
            self._hash_vectorizer = SubwordHashVectorizer(dim=384)
        return self._hash_vectorizer.encode(texts)

    def get_embed_fn(self) -> Optional[Callable[[List[str]], Optional[np.ndarray]]]:
        """
        Returns a callable embed_fn suitable for dependency injection into WorkspaceRepository.
        """
        if not self._load_attempted:
            self.load_model()

        return self.embed_texts


# Singleton instance
embedding_provider = EmbeddingProvider()
