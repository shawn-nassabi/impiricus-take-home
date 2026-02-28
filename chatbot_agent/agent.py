from __future__ import annotations
"""LangChain-backed agent runner used by the chatbot service."""

import logging
import os
from collections.abc import AsyncIterator
from typing import Any, Protocol

from chatbot_agent.retrieval_adapter import ChatbotRetrievalAdapter
from chatbot_agent.tools import (
    activate_tool_call_budget,
    build_langchain_tools,
    get_recorded_tool_references,
    reset_tool_call_budget,
)

DEFAULT_CHAT_MODEL = "gpt-4.1-mini"
MAX_AGENT_TOOL_CALLS = 4
DEFAULT_SYSTEM_PROMPT = (
    "You are a Brown University course assistant. Use the available retrieval "
    "tools before answering factual questions about courses. Your answer must "
    "stay grounded in the retrieved references returned by the tools. Do not "
    "invent facts that are not supported by retrieved references. Prefer the "
    "CAB tool for meeting times, instructors, sections, and scheduling details. "
    "Prefer the bulletin tool for catalog descriptions and general summaries. "
    "If the initial references are not sufficient, you may call a retrieval tool "
    "again with a refined query or a larger k to gather more references. You may "
    "make up to 4 total tool calls. If the tools still do not provide enough "
    "evidence, say that clearly. Only apply a department filter when the user "
    "explicitly supplied one in the request. Do not infer a department filter "
    "from subject words in the query text. If CAB and bulletin conflict, prefer "
    "CAB for operational details and mention the discrepancy. When answering, "
    "reference the retrieved courses directly and keep the response tied to "
    "those results."
)
LOGGER = logging.getLogger(__name__)


class AgentRunner(Protocol):
    """Interface consumed by the chatbot service."""

    model_name: str

    async def stream_answer(self, query: str, department: str | None = None) -> AsyncIterator[str]:
        ...

    async def generate_answer(self, query: str, department: str | None = None) -> str:
        ...

    def get_last_run_references(self) -> list[dict[str, object]]:
        ...


class LangChainAgentRunner:
    """Wrap a lazily-created LangChain agent with streaming helpers."""

    def __init__(self, retrieval_adapter: ChatbotRetrievalAdapter, model_name: str = DEFAULT_CHAT_MODEL) -> None:
        self.retrieval_adapter = retrieval_adapter
        self.model_name = model_name
        self._agent: Any | None = None
        self._last_run_references: list[dict[str, object]] = []

    def _ensure_api_key(self) -> None:
        """Fail fast with a clear message when the OpenAI key is absent."""
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required to use the chatbot.")

    def _get_agent(self) -> Any:
        """Create the LangChain agent on first use."""
        if self._agent is not None:
            return self._agent

        self._ensure_api_key()

        try:
            from langchain.agents import create_agent
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "LangChain OpenAI support is unavailable. Install `langchain-openai` and retry."
            ) from exc

        model = ChatOpenAI(model=self.model_name, api_key=os.getenv("OPENAI_API_KEY"))
        tools = build_langchain_tools(self.retrieval_adapter)

        try:
            self._agent = create_agent(model=model, tools=tools, system_prompt=DEFAULT_SYSTEM_PROMPT)
        except TypeError:
            self._agent = create_agent(model=model, tools=tools)
        return self._agent

    async def stream_answer(self, query: str, department: str | None = None) -> AsyncIterator[str]:
        """Stream model deltas when available, falling back to a full completion."""
        agent = self._get_agent()
        payload = self._agent_input(query=query, department=department)
        yielded = False
        budget_tokens = activate_tool_call_budget(MAX_AGENT_TOOL_CALLS, request_department=department)
        self._last_run_references = []

        try:
            if hasattr(agent, "astream"):
                try:
                    async for item in agent.astream(payload, stream_mode="messages"):
                        token = _extract_stream_event_text(item)
                        if not token:
                            continue
                        yielded = True
                        yield token
                except TypeError:
                    if yielded:
                        raise
                    yielded = False

            if not yielded:
                answer = await self._invoke_agent(agent, payload, mode="stream_fallback")
                if answer:
                    yield answer
        finally:
            self._last_run_references = list(get_recorded_tool_references())
            reset_tool_call_budget(budget_tokens)

    async def generate_answer(self, query: str, department: str | None = None) -> str:
        """Return a full answer in one string."""
        agent = self._get_agent()
        payload = self._agent_input(query=query, department=department)
        budget_tokens = activate_tool_call_budget(MAX_AGENT_TOOL_CALLS, request_department=department)
        self._last_run_references = []
        try:
            answer = await self._invoke_agent(agent, payload, mode="invoke")
            return answer
        finally:
            self._last_run_references = list(get_recorded_tool_references())
            reset_tool_call_budget(budget_tokens)

    def _agent_input(self, query: str, department: str | None = None) -> dict[str, Any]:
        """Shape the user input consistently for the agent."""
        lines = [f"User question: {query.strip()}"]
        if department:
            lines.append(f"Department filter: {department.strip().upper()}")
        lines.append(
            "Use retrieval tools before answering factual course questions. Stay grounded in "
            "retrieved references. If the first search is too thin, you may retrieve again "
            "with a refined query or a larger k, but use at most 4 tool calls total. "
            "Do not apply a department filter unless the request explicitly included one."
        )
        return {"messages": [{"role": "user", "content": "\n".join(lines)}]}

    async def _invoke_agent(self, agent: Any, payload: dict[str, Any], mode: str) -> str:
        """Invoke the agent once and normalize the returned answer text."""
        del mode
        if hasattr(agent, "ainvoke"):
            response = await agent.ainvoke(payload)
        elif hasattr(agent, "invoke"):
            response = agent.invoke(payload)
        else:
            raise RuntimeError("Configured agent does not support invocation.")

        return _extract_final_text(response)

    def get_last_run_references(self) -> list[dict[str, object]]:
        """Expose references gathered through tool calls in the last agent run."""
        return [dict(item) for item in self._last_run_references if isinstance(item, dict)]


