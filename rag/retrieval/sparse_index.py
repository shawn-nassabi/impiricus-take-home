from __future__ import annotations
"""Local sparse retrieval using BM25 over the canonical document text."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag.models import CanonicalCourseDocument, RetrievalFilters

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+")


@dataclass(frozen=True)
class SparseHit:
    """Sparse retrieval result returned before hybrid fusion."""

    doc_id: str
    score: float
    rank: int
    metadata: dict[str, Any]
    text: str


class SparseKeywordIndex:
    """In-memory BM25 index rebuilt from persisted canonical documents."""

    def __init__(self, documents: list[CanonicalCourseDocument]) -> None:
        if not documents:
            raise ValueError("SparseKeywordIndex requires at least one document.")

        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise RuntimeError("rank-bm25 is required for sparse retrieval.") from exc

        self.documents = documents
        # The lookup is kept for future extensions where direct random access by
        # id may be useful during reranking or debugging.
        self._doc_lookup = {document.doc_id: document for document in documents}
        self._tokenized_docs = [tokenize(document.text) for document in documents]
        self._bm25 = BM25Okapi(self._tokenized_docs)

    @classmethod
    def from_documents(cls, documents: list[CanonicalCourseDocument]) -> "SparseKeywordIndex":
        """Factory for build-time sparse index creation."""
        return cls(documents=documents)

    @classmethod
    def load(cls, directory: Path) -> "SparseKeywordIndex":
        """Load the sparse index from the saved document payloads on disk."""
        payload_path = directory / "documents.jsonl"
        if not payload_path.exists():
            raise FileNotFoundError(payload_path)

        documents: list[CanonicalCourseDocument] = []
        for raw_line in payload_path.read_text().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                continue
            documents.append(CanonicalCourseDocument.from_json_dict(item))

        return cls.from_documents(documents)

    def save(self, directory: Path) -> None:
        """Persist the source documents needed to reconstruct the BM25 index."""
        directory.mkdir(parents=True, exist_ok=True)
        payload_path = directory / "documents.jsonl"
        lines = [json.dumps(document.to_json_dict(), ensure_ascii=True) for document in self.documents]
        payload_path.write_text("\n".join(lines) + ("\n" if lines else ""))

    def query(
        self,
        query_text: str,
        filters: RetrievalFilters | None,
        limit: int,
        fuzzy_bonus: bool = True,
    ) -> list[SparseHit]:
        """Run BM25 retrieval with optional fuzzy boosting on code/title."""
        query_tokens = tokenize(query_text)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        candidates: list[tuple[int, float]] = []
        for index, score in enumerate(scores):
            document = self.documents[index]
            if not matches_filters(document, filters):
                continue

            adjusted_score = float(score)
            if fuzzy_bonus:
                # BM25 handles token overlap well, while the fuzzy bonus helps
                # users who type partial course codes or slightly-off titles.
                adjusted_score += fuzzy_match_bonus(query_text=query_text, document=document)

            if adjusted_score <= 0:
                continue
            candidates.append((index, adjusted_score))

        candidates.sort(key=lambda item: item[1], reverse=True)
        hits: list[SparseHit] = []
        for rank, (index, score) in enumerate(candidates[:limit], start=1):
            document = self.documents[index]
            hits.append(
                SparseHit(
                    doc_id=document.doc_id,
                    score=float(score),
                    rank=rank,
                    metadata=document.response_metadata(),
                    text=document.text,
                )
            )
        return hits


def tokenize(text: str) -> list[str]:
    """Tokenize to lowercase alphanumeric terms for BM25 indexing."""
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def matches_filters(document: CanonicalCourseDocument, filters: RetrievalFilters | None) -> bool:
    """Apply metadata filters consistently on the sparse side."""
    if filters is None:
        return True

    if filters.source and document.source != filters.source.strip().lower():
        return False

    if filters.department:
        expected = filters.department.strip().upper()
        if (document.department or "") != expected:
            return False

    if filters.instructor_name:
        needle = filters.instructor_name.strip().lower()
        if needle and not any(needle in name.lower() for name in document.instructor_names):
            return False

    return True


def fuzzy_match_bonus(query_text: str, document: CanonicalCourseDocument) -> float:
    """Add a small score boost for near-matches on code and title.

    This is intentionally bounded so fuzzy matching nudges ordering instead of
    completely overwhelming the underlying BM25 score.
    """
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return 0.0

    query = query_text.strip()
    if not query:
        return 0.0

    code_ratio = float(fuzz.partial_ratio(query, document.course_code)) / 100.0
    title_ratio = float(fuzz.partial_ratio(query, document.title)) / 100.0
    return max(code_ratio, title_ratio) * 0.5
