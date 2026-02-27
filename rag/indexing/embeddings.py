from __future__ import annotations
"""Embedding backend selection and model loading."""

import os
from collections.abc import Sequence
from typing import Protocol

DEFAULT_EMBEDDING_MODEL = "mixedbread-ai/mxbai-embed-large-v1"


class EmbeddingBackend(Protocol):
    """Minimal protocol so retrievers can swap embedding implementations."""

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        ...


class SentenceTransformerBackend:
    """SentenceTransformers-backed embedding implementation."""

    def __init__(self, model_name: str | None = None) -> None:
        # The model can be overridden so other developers can use a lighter
        # local model without changing code.
        selected_name = model_name or os.getenv("RAG_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        self.model_name = selected_name

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for embedding generation. "
                "Install dependencies and retry."
            ) from exc

        self._model = SentenceTransformer(self.model_name)

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode text into normalized dense vectors.

        Normalized embeddings make cosine-like comparisons more stable and are a
        reasonable default for local semantic retrieval.
        """
        if not texts:
            return []
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, vector)) for vector in vectors]


def build_embedding_backend(model_name: str | None = None) -> EmbeddingBackend:
    """Factory used by build and query paths."""
    return SentenceTransformerBackend(model_name=model_name)
