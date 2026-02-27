from __future__ import annotations
"""FastAPI entrypoint for retrieval-only RAG access.

The API intentionally exposes only retrieval right now. The future chatbot can
call the same service layer, then pass the returned hits into an LLM prompt.
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from rag.models import RetrievalRequest, RetrievalResponse
from rag.query_service import LocalHybridRetrievalService
from rag.vector_store import DEFAULT_COLLECTION_NAME

app = FastAPI(title="Impiricus Course Retrieval API", version="0.1.0")

_service: LocalHybridRetrievalService | None = None


def get_service() -> LocalHybridRetrievalService:
    """Lazily initialize the retrieval service from persisted local artifacts."""
    global _service
    if _service is not None:
        return _service

    persist_dir = Path(os.getenv("RAG_PERSIST_DIR", "data"))
    embedding_model = os.getenv("RAG_EMBEDDING_MODEL")
    collection_name = os.getenv("RAG_CHROMA_COLLECTION", DEFAULT_COLLECTION_NAME)

    try:
        _service = LocalHybridRetrievalService.from_persisted(
            persist_dir=persist_dir,
            embedding_model=embedding_model,
            collection_name=collection_name,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Sparse index artifacts are missing. Run `python3 -m rag.build_index` "
                "to build retrieval indices first."
            ),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _service


@app.get("/health")
def health() -> dict[str, str]:
    """Cheap liveness check that does not force index loading."""
    return {"status": "ok"}


@app.post("/query", response_model=RetrievalResponse)
def query(payload: RetrievalRequest) -> RetrievalResponse:
    """Run hybrid retrieval and return ranked hits without answer generation."""
    service = get_service()
    return service.search(payload)
