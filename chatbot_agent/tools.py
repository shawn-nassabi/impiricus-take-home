from __future__ import annotations
"""LangChain tool definitions backed by the local hybrid retriever."""

from contextvars import ContextVar, Token
from dataclasses import dataclass
import logging
from typing import Any, Callable

from chatbot_agent.logging_utils import COLOR_BLUE, COLOR_YELLOW, format_log
from rag.models import BaseModel, Field

from chatbot_agent.retrieval_adapter import ChatbotRetrievalAdapter

LOGGER = logging.getLogger(__name__)
_TOOL_CALL_COUNT: ContextVar[int] = ContextVar("chatbot_tool_call_count", default=0)
_TOOL_CALL_LIMIT: ContextVar[int] = ContextVar("chatbot_tool_call_limit", default=0)
_TOOL_REFERENCES: ContextVar[list[dict[str, Any]] | None] = ContextVar("chatbot_tool_references", default=None)
_REQUEST_DEPARTMENT: ContextVar[str | None] = ContextVar("chatbot_request_department", default=None)


class CourseSearchToolInput(BaseModel):
    """Input schema shared by the retrieval tools."""

    query: str = Field(min_length=1)
    department: str | None = None
    k: int | None = Field(default=None, ge=1, le=20)


@dataclass(frozen=True)
class ToolSpec:
    """Description plus callable for building LangChain tools lazily."""

    name: str
    description: str
    handler: Callable[..., dict[str, Any]]


def build_tool_specs(adapter: ChatbotRetrievalAdapter) -> list[ToolSpec]:
    """Build the retrieval tools the agent can invoke."""

    def search_cab_courses(query: str, department: str | None = None, k: int | None = None) -> dict[str, Any]:
        """Use CAB data for detailed scheduling and instructor questions."""
        allowed, call_number, call_limit = consume_tool_call("search_cab_courses")
        if not allowed:
            LOGGER.info(
                format_log(
                    "agent_tool_limit_reached",
                    COLOR_YELLOW,
                    tool="search_cab_courses",
                    attempted_call=call_number,
                    limit=call_limit,
                )
            )
            return _tool_limit_payload("CAB", call_limit)
        effective_department = _resolve_effective_department(department)
        LOGGER.info(
            format_log(
                "agent_tool_start",
                COLOR_BLUE,
                tool="search_cab_courses",
                call=call_number,
                limit=call_limit,
                query=query,
                department=effective_department,
                k=k,
            )
        )
        payload = adapter.retrieve_cab_courses(query=query, department=effective_department, k=k)
        _record_tool_references(payload)
        LOGGER.info(
            format_log(
                "agent_tool_done",
                COLOR_BLUE,
                tool="search_cab_courses",
                call=call_number,
                retrieval_count=payload.get("retrieval_count", 0),
            )
        )
        return payload

    def search_bulletin_courses(query: str, department: str | None = None, k: int | None = None) -> dict[str, Any]:
        """Use bulletin data for general catalog title and description questions."""
        allowed, call_number, call_limit = consume_tool_call("search_bulletin_courses")
        if not allowed:
            LOGGER.info(
                format_log(
                    "agent_tool_limit_reached",
                    COLOR_YELLOW,
                    tool="search_bulletin_courses",
                    attempted_call=call_number,
                    limit=call_limit,
                )
            )
            return _tool_limit_payload("bulletin", call_limit)
        effective_department = _resolve_effective_department(department)
        LOGGER.info(
            format_log(
                "agent_tool_start",
                COLOR_BLUE,
                tool="search_bulletin_courses",
                call=call_number,
                limit=call_limit,
                query=query,
                department=effective_department,
                k=k,
            )
        )
        payload = adapter.retrieve_bulletin_courses(query=query, department=effective_department, k=k)
        _record_tool_references(payload)
        LOGGER.info(
            format_log(
                "agent_tool_done",
                COLOR_BLUE,
                tool="search_bulletin_courses",
                call=call_number,
                retrieval_count=payload.get("retrieval_count", 0),
            )
        )
        return payload

    return [
        ToolSpec(
            name="search_cab_courses",
            description=(
                "Retrieve course records from CAB only. Prefer this for meeting times, "
                "sections, instructors, and operational course details."
            ),
            handler=search_cab_courses,
        ),
        ToolSpec(
            name="search_bulletin_courses",
            description=(
                "Retrieve course records from the bulletin only. Prefer this for "
                "catalog descriptions and general course summaries."
            ),
            handler=search_bulletin_courses,
        ),
    ]


