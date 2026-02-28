from chatbot_agent.retrieval_adapter import ChatbotRetrievalAdapter
from rag.models import RetrievalHit, RetrievalRequest, RetrievalResponse


class _RecordingRetrievalService:
    def __init__(self) -> None:
        self.requests: list[RetrievalRequest] = []

    def search(self, request: RetrievalRequest) -> RetrievalResponse:
        self.requests.append(request)
        return RetrievalResponse(
            query=request.query,
            hits=[
                RetrievalHit(
                    doc_id="cab:CSCI 0111:abc",
                    score=0.88,
                    dense_rank=1,
                    sparse_rank=2,
                    source="cab",
                    course_code="CSCI 0111",
                    title="Computing Foundations",
                    metadata={
                        "source": "cab",
                        "source_label": "CAB",
                        "course_code": "CSCI 0111",
                        "title": "Computing Foundations",
                        "department": "CSCI",
                    },
                    text="Course code: CSCI 0111",
                )
            ],
        )


def test_retrieve_cab_courses_applies_source_and_department_filters() -> None:
    service = _RecordingRetrievalService()
    adapter = ChatbotRetrievalAdapter(service, default_k=5)

    payload = adapter.retrieve_cab_courses(query="  foundations  ", department="csci")

    request = service.requests[-1]
    assert request.query == "foundations"
    assert request.k == 5
    assert request.filters is not None
    assert request.filters.source == "cab"
    assert request.filters.department == "CSCI"
    assert payload["retrieval_count"] == 1
    assert payload["retrieved_courses"][0]["source"] == "CAB"
    assert payload["retrieved_courses"][0]["similarity"] == 0.88
    assert payload["retrieved_courses"][0]["metadata"]["department"] == "CSCI"
    assert payload["retrieved_courses"][0]["metadata"]["source_label"] == "CAB"


def test_retrieve_bulletin_courses_uses_bulletin_source_scope() -> None:
    service = _RecordingRetrievalService()
    adapter = ChatbotRetrievalAdapter(service)

    payload = adapter.retrieve_bulletin_courses(query="history", department=None)

    request = service.requests[-1]
    assert request.filters is not None
    assert request.filters.source == "bulletin"
    assert payload["source_scope"] == "bulletin"


def test_retrieve_all_courses_allows_k_override_with_clamp() -> None:
    service = _RecordingRetrievalService()
    adapter = ChatbotRetrievalAdapter(service)

    adapter.retrieve_all_courses(query="history", department=None, k=25)

    request = service.requests[-1]
    assert request.k == 20
