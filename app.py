from __future__ import annotations
"""FastAPI entrypoint for the LangChain-backed chatbot API."""

import logging
import os
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from chatbot_agent.agent import LangChainAgentRunner
from chatbot_agent.logging_utils import COLOR_CYAN, format_log
from chatbot_agent.models import ChatQueryRequest, EvaluateResponse
from chatbot_agent.retrieval_adapter import ChatbotRetrievalAdapter
from chatbot_agent.service import ChatbotService
from rag.indexing.vector_store import DEFAULT_COLLECTION_NAME
from rag.retrieval.query_service import LocalHybridRetrievalService


def _load_dotenv() -> None:
    """Load environment variables from `.env` when python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


_load_dotenv()

app = FastAPI(title="Impiricus Course Chatbot API", version="0.2.0")
LOGGER = logging.getLogger(__name__)

_retrieval_service: LocalHybridRetrievalService | None = None
_chatbot_service: ChatbotService | None = None


def _configure_application_logging() -> None:
    """Route app/package logs through uvicorn's configured handlers."""
    uvicorn_logger = logging.getLogger("uvicorn.error")
    target_level = uvicorn_logger.level or logging.INFO
    handlers = list(uvicorn_logger.handlers)

    if not handlers:
        fallback_handler = logging.StreamHandler()
        fallback_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        handlers = [fallback_handler]

    for logger_name in ("app", "chatbot_agent", "rag"):
        logger = logging.getLogger(logger_name)
        logger.setLevel(target_level)
        if not logger.handlers:
            for handler in handlers:
                logger.addHandler(handler)
        logger.propagate = False


_configure_application_logging()


def get_retrieval_service() -> LocalHybridRetrievalService:
    """Lazily initialize the retrieval service from persisted local artifacts."""
    global _retrieval_service
    if _retrieval_service is not None:
        return _retrieval_service

    persist_dir = Path(os.getenv("RAG_PERSIST_DIR", "data"))
    embedding_model = os.getenv("RAG_EMBEDDING_MODEL")
    collection_name = os.getenv("RAG_CHROMA_COLLECTION", DEFAULT_COLLECTION_NAME)

    try:
        _retrieval_service = LocalHybridRetrievalService.from_persisted(
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

    return _retrieval_service


def get_service() -> LocalHybridRetrievalService:
    """Backward-compatible alias for tests and internal imports."""
    return get_retrieval_service()


def get_chatbot_service() -> ChatbotService:
    """Lazily initialize the chatbot service."""
    global _chatbot_service
    if _chatbot_service is not None:
        return _chatbot_service

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is required to use the chatbot.")

    retrieval_service = get_retrieval_service()
    retrieval_adapter = ChatbotRetrievalAdapter(retrieval_service)
    agent_runner = LangChainAgentRunner(retrieval_adapter)
    _chatbot_service = ChatbotService(retrieval_adapter=retrieval_adapter, agent_runner=agent_runner)
    return _chatbot_service


def _clean_query(raw_query: str) -> str:
    """Reject empty or whitespace-only query text."""
    clean_query = raw_query.strip()
    if not clean_query:
        raise HTTPException(status_code=422, detail="`q` must not be empty.")
    return clean_query


@app.get("/health")
def health() -> dict[str, str]:
    """Cheap liveness check that does not force index loading."""
    return {"status": "ok"}


@app.post("/query")
async def query(payload: ChatQueryRequest) -> StreamingResponse:
    """Run deterministic retrieval, then stream the chatbot response over SSE."""
    started_at = time.perf_counter()
    clean_query = _clean_query(payload.q)
    service = get_chatbot_service()
    clean_department = (payload.department or "").strip().upper() or None
    LOGGER.info(
        format_log(
            "api_request_received",
            COLOR_CYAN,
            endpoint="/query",
            query=clean_query,
            department=clean_department,
        )
    )

    try:
        prepared = service.prepare_query(query=clean_query, department=payload.department, started_at=started_at)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return StreamingResponse(
        service.stream_prepared_query(prepared),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(payload: ChatQueryRequest) -> EvaluateResponse:
    """Return synchronous timing and retrieval diagnostics."""
    started_at = time.perf_counter()
    clean_query = _clean_query(payload.q)
    service = get_chatbot_service()
    clean_department = (payload.department or "").strip().upper() or None
    LOGGER.info(
        format_log(
            "api_request_received",
            COLOR_CYAN,
            endpoint="/evaluate",
            query=clean_query,
            department=clean_department,
        )
    )

    try:
        return await service.evaluate(query=clean_query, department=payload.department, started_at=started_at)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
