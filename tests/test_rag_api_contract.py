import json
import time

import pytest

try:
    from fastapi.testclient import TestClient
except Exception as exc:
    pytest.skip(f"fastapi test dependencies unavailable: {exc}", allow_module_level=True)

import app as api
from chatbot_agent.models import EvaluateResponse, RetrievedCourseSummary
from chatbot_agent.service import PreparedChatQuery


class _FakeChatbotService:
    def prepare_query(self, query: str, department: str | None = None) -> PreparedChatQuery:
        return PreparedChatQuery(
            started_at=time.perf_counter(),
            query=query,
            department=department,
            retrieved_courses=[
                RetrievedCourseSummary(
                    course_code="CSCI 0111",
                    title="Computing Foundations",
                    department="CSCI",
                    similarity=0.91,
                    source="CAB",
                    metadata={
                        "source": "cab",
                        "source_label": "CAB",
                        "course_code": "CSCI 0111",
                        "title": "Computing Foundations",
                        "department": "CSCI",
                        "instructor_names": ["Ada Lovelace"],
                        "meetings": ["MWF 10-10:50a"],
                        "course_url": "https://example.test/csci-0111",
                        "has_prerequisites": False,
                    },
                )
            ],
        )

    async def stream_prepared_query(self, prepared: PreparedChatQuery):
        yield (
            "event: retrieval\n"
            "data: "
            + json.dumps(
                {
                    "query": prepared.query,
                    "retrieved_courses": [course.model_dump() for course in prepared.retrieved_courses],
                    "retrieval_count": prepared.retrieval_count,
                }
            )
            + "\n\n"
        )
        yield 'event: token\ndata: {"delta": "Course "}\n\n'
        yield 'event: token\ndata: {"delta": "details"}\n\n'
        yield (
            "event: done\n"
            'data: {"response_text": "Course details", "latency_ms": 12, "retrieval_count": 1}\n\n'
        )

    async def evaluate(self, query: str, department: str | None = None) -> EvaluateResponse:
        return EvaluateResponse(
            query=query,
            department=department,
            latency_ms=12,
            retrieval_count=1,
            retrieved_courses=[
                RetrievedCourseSummary(
                    course_code="CSCI 0111",
                    title="Computing Foundations",
                    department="CSCI",
                    similarity=0.91,
                    source="CAB",
                    metadata={
                        "source": "cab",
                        "source_label": "CAB",
                        "course_code": "CSCI 0111",
                        "title": "Computing Foundations",
                        "department": "CSCI",
                        "instructor_names": ["Ada Lovelace"],
                        "meetings": ["MWF 10-10:50a"],
                        "course_url": "https://example.test/csci-0111",
                        "has_prerequisites": False,
                    },
                )
            ],
            model="gpt-4.1-mini",
        )


def test_query_endpoint_streams_sse_events(monkeypatch) -> None:
    monkeypatch.setattr(api, "get_chatbot_service", lambda: _FakeChatbotService())

    client = TestClient(api.app)

    with client.stream("POST", "/query", json={"q": "csci foundations", "department": "csci"}) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: retrieval" in body
    assert "event: token" in body
    assert "event: done" in body
    assert '"course_code": "CSCI 0111"' in body
    assert '"metadata": {"source": "cab"' in body


def test_evaluate_endpoint_returns_metrics(monkeypatch) -> None:
    monkeypatch.setattr(api, "get_chatbot_service", lambda: _FakeChatbotService())

    client = TestClient(api.app)

    response = client.post("/evaluate", json={"q": "csci foundations", "department": "csci"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "csci foundations"
    assert payload["department"] == "csci"
    assert payload["latency_ms"] == 12
    assert payload["retrieval_count"] == 1
    assert payload["retrieved_courses"][0]["source"] == "CAB"
    assert payload["retrieved_courses"][0]["metadata"]["instructor_names"] == ["Ada Lovelace"]
    assert payload["model"] == "gpt-4.1-mini"


def test_query_endpoint_rejects_whitespace_query(monkeypatch) -> None:
    monkeypatch.setattr(api, "get_chatbot_service", lambda: _FakeChatbotService())

    client = TestClient(api.app)

    response = client.post("/query", json={"q": "   "})

    assert response.status_code == 422
