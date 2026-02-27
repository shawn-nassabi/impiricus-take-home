# RAG Setup

## Overview

This directory contains the local retrieval foundation for the take-home project.

The current implementation is focused on:
- ingesting the two existing ETL outputs,
- normalizing them into one canonical course corpus,
- building a local dense vector index in Chroma,
- building a local sparse keyword index with BM25,
- combining dense and sparse retrieval with Reciprocal Rank Fusion (RRF),
- exposing a retrieval service that can later be used by a LangChain agent / chatbot.

The chatbot / generation layer is not implemented yet. The current API returns retrieval results only.

## Input Data

The build process consumes:
- `data/cab_courses.json`
- `data/bulletin_courses.json`

These files are produced by the ETL pipelines in `etl/`.

## High-Level Flow

1. Load raw CAB and bulletin JSON files.
2. Normalize both datasets into a single canonical document shape.
3. Build one deterministic text string per course document.
4. Save the canonical corpus to `data/rag_corpus.jsonl`.
5. Build a local sparse BM25 index and save it to `data/sparse_index/`.
6. Build embeddings for every canonical text string.
7. Upsert those embeddings into a local Chroma collection in `data/chroma/`.
8. At query time, run:
   - dense semantic search in Chroma,
   - sparse BM25 keyword search,
   - then fuse the two ranked lists with RRF.

## Package Layout

- `rag/models.py`
  - Shared data models for canonical documents and retrieval request/response types.

- `rag/indexing/normalize.py`
  - Loads JSON input.
  - Converts CAB + bulletin rows into the same canonical schema.
  - Builds the exact text that is embedded and searched.
  - Writes / reads the canonical JSONL corpus.

- `rag/indexing/embeddings.py`
  - Loads the embedding backend.
  - Default model is `mixedbread-ai/mxbai-embed-large-v1`.
  - Can be overridden with `--embedding-model` or `RAG_EMBEDDING_MODEL`.

- `rag/indexing/vector_store.py`
  - Wraps local Chroma usage.
  - Creates / resets / loads the Chroma collection.
  - Embeds batches and upserts them into Chroma.
  - Performs dense retrieval.

- `rag/retrieval/sparse_index.py`
  - Builds a BM25 index from the same canonical text used for embedding.
  - Saves the document payloads used to reconstruct the sparse index.
  - Performs sparse retrieval.

- `rag/retrieval/hybrid_retriever.py`
  - Runs dense + sparse retrieval.
  - Applies filters.
  - Combines results with Reciprocal Rank Fusion.

- `rag/retrieval/query_service.py`
  - Loads persisted indices.
  - Exposes a `LocalHybridRetrievalService` that the API can call.

- `rag/build_index.py`
  - Compatibility wrapper so `python3 -m rag.build_index` continues to work.

- `rag/indexing/build_index.py`
  - Actual CLI implementation for building or rebuilding the local retrieval artifacts.
  - Also emits progress logs during the build.

## Canonical Document Shape

Each course is converted into a `CanonicalCourseDocument` with:
- `doc_id`: deterministic unique id
- `source`: normalized source key (`cab` or `bulletin`)
- `source_label`: display label (`CAB` or `bulletin`)
- `course_code`
- `title`
- `description`
- `prerequisites`
- `department`
- `instructor_names`
- `meetings`
- `course_url`
- `text`: the canonical string used for embedding and keyword retrieval

### How bulletin records are normalized

Bulletin data does not have the same fields as CAB, so missing fields are filled with neutral defaults:
- `department = None`
- `prerequisites = None`
- `meetings = []`
- `instructor = []`
- `course_url = None`

This keeps a single schema for indexing while preserving the source in metadata.

## The Exact String That Gets Embedded

This is the most important part for understanding retrieval quality.

Every indexed document gets a single canonical text string built in `rag/indexing/normalize.py` by `_canonical_text(...)`.

The text is composed as newline-separated labeled fields:

```text
Course code: <course_code>
Title: <title>
Description: <description>
Prerequisites: <prerequisites>
Meetings: <meeting_1>; <meeting_2>; ...
Instructors: <instructor_1>; <instructor_2>; ...
```

### Important behavior

- Fields are added in that exact order.
- Empty / missing fields are omitted entirely.
- The final string is joined with newline characters (`\n`).
- `Meetings` joins multiple meeting strings with `; `.
- `Instructors` joins multiple instructor names with `; `.
- The `department` is not currently included in the embedded text itself.
  - It is stored as metadata and used for filtering.
- `course_url` is also not embedded.
  - It is metadata only.

### Example: CAB course

A CAB course might produce a string like:

