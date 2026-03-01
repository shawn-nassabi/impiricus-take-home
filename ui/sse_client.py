from __future__ import annotations

"""Lightweight SSE client for the Streamlit frontend."""

import json
from dataclasses import dataclass
from typing import Iterable, Iterator, TypeAlias

try:
    import requests  # type: ignore[import-untyped]
    _REQUESTS_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - import failure depends on local env
    class _RequestsShim:
        """Minimal shim so the module remains importable when requests is broken."""

        RequestException = Exception
        Response = object
        post = None

    requests = _RequestsShim()  # type: ignore[assignment]
    _REQUESTS_IMPORT_ERROR = exc

DEFAULT_TIMEOUT = (5, 300)


class SSEClientError(RuntimeError):
    """Raised when the API stream cannot be established or parsed."""


@dataclass(frozen=True)
class RetrievalEvent:
    """Retrieval metadata emitted before token streaming begins."""

    query: str
    retrieved_courses: list[dict[str, object]]
    retrieval_count: int
    type: str = "retrieval"


@dataclass(frozen=True)
class TokenEvent:
    """Incremental token delta."""

    delta: str
    type: str = "token"


@dataclass(frozen=True)
class DoneEvent:
    """Final completion payload."""

    response_text: str
    latency_ms: int
    retrieval_count: int
    retrieved_courses: list[dict[str, object]]
    type: str = "done"


@dataclass(frozen=True)
class ErrorEvent:
    """Terminal stream error from the backend."""

    message: str
    type: str = "error"


StreamEvent: TypeAlias = RetrievalEvent | TokenEvent | DoneEvent | ErrorEvent


def stream_query(api_base_url: str, query: str, department: str | None = None) -> Iterator[StreamEvent]:
    """Send a POST request to `/query` and yield parsed SSE events."""
    post = getattr(requests, "post", None)
    if not callable(post):
        detail = ""
        if _REQUESTS_IMPORT_ERROR is not None:
            detail = f": {_REQUESTS_IMPORT_ERROR}"
        raise SSEClientError(f"The requests dependency is unavailable{detail}")

    payload: dict[str, object] = {"q": query}
    if department:
        payload["department"] = department

    response = None
    saw_terminal_event = False

    try:
        response = post(
            f"{api_base_url.rstrip('/')}/query",
            json=payload,
            headers={
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
            },
            stream=True,
            timeout=DEFAULT_TIMEOUT,
        )
        _ensure_streaming_response(response)

        for event in _iter_sse_events(response.iter_lines(decode_unicode=True)):
            yield event
            if isinstance(event, (DoneEvent, ErrorEvent)):
                saw_terminal_event = True

        if not saw_terminal_event:
            raise SSEClientError("Stream ended before the server sent a completion event.")
    except requests.RequestException as exc:
        raise SSEClientError(f"Could not connect to the API: {exc}") from exc
    finally:
        if response is not None:
            response.close()


def _ensure_streaming_response(response: requests.Response) -> None:
    """Validate the HTTP response before parsing the event stream."""
    if response.status_code != 200:
        raise SSEClientError(_format_http_error(response))

    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("text/event-stream"):
        body = _read_response_text(response)
        message = f"Expected a text/event-stream response, got {content_type or 'an unknown content type'}."
        if body:
            message = f"{message} Body: {body}"
        raise SSEClientError(message)


def _format_http_error(response: requests.Response) -> str:
    """Create a readable error message from a non-200 response."""
    prefix = f"API request failed with status {response.status_code}"

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict) and "detail" in payload:
        detail = payload["detail"]
        return f"{prefix}: {detail}"

    body = _read_response_text(response)
    if body:
        return f"{prefix}: {body}"
    return prefix


def _read_response_text(response: requests.Response) -> str:
    """Safely read and trim the response body for error messages."""
    body = (getattr(response, "text", "") or "").strip()
    if len(body) > 300:
        return f"{body[:297]}..."
    return body


def _iter_sse_events(lines: Iterable[str | bytes]) -> Iterator[StreamEvent]:
    """Parse raw SSE lines into typed events."""
    frame_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line

        if line == "":
            if frame_lines:
                event = _parse_sse_frame(frame_lines)
                if event is not None:
                    yield event
                frame_lines = []
            continue

        frame_lines.append(line)

    if frame_lines:
        event = _parse_sse_frame(frame_lines)
        if event is not None:
            yield event


def _parse_sse_frame(lines: list[str]) -> StreamEvent | None:
    """Parse a single SSE frame."""
    event_name: str | None = None
    data_lines: list[str] = []

    for line in lines:
        if not line or line.startswith(":"):
            continue

        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip() or None
            continue

        if line.startswith("data:"):
            value = line.split(":", 1)[1]
            if value.startswith(" "):
                value = value[1:]
            data_lines.append(value)

    if event_name is None or not data_lines:
        return None

    try:
        payload = json.loads("\n".join(data_lines))
    except json.JSONDecodeError as exc:
        raise SSEClientError(f"Malformed JSON payload for SSE event '{event_name}'.") from exc

    if not isinstance(payload, dict):
        raise SSEClientError(f"Expected an object payload for SSE event '{event_name}'.")

    if event_name == "retrieval":
        courses = payload.get("retrieved_courses")
        return RetrievalEvent(
            query=str(payload.get("query", "")),
            retrieved_courses=[item for item in courses if isinstance(item, dict)] if isinstance(courses, list) else [],
            retrieval_count=_coerce_int(payload.get("retrieval_count")),
        )

    if event_name == "token":
        return TokenEvent(delta=str(payload.get("delta", "")))

    if event_name == "done":
        courses = payload.get("retrieved_courses")
        return DoneEvent(
            response_text=str(payload.get("response_text", "")),
            latency_ms=_coerce_int(payload.get("latency_ms")),
            retrieval_count=_coerce_int(payload.get("retrieval_count")),
            retrieved_courses=[item for item in courses if isinstance(item, dict)] if isinstance(courses, list) else [],
        )

    if event_name == "error":
        return ErrorEvent(message=str(payload.get("message", "The stream failed.")))

    return None


def _coerce_int(value: object) -> int:
    """Best-effort integer conversion for event payloads."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
