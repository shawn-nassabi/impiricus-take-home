import pytest

try:
    from fastapi.testclient import TestClient
except Exception as exc:
    pytest.skip(f"fastapi test dependencies unavailable: {exc}", allow_module_level=True)

import app as api
from rag.models import RetrievalHit, RetrievalRequest, RetrievalResponse


class _FakeService:
    def search(self, request: RetrievalRequest) -> RetrievalResponse:
        return RetrievalResponse(
            query=request.query,
            hits=[
                RetrievalHit(
                    doc_id="cab:CSCI 0111:abc",
                    score=0.9,
                    dense_rank=1,
                    sparse_rank=2,
                    source="cab",
                    course_code="CSCI 0111",
                    title="Computing Foundations",
                    metadata={"source": "cab", "course_code": "CSCI 0111", "title": "Computing Foundations"},
                    text="Course code: CSCI 0111\nTitle: Computing Foundations",
                )
            ],
        )


def test_query_endpoint_returns_retrieval_response(monkeypatch) -> None:
    monkeypatch.setattr(api, "get_service", lambda: _FakeService())

    client = TestClient(api.app)

    response = client.post(
        "/query",
        json={"query": "csci foundations", "k": 5, "filters": {"source": "cab"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "csci foundations"
    assert len(payload["hits"]) == 1
    assert payload["hits"][0]["doc_id"] == "cab:CSCI 0111:abc"
    assert payload["hits"][0]["source"] == "cab"
