from __future__ import annotations
"""Hybrid retrieval orchestration and Reciprocal Rank Fusion (RRF)."""

from dataclasses import dataclass
from typing import Any

from rag.indexing.embeddings import EmbeddingBackend
from rag.models import RetrievalHit, RetrievalRequest, RetrievalResponse
from rag.retrieval.sparse_index import SparseHit, SparseKeywordIndex
from rag.indexing.vector_store import ChromaVectorStore, DenseHit

DEFAULT_RRF_K = 60


@dataclass
class _FusionState:
    """Temporary accumulator used while merging dense and sparse rankings."""

    score: float
    dense_rank: int | None
    sparse_rank: int | None
    metadata: dict[str, Any]
    text: str


class HybridRetriever:
    """Coordinates dense retrieval, sparse retrieval, and rank fusion."""

    def __init__(
        self,
        vector_store: ChromaVectorStore,
        sparse_index: SparseKeywordIndex,
        embedding_backend: EmbeddingBackend,
        rrf_k: int = DEFAULT_RRF_K,
        candidate_multiplier: int = 4,
        min_candidates: int = 40,
    ) -> None:
        self.vector_store = vector_store
        self.sparse_index = sparse_index
        self.embedding_backend = embedding_backend
        self.rrf_k = rrf_k
        self.candidate_multiplier = candidate_multiplier
        self.min_candidates = min_candidates

    def search(self, request: RetrievalRequest) -> RetrievalResponse:
        """Execute the full hybrid retrieval flow for one user query."""
        # Pull a wider candidate pool than the final `k` so RRF has enough
        # overlap and headroom to produce a better final ranking.
        candidate_count = max(request.k * self.candidate_multiplier, self.min_candidates)

        dense_hits = self.vector_store.query(
            query_text=request.query,
            backend=self.embedding_backend,
            filters=request.filters,
            n_results=candidate_count,
        )
        dense_hits = [hit for hit in dense_hits if _matches_instructor_filter(hit, request)]

        sparse_hits = self.sparse_index.query(
            query_text=request.query,
            filters=request.filters,
            limit=candidate_count,
            fuzzy_bonus=True,
        )

        fused = reciprocal_rank_fusion(
            dense_hits=dense_hits,
            sparse_hits=sparse_hits,
            rrf_k=self.rrf_k,
            limit=request.k,
        )

        return RetrievalResponse(query=request.query, hits=fused)


def _matches_instructor_filter(hit: DenseHit, request: RetrievalRequest) -> bool:
    """Apply instructor filtering on dense hits after Chroma returns results.

    Instructor names are stored as a flattened metadata string, so we do this
    check in Python rather than relying on Chroma metadata operators.
    """
    filters = request.filters
    if filters is None or not filters.instructor_name:
        return True

    needle = filters.instructor_name.strip().lower()
    if not needle:
        return True

    haystack = str(hit.metadata.get("instructor_names") or "").lower()
    return needle in haystack


def reciprocal_rank_fusion(
    dense_hits: list[DenseHit],
    sparse_hits: list[SparseHit],
    rrf_k: int,
    limit: int,
) -> list[RetrievalHit]:
    """Merge two ranked lists using Reciprocal Rank Fusion.

    RRF is rank-based instead of score-based, which avoids having to calibrate
    BM25 scores against dense similarity scores that live on different scales.
    """
    state: dict[str, _FusionState] = {}

    for rank, hit in enumerate(dense_hits, start=1):
        fused = state.get(hit.doc_id)
        if fused is None:
            fused = _FusionState(
                score=0.0,
                dense_rank=rank,
                sparse_rank=None,
                metadata=dict(hit.metadata),
                text=hit.text,
            )
            state[hit.doc_id] = fused
        fused.score += 1.0 / (rrf_k + rank)
        if fused.dense_rank is None:
            fused.dense_rank = rank
        if not fused.text:
            fused.text = hit.text
        if not fused.metadata:
            fused.metadata = dict(hit.metadata)

    for rank, hit in enumerate(sparse_hits, start=1):
        fused = state.get(hit.doc_id)
        if fused is None:
            fused = _FusionState(
                score=0.0,
                dense_rank=None,
                sparse_rank=rank,
                metadata=dict(hit.metadata),
                text=hit.text,
            )
            state[hit.doc_id] = fused
        fused.score += 1.0 / (rrf_k + rank)
        if fused.sparse_rank is None:
            fused.sparse_rank = rank
        if not fused.text:
            fused.text = hit.text
        if not fused.metadata:
            fused.metadata = dict(hit.metadata)

    ordered = sorted(
        state.items(),
        key=lambda item: (
            -item[1].score,
            # Tie-breakers keep ordering deterministic when fused scores match.
            item[1].dense_rank or 10_000,
            item[1].sparse_rank or 10_000,
            item[0],
        ),
    )

    hits: list[RetrievalHit] = []
    for doc_id, fused in ordered[:limit]:
        metadata = fused.metadata
        hits.append(
            RetrievalHit(
                doc_id=doc_id,
                score=fused.score,
                dense_rank=fused.dense_rank,
                sparse_rank=fused.sparse_rank,
                source=str(metadata.get("source") or metadata.get("source_label") or ""),
                course_code=str(metadata.get("course_code") or ""),
                title=str(metadata.get("title") or ""),
                metadata=metadata,
                text=fused.text,
            )
        )

    return hits
