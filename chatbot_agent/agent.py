from __future__ import annotations
"""LangChain-backed agent runner used by the chatbot service."""

import os
from collections.abc import AsyncIterator
from typing import Any, Protocol

from chatbot_agent.retrieval_adapter import ChatbotRetrievalAdapter
from chatbot_agent.tools import build_langchain_tools

DEFAULT_CHAT_MODEL = "gpt-4.1-mini"
DEFAULT_SYSTEM_PROMPT = (
    "You are a Brown University course assistant. Use the available retrieval "
    "tools before answering factual questions about courses. Prefer the CAB tool "
    "for meeting times, instructors, sections, and scheduling details. Prefer "
    "the bulletin tool for catalog descriptions and general summaries. If the "
    "tools do not provide enough evidence, say that directly and do not invent "
    "course details. If CAB and bulletin conflict, prefer CAB for operational "
    "details and mention the discrepancy."
)


class AgentRunner(Protocol):
    """Interface consumed by the chatbot service."""

    model_name: str

    async def stream_answer(self, query: str, department: str | None = None) -> AsyncIterator[str]:
        ...

    async def generate_answer(self, query: str, department: str | None = None) -> str:
        ...


class LangChainAgentRunner:
    """Wrap a lazily-created LangChain agent with streaming helpers."""

    def __init__(self, retrieval_adapter: ChatbotRetrievalAdapter, model_name: str = DEFAULT_CHAT_MODEL) -> None:
        self.retrieval_adapter = retrieval_adapter
        self.model_name = model_name
        self._agent: Any | None = None

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

        if hasattr(agent, "astream"):
            try:
                async for item in agent.astream(payload, stream_mode="messages"):
                    token = _extract_stream_text(item)
                    if not token:
                        continue
                    yielded = True
                    yield token
            except TypeError:
                if yielded:
                    raise
                yielded = False

        if not yielded:
            answer = await self.generate_answer(query=query, department=department)
            if answer:
                yield answer

    async def generate_answer(self, query: str, department: str | None = None) -> str:
        """Return a full answer in one string."""
        agent = self._get_agent()
        payload = self._agent_input(query=query, department=department)

        if hasattr(agent, "ainvoke"):
            response = await agent.ainvoke(payload)
        elif hasattr(agent, "invoke"):
            response = agent.invoke(payload)
        else:
            raise RuntimeError("Configured agent does not support invocation.")

        return _extract_final_text(response)

    def _agent_input(self, query: str, department: str | None = None) -> dict[str, Any]:
        """Shape the user input consistently for the agent."""
        lines = [f"User question: {query.strip()}"]
        if department:
            lines.append(f"Department filter: {department.strip().upper()}")
        lines.append("Use retrieval tools before answering factual course questions.")
        return {"messages": [{"role": "user", "content": "\n".join(lines)}]}


def _extract_stream_text(item: Any) -> str:
    """Best-effort extraction of token text from LangChain stream events."""
    if isinstance(item, tuple) and item:
        return _extract_stream_text(item[0])

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
