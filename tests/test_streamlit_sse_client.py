import pytest

from ui.sse_client import DoneEvent, ErrorEvent, RetrievalEvent, SSEClientError, TokenEvent, stream_query


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        lines: list[str] | None = None,
        json_body: object | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/event-stream; charset=utf-8"}
        self._lines = lines or []
        self._json_body = json_body
        self.text = text
        self.closed = False

    def iter_lines(self, decode_unicode: bool = False):
        for line in self._lines:
            yield line if decode_unicode else line.encode("utf-8")

    def json(self):
        if self._json_body is None:
            raise ValueError("No JSON body configured.")
        return self._json_body

    def close(self) -> None:
        self.closed = True


def test_stream_query_parses_standard_event_sequence(monkeypatch) -> None:
    captured: dict[str, object] = {}
    response = _FakeResponse(
        lines=[
            "event: retrieval",
            'data: {"query": "csci foundations", "retrieved_courses": [{"course_code": "CSCI 0111", "title": "Computing Foundations", "department": "CSCI", "similarity": 0.91, "source": "CAB"}], "retrieval_count": 1}',
            "",
            "event: token",
            'data: {"delta": "Course "}',
            "",
            "event: token",
            'data: {"delta": "details"}',
            "",
            "event: done",
            'data: {"response_text": "Course details", "latency_ms": 12, "retrieval_count": 1, "retrieved_courses": [{"course_code": "CSCI 0111", "title": "Computing Foundations", "department": "CSCI", "similarity": 0.91, "source": "CAB"}]}',
            "",
        ]
    )

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return response

    monkeypatch.setattr("ui.sse_client.requests.post", fake_post)

    events = list(stream_query("http://localhost:8000", "csci foundations", "CSCI"))

    assert response.closed is True
    assert captured["url"] == "http://localhost:8000/query"
    assert captured["kwargs"]["json"] == {"q": "csci foundations", "department": "CSCI"}
    assert captured["kwargs"]["stream"] is True
    assert isinstance(events[0], RetrievalEvent)
    assert isinstance(events[1], TokenEvent)
    assert isinstance(events[2], TokenEvent)
    assert isinstance(events[3], DoneEvent)
    assert events[3].response_text == "Course details"
    assert len(events[3].retrieved_courses) == 1


def test_stream_query_joins_multiple_data_lines(monkeypatch) -> None:
    response = _FakeResponse(
        lines=[
            "event: token",
            'data: {"delta":',
            'data:  "Course details"}',
            "",
            "event: done",
            'data: {"response_text": "Course details", "latency_ms": 4, "retrieval_count": 0, "retrieved_courses": []}',
            "",
        ]
    )

    monkeypatch.setattr("ui.sse_client.requests.post", lambda *args, **kwargs: response)

    events = list(stream_query("http://localhost:8000", "csci foundations"))

    assert len(events) == 2
    assert isinstance(events[0], TokenEvent)
    assert events[0].delta == "Course details"


def test_stream_query_raises_for_http_error_response(monkeypatch) -> None:
    response = _FakeResponse(
        status_code=422,
        headers={"content-type": "application/json"},
        json_body={"detail": "`q` must not be empty."},
    )

    monkeypatch.setattr("ui.sse_client.requests.post", lambda *args, **kwargs: response)

    with pytest.raises(SSEClientError, match="API request failed with status 422: `q` must not be empty."):
        list(stream_query("http://localhost:8000", ""))


def test_stream_query_raises_for_malformed_json(monkeypatch) -> None:
    response = _FakeResponse(
        lines=[
            "event: token",
            'data: {"delta": "broken"',
            "",
        ]
    )

    monkeypatch.setattr("ui.sse_client.requests.post", lambda *args, **kwargs: response)

    with pytest.raises(SSEClientError, match="Malformed JSON payload for SSE event 'token'."):
        list(stream_query("http://localhost:8000", "csci foundations"))


def test_stream_query_ignores_unknown_events(monkeypatch) -> None:
    response = _FakeResponse(
        lines=[
            "event: ping",
            'data: {"ok": true}',
            "",
            "event: done",
            'data: {"response_text": "Done", "latency_ms": 3, "retrieval_count": 0, "retrieved_courses": []}',
            "",
        ]
    )

    monkeypatch.setattr("ui.sse_client.requests.post", lambda *args, **kwargs: response)

    events = list(stream_query("http://localhost:8000", "csci foundations"))

    assert len(events) == 1
    assert isinstance(events[0], DoneEvent)


def test_stream_query_returns_backend_error_event(monkeypatch) -> None:
    response = _FakeResponse(
        lines=[
            "event: error",
            'data: {"message": "upstream failed"}',
            "",
        ]
    )

    monkeypatch.setattr("ui.sse_client.requests.post", lambda *args, **kwargs: response)

    events = list(stream_query("http://localhost:8000", "csci foundations"))

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert events[0].message == "upstream failed"
