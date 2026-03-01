"""Tests for the new adapter methods: lookup_course_by_code, search_by_schedule, find_similar_courses."""

from typing import Any

from chatbot_agent.retrieval_adapter import ChatbotRetrievalAdapter, summarize_canonical_doc
from rag.models import (
    CanonicalCourseDocument,
    RetrievalFilters,
    RetrievalHit,
    RetrievalRequest,
    RetrievalResponse,
)


def _make_doc(
    course_code: str = "CSCI 0320",
    source: str = "cab",
    source_label: str = "CAB",
    title: str = "Software Engineering",
    meetings: list[str] | None = None,
) -> CanonicalCourseDocument:
    return CanonicalCourseDocument(
        doc_id=f"{source}:{course_code}:abc123",
        source=source,
        source_label=source_label,
        course_code=course_code,
        title=title,
        description="A software engineering course.",
        prerequisites="CSCI 0200",
        department="CSCI",
        instructor_names=["Tim Nelson"],
        meetings=meetings or ["MWF 10am-10:50am"],
        course_url=None,
        text=f"Course code: {course_code}\nTitle: {title}\nDescription: A software engineering course.\nMeetings: MWF 10am-10:50am\nInstructors: Tim Nelson",
    )


class _FakeService:
    """Minimal service fake with lookup_by_code, search, and score_all_by_keyword."""

    def __init__(
        self,
        docs: list[CanonicalCourseDocument],
        *,
        search_returns: list[CanonicalCourseDocument] | None = None,
    ) -> None:
        self._docs = docs
        self._search_docs = search_returns if search_returns is not None else docs

    def search(self, request: RetrievalRequest) -> RetrievalResponse:
        hits: list[RetrievalHit] = []
        for doc in self._search_docs:
            if request.filters and request.filters.source:
                if doc.source != request.filters.source.strip().lower():
                    continue
            hits.append(
                RetrievalHit(
                    doc_id=doc.doc_id,
                    score=0.9,
                    source=doc.source,
                    course_code=doc.course_code,
                    title=doc.title,
                    metadata=doc.response_metadata(),
                    text=doc.text,
                )
            )
        return RetrievalResponse(query=request.query, hits=hits[: request.k])

    def lookup_by_code(self, course_code: str, source: str | None = None) -> list[CanonicalCourseDocument]:
        from rag.retrieval.query_service import normalize_course_code
        normalized = normalize_course_code(course_code)
        results = []
        for doc in self._docs:
            doc_code = normalize_course_code(doc.course_code)
            if doc_code != normalized:
                continue
            if source and doc.source != source.strip().lower():
                continue
            results.append(doc)
        return results

    def score_all_by_keyword(
        self,
        query: str,
        source: str | None = None,
        department: str | None = None,
    ) -> list[tuple[CanonicalCourseDocument, float]]:
        results = []
        for doc in self._docs:
            if source and doc.source != source.strip().lower():
                continue
            if department and (doc.department or "").upper() != department.strip().upper():
                continue
            score = 1.0 if query.lower() in doc.text.lower() else 0.1
            results.append((doc, score))
        results.sort(key=lambda p: p[1], reverse=True)
        return results


class TestLookupCourseByCode:
    def test_exact_match(self) -> None:
        doc = _make_doc()
        service = _FakeService([doc])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.lookup_course_by_code("CSCI 0320")
        assert result["retrieval_count"] == 1
        assert result["retrieved_courses"][0]["course_code"] == "CSCI 0320"

    def test_case_insensitive(self) -> None:
        doc = _make_doc()
        service = _FakeService([doc])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.lookup_course_by_code("csci 0320")
        assert result["retrieval_count"] == 1

    def test_no_match(self) -> None:
        doc = _make_doc()
        service = _FakeService([doc])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.lookup_course_by_code("MATH 0100")
        assert result["retrieval_count"] == 0

    def test_source_filter(self) -> None:
        cab_doc = _make_doc(source="cab", source_label="CAB")
        bul_doc = _make_doc(source="bulletin", source_label="bulletin")
        service = _FakeService([cab_doc, bul_doc])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.lookup_course_by_code("CSCI 0320", source="bulletin")
        assert result["retrieval_count"] == 1
        assert result["retrieved_courses"][0]["source"] == "bulletin"

    def test_compact_code_without_space(self) -> None:
        """'CSCI0320' (no space) should match 'CSCI 0320' in the index."""
        doc = _make_doc(course_code="CSCI 0320")
        service = _FakeService([doc])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.lookup_course_by_code("CSCI0320")
        assert result["retrieval_count"] == 1
        assert result["retrieved_courses"][0]["course_code"] == "CSCI 0320"

    def test_compact_code_lowercase(self) -> None:
        """'apma2680' should match 'APMA 2680'."""
        doc = _make_doc(course_code="APMA 2680")
        service = _FakeService([doc])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.lookup_course_by_code("apma2680")
        assert result["retrieval_count"] == 1


class TestSearchBySchedule:
    def test_filter_by_day(self) -> None:
        fri_doc = _make_doc(course_code="CSCI 0111", meetings=["F 3pm-5:30pm"])
        mon_doc = _make_doc(course_code="CSCI 0200", meetings=["M 10am-10:50am"])
        service = _FakeService([fri_doc, mon_doc])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.search_by_schedule(query="computer science", day="F")
        assert result["retrieval_count"] == 1
        assert result["retrieved_courses"][0]["course_code"] == "CSCI 0111"

    def test_filter_by_after_time(self) -> None:
        late = _make_doc(course_code="CSCI 0111", meetings=["F 3pm-5:30pm"])
        early = _make_doc(course_code="CSCI 0200", meetings=["F 9am-9:50am"])
        service = _FakeService([late, early])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.search_by_schedule(query="cs", day="F", after_time="3 PM")
        assert result["retrieval_count"] == 1
        assert result["retrieved_courses"][0]["course_code"] == "CSCI 0111"


