from __future__ import annotations
"""Request and response models for the chatbot API surface."""

from rag.models import BaseModel, Field


class ChatQueryRequest(BaseModel):
    """Incoming request for the chatbot endpoints."""

    q: str = Field(min_length=1)
    department: str | None = None


class RetrievedCourseSummary(BaseModel):
    """Flattened retrieval metadata exposed through the chatbot API."""

    course_code: str
    title: str
    department: str | None = None
    similarity: float
    source: str
    description: str | None = None
    meetings: list[str] = Field(default_factory=list)
    instructors: list[str] = Field(default_factory=list)
    prerequisites: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class EvaluateResponse(BaseModel):
    """Diagnostics returned by the evaluation endpoint."""

    query: str
    department: str | None = None
    latency_ms: int
    retrieval_count: int
    retrieved_courses: list[RetrievedCourseSummary]
    model: str
