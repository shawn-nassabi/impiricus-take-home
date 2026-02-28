from __future__ import annotations
"""Local Chroma integration for dense indexing and retrieval."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from rag.indexing.embeddings import EmbeddingBackend
from rag.models import CanonicalCourseDocument, RetrievalFilters

DEFAULT_COLLECTION_NAME = "courses"


@dataclass(frozen=True)
class DenseHit:
    """Dense retrieval result returned before hybrid fusion."""

    doc_id: str
    score: float
    rank: int
    metadata: dict[str, Any]
    text: str


class ChromaVectorStore:
    """Thin wrapper around a persisted local Chroma collection."""

    def __init__(self, persist_dir: Path, collection_name: str = DEFAULT_COLLECTION_NAME) -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client: Any | None = None
        self._collection: Any | None = None

    def _load_client(self) -> Any:
        """Create the persistent client lazily so callers pay setup only on use."""
        if self._client is None:
            try:
                import chromadb
            except ImportError as exc:
                raise RuntimeError("chromadb is required to use the vector store.") from exc
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        return self._client

    def _load_collection(self) -> Any:
        """Create or fetch the configured collection on first access."""
        if self._collection is None:
            client = self._load_client()
            self._collection = client.get_or_create_collection(name=self.collection_name)
        return self._collection

    def reset_collection(self) -> None:
        """Drop and recreate the collection before a rebuild."""
        client = self._load_client()
        try:
            client.delete_collection(name=self.collection_name)
        except Exception:
            pass
        self._collection = client.get_or_create_collection(name=self.collection_name)

    def count(self) -> int:
        """Return the current number of indexed vectors."""
        collection = self._load_collection()
        return int(collection.count())

    def upsert_documents(
        self,
        documents: list[CanonicalCourseDocument],
        backend: EmbeddingBackend,
        batch_size: int = 64,
        progress_callback: Callable[[int, int, int, int, int], None] | None = None,
    ) -> None:
        """Embed and upsert documents in batches.

        The callback is used by the build command to log progress without
        coupling logging behavior directly into this storage layer.
        """
        collection = self._load_collection()
        total = len(documents)
        total_batches = max(1, (total + batch_size - 1) // batch_size) if total else 0

        for batch_number, start in enumerate(range(0, total, batch_size), start=1):
            batch = documents[start : start + batch_size]
            ids = [document.doc_id for document in batch]
            texts = [document.text for document in batch]
            # Embeddings are computed outside Chroma so the same model can be
            # used consistently at both build and query time.
            embeddings = backend.encode(texts)
            metadatas = [document.chroma_metadata() for document in batch]

            collection.upsert(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )

            if progress_callback:
                end = start + len(batch)
                progress_callback(batch_number, total_batches, start + 1, end, total)

    def query(
        self,
        query_text: str,
        backend: EmbeddingBackend,
        filters: RetrievalFilters | None,
        n_results: int,
    ) -> list[DenseHit]:
        """Run dense semantic search against the persisted Chroma collection."""
        collection = self._load_collection()

        where_filter = build_chroma_where(filters)
        # We embed the query with the same backend used during indexing so the
        # vector space stays aligned.
        query_embedding = backend.encode([query_text])[0]

        payload = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter or None,
            include=["distances", "metadatas", "documents"],
        )

        ids = payload.get("ids", [[]])[0]
        distances = payload.get("distances", [[]])[0]
        metadatas = payload.get("metadatas", [[]])[0]
        documents = payload.get("documents", [[]])[0]

        hits: list[DenseHit] = []
        for index, doc_id in enumerate(ids):
            distance = float(distances[index]) if index < len(distances) else 1.0
            # Chroma distance is lower-is-better. Convert to a monotonic similarity score.
            score = 1.0 / (1.0 + distance)
            metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
            text = documents[index] if index < len(documents) and isinstance(documents[index], str) else ""
            hits.append(
                DenseHit(
                    doc_id=str(doc_id),
                    score=score,
                    rank=index + 1,
                    metadata=metadata,
                    text=text,
                )
            )
        return hits


def build_chroma_where(filters: RetrievalFilters | None) -> dict[str, Any]:
    """Translate supported filters into Chroma's metadata filter format."""
    if filters is None:
        return {}

    clauses: list[dict[str, Any]] = []

    if filters.source:
        lowered = filters.source.strip().lower()
        if lowered:
            clauses.append({"source": lowered})

    if filters.department:
        department = filters.department.strip().upper()
        if department:
            clauses.append({"department": department})

    if not clauses:
        return {}

    if len(clauses) == 1:
        return clauses[0]

    return {"$and": clauses}
