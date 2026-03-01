import asyncio
import json

from chatbot_agent.models import RetrievedCourseSummary
from chatbot_agent.service import ChatbotService


class _FakeRetrievalAdapter:
    def retrieve_all_courses(self, query: str, department: str | None = None) -> dict[str, object]:
        return {
            "query": query,
            "retrieved_courses": [
                {
                    "course_code": "CSCI 0111",
                    "title": "Computing Foundations",
                    "department": "CSCI",
                    "similarity": 0.92,
                    "source": "CAB",
                    "metadata": {
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
                }
            ],
            "retrieval_count": 1,
            "source_scope": "all",
        }


class _FakeAgentRunner:
    model_name = "gpt-4.1-mini"

    def __init__(self, fail_on_stream: bool = False, references: list[dict[str, object]] | None = None) -> None:
        self.fail_on_stream = fail_on_stream
        self.references = references or []

    async def stream_answer(self, query: str, department: str | None = None):
        if self.fail_on_stream:
            raise RuntimeError("upstream failed")
        yield "Course "
        yield "details"

    async def generate_answer(self, query: str, department: str | None = None) -> str:
        return "Course details"

    def get_last_run_references(self) -> list[dict[str, object]]:
        return list(self.references)


async def _collect(async_iterable) -> list[str]:
    events: list[str] = []
    async for item in async_iterable:
        events.append(item)
    return events


def _event_payload(frame: str) -> dict[str, object]:
    lines = frame.strip().splitlines()
    data_line = next(line for line in lines if line.startswith("data: "))
    return json.loads(data_line.split("data: ", 1)[1])


def test_stream_prepared_query_emits_retrieval_then_tokens_then_done() -> None:
    service = ChatbotService(_FakeRetrievalAdapter(), _FakeAgentRunner())
    prepared = service.prepare_query(query="csci foundations", department="csci")

    events = asyncio.run(_collect(service.stream_prepared_query(prepared)))

    assert events[0].startswith("event: retrieval")
    assert events[1].startswith("event: token")
    assert events[2].startswith("event: token")
    assert events[3].startswith("event: done")

    done_payload = _event_payload(events[3])
    assert done_payload["response_text"] == "Course details"
    assert done_payload["retrieval_count"] == 1
    assert done_payload["retrieved_courses"][0]["course_code"] == "CSCI 0111"


def test_stream_prepared_query_emits_error_when_agent_fails() -> None:
    service = ChatbotService(_FakeRetrievalAdapter(), _FakeAgentRunner(fail_on_stream=True))
    prepared = service.prepare_query(query="csci foundations", department=None)

    events = asyncio.run(_collect(service.stream_prepared_query(prepared)))

    assert events[0].startswith("event: retrieval")
    assert events[1].startswith("event: error")
    error_payload = _event_payload(events[1])
    assert error_payload["message"] == "upstream failed"


def test_evaluate_returns_latency_and_retrieval_count() -> None:
    service = ChatbotService(_FakeRetrievalAdapter(), _FakeAgentRunner())

    response = asyncio.run(service.evaluate(query="csci foundations", department="csci"))

    assert response.query == "csci foundations"
    assert response.department == "CSCI"
    assert response.retrieval_count == 1
    assert response.model == "gpt-4.1-mini"
    assert isinstance(response.retrieved_courses[0], RetrievedCourseSummary)
    assert response.latency_ms >= 0


def test_stream_done_includes_additional_tool_references() -> None:
    extra_reference = {
        "course_code": "ARCH 1773",
        "title": "Bioarchaeology and Forensic Anthropology",
        "department": None,
        "similarity": 0.81,
        "source": "bulletin",
        "metadata": {
            "source": "bulletin",
            "course_code": "ARCH 1773",
            "title": "Bioarchaeology and Forensic Anthropology",
        },
    }
    service = ChatbotService(_FakeRetrievalAdapter(), _FakeAgentRunner(references=[extra_reference]))
    prepared = service.prepare_query(query="anthropology", department="anth")

    events = asyncio.run(_collect(service.stream_prepared_query(prepared)))

    done_payload = _event_payload(events[3])
    assert done_payload["retrieval_count"] == 2
    assert {item["course_code"] for item in done_payload["retrieved_courses"]} == {"CSCI 0111", "ARCH 1773"}
