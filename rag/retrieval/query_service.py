from __future__ import annotations
"""High-level retrieval service used by the API layer."""

import re
from pathlib import Path
from typing import Any

from rag.indexing.embeddings import EmbeddingBackend, build_embedding_backend
from rag.retrieval.hybrid_retriever import HybridRetriever
from rag.models import CanonicalCourseDocument, RetrievalRequest, RetrievalResponse
from rag.retrieval.sparse_index import SparseKeywordIndex
from rag.indexing.vector_store import ChromaVectorStore, DEFAULT_COLLECTION_NAME

_CODE_NORMALIZE_RE = re.compile(r"\s+")
_CODE_SPLIT_RE = re.compile(r"^([A-Za-z]+)(\d.*)$")


def normalize_course_code(raw: str) -> str:
    """Normalize a course code to 'DEPT NNNN' form for reliable matching.

    Handles inputs like 'APMA2680', 'apma 2680', 'APMA  2680', etc.
    """
    collapsed = _CODE_NORMALIZE_RE.sub(" ", raw.strip()).upper()
    if " " in collapsed:
        return collapsed
    m = _CODE_SPLIT_RE.match(collapsed)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return collapsed


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

    def lookup_by_code(
        self,
        course_code: str,
        source: str | None = None,
    ) -> list[CanonicalCourseDocument]:
        """Find documents by exact course code (case/whitespace insensitive).

        Handles compact forms like 'APMA2680' as well as 'APMA 2680'.
        """
        normalized = normalize_course_code(course_code)
        results: list[CanonicalCourseDocument] = []
        for doc in self.retriever.sparse_index.documents:
            doc_normalized = normalize_course_code(doc.course_code)
            if doc_normalized != normalized:
                continue
            if source and doc.source != source.strip().lower():
                continue
            results.append(doc)
        return results

    def get_all_documents(self) -> list[CanonicalCourseDocument]:
        """Expose the full document list for iteration-based tools."""
        return self.retriever.sparse_index.documents
