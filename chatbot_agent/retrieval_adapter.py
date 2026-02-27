from __future__ import annotations
"""Adapters that reshape the retrieval service for chatbot use cases."""

from typing import Any

from chatbot_agent.models import RetrievedCourseSummary
from rag.models import RetrievalFilters, RetrievalHit, RetrievalRequest, RetrievalResponse, RetrievalService

DEFAULT_CHATBOT_K = 8


class ChatbotRetrievalAdapter:
    """Wrap the existing hybrid retriever with chatbot-friendly helpers."""

    def __init__(self, service: RetrievalService, default_k: int = DEFAULT_CHATBOT_K) -> None:
        self.service = service
        self.default_k = default_k

    def retrieve_all_courses(self, query: str, department: str | None = None) -> dict[str, Any]:
        """Run the default hybrid search without constraining source."""
        response = self._search(query=query, department=department)
        return self._payload_from_response(response=response, source_scope="all")

    def retrieve_cab_courses(self, query: str, department: str | None = None) -> dict[str, Any]:
        """Retrieve only CAB-backed course documents."""
        response = self._search(query=query, department=department, source="cab")
        return self._payload_from_response(response=response, source_scope="CAB")

    def retrieve_bulletin_courses(self, query: str, department: str | None = None) -> dict[str, Any]:
        """Retrieve only bulletin-backed course documents."""
        response = self._search(query=query, department=department, source="bulletin")
        return self._payload_from_response(response=response, source_scope="bulletin")

    def _search(
        self,
        query: str,
        department: str | None = None,
        source: str | None = None,
    ) -> RetrievalResponse:
        """Translate the chatbot API contract into the retrieval contract."""
        clean_query = query.strip()
        clean_department = (department or "").strip().upper() or None
        filters = RetrievalFilters(source=source, department=clean_department, instructor_name=None)
        request = RetrievalRequest(query=clean_query, k=self.default_k, filters=filters)
        return self.service.search(request)

    def _payload_from_response(self, response: RetrievalResponse, source_scope: str) -> dict[str, Any]:
        """Convert retrieval hits into a stable tool/API payload."""
        summaries = [summarize_hit(hit) for hit in response.hits]
        return {
            "query": response.query,
            "retrieved_courses": [summary.model_dump() for summary in summaries],
            "retrieval_count": len(summaries),
            "source_scope": source_scope,
        }


def summarize_hit(hit: RetrievalHit) -> RetrievedCourseSummary:
    """Flatten the fields that the chatbot API exposes publicly."""
    metadata = hit.metadata
    raw_source = metadata.get("source_label") or metadata.get("source") or hit.source
    source_text = str(raw_source or "")
    if source_text.lower() == "cab":
        source_text = "CAB"

    department = metadata.get("department")
    return RetrievedCourseSummary(
        course_code=str(metadata.get("course_code") or hit.course_code),
        title=str(metadata.get("title") or hit.title),
        department=str(department) if department else None,
        similarity=float(hit.score),
        source=source_text,
    )
