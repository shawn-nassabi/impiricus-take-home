from __future__ import annotations
"""High-level retrieval service used by the API layer."""

from pathlib import Path

from rag.indexing.embeddings import EmbeddingBackend, build_embedding_backend
from rag.retrieval.hybrid_retriever import HybridRetriever
from rag.models import RetrievalRequest, RetrievalResponse
from rag.retrieval.sparse_index import SparseKeywordIndex
from rag.indexing.vector_store import ChromaVectorStore, DEFAULT_COLLECTION_NAME


class LocalHybridRetrievalService:
    """Loads persisted local indices and exposes a single search entrypoint."""

    def __init__(self, retriever: HybridRetriever) -> None:
        self.retriever = retriever

    @classmethod
    def from_persisted(
        cls,
        persist_dir: Path,
        embedding_backend: EmbeddingBackend | None = None,
        embedding_model: str | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> "LocalHybridRetrievalService":
        """Construct the service from artifacts produced by `rag.build_index`."""
        chroma_dir = persist_dir / "chroma"
        sparse_dir = persist_dir / "sparse_index"

        backend = embedding_backend or build_embedding_backend(model_name=embedding_model)
        vector_store = ChromaVectorStore(persist_dir=chroma_dir, collection_name=collection_name)
        sparse_index = SparseKeywordIndex.load(sparse_dir)

        retriever = HybridRetriever(
            vector_store=vector_store,
            sparse_index=sparse_index,
            embedding_backend=backend,
        )
        return cls(retriever=retriever)

    def search(self, request: RetrievalRequest) -> RetrievalResponse:
        """Delegate to the hybrid retriever."""
        return self.retriever.search(request)
