from __future__ import annotations

"""Streamlit app for the course search chatbot."""

import json
import os
from html import escape
from typing import Any

import streamlit as st

try:
    from ui.sse_client import DoneEvent, ErrorEvent, RetrievalEvent, SSEClientError, TokenEvent, stream_query
except ModuleNotFoundError:
    from sse_client import DoneEvent, ErrorEvent, RetrievalEvent, SSEClientError, TokenEvent, stream_query

DEFAULT_API_BASE_URL = os.getenv("CHATBOT_API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Course Search Chatbot", page_icon=":books:", layout="centered")


def _init_state() -> None:
    """Populate required Streamlit session state defaults."""
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("api_base_url", DEFAULT_API_BASE_URL)
    st.session_state.setdefault("department_filter", "")


def _inject_styles() -> None:
    """Apply a restrained, modern visual treatment."""
    st.markdown(
        """
        <style>
        :root {
            --canvas: #f6f4ee;
            --text-main: #3c6e8a;
            --text-muted: #6c8ea2;
            --text-soft: #8da8b7;
            --accent: #2a8c8c;
            --accent-strong: #d6835b;
            --accent-soft: rgba(42, 140, 140, 0.14);
            --line-soft: rgba(58, 108, 136, 0.12);
            --shadow-soft: 0 16px 40px rgba(62, 92, 112, 0.08);
            --header-bg: linear-gradient(135deg, rgba(255, 250, 244, 0.95) 0%, rgba(239, 249, 248, 0.92) 55%, rgba(247, 241, 232, 0.95) 100%);
            --user-bg: linear-gradient(135deg, rgba(223, 244, 242, 0.96) 0%, rgba(236, 250, 247, 0.96) 100%);
            --assistant-bg: linear-gradient(180deg, rgba(255, 252, 248, 0.98) 0%, rgba(252, 247, 240, 0.98) 100%);
            --control-bg: rgba(255, 255, 255, 0.95);
            --reference-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.82) 0%, rgba(245, 252, 251, 0.74) 100%);
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(42, 140, 140, 0.18), transparent 30%),
                radial-gradient(circle at top right, rgba(214, 131, 91, 0.16), transparent 24%),
                radial-gradient(circle at 50% 100%, rgba(126, 183, 200, 0.12), transparent 30%),
                linear-gradient(180deg, #fcfbf7 0%, var(--canvas) 100%);
            color: var(--text-main);
        }
        .block-container {
            max-width: 860px;
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        .stApp,
        .stApp p,
        .stApp li,
        .stApp label,
        .stApp .stMarkdown,
        .stApp .stMarkdown p,
        .stApp .stMarkdown span,
        .stApp [data-testid="stMarkdownContainer"],
        .stApp [data-testid="stMarkdownContainer"] * {
            color: var(--text-main);
        }
        [data-testid="stChatMessage"] {
            background: var(--assistant-bg);
            border: 1px solid var(--line-soft);
            border-radius: 24px;
            padding: 0.55rem 0.65rem;
            box-shadow: var(--shadow-soft);
            margin-bottom: 0.75rem;
        }
        [data-testid="stChatMessageContent"] {
            width: 100%;
        }
        [data-testid="stChatMessageContent"] * {
            color: var(--text-main) !important;
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
            background: var(--user-bg);
            border-color: rgba(42, 140, 140, 0.18);
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
            background: var(--assistant-bg);
        }
        [data-testid="stSidebar"] {
            background: rgba(253, 250, 244, 0.92);
            border-right: 1px solid var(--line-soft);
        }
        [data-testid="stSidebar"] * {
            color: var(--text-main) !important;
        }
        .ui-shell {
            background: var(--header-bg);
            border: 1px solid rgba(95, 129, 148, 0.14);
            border-radius: 28px;
            padding: 1.2rem 1.2rem 0.95rem;
            box-shadow: 0 18px 42px rgba(76, 104, 122, 0.09);
            margin-bottom: 1.2rem;
        }
        .ui-kicker {
            display: inline-block;
            margin-bottom: 0.6rem;
            padding: 0.24rem 0.62rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.72);
            color: var(--accent);
            font-size: 0.74rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            border: 1px solid rgba(42, 140, 140, 0.12);
        }
        .ui-shell h1 {
            margin: 0;
            font-size: 2.25rem;
            font-weight: 650;
            letter-spacing: -0.02em;
            line-height: 1.05;
            color: var(--text-main);
        }
        .ui-shell p {
            margin: 0.42rem 0 0;
            color: var(--text-muted);
            font-size: 1rem;
            line-height: 1.55;
        }
        .api-note {
            color: var(--text-soft);
            font-size: 0.9rem;
            margin-top: 0.75rem;
        }
        .filter-shell {
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.82) 0%, rgba(244, 251, 250, 0.76) 100%);
            border: 1px solid rgba(95, 129, 148, 0.12);
            border-radius: 20px;
            padding: 0.95rem 1rem 0.4rem;
            margin-bottom: 0.85rem;
            box-shadow: 0 10px 26px rgba(76, 104, 122, 0.05);
        }
        .filter-shell strong {
            display: block;
            margin-bottom: 0.2rem;
            color: var(--text-main);
            font-size: 0.96rem;
        }
        .filter-shell span {
            color: var(--text-muted) !important;
            font-size: 0.9rem;
            line-height: 1.4;
        }
        .stTextInput > div > div > input,
        [data-testid="stChatInput"] textarea {
            background: var(--control-bg) !important;
            color: var(--text-main) !important;
            border: 1px solid rgba(118, 176, 189, 0.26) !important;
            border-radius: 18px !important;
            box-shadow: none !important;
            outline: none !important;
        }
        .stTextInput > div > div > input:focus,
        .stTextInput > div > div > input:focus-visible,
        [data-testid="stChatInput"] textarea:focus,
        [data-testid="stChatInput"] textarea:focus-visible {
            border-color: rgba(42, 140, 140, 0.44) !important;
            box-shadow: 0 0 0 3px rgba(42, 140, 140, 0.12) !important;
            outline: none !important;
        }
        .stTextInput div[data-baseweb="input"],
        [data-testid="stChatInput"] div[data-baseweb="textarea"] {
            background: var(--control-bg) !important;
            border: 1px solid rgba(118, 176, 189, 0.24) !important;
            border-radius: 18px !important;
            box-shadow: none !important;
        }
        .stTextInput div[data-baseweb="input"]:focus-within,
        [data-testid="stChatInput"] div[data-baseweb="textarea"]:focus-within {
            border-color: rgba(42, 140, 140, 0.40) !important;
            box-shadow: 0 0 0 3px rgba(42, 140, 140, 0.10) !important;
        }
        .stTextInput div[data-baseweb="input"] > div,
        [data-testid="stChatInput"] div[data-baseweb="textarea"] > div {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }
        .stTextInput > div > div > input::placeholder,
        [data-testid="stChatInput"] textarea::placeholder {
            color: var(--text-soft) !important;
            -webkit-text-fill-color: var(--text-soft) !important;
        }
        .stTextInput label,
        [data-testid="stChatInput"] label {
            color: var(--text-main) !important;
            font-weight: 600;
        }
        [data-testid="stChatInput"] {
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.92) 0%, rgba(248, 252, 251, 0.88) 100%);
            border: 1px solid rgba(118, 176, 189, 0.18);
            border-radius: 22px;
            padding: 0.25rem;
            box-shadow: 0 12px 28px rgba(76, 104, 122, 0.06);
        }
        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] > div > div,
        [data-testid="stChatInput"] form {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            outline: none !important;
        }
        [data-testid="stChatInput"]:focus-within {
            border-color: rgba(42, 140, 140, 0.30);
            box-shadow:
                0 12px 28px rgba(76, 104, 122, 0.06),
                0 0 0 4px rgba(42, 140, 140, 0.08);
        }
        [data-testid="stChatInput"] form:focus-within,
        [data-testid="stChatInput"] > div:focus-within,
        [data-testid="stChatInput"] > div > div:focus-within {
            border: 0 !important;
            box-shadow: none !important;
            outline: none !important;
        }
        [data-testid="stExpander"] {
            background: rgba(255, 255, 255, 0.64);
            border: 1px solid rgba(95, 129, 148, 0.10);
            border-radius: 18px;
            overflow: hidden;
        }
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary * {
            color: var(--text-main) !important;
        }
        [data-testid="stExpanderDetails"] * {
            color: var(--text-main) !important;
        }
        .stButton > button {
            border-radius: 999px;
            border: 1px solid rgba(95, 129, 148, 0.12);
            background: rgba(255, 255, 255, 0.95);
            color: var(--text-main);
            font-weight: 600;
        }
        .stButton > button:hover {
            border-color: rgba(42, 140, 140, 0.28);
            color: var(--accent);
        }
        .stCaption,
        [data-testid="stCaptionContainer"] * {
            color: var(--text-muted) !important;
        }
        .reference-card {
            background: var(--reference-bg);
            border: 1px solid rgba(95, 129, 148, 0.12);
            border-radius: 16px;
            padding: 0.85rem 0.9rem;
            margin-bottom: 0.7rem;
        }
        .reference-block {
            margin-bottom: 0.95rem;
            padding: 0.85rem 0.9rem;
            border-radius: 16px;
            background: var(--reference-bg);
            border: 1px solid rgba(95, 129, 148, 0.12);
        }
        .reference-topline {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.35rem;
        }
        .reference-rank {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 2rem;
            padding: 0.18rem 0.5rem;
            border-radius: 999px;
            background: rgba(42, 140, 140, 0.12);
            color: var(--accent);
            font-size: 0.78rem;
            font-weight: 700;
        }
        .reference-title {
            color: var(--text-main);
            font-size: 1rem;
            font-weight: 650;
            line-height: 1.35;
            margin-bottom: 0.25rem;
        }
        .reference-code {
            color: var(--accent-strong);
            font-size: 0.82rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        .reference-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.5rem;
            margin-top: 0.65rem;
        }
        .reference-meta {
            padding: 0.45rem 0.55rem;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.7);
            border: 1px solid rgba(95, 129, 148, 0.08);
        }
        .reference-meta-label {
            color: var(--text-soft);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin-bottom: 0.12rem;
        }
        .reference-meta-value {
            color: var(--text-main);
            font-size: 0.9rem;
            line-height: 1.3;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _normalize_department(raw_value: str) -> str | None:
    """Normalize the optional department filter for the API."""
    clean_value = raw_value.strip().upper()
    return clean_value or None


def _format_metadata_label(key: str) -> str:
    """Convert raw payload keys into readable labels."""
    return key.replace("_", " ").strip().title() or "Metadata"


def _format_metadata_value(value: object) -> str:
    """Format arbitrary metadata values for display."""
    if value is None:
        return "None"

    if isinstance(value, float):
        return f"{value:.4f}"

    if isinstance(value, bool):
        return "Yes" if value else "No"

    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)

    return str(value)


def _ordered_metadata_keys(course: dict[str, object]) -> list[str]:
    """Return course metadata keys in a stable, user-friendly order."""
    preferred_order = [
        "department",
        "source",
        "similarity",
        "prerequisites",
        "score",
        "raw_score",
        "course_level",
        "term",
        "instructor_name",
        "instructors",
        "credits",
        "meets",
        "location",
        "section",
        "crn",
        "description",
        "why_relevant",
    ]
    hidden_keys = {"course_code", "title"}

    present_keys = [key for key in course if key not in hidden_keys]
    ordered_keys = [key for key in preferred_order if key in present_keys]
    remaining_keys = sorted(key for key in present_keys if key not in ordered_keys)
    return ordered_keys + remaining_keys


def _metadata_entries(course: dict[str, object]) -> list[tuple[str, object]]:
    """Flatten top-level and nested metadata into displayable key/value pairs."""
    entries: dict[str, object] = {}

    for key in _ordered_metadata_keys(course):
        value = course.get(key)
        if key == "metadata" and isinstance(value, dict):
            for nested_key, nested_value in value.items():
                if nested_key in {"course_code", "title"}:
                    continue
                if nested_key in course:
                    continue
                entries[nested_key] = nested_value
            continue

        entries[key] = value

    has_prerequisites = entries.pop("has_prerequisites", None)
    prerequisite_text = entries.get("prerequisites")

    if isinstance(prerequisite_text, str):
        prerequisite_text = prerequisite_text.strip()
        if prerequisite_text:
            entries["prerequisites"] = prerequisite_text
        else:
            entries.pop("prerequisites", None)
            prerequisite_text = None

    if prerequisite_text in (None, "") and has_prerequisites is not None:
        if bool(has_prerequisites):
            entries["prerequisites"] = "Prerequisites listed, but the backend did not include the text."
        else:
            entries["prerequisites"] = "No prerequisites listed."

    return list(entries.items())


def _render_header() -> None:
    """Render the top-of-page shell."""
    api_base_url = st.session_state.api_base_url.rstrip("/")
    st.markdown(
        f"""
        <div class="ui-shell">
            <div class="ui-kicker">Live SSE Chat</div>
            <h1>Course Search Chatbot</h1>
            <p>Ask about courses, requirements, and departments. Responses stream in real time from the FastAPI backend.</p>
            <div class="api-note">API base URL: {api_base_url}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar() -> None:
    """Render API and session controls."""
    with st.sidebar:
        st.subheader("Settings")
        st.text_input(
            "API base URL",
            key="api_base_url",
            help="Defaults to CHATBOT_API_BASE_URL or http://localhost:8000.",
        )
        if st.button("Clear chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


def _render_user_message(message: dict[str, Any]) -> None:
    """Render a user chat bubble."""
    with st.chat_message("user"):
        st.markdown(str(message.get("content", "")))
        department = message.get("department")
        if department:
            st.caption(f"Department filter: {department}")


def _render_retrieval_panel(retrieved_courses: list[dict[str, object]], retrieval_count: int) -> None:
    """Render retrieval metadata inside an expander."""
    label = f"Retrieved courses ({retrieval_count})"
    with st.expander(label, expanded=False):
        if not retrieved_courses:
            st.caption("No matching courses were retrieved for this turn.")
            return

        st.caption(f"Showing {len(retrieved_courses)} reference(s) returned by the backend.")

        for index, course in enumerate(retrieved_courses, start=1):
            course_code = str(course.get("course_code") or "Unknown code")
            title = str(course.get("title") or "Untitled course")
            st.markdown(
                f"""
                <div class="reference-block">
                    <div class="reference-topline">
                        <div class="reference-code">{escape(course_code)}</div>
                        <div class="reference-rank">#{index}</div>
                    </div>
                    <div class="reference-title">{escape(title)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            entries = _metadata_entries(course)
            for start in range(0, len(entries), 2):
                row = entries[start : start + 2]
                columns = st.columns(2)
                for column, (key, raw_value) in zip(columns, row):
                    formatted_value = _format_metadata_value(raw_value)

                    if key == "similarity":
                        try:
                            similarity_value = float(raw_value)
                        except (TypeError, ValueError):
                            similarity_value = None
                        if similarity_value is not None:
                            formatted_value = f"{similarity_value * 100:.1f}% ({similarity_value:.4f})"

                    with column:
                        st.caption(_format_metadata_label(key))
                        if isinstance(raw_value, (list, dict)):
                            st.code(
                                json.dumps(raw_value, ensure_ascii=True, sort_keys=True, indent=2),
                                language="json",
                            )
                        else:
                            st.markdown(formatted_value)

            if index < len(retrieved_courses):
                st.markdown("")


def _render_assistant_message(message: dict[str, Any]) -> None:
    """Render an assistant chat bubble and any related metadata."""
    with st.chat_message("assistant"):
        content = str(message.get("content", ""))
        st.markdown(content or "_No response received._")

        retrieval_count = int(message.get("retrieval_count") or 0)
        latency_ms = message.get("latency_ms")
        if latency_ms is not None:
            st.caption(f"Retrieved {retrieval_count} course(s) in {latency_ms} ms.")
        elif message.get("retrieved_courses") is not None:
            st.caption(f"Retrieved {retrieval_count} course(s).")

        error = message.get("error")
        if error:
            st.error(str(error))

        retrieved_courses = message.get("retrieved_courses")
        if isinstance(retrieved_courses, list):
            _render_retrieval_panel(retrieved_courses, retrieval_count)


def _render_history() -> None:
    """Render all persisted transcript messages."""
    for message in st.session_state.messages:
        if message.get("role") == "user":
            _render_user_message(message)
        else:
            _render_assistant_message(message)


def _stream_assistant_turn(
    api_base_url: str,
    query: str,
    department: str | None,
    assistant_message: dict[str, Any],
) -> None:
    """Stream one assistant turn and update the live placeholders."""
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        status_placeholder = st.empty()
        error_placeholder = st.empty()
        details_placeholder = st.empty()

        response_placeholder.markdown("_Thinking..._")

        try:
            for event in stream_query(api_base_url=api_base_url, query=query, department=department):
                if isinstance(event, RetrievalEvent):
                    assistant_message["retrieved_courses"] = event.retrieved_courses
                    assistant_message["retrieval_count"] = event.retrieval_count
                    status_placeholder.caption(
                        f"Retrieved {event.retrieval_count} course(s). Generating answer..."
                    )
                    with details_placeholder.container():
                        _render_retrieval_panel(event.retrieved_courses, event.retrieval_count)
                    continue

                if isinstance(event, TokenEvent):
                    assistant_message["content"] += event.delta
                    response_placeholder.markdown(assistant_message["content"])
                    continue

                if isinstance(event, DoneEvent):
                    assistant_message["content"] = event.response_text or assistant_message["content"]
                    assistant_message["latency_ms"] = event.latency_ms
                    assistant_message["retrieval_count"] = event.retrieval_count
                    if event.retrieved_courses:
                        assistant_message["retrieved_courses"] = event.retrieved_courses
                    status_placeholder.caption(
                        f"Retrieved {event.retrieval_count} course(s) in {event.latency_ms} ms."
                    )
                    response_placeholder.markdown(assistant_message["content"] or "_No response received._")
                    continue

                if isinstance(event, ErrorEvent):
                    assistant_message["error"] = event.message
                    break
        except SSEClientError as exc:
            assistant_message["error"] = str(exc)

        if assistant_message["content"]:
            response_placeholder.markdown(assistant_message["content"])
        else:
            response_placeholder.markdown("_No response received._")

        if assistant_message["latency_ms"] is None and assistant_message["retrieved_courses"] is not None:
            count = int(assistant_message["retrieval_count"] or 0)
            status_placeholder.caption(f"Retrieved {count} course(s).")

        if assistant_message["error"]:
            error_placeholder.error(str(assistant_message["error"]))

        if isinstance(assistant_message["retrieved_courses"], list):
            with details_placeholder.container():
                _render_retrieval_panel(
                    assistant_message["retrieved_courses"],
                    int(assistant_message["retrieval_count"] or 0),
                )


def main() -> None:
    """Render the application."""
    _init_state()
    _inject_styles()
    _render_sidebar()
    _render_header()

    transcript = st.container()
    with transcript:
        _render_history()

    st.caption("Type an optional department code in the smaller field on the right to narrow the search.")

    with st.form("query_form", clear_on_submit=True):
        input_columns = st.columns([4.8, 1.8, 0.9])
        with input_columns[0]:
            prompt = st.text_input(
                "Ask about courses, departments, or requirements",
                placeholder="Ask about courses, departments, or requirements",
                label_visibility="collapsed",
            )
        with input_columns[1]:
            department_input = st.text_input(
                "Department filter",
                value=st.session_state.department_filter,
                placeholder="Type here, e.g. CSCI",
                help="Optional. Type a department code like CSCI to narrow results.",
            )
        with input_columns[2]:
            submitted = st.form_submit_button("Send", use_container_width=True)

    if not submitted:
        return

    st.session_state.department_filter = department_input.strip()

    query = prompt.strip()
    if not query:
        return

    department = _normalize_department(st.session_state.department_filter)
    api_base_url = st.session_state.api_base_url.strip() or DEFAULT_API_BASE_URL

    user_message = {
        "role": "user",
        "content": query,
        "department": department,
    }
    st.session_state.messages.append(user_message)

    assistant_message = {
        "role": "assistant",
        "content": "",
        "department": department,
        "retrieved_courses": None,
        "retrieval_count": 0,
        "latency_ms": None,
        "error": None,
    }
    with transcript:
        _render_user_message(user_message)
        _stream_assistant_turn(
            api_base_url=api_base_url,
            query=query,
            department=department,
            assistant_message=assistant_message,
        )
    st.session_state.messages.append(assistant_message)


main()
