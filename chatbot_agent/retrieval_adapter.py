from __future__ import annotations
"""Adapters that reshape the retrieval service for chatbot use cases."""

import re
from typing import Any

from chatbot_agent.models import RetrievedCourseSummary
from chatbot_agent.schedule_utils import matches_schedule_filter
from rag.models import (
    CanonicalCourseDocument,
    RetrievalFilters,
    RetrievalHit,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalService,
)
from rag.retrieval.query_service import normalize_course_code

DEFAULT_CHATBOT_K = 8


class ChatbotRetrievalAdapter:
    """Wrap the existing hybrid retriever with chatbot-friendly helpers."""

    def __init__(self, service: RetrievalService, default_k: int = DEFAULT_CHATBOT_K) -> None:
        self.service = service
        self.default_k = default_k

    def retrieve_all_courses(
        self,
        query: str,
        department: str | None = None,
        k: int | None = None,
    ) -> dict[str, Any]:
        """Run the default hybrid search without constraining source."""
        response = self._search(query=query, department=department, k=k)
        return self._payload_from_response(response=response, source_scope="all")

    def retrieve_cab_courses(
        self,
        query: str,
        department: str | None = None,
        k: int | None = None,
    ) -> dict[str, Any]:
        """Retrieve only CAB-backed course documents."""
        response = self._search(query=query, department=department, source="cab", k=k)
        return self._payload_from_response(response=response, source_scope="CAB")

    def retrieve_bulletin_courses(
        self,
        query: str,
        department: str | None = None,
        k: int | None = None,
    ) -> dict[str, Any]:
        """Retrieve only bulletin-backed course documents."""
        response = self._search(query=query, department=department, source="bulletin", k=k)
        return self._payload_from_response(response=response, source_scope="bulletin")

    def _search(
        self,
        query: str,
        department: str | None = None,
        source: str | None = None,
        k: int | None = None,
    ) -> RetrievalResponse:
        """Translate the chatbot API contract into the retrieval contract."""
        clean_query = query.strip()
        clean_department = (department or "").strip().upper() or None
        resolved_k = self._resolve_k(k)
        filters = RetrievalFilters(source=source, department=clean_department, instructor_name=None)
        request = RetrievalRequest(query=clean_query, k=resolved_k, filters=filters)
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

    def lookup_course_by_code(
        self,
        course_code: str,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Direct lookup of a course by its code, bypassing semantic search."""
        if not hasattr(self.service, "lookup_by_code"):
            return {
                "query": course_code,
                "retrieved_courses": [],
                "retrieval_count": 0,
                "source_scope": source or "all",
                "error": "Direct course lookup is not supported by this retrieval service.",
            }

        docs = self.service.lookup_by_code(course_code=course_code, source=source)
        summaries = [summarize_canonical_doc(doc) for doc in docs]
        return {
            "query": course_code,
            "retrieved_courses": [s.model_dump() for s in summaries],
            "retrieval_count": len(summaries),
            "source_scope": source or "all",
        }

    def search_by_schedule(
        self,
        query: str,
        day: str | None = None,
        after_time: str | None = None,
        before_time: str | None = None,
        source: str | None = None,
        department: str | None = None,
        k: int | None = None,
    ) -> dict[str, Any]:
        """Two-pass retrieval combining semantic search and corpus scan.

        Pass 1 -- hybrid search with a wide candidate pool, then schedule
        filter.  Pass 2 -- BM25 scoring across the *full* corpus with
        schedule pre-filtering (catches courses missed by the semantic
        truncation).  Results are merged and deduplicated.
        """
        desired_k = self._resolve_k(k)
        seen_doc_ids: set[str] = set()
        merged: list[RetrievedCourseSummary] = []

        # --- Pass 1: semantic search + schedule filter ---
        wide_k = max(desired_k * 5, 50)
        response = self._search(
            query=query, department=department, source=source, k=wide_k,
        )
        for hit in response.hits:
            summary = summarize_hit(hit)
            if not summary.meetings:
                continue
            if matches_schedule_filter(
                summary.meetings, day=day, after_time=after_time, before_time=before_time,
            ):
                merged.append(summary)
                seen_doc_ids.add(hit.doc_id)

        # --- Pass 2: corpus-scan fallback via BM25 ---
        if hasattr(self.service, "score_all_by_keyword"):
            clean_dept = (department or "").strip().upper() or None
            scored_docs = self.service.score_all_by_keyword(
                query=query, source=source, department=clean_dept,
            )
            for doc, bm25_score in scored_docs:
                if doc.doc_id in seen_doc_ids:
                    continue
                if not doc.meetings:
                    continue
                if not matches_schedule_filter(
                    doc.meetings, day=day, after_time=after_time, before_time=before_time,
                ):
                    continue
                merged.append(summarize_canonical_doc(doc))
                seen_doc_ids.add(doc.doc_id)

        merged = merged[:desired_k]

        return {
            "query": query,
            "retrieved_courses": [s.model_dump() for s in merged],
            "retrieval_count": len(merged),
            "source_scope": source or "all",
            "schedule_filter": {
                "day": day,
                "after_time": after_time,
                "before_time": before_time,
            },
        }

    def find_similar_courses(
        self,
        course_code: str,
        target_source: str | None = None,
        k: int | None = None,
    ) -> dict[str, Any]:
        """Find courses similar to a given course code, optionally in a different source."""
        if not hasattr(self.service, "lookup_by_code"):
            return {
                "query": course_code,
                "retrieved_courses": [],
                "retrieval_count": 0,
                "source_scope": target_source or "all",
                "error": "Direct course lookup is not supported by this retrieval service.",
            }

        ref_docs = self.service.lookup_by_code(course_code=course_code, source=None)
        if not ref_docs:
            return {
                "query": course_code,
                "retrieved_courses": [],
                "retrieval_count": 0,
                "source_scope": target_source or "all",
                "message": f"Could not find reference course {course_code}.",
            }

        ref_doc = ref_docs[0]
        query_text = ref_doc.text

        resolved_k = self._resolve_k(k)
        extra_k = resolved_k + len(ref_docs)
        response = self._search(
            query=query_text, source=target_source, k=extra_k,
        )

        ref_code_normalized = normalize_course_code(course_code)
        filtered: list[RetrievedCourseSummary] = []
        for hit in response.hits:
            hit_code = normalize_course_code(hit.course_code)
            if hit_code == ref_code_normalized:
                continue
            filtered.append(summarize_hit(hit))
            if len(filtered) >= resolved_k:
                break

        return {
            "query": f"similar to {course_code}",
            "reference_course": {
                "course_code": ref_doc.course_code,
                "title": ref_doc.title,
                "source": ref_doc.source_label,
            },
            "retrieved_courses": [s.model_dump() for s in filtered],
            "retrieval_count": len(filtered),
            "source_scope": target_source or "all",
        }

    def _resolve_k(self, k: int | None) -> int:
        """Clamp caller-provided k to a safe range for the chatbot."""
        if k is None:
            return self.default_k
        return max(1, min(int(k), 20))


def summarize_canonical_doc(doc: CanonicalCourseDocument) -> RetrievedCourseSummary:
    """Convert a canonical document into a chatbot summary."""
    source_text = doc.source_label
    if source_text.lower() == "cab":
        source_text = "CAB"

    return RetrievedCourseSummary(
        course_code=doc.course_code,
        title=doc.title,
        department=doc.department,
        similarity=1.0,
        source=source_text,
        description=doc.description,
        meetings=doc.meetings,
        instructors=doc.instructor_names,
        prerequisites=doc.prerequisites,
        metadata=doc.response_metadata(),
    )


def summarize_hit(hit: RetrievalHit) -> RetrievedCourseSummary:
    """Flatten the fields that the chatbot API exposes publicly."""
    metadata = dict(hit.metadata)
    raw_source = metadata.get("source_label") or metadata.get("source") or hit.source
    source_text = str(raw_source or "")
    if source_text.lower() == "cab":
        source_text = "CAB"

    department = metadata.get("department")

    meetings = _extract_list_field(metadata, "meetings")
    instructors = _extract_list_field(metadata, "instructor_names")
    description = _extract_str_field(metadata, "description")
    prerequisites = _extract_str_field(metadata, "prerequisites")

    if not meetings and hit.text:
        meetings = _parse_field_from_text(hit.text, "Meetings")
    if not instructors and hit.text:
        instructors = _parse_field_from_text(hit.text, "Instructors")
        if not instructors:
            raw_names = metadata.get("instructor_names")
            if isinstance(raw_names, str) and raw_names.strip():
                instructors = [n.strip() for n in raw_names.split("|") if n.strip()]
    if not description and hit.text:
        desc_parts = _parse_field_from_text(hit.text, "Description")
        description = desc_parts[0] if desc_parts else None
    if not prerequisites and hit.text:
        prereq_parts = _parse_field_from_text(hit.text, "Prerequisites")
        prerequisites = prereq_parts[0] if prereq_parts else None

    return RetrievedCourseSummary(
        course_code=str(metadata.get("course_code") or hit.course_code),
        title=str(metadata.get("title") or hit.title),
        department=str(department) if department else None,
        similarity=float(hit.score),
        source=source_text,
        description=description,
        meetings=meetings,
        instructors=instructors,
        prerequisites=prerequisites,
        metadata=metadata,
    )


def _extract_list_field(metadata: dict[str, Any], key: str) -> list[str]:
    """Safely extract a list-of-strings field from metadata."""
    value = metadata.get(key)
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []


def _extract_str_field(metadata: dict[str, Any], key: str) -> str | None:
    """Safely extract a string field from metadata."""
    value = metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


_TEXT_FIELD_PATTERN = re.compile(r"^([A-Za-z ]+?):\s*(.+)$")


def _parse_field_from_text(text: str, field_name: str) -> list[str]:
    """Extract a labeled field from the canonical embedded text as a fallback."""
    for line in text.splitlines():
        m = _TEXT_FIELD_PATTERN.match(line.strip())
        if m and m.group(1).strip().lower() == field_name.lower():
            raw = m.group(2).strip()
            return [part.strip() for part in raw.split(";") if part.strip()]
    return []
