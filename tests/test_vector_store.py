from rag.indexing.vector_store import build_chroma_where
from rag.models import RetrievalFilters


def test_build_chroma_where_returns_and_expression_for_multiple_filters() -> None:
    where = build_chroma_where(RetrievalFilters(source="cab", department="anth"))

    assert where == {"$and": [{"source": "cab"}, {"department": "ANTH"}]}


def test_build_chroma_where_returns_single_clause_when_one_filter_is_set() -> None:
    where = build_chroma_where(RetrievalFilters(source="cab", department=None))

    assert where == {"source": "cab"}