class TestFindSimilarCourses:
    def test_finds_similar(self) -> None:
        ref = _make_doc(course_code="CSCI 0320", source="cab", source_label="CAB")
        similar = _make_doc(
            course_code="CSCI 0330",
            source="bulletin",
            source_label="bulletin",
            title="Intro Computer Systems",
        )
        service = _FakeService([ref, similar])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.find_similar_courses("CSCI 0320", target_source="bulletin")
        assert result["retrieval_count"] >= 1
        codes = [c["course_code"] for c in result["retrieved_courses"]]
        assert "CSCI 0320" not in codes

    def test_reference_not_found(self) -> None:
        service = _FakeService([])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.find_similar_courses("NONEXISTENT 9999")
        assert result["retrieval_count"] == 0
        assert "Could not find" in result.get("message", "")


class TestFindSimilarCoursesCompactCode:
    def test_compact_code_finds_reference(self) -> None:
        """'CSCI0320' should resolve to 'CSCI 0320' for similarity lookup."""
        ref = _make_doc(course_code="CSCI 0320", source="cab", source_label="CAB")
        similar = _make_doc(
            course_code="CSCI 0330",
            source="bulletin",
            source_label="bulletin",
            title="Intro Computer Systems",
        )
        service = _FakeService([ref, similar])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.find_similar_courses("CSCI0320", target_source="bulletin")
        assert result["retrieval_count"] >= 1
        assert "reference_course" in result
        assert result["reference_course"]["course_code"] == "CSCI 0320"


class TestNormalizeCourseCode:
    def test_with_space(self) -> None:
        from rag.retrieval.query_service import normalize_course_code
        assert normalize_course_code("CSCI 0320") == "CSCI 0320"

    def test_without_space(self) -> None:
        from rag.retrieval.query_service import normalize_course_code
        assert normalize_course_code("CSCI0320") == "CSCI 0320"

    def test_lowercase(self) -> None:
        from rag.retrieval.query_service import normalize_course_code
        assert normalize_course_code("apma2680") == "APMA 2680"

    def test_extra_whitespace(self) -> None:
        from rag.retrieval.query_service import normalize_course_code
        assert normalize_course_code("CSCI  0320") == "CSCI 0320"

    def test_with_letter_suffix(self) -> None:
        from rag.retrieval.query_service import normalize_course_code
        assert normalize_course_code("AFRI1050E") == "AFRI 1050E"

    def test_already_normalized(self) -> None:
        from rag.retrieval.query_service import normalize_course_code
        assert normalize_course_code("AFRI 1050E") == "AFRI 1050E"


class TestSearchByScheduleTwoPass:
    """Verify that the corpus-scan pass catches courses missed by semantic search."""

    def test_corpus_scan_finds_schedule_match_missed_by_semantic(self) -> None:
        """A course only in the full corpus (not in semantic results) should
        still appear when it matches the schedule filter."""
        semantic_hit = _make_doc(
            course_code="CSCI 1420",
            title="Machine Learning",
            meetings=["TTh 2:30pm-3:50pm"],
        )
        corpus_only = _make_doc(
            course_code="CSCI 0410",
            title="Foundations of AI and Machine Learning",
            meetings=["202510 | Section L03 | F 3-3:50p | E. Ewing"],
        )
        service = _FakeService(
            docs=[semantic_hit, corpus_only],
            search_returns=[semantic_hit],
        )
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.search_by_schedule(
            query="machine learning", day="F", after_time="3 PM", source="cab",
        )
        codes = [c["course_code"] for c in result["retrieved_courses"]]
        assert "CSCI 0410" in codes

    def test_no_duplicates_across_passes(self) -> None:
        """A course found in both semantic and corpus passes should only appear once."""
        doc = _make_doc(
            course_code="CSCI 0111",
            meetings=["F 3pm-5:30pm"],
        )
        service = _FakeService(docs=[doc])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.search_by_schedule(query="cs", day="F", after_time="3 PM")
        assert result["retrieval_count"] == 1

    def test_pipe_delimited_meetings_parsed_in_corpus_scan(self) -> None:
        """Pipe-delimited meeting strings should be parseable for schedule filtering."""
        doc = _make_doc(
            course_code="APMA 1931B",
            title="Foundations of Machine Learning",
            meetings=[
                "202510 | Section S01 | M 3-5:30p | Y. Sohn",
                "M 3pm-5:30pm",
            ],
        )
        service = _FakeService(docs=[doc], search_returns=[])
        adapter = ChatbotRetrievalAdapter(service)

        result = adapter.search_by_schedule(query="machine learning", day="M", after_time="3 PM")
        assert result["retrieval_count"] == 1
        assert result["retrieved_courses"][0]["course_code"] == "APMA 1931B"


class TestSummarizeCanonicalDoc:
    def test_includes_structured_fields(self) -> None:
        doc = _make_doc(meetings=["TTh 1pm-2:20pm"])
        summary = summarize_canonical_doc(doc)

        assert summary.course_code == "CSCI 0320"
        assert summary.meetings == ["TTh 1pm-2:20pm"]
        assert summary.instructors == ["Tim Nelson"]
        assert summary.description == "A software engineering course."
        assert summary.prerequisites == "CSCI 0200"
        assert summary.source == "CAB"
