# Short Written Report

## How the RAG pipeline works

The pipeline has an offline indexing phase and an online query phase.

Offline, `rag.build_index` loads the checked-in CAB and Bulletin JSON datasets, normalizes both sources into a single `CanonicalCourseDocument` schema, and builds one canonical text block per course. That text is written to `data/rag_corpus.jsonl`, indexed into a BM25 sparse index (`data/sparse_index`), and embedded into a local Chroma vector store (`data/chroma`).

Online, the FastAPI app loads those persisted artifacts through `LocalHybridRetrievalService`. For each query, the retriever runs dense vector search in Chroma and sparse keyword search in BM25, then combines both ranked lists with Reciprocal Rank Fusion (RRF). The chatbot layer does a deterministic pre-retrieval pass first, then hands the question to a LangChain agent that can call source-specific retrieval tools (`search_cab_courses`, `search_bulletin_courses`, `get_course_by_code`, schedule search, and similar-course search) before generating the final grounded answer with `gpt-4.1-mini`.

## Why I chose the embedding model

The default embedding model is `mixedbread-ai/mxbai-embed-large-v1`, loaded through `sentence-transformers`. I chose it because this project is explicitly local-first, so I wanted a model that works well without a hosted vectorization dependency, plugs cleanly into the Python stack, and is strong enough for semantic course matching across short titles, descriptions, prerequisites, and meeting text.

The implementation also normalizes embeddings at encode time, which makes similarity comparisons more stable, and the model is configurable through `RAG_EMBEDDING_MODEL` so it can be swapped for a smaller or cheaper option without changing the retrieval code.

Compared with the alternatives, `mixedbread-ai/mxbai-embed-large-v1` is the strongest quality-first default for this exact pipeline. `sentence-transformers/all-MiniLM-L6-v2` is faster and lighter, but it is a smaller, older model and is more likely to lose semantic nuance. `intfloat/e5-small-v2` and `intfloat/e5-base-v2` are strong retrieval models, but they usually work best when queries and documents are formatted with E5-style prefixes such as `query:` and `passage:`; this codebase currently embeds raw text directly, so they are not as clean a drop-in. `BAAI/bge-small-en-v1.5` and `BAAI/bge-base-en-v1.5` are also credible options, but they do not offer a clear advantage here without benchmarking. Because this corpus is only 5,658 documents, the larger Mixedbread model is still practical locally, and the hybrid BM25 layer already covers exact-match behavior, so using the denser model for better semantic recall is a reasonable default.

## Observations on performance

On the current corpus (`data/rag_corpus.jsonl`) there are 5,658 indexed course documents, which is small enough for a local BM25 index and a local Chroma collection to remain practical. In this setup, retrieval should stay fast and predictable, and the hybrid approach improves recall because exact course-code lookups and fuzzy title matches benefit from BM25 while broader intent-based searches benefit from dense retrieval.

The main cost is in the first build and first-request warmup. Embedding generation and Chroma upserts are the slowest part of indexing, while the first live query also pays for lazy loading of the retriever and LLM client. Schedule-based queries are intentionally more expensive than simple semantic search because they widen the candidate pool and then run a full-corpus BM25 fallback to improve recall after applying day/time filters.

## What I would improve for production

For production, I would separate retrieval from generation more cleanly and add better observability. Specifically, I would persist explicit retrieval metrics (latency by dense, sparse, fusion, and tool call), log per-tool relevance outcomes, and add offline evaluation sets so ranking changes can be measured instead of judged manually.

I would also tighten the retrieval stack itself: add reranking, include department and other structured fields in the searchable representation more deliberately, cache hot queries, and move from local Chroma to a deployment model with clearer operational guarantees. On the serving side, I would add conversation memory, stronger guardrails around tool use, and background jobs for scheduled re-indexing so the corpus stays fresh without manual rebuilds.