def build_langchain_tools(adapter: ChatbotRetrievalAdapter) -> list[Any]:
    """Create StructuredTool instances lazily so imports stay optional."""
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise RuntimeError(
            "LangChain tool support is unavailable. Install `langchain` and retry."
        ) from exc

    tools: list[Any] = []
    for spec in build_tool_specs(adapter):
        tools.append(
            StructuredTool.from_function(
                func=spec.handler,
                name=spec.name,
                description=spec.description,
                args_schema=CourseSearchToolInput,
            )
        )
    return tools


def activate_tool_call_budget(
    max_calls: int,
    request_department: str | None = None,
) -> tuple[Token[int], Token[int], Token[list[dict[str, Any]] | None], Token[str | None]]:
    """Initialize per-request tool-call counters and request-scoped constraints."""
    count_token = _TOOL_CALL_COUNT.set(0)
    limit_token = _TOOL_CALL_LIMIT.set(max_calls)
    references_token = _TOOL_REFERENCES.set([])
    department_token = _REQUEST_DEPARTMENT.set((request_department or "").strip().upper() or None)
    return count_token, limit_token, references_token, department_token


def reset_tool_call_budget(
    tokens: tuple[Token[int], Token[int], Token[list[dict[str, Any]] | None], Token[str | None]]
) -> None:
    """Restore the previous per-request tool-call counter state."""
    count_token, limit_token, references_token, department_token = tokens
    _TOOL_CALL_COUNT.reset(count_token)
    _TOOL_CALL_LIMIT.reset(limit_token)
    _TOOL_REFERENCES.reset(references_token)
    _REQUEST_DEPARTMENT.reset(department_token)


def consume_tool_call(tool_name: str) -> tuple[bool, int, int]:
    """Increment the per-request tool-call count and enforce the limit."""
    del tool_name
    current_count = _TOOL_CALL_COUNT.get()
    call_limit = _TOOL_CALL_LIMIT.get()
    next_count = current_count + 1

    if call_limit and next_count > call_limit:
        return False, next_count, call_limit

    _TOOL_CALL_COUNT.set(next_count)
    return True, next_count, call_limit


def _tool_limit_payload(source_scope: str, call_limit: int) -> dict[str, Any]:
    """Structured tool payload returned when the per-request limit is exceeded."""
    return {
        "query": "",
        "retrieved_courses": [],
        "retrieval_count": 0,
        "source_scope": source_scope,
        "limit_reached": True,
        "message": f"Tool call limit reached ({call_limit}).",
    }


def get_recorded_tool_references() -> list[dict[str, Any]]:
    """Return references collected from tool outputs in the current request."""
    stored = _TOOL_REFERENCES.get()
    if stored is None:
        return []
    return [dict(item) for item in stored if isinstance(item, dict)]


def _record_tool_references(payload: dict[str, Any]) -> None:
    """Append tool-returned references to the per-request capture buffer."""
    stored = _TOOL_REFERENCES.get()
    if stored is None:
        return

    courses = payload.get("retrieved_courses")
    if not isinstance(courses, list):
        return

    for item in courses:
        if isinstance(item, dict):
            stored.append(dict(item))


def _resolve_effective_department(requested_department: str | None) -> str | None:
    """Only apply department filtering when the incoming request explicitly set it."""
    del requested_department
    return _REQUEST_DEPARTMENT.get()
