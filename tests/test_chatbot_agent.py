from chatbot_agent.agent import _extract_stream_event_text


class _ToolMessage:
    type = "tool"

    def __init__(self, content: str) -> None:
        self.content = content


class _AiMessageChunk:
    type = "ai"

    def __init__(self, content: str) -> None:
        self.content = content


def test_stream_extractor_ignores_tool_messages() -> None:
    item = (_ToolMessage('{"retrieved_courses": []}'), {"langgraph_node": "tools"})

    assert _extract_stream_event_text(item) == ""


def test_stream_extractor_keeps_model_tokens() -> None:
    item = (_AiMessageChunk("There"), {"langgraph_node": "model"})

    assert _extract_stream_event_text(item) == "There"
