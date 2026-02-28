from chatbot_agent.tools import (
    activate_tool_call_budget,
    build_tool_specs,
    get_recorded_tool_references,
    reset_tool_call_budget,
)


class _FakeRetrievalAdapter:
    def __init__(self) -> None:
        self.cab_departments: list[str | None] = []
        self.bulletin_departments: list[str | None] = []

    def retrieve_cab_courses(self, query: str, department: str | None = None, k: int | None = None):
        self.cab_departments.append(department)
        return {
            "query": query,
            "retrieved_courses": [{"course_code": "CSCI 0111"}],
            "retrieval_count": 1,
            "source_scope": "CAB",
            "requested_k": k,
        }

    def retrieve_bulletin_courses(self, query: str, department: str | None = None, k: int | None = None):
        self.bulletin_departments.append(department)
        return {
            "query": query,
            "retrieved_courses": [{"course_code": "HIST 0101"}],
            "retrieval_count": 1,
            "source_scope": "bulletin",
            "requested_k": k,
        }


def test_tool_specs_pass_k_override_to_adapter() -> None:
    specs = build_tool_specs(_FakeRetrievalAdapter())
    cab_tool = next(spec for spec in specs if spec.name == "search_cab_courses")

    tokens = activate_tool_call_budget(4)
    try:
        payload = cab_tool.handler(query="foundations", department="CSCI", k=12)
        refs = get_recorded_tool_references()
    finally:
        reset_tool_call_budget(tokens)

    assert payload["requested_k"] == 12
    assert payload["retrieval_count"] == 1
    assert refs[0]["course_code"] == "CSCI 0111"


def test_tool_specs_enforce_per_request_call_limit() -> None:
    specs = build_tool_specs(_FakeRetrievalAdapter())
    bulletin_tool = next(spec for spec in specs if spec.name == "search_bulletin_courses")

    tokens = activate_tool_call_budget(1)
    try:
        first = bulletin_tool.handler(query="history", department=None, k=None)
        second = bulletin_tool.handler(query="history", department=None, k=None)
    finally:
        reset_tool_call_budget(tokens)

    assert first["retrieval_count"] == 1
    assert second["retrieval_count"] == 0
    assert second["limit_reached"] is True


def test_tool_specs_ignore_inferred_department_without_explicit_request_filter() -> None:
    adapter = _FakeRetrievalAdapter()
    specs = build_tool_specs(adapter)
    cab_tool = next(spec for spec in specs if spec.name == "search_cab_courses")

    tokens = activate_tool_call_budget(4, request_department=None)
    try:
        payload = cab_tool.handler(query="anthropology", department="ANTH", k=8)
    finally:
        reset_tool_call_budget(tokens)

    assert payload["requested_k"] == 8
    assert payload["query"] == "anthropology"
    assert adapter.cab_departments == [None]


def test_tool_specs_preserve_explicit_request_department_filter() -> None:
    class _RecordingRetrievalAdapter(_FakeRetrievalAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.departments: list[str | None] = []

        def retrieve_cab_courses(self, query: str, department: str | None = None, k: int | None = None):
            self.departments.append(department)
            return super().retrieve_cab_courses(query=query, department=department, k=k)

    adapter = _RecordingRetrievalAdapter()
    specs = build_tool_specs(adapter)
    cab_tool = next(spec for spec in specs if spec.name == "search_cab_courses")

    tokens = activate_tool_call_budget(4, request_department="CSCI")
    try:
        cab_tool.handler(query="foundations", department="HIST", k=5)
    finally:
        reset_tool_call_budget(tokens)

    assert adapter.departments == ["CSCI"]
