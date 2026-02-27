from __future__ import annotations
"""LangChain tool definitions backed by the local hybrid retriever."""

from dataclasses import dataclass
from typing import Any, Callable

from rag.models import BaseModel, Field

from chatbot_agent.retrieval_adapter import ChatbotRetrievalAdapter


class CourseSearchToolInput(BaseModel):
    """Input schema shared by the retrieval tools."""

    query: str = Field(min_length=1)
    department: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    """Description plus callable for building LangChain tools lazily."""

    name: str
    description: str
    handler: Callable[..., dict[str, Any]]


def build_tool_specs(adapter: ChatbotRetrievalAdapter) -> list[ToolSpec]:
    """Build the retrieval tools the agent can invoke."""

    def search_cab_courses(query: str, department: str | None = None) -> dict[str, Any]:
        """Use CAB data for detailed scheduling and instructor questions."""
        return adapter.retrieve_cab_courses(query=query, department=department)

    def search_bulletin_courses(query: str, department: str | None = None) -> dict[str, Any]:
        """Use bulletin data for general catalog title and description questions."""
        return adapter.retrieve_bulletin_courses(query=query, department=department)

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