```text
Course code: CSCI 0111
Title: Computing Foundations: Data
Description: Introduction to computational thinking and structured problem solving.
Prerequisites: None.
Meetings: 202510 | Section S01 | MWF 10-10:50a | Ada Lovelace; Lab W 1-2p
Instructors: Ada Lovelace; Grace Hopper
```

### Example: bulletin course

A bulletin-only course usually has fewer lines because the source data is smaller:

```text
Course code: BIOL 3001
Title: Clerkship in Medicine
Description: Twelve weeks.
```

### Why this format was chosen

This format makes the embedded text:
- human-readable for debugging,
- consistent across both sources,
- explicit about field semantics because each line is labeled,
- usable by both dense and sparse retrieval without maintaining separate text formats.

The labels (`Course code:`, `Title:`, etc.) also help retrieval by making the semantic structure explicit to the embedding model.

## Deterministic Document IDs

Each document gets a deterministic id:

```text
<source>:<course_code>:<hash>
```

The hash is derived from:
- source
- course code
- title
- canonical embedded text

This means:
- two overlapping course codes from different sources are kept as separate docs,
- rebuilding from the same inputs generates stable ids,
- if the content changes, the document id changes.

## Metadata Stored Alongside the Embedding

For Chroma, each document stores metadata including:
- `source`
- `source_label`
- `course_code`
- `title`
- `department`
- `instructor_names` (flattened into a single string separated by ` | `)
- `course_url`
- `has_prerequisites`

This metadata is used for:
- filtering,
- display in retrieval responses,
- future ranking logic.

## Dense Retrieval

Dense retrieval uses:
- local Chroma (`chromadb.PersistentClient`)
- one collection (default: `courses`)
- embeddings generated from the canonical `text`

Query flow:
1. Embed the query text.
2. Query Chroma for nearest neighbors.
3. Convert Chroma distance into a monotonic similarity score:
   - `score = 1 / (1 + distance)`
4. Return dense hits with metadata and rank.

## Sparse Retrieval

Sparse retrieval uses:
- `rank-bm25`
- tokenization with regex: `[a-zA-Z0-9]+`
- the same canonical `text` used for dense embedding

Behavior:
- Documents are tokenized into lowercase alphanumeric tokens.
- BM25 scores keyword relevance.
- Optional fuzzy bonus is added using `rapidfuzz` against:
  - `course_code`
  - `title`

This helps exact-ish queries like course codes or partial course titles.

## Hybrid Retrieval (RRF)

At query time, the retriever:
1. Runs dense retrieval.
2. Runs sparse retrieval.
3. Applies filters.
4. Combines both ranked lists using Reciprocal Rank Fusion.

RRF score contribution per list:

```text
1 / (rrf_k + rank)
```

Current default:
- `rrf_k = 60`

The final result stores:
- fused score
- `dense_rank`
- `sparse_rank`
- metadata
- canonical text

This makes it easy to inspect how a document surfaced.

## Filtering

Current retrieval filters are:
- `source`
- `department`
- `instructor_name`

How they work:
- `source` and `department` are applied in Chroma metadata filtering for dense search.
- `instructor_name` is applied after dense retrieval, because instructor names are stored as a flattened string.
- All filters are applied directly during sparse retrieval.

## Build Artifacts

A successful build writes:
- `data/rag_corpus.jsonl`
- `data/sparse_index/documents.jsonl`
- `data/chroma/` (Chroma persisted data)

## Build Command

Build indices:

```bash
python3 -m rag.build_index --persist-dir data
```

Rebuild from scratch:

```bash
python3 -m rag.build_index --persist-dir data --rebuild true
```

With logs:

```bash
python3 -m rag.build_index --persist-dir data --rebuild true --log-level INFO
```

## API Integration

The FastAPI app uses `LocalHybridRetrievalService`.

Current endpoint:
- `POST /query`

It accepts:
- `query`
- `k`
- optional `filters`

It returns retrieved hits only. This is the retrieval layer that a future LangChain agent can call before generating a final answer.

## Current Limitations

- No chunking yet: one course = one indexed document.
- `department` is metadata only, not part of the embedded text.
- No cross-source merging of overlapping course codes.
- No generation / answer synthesis yet.
- Chroma embedding function is handled explicitly by this code, not by Chroma-managed embeddings.

## Why This Is Ready for a Future Chatbot

This setup already separates concerns cleanly:
- ETL creates raw course datasets.
- RAG normalization creates canonical docs.
- Build pipeline creates persistent retrieval artifacts.
- Retrieval service exposes a stable interface for future chatbot orchestration.

A future agent can use this in a standard flow:
1. receive user question,
2. call retrieval service,
3. inspect top hits + metadata,
4. generate an answer grounded in the retrieved course content.
