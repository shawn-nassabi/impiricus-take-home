from __future__ import annotations
"""High-level orchestration for streaming and evaluated chatbot responses."""

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from chatbot_agent.agent import AgentRunner
from chatbot_agent.logging_utils import COLOR_GREEN, COLOR_RED, format_log
from chatbot_agent.models import EvaluateResponse, RetrievedCourseSummary
from chatbot_agent.retrieval_adapter import ChatbotRetrievalAdapter


@dataclass(frozen=True)
class PreparedChatQuery:
    """Deterministic retrieval payload emitted before generation starts."""

    started_at: float
    query: str
    department: str | None
    retrieved_courses: list[RetrievedCourseSummary]

    @property
    def retrieval_count(self) -> int:
        """Expose the number of retrieved courses."""
        return len(self.retrieved_courses)


class ChatbotService:
    """Coordinate retrieval, agent generation, SSE framing, and logging."""

    def __init__(
        self,
        retrieval_adapter: ChatbotRetrievalAdapter,
        agent_runner: AgentRunner,
        logger: logging.Logger | None = None,
    ) -> None:
        self.retrieval_adapter = retrieval_adapter
        self.agent_runner = agent_runner
        self.logger = logger or logging.getLogger(__name__)

    def prepare_query(
        self,
        query: str,
        department: str | None = None,
        started_at: float | None = None,
    ) -> PreparedChatQuery:
        """Run the deterministic pre-agent retrieval pass."""
        effective_started_at = started_at if started_at is not None else time.perf_counter()
        payload = self.retrieval_adapter.retrieve_all_courses(query=query, department=department)
        raw_courses = payload.get("retrieved_courses") or []
        courses = [RetrievedCourseSummary(**item) for item in raw_courses if isinstance(item, dict)]
        return PreparedChatQuery(
            started_at=effective_started_at,
            query=query,
            department=(department or "").strip().upper() or None,
            retrieved_courses=courses,
        )

    async def stream_prepared_query(self, prepared: PreparedChatQuery) -> AsyncIterator[str]:
        """Emit retrieval metadata, then token deltas, then completion metadata."""
        response_parts: list[str] = []
        first_token_ms: int | None = None

        yield _format_sse(
            "retrieval",
            {
                "query": prepared.query,
                "retrieved_courses": [course.model_dump() for course in prepared.retrieved_courses],
                "retrieval_count": prepared.retrieval_count,
            },
        )

        try:
            async for chunk in self.agent_runner.stream_answer(
                query=prepared.query,
                department=prepared.department,
            ):
                if first_token_ms is None:
                    first_token_ms = _elapsed_ms(prepared.started_at)
                    self.logger.info(
                        format_log(
                            "chatbot_first_token",
                            COLOR_GREEN,
                            endpoint="/query",
                            query=prepared.query,
                            department=prepared.department,
                            time_to_first_token_ms=first_token_ms,
                        )
                    )
                response_parts.append(chunk)
                yield _format_sse("token", {"delta": chunk})
        except Exception as exc:
            latency_ms = _elapsed_ms(prepared.started_at)
            self._log_request(
                endpoint="/query",
                query=prepared.query,
                department=prepared.department,
                retrieval_count=prepared.retrieval_count,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
                first_token_ms=first_token_ms,
            )
            yield _format_sse("error", {"message": str(exc)})
            return

        merged_courses = self._merge_retrieved_courses(prepared.retrieved_courses)
        latency_ms = _elapsed_ms(prepared.started_at)
        response_text = "".join(response_parts)
        self._log_request(
            endpoint="/query",
            query=prepared.query,
            department=prepared.department,
            retrieval_count=len(merged_courses),
            latency_ms=latency_ms,
            success=True,
            first_token_ms=first_token_ms,
        )
        yield _format_sse(
            "done",
            {
                "response_text": response_text,
                "latency_ms": latency_ms,
                "retrieval_count": len(merged_courses),
                "retrieved_courses": [course.model_dump() for course in merged_courses],
            },
        )

    async def evaluate(
        self,
        query: str,
        department: str | None = None,
        started_at: float | None = None,
    ) -> EvaluateResponse:
        """Run retrieval plus answer generation and return timing metadata."""
        prepared = self.prepare_query(query=query, department=department, started_at=started_at)

        try:
            await self.agent_runner.generate_answer(query=prepared.query, department=prepared.department)
        except Exception as exc:
            merged_courses = self._merge_retrieved_courses(prepared.retrieved_courses)
            latency_ms = _elapsed_ms(prepared.started_at)
            self._log_request(
                endpoint="/evaluate",
                query=prepared.query,
                department=prepared.department,
                retrieval_count=len(merged_courses),
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )
            raise

        merged_courses = self._merge_retrieved_courses(prepared.retrieved_courses)
        latency_ms = _elapsed_ms(prepared.started_at)
        self._log_request(
            endpoint="/evaluate",
            query=prepared.query,
            department=prepared.department,
            retrieval_count=len(merged_courses),
            latency_ms=latency_ms,
            success=True,
        )
        return EvaluateResponse(
            query=prepared.query,
            department=prepared.department,
            latency_ms=latency_ms,
            retrieval_count=len(merged_courses),
            retrieved_courses=merged_courses,
            model=self.agent_runner.model_name,
        )

    def _log_request(
        self,
        endpoint: str,
        query: str,
        department: str | None,
        retrieval_count: int,
        latency_ms: int,
        success: bool,
        error: str | None = None,
        first_token_ms: int | None = None,
    ) -> None:
        """Emit one structured log line per request."""
        self.logger.info(
            format_log(
                "chatbot_request",
                COLOR_GREEN if success else COLOR_RED,
                endpoint=endpoint,
                success=success,
                first_token_ms=first_token_ms,
                full_response_ms=latency_ms,
                retrieval_count=retrieval_count,
                department=department,
                query=query,
                error=error,
            )
        )

    def _merge_retrieved_courses(self, initial_courses: list[RetrievedCourseSummary]) -> list[RetrievedCourseSummary]:
        """Merge pre-retrieval references with any additional tool-returned references."""
        merged: list[RetrievedCourseSummary] = []
        seen: set[tuple[str, str]] = set()

        def add_course(course: RetrievedCourseSummary) -> None:
            key = (course.source, course.course_code)
            if key in seen:
                return
            seen.add(key)
            merged.append(course)

        for course in initial_courses:
            add_course(course)

        for item in self.agent_runner.get_last_run_references():
            if not isinstance(item, dict):
                continue
            try:
                course = RetrievedCourseSummary(**item)
            except Exception:
                continue
            add_course(course)

        return merged


def _elapsed_ms(started: float) -> int:
    """Convert a perf_counter start time to integer milliseconds."""
    return int((time.perf_counter() - started) * 1000)


def _format_sse(event: str, payload: dict[str, object]) -> str:
    """Format one server-sent event frame."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"
