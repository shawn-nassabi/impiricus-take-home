from rag.retrieval.hybrid_retriever import reciprocal_rank_fusion
from rag.retrieval.sparse_index import SparseHit
from rag.indexing.vector_store import DenseHit


def test_reciprocal_rank_fusion_combines_dense_and_sparse() -> None:
    dense_hits = [
        DenseHit(
            doc_id="cab:CSCI 0111:abc",
            score=0.9,
            rank=1,
            metadata={"source": "cab", "course_code": "CSCI 0111", "title": "Foundations"},
            text="doc-1",
        ),
        DenseHit(
            doc_id="bulletin:BIOL 3001:def",
            score=0.8,
            rank=2,
            metadata={"source": "bulletin", "course_code": "BIOL 3001", "title": "Clerkship"},
            text="doc-2",
        ),
    ]

    sparse_hits = [
        SparseHit(
            doc_id="bulletin:BIOL 3001:def",
            score=7.5,
            rank=1,
            metadata={"source": "bulletin", "course_code": "BIOL 3001", "title": "Clerkship"},
            text="doc-2",
        ),
        SparseHit(
            doc_id="cab:CSCI 0111:abc",
            score=6.0,
            rank=2,
            metadata={"source": "cab", "course_code": "CSCI 0111", "title": "Foundations"},
            text="doc-1",
        ),
    ]

    hits = reciprocal_rank_fusion(dense_hits=dense_hits, sparse_hits=sparse_hits, rrf_k=60, limit=5)

    assert len(hits) == 2

    by_id = {hit.doc_id: hit for hit in hits}
    assert set(by_id) == {"cab:CSCI 0111:abc", "bulletin:BIOL 3001:def"}
    assert by_id["cab:CSCI 0111:abc"].dense_rank == 1
    assert by_id["cab:CSCI 0111:abc"].sparse_rank == 2
    assert by_id["bulletin:BIOL 3001:def"].dense_rank == 2
    assert by_id["bulletin:BIOL 3001:def"].sparse_rank == 1
