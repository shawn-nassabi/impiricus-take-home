from __future__ import annotations
"""Shared types for normalization, retrieval, and API responses."""

from dataclasses import dataclass
from typing import Any, Protocol

try:
    from pydantic import BaseModel, Field
except Exception:
    class BaseModel:  # type: ignore[no-redef]
        """Minimal fallback used only when pydantic is unavailable in the local env.

        This keeps tests and pure-Python code importable in environments where the
        compiled `pydantic_core` wheel is missing or has the wrong architecture.
        """

        def __init__(self, **data: Any) -> None:
            annotations = getattr(self.__class__, "__annotations__", {})
            for key in annotations:
                if key in data:
                    value = data[key]
                else:
                    value = getattr(self.__class__, key, None)
                setattr(self, key, value)

        def model_dump(self) -> dict[str, Any]:
            annotations = getattr(self.__class__, "__annotations__", {})
            return {key: getattr(self, key) for key in annotations}

    def Field(*args: Any, default: Any = None, **_: Any) -> Any:  # type: ignore[no-redef]
        """Fallback that preserves class defaults without validation behavior."""
        if args:
            return args[0]
        return default


@dataclass(frozen=True)
class CanonicalCourseDocument:
    """Canonical representation used by both dense and sparse retrieval."""

    doc_id: str
    source: str
    source_label: str
    course_code: str
    title: str
    description: str | None
    prerequisites: str | None
    department: str | None
    instructor_names: list[str]
    meetings: list[str]
    course_url: str | None
    text: str

    def chroma_metadata(self) -> dict[str, str | int | float | bool]:
        """Flatten metadata into Chroma-friendly scalar fields.

        Chroma metadata filtering works best with simple scalar values, so list
        fields such as instructor names are joined into a single string.
        """
        return {
            "source": self.source,
            "source_label": self.source_label,
            "course_code": self.course_code,
            "title": self.title,
            "department": self.department or "",
            "instructor_names": " | ".join(self.instructor_names),
            "course_url": self.course_url or "",
            "has_prerequisites": bool(self.prerequisites),
        }

    def response_metadata(self) -> dict[str, Any]:
        """Return richer metadata for API responses and sparse retrieval results."""
        return {
            "source": self.source,
            "source_label": self.source_label,
            "course_code": self.course_code,
            "title": self.title,
            "department": self.department,
            "instructor_names": self.instructor_names,
            "meetings": self.meetings,
            "course_url": self.course_url,
            "has_prerequisites": bool(self.prerequisites),
        }

    def to_json_dict(self) -> dict[str, Any]:
        """Serialize the canonical document to the on-disk JSONL corpus format."""
        return {
            "doc_id": self.doc_id,
            "source": self.source,
            "source_label": self.source_label,
            "course_code": self.course_code,
            "title": self.title,
            "description": self.description,
            "prerequisites": self.prerequisites,
            "department": self.department,
            "instructor_names": self.instructor_names,
            "meetings": self.meetings,
            "course_url": self.course_url,
            "text": self.text,
        }

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> "CanonicalCourseDocument":
        """Rehydrate a canonical document from persisted JSONL data."""
        return cls(
            doc_id=str(payload["doc_id"]),
            source=str(payload["source"]),
            source_label=str(payload["source_label"]),
            course_code=str(payload["course_code"]),
            title=str(payload["title"]),
            description=payload.get("description"),
            prerequisites=payload.get("prerequisites"),
            department=payload.get("department"),
            instructor_names=list(payload.get("instructor_names") or []),
            meetings=list(payload.get("meetings") or []),
            course_url=payload.get("course_url"),
            text=str(payload["text"]),
        )


class RetrievalFilters(BaseModel):
    """Supported metadata filters for retrieval."""

    source: str | None = None
    department: str | None = None
    instructor_name: str | None = None


class RetrievalRequest(BaseModel):
    """Stable request contract for the retriever / API."""

    query: str = Field(min_length=1)
    k: int = Field(default=8, ge=1, le=50)
    filters: RetrievalFilters | None = None


class RetrievalHit(BaseModel):
    """One ranked retrieval result, including fusion metadata."""

    doc_id: str
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    source: str
    course_code: str
    title: str
    metadata: dict[str, Any]
    text: str


class RetrievalResponse(BaseModel):
    """Retrieval-only response returned by the API and service layer."""

    query: str
    hits: list[RetrievalHit]


class RetrievalService(Protocol):
    """Interface the future chatbot layer can depend on."""

    def search(self, request: RetrievalRequest) -> RetrievalResponse:
        ...