def _extract_stream_text(item: Any) -> str:
    """Best-effort extraction of token text from LangChain stream events."""
    if isinstance(item, dict):
        for key in ("delta", "text", "content"):
            if key in item:
                return _extract_stream_text(item[key])
        return ""

    if isinstance(item, str):
        return item

    content = getattr(item, "content", None)
    if content is not None:
        return _content_to_text(content)

    text = getattr(item, "text", None)
    if isinstance(text, str):
        return text

    return ""


def _extract_stream_event_text(item: Any) -> str:
    """Only surface assistant model text from streaming events.

    LangChain agent message streams can include tool-call messages and tool
    outputs. Those should not be forwarded to the frontend as visible answer
    text.
    """
    if isinstance(item, tuple):
        if not item:
            return ""
        message = item[0]
        metadata = item[1] if len(item) > 1 and isinstance(item[1], dict) else {}

        langgraph_node = str(metadata.get("langgraph_node") or "")
        if langgraph_node and langgraph_node != "model":
            return ""

        if _is_tool_message(message):
            return ""

        return _extract_stream_text(message)

    if _is_tool_message(item):
        return ""

    return _extract_stream_text(item)


def _extract_final_text(response: Any) -> str:
    """Normalize the final agent response into a single answer string."""
    if isinstance(response, dict):
        messages = response.get("messages")
        if isinstance(messages, list) and messages:
            return _extract_final_text(messages[-1])
        for key in ("output", "response", "content", "text"):
            if key in response:
                return _extract_final_text(response[key])
        return ""

    if isinstance(response, list):
        if not response:
            return ""
        return _extract_final_text(response[-1])

    if isinstance(response, tuple):
        if not response:
            return ""
        return _extract_final_text(response[0])

    if isinstance(response, str):
        return response

    content = getattr(response, "content", None)
    if content is not None:
        return _content_to_text(content)

    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text

    return str(response) if response is not None else ""


def _content_to_text(content: Any) -> str:
    """Flatten LangChain/OpenAI content blocks into plain text."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                continue
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)

    return ""


def _is_tool_message(item: Any) -> bool:
    """Detect tool-related messages that should not be shown to end users."""
    message_type = getattr(item, "type", None)
    if isinstance(message_type, str) and message_type in {"tool", "tool_call", "tool_result"}:
        return True

    if item.__class__.__name__ == "ToolMessage":
        return True

    additional_kwargs = getattr(item, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict) and additional_kwargs.get("tool_calls"):
        return True

    return False
