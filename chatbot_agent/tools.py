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
    """Input schema shared by the semantic retrieval tools."""

    query: str = Field(min_length=1)
    department: str | None = None
    k: int | None = Field(default=None, ge=1, le=20)


class CourseCodeLookupInput(BaseModel):
    """Input schema for direct course code lookup."""

    course_code: str = Field(min_length=1)
    source: str | None = Field(
        default=None,
        description='Optional source filter: "cab" or "bulletin".',
    )


class ScheduleSearchInput(BaseModel):
    """Input schema for schedule-filtered course search."""

    query: str = Field(min_length=1)
    day: str | None = Field(
        default=None,
        description="Day filter using codes: M, T, W, Th, F, or combos like MWF, TTh.",
    )
    after_time: str | None = Field(
        default=None,
        description='Minimum start time, e.g. "3 PM" or "15:00".',
    )
    before_time: str | None = Field(
        default=None,
        description='Maximum start time, e.g. "5 PM" or "17:00".',
    )
    source: str | None = Field(
        default=None,
        description='Optional source filter: "cab" or "bulletin".',
    )
    k: int | None = Field(default=None, ge=1, le=20)


class SimilarCourseInput(BaseModel):
    """Input schema for finding courses similar to a given one."""

    course_code: str = Field(min_length=1)
    target_source: str | None = Field(
        default=None,
        description='Source to search in for similar courses: "cab" or "bulletin".',
    )
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

    def get_course_by_code(course_code: str, source: str | None = None) -> dict[str, Any]:
        """Look up a specific course by its exact course code."""
        allowed, call_number, call_limit = consume_tool_call("get_course_by_code")
        if not allowed:
            LOGGER.info(
                format_log("agent_tool_limit_reached", COLOR_YELLOW,
                           tool="get_course_by_code", attempted_call=call_number, limit=call_limit)
            )
            return _tool_limit_payload("all", call_limit)
        LOGGER.info(
            format_log("agent_tool_start", COLOR_BLUE,
                       tool="get_course_by_code", call=call_number, limit=call_limit,
                       course_code=course_code, source=source)
        )
        payload = adapter.lookup_course_by_code(course_code=course_code, source=source)
        _record_tool_references(payload)
        LOGGER.info(
            format_log("agent_tool_done", COLOR_BLUE,
                       tool="get_course_by_code", call=call_number,
                       retrieval_count=payload.get("retrieval_count", 0))
        )
        return payload

    def search_courses_by_schedule(
        query: str,
        day: str | None = None,
        after_time: str | None = None,
        before_time: str | None = None,
        source: str | None = None,
        k: int | None = None,
    ) -> dict[str, Any]:
        """Search courses by topic and filter by meeting day/time."""
        allowed, call_number, call_limit = consume_tool_call("search_courses_by_schedule")
        if not allowed:
            LOGGER.info(
                format_log("agent_tool_limit_reached", COLOR_YELLOW,
                           tool="search_courses_by_schedule", attempted_call=call_number, limit=call_limit)
            )
            return _tool_limit_payload(source or "all", call_limit)
        effective_department = _resolve_effective_department(None)
        LOGGER.info(
            format_log("agent_tool_start", COLOR_BLUE,
                       tool="search_courses_by_schedule", call=call_number, limit=call_limit,
                       query=query, day=day, after_time=after_time, before_time=before_time,
                       source=source, k=k)
        )
        payload = adapter.search_by_schedule(
            query=query, day=day, after_time=after_time, before_time=before_time,
            source=source, department=effective_department, k=k,
        )
        _record_tool_references(payload)
        LOGGER.info(
            format_log("agent_tool_done", COLOR_BLUE,
                       tool="search_courses_by_schedule", call=call_number,
                       retrieval_count=payload.get("retrieval_count", 0))
        )
        return payload

    def find_similar_courses(
        course_code: str,
        target_source: str | None = None,
        k: int | None = None,
    ) -> dict[str, Any]:
        """Find courses semantically similar to a given course, optionally in a different source."""
        allowed, call_number, call_limit = consume_tool_call("find_similar_courses")
        if not allowed:
            LOGGER.info(
                format_log("agent_tool_limit_reached", COLOR_YELLOW,
                           tool="find_similar_courses", attempted_call=call_number, limit=call_limit)
            )
            return _tool_limit_payload(target_source or "all", call_limit)
        LOGGER.info(
            format_log("agent_tool_start", COLOR_BLUE,
                       tool="find_similar_courses", call=call_number, limit=call_limit,
                       course_code=course_code, target_source=target_source, k=k)
        )
        payload = adapter.find_similar_courses(
            course_code=course_code, target_source=target_source, k=k,
        )
        _record_tool_references(payload)
        LOGGER.info(
            format_log("agent_tool_done", COLOR_BLUE,
                       tool="find_similar_courses", call=call_number,
                       retrieval_count=payload.get("retrieval_count", 0))
        )
        return payload

    return [
        ToolSpec(
            name="search_cab_courses",
            description=(
                "Semantic search over CAB course records. Returns meeting times, "
                "sections, instructors, and operational details. Use for general "
                "topic searches when you need CAB data."
            ),
            handler=search_cab_courses,
        ),
        ToolSpec(
            name="search_bulletin_courses",
            description=(
                "Semantic search over bulletin course records. Returns catalog "
                "descriptions and general course summaries. Use for general topic "
                "searches when you need bulletin data."
            ),
            handler=search_bulletin_courses,
        ),
        ToolSpec(
            name="get_course_by_code",
            description=(
                "Look up a specific course by its exact course code (e.g. 'CSCI 0320'). "
                "Returns full details including description, meetings, and instructors. "
                "Use when the user asks about a specific known course."
            ),
            handler=get_course_by_code,
        ),
        ToolSpec(
            name="search_courses_by_schedule",
            description=(
                "Search for courses by topic AND filter by meeting schedule. "
                "Supports filtering by day (M/T/W/Th/F), start time (after_time, "
                "before_time). Use when the user asks about courses on specific "
                "days or at specific times."
            ),
            handler=search_courses_by_schedule,
        ),
        ToolSpec(
            name="find_similar_courses",
            description=(
                "Find courses that are semantically similar to a given course code. "
                "Optionally restrict results to a specific source (cab or bulletin). "
                "Use when the user asks to find courses similar to or related to "
                "a specific course, or to cross-reference between CAB and bulletin."
            ),
            handler=find_similar_courses,
        ),
    ]


_TOOL_SCHEMA_MAP: dict[str, type[BaseModel]] = {
    "search_cab_courses": CourseSearchToolInput,
    "search_bulletin_courses": CourseSearchToolInput,
    "get_course_by_code": CourseCodeLookupInput,
    "search_courses_by_schedule": ScheduleSearchInput,
    "find_similar_courses": SimilarCourseInput,
}


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
        schema = _TOOL_SCHEMA_MAP.get(spec.name, CourseSearchToolInput)
        tools.append(
            StructuredTool.from_function(
                func=spec.handler,
                name=spec.name,
                description=spec.description,
                args_schema=schema,
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
