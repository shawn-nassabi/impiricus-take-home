from __future__ import annotations
"""CLI for building the local dense+sparse retrieval artifacts."""

import argparse
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from rag.indexing.embeddings import EmbeddingBackend, build_embedding_backend
from rag.indexing.normalize import load_json_records, normalize_records, write_corpus_jsonl
from rag.retrieval.sparse_index import SparseKeywordIndex
from rag.indexing.vector_store import ChromaVectorStore, DEFAULT_COLLECTION_NAME

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for index creation and rebuilds."""
    parser = argparse.ArgumentParser(description="Build local dense+sparse retrieval indices")
    parser.add_argument("--cab", type=Path, default=Path("data/cab_courses.json"))
    parser.add_argument("--bulletin", type=Path, default=Path("data/bulletin_courses.json"))
    parser.add_argument("--persist-dir", type=Path, default=Path("data"))
    parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION_NAME)
    parser.add_argument("--embedding-model", type=str, default=None)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--rebuild", type=parse_bool, default=False)
    parser.add_argument("--log-level", type=str, default="INFO")
    return parser.parse_args()


def parse_bool(raw: str | bool) -> bool:
    """Accept common truthy CLI values for the `--rebuild` flag."""
    if isinstance(raw, bool):
        return raw
    return raw.strip().lower() in {"1", "true", "yes", "y"}


def artifacts_present(persist_dir: Path) -> bool:
    """Check whether the persisted artifacts already exist on disk."""
    corpus_path = persist_dir / "rag_corpus.jsonl"
    sparse_docs = persist_dir / "sparse_index" / "documents.jsonl"
    chroma_dir = persist_dir / "chroma"
    return corpus_path.exists() and sparse_docs.exists() and chroma_dir.exists() and any(chroma_dir.iterdir())


def build_indices(
    cab_path: Path,
    bulletin_path: Path,
    persist_dir: Path,
    rebuild: bool,
    embedding_model: str | None,
    batch_size: int,
    collection_name: str,
    embedding_backend: EmbeddingBackend | None = None,
) -> dict[str, Any]:
    """Build the canonical corpus, sparse index, and Chroma vector store."""
    start_time = time.perf_counter()
    persist_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Starting RAG index build in %s", persist_dir)
    LOGGER.info(
        "Inputs: cab=%s bulletin=%s collection=%s rebuild=%s batch_size=%s",
        cab_path,
        bulletin_path,
        collection_name,
        rebuild,
        batch_size,
    )

    if artifacts_present(persist_dir) and not rebuild:
        # Skipping avoids accidental expensive re-embedding when artifacts are
        # already present and still valid.
        LOGGER.info("Skipping build because artifacts already exist. Use --rebuild true to regenerate.")
        return {
            "status": "skipped",
            "reason": "artifacts already present; run with --rebuild true to regenerate",
            "persist_dir": str(persist_dir),
        }

    chroma_dir = persist_dir / "chroma"
    sparse_dir = persist_dir / "sparse_index"
    corpus_path = persist_dir / "rag_corpus.jsonl"

    if rebuild:
        LOGGER.info("Rebuild requested. Removing existing artifacts under %s", persist_dir)
        shutil.rmtree(chroma_dir, ignore_errors=True)
        shutil.rmtree(sparse_dir, ignore_errors=True)
        if corpus_path.exists():
            corpus_path.unlink()

    LOGGER.info("Loading CAB records from %s", cab_path)
    cab_records = load_json_records(cab_path)
    LOGGER.info("Loaded %s CAB records", len(cab_records))
    LOGGER.info("Loading bulletin records from %s", bulletin_path)
    bulletin_records = load_json_records(bulletin_path)
    LOGGER.info("Loaded %s bulletin records", len(bulletin_records))

    LOGGER.info("Normalizing and consolidating records")
    documents = normalize_records(cab_records=cab_records, bulletin_records=bulletin_records)
    LOGGER.info("Normalized %s total documents", len(documents))

    LOGGER.info("Writing canonical corpus to %s", corpus_path)
    write_corpus_jsonl(documents=documents, path=corpus_path)
    LOGGER.info("Wrote canonical corpus JSONL")

    sparse_start = time.perf_counter()
    LOGGER.info("Building sparse BM25 index")
    sparse_index = SparseKeywordIndex.from_documents(documents)
    sparse_index.save(sparse_dir)
    LOGGER.info(
        "Sparse index saved to %s (%.2fs)",
        sparse_dir,
        time.perf_counter() - sparse_start,
    )

    LOGGER.info("Initializing embedding backend")
    backend = embedding_backend or build_embedding_backend(model_name=embedding_model)
    LOGGER.info("Embedding model: %s", getattr(backend, "model_name", "<custom-backend>"))
    vector_store = ChromaVectorStore(persist_dir=chroma_dir, collection_name=collection_name)
    LOGGER.info("Resetting Chroma collection '%s' in %s", collection_name, chroma_dir)
    vector_store.reset_collection()
    dense_start = time.perf_counter()

    def log_batch_progress(batch_num: int, total_batches: int, start_idx: int, end_idx: int, total_docs: int) -> None:
        """Log batch progress from the vector-store upsert loop."""
        LOGGER.info(
            "Dense upsert batch %s/%s (%s-%s of %s docs)",
            batch_num,
            total_batches,
            start_idx,
            end_idx,
            total_docs,
        )

    vector_store.upsert_documents(
        documents=documents,
        backend=backend,
        batch_size=batch_size,
        progress_callback=log_batch_progress,
    )
    LOGGER.info("Dense index upsert complete (%.2fs)", time.perf_counter() - dense_start)
    chroma_count = vector_store.count()
    LOGGER.info("Chroma collection now contains %s vectors", chroma_count)

    total_elapsed = time.perf_counter() - start_time
    LOGGER.info("RAG index build completed in %.2fs", total_elapsed)

    return {
        "status": "built",
        "persist_dir": str(persist_dir),
        "documents": len(documents),
        "collection": collection_name,
        "chroma_count": chroma_count,
        "elapsed_seconds": round(total_elapsed, 2),
    }


def configure_logging(level_name: str) -> None:
    """Configure simple CLI logging for the build command."""
    level = getattr(logging, level_name.strip().upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    configure_logging(args.log_level)
    summary = build_indices(
        cab_path=args.cab,
        bulletin_path=args.bulletin,
        persist_dir=args.persist_dir,
        rebuild=args.rebuild,
        embedding_model=args.embedding_model,
        batch_size=args.batch_size,
        collection_name=args.collection,
    )
    print(summary)


if __name__ == "__main__":
    main()
