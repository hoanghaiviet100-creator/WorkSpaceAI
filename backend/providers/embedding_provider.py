"""
backend/providers/embedding_provider.py
R3 Dense Embedding Provider with Lazy Loading.

Model: paraphrase-multilingual-MiniLM-L12-v2
Architecture Rules:
- Lazy loading: Does not import sentence_transformers or download weights until explicitly requested.
- Graceful degradation: Catches all import/model loading errors cleanly; sets is_available = False
  without crashing the application.
- Decoupled from Repository: WorkspaceRepository does NOT import this file directly;
  the service layer injects the embed_fn.
"""
from typing import Any, Callable, List, Optional
import numpy as np


class EmbeddingProvider:
    """
    Local multilingual embedding provider using SentenceTransformers.
    Employs the lightweight 'paraphrase-multilingual-MiniLM-L12-v2' model for Vietnamese and English.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2") -> None:
        self.model_name = model_name
        self._model: Optional[Any] = None
        self._load_attempted: bool = False
        self.is_available: bool = False

    def load_model(self) -> bool:
        """Attempts to import sentence_transformers and load the model lazily."""
        if self._load_attempted:
            return self.is_available

        self._load_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self.is_available = True
            return True
        except Exception:
            # sentence_transformers not installed, network down, or weights unavailable
            self._model = None
            self.is_available = False
            return False

    def embed_texts(self, texts: List[str]) -> Optional[np.ndarray]:
        """
        Encodes a list of string passages into unit-normalized numpy vectors.
        Returns None if embedding model is unavailable.
        """
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        if not self._load_attempted:
            self.load_model()

        if not self.is_available or self._model is None:
            return None

        try:
            embeddings = self._model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return embeddings
        except Exception:
            return None

    def get_embed_fn(self) -> Optional[Callable[[List[str]], Optional[np.ndarray]]]:
        """
        Returns a callable embed_fn suitable for dependency injection into WorkspaceRepository.
        Returns None if embedding is unavailable.
        """
        if not self._load_attempted:
            self.load_model()

        if self.is_available:
            return self.embed_texts
        return None


# Singleton instance
embedding_provider = EmbeddingProvider()
