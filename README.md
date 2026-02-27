# Impiricus take-home

## CAB ETL

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Run CAB scrape:

```bash
python -m etl.scrape_cab --out data/courses.json --workers 4 --resume true
```

Key outputs:

- `data/courses.json`: one course object per CAB course.
- `data/cab_checkpoint.json`: discovered/completed/failed URL state.
- `data/cab_run_summary.json`: run timestamps, counts, and failures.

## Bulletin ETL

Run bulletin scrape:

```bash
python3 -m etl.scrape_bulletin --pdf etl/2025-26-bulletin.pdf --out data/bulletin_courses.json
```

Key output:

- `data/bulletin_courses.json`: one course object per bulletin course.

## RAG Index Build

This project uses a local vector database (Chroma) plus a local BM25 index for hybrid retrieval.

### Initial Vector DB Setup

For a fresh clone, the first-time setup flow is:

1. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Make sure the source course JSON files exist:
   - `data/cab_courses.json`
   - `data/bulletin_courses.json`

These are already included in this repository. If you need to regenerate them, run the CAB and bulletin ETL steps above first.

3. Build the local retrieval artifacts (this is the initial vector DB setup):

```bash
python3 -m rag.build_index --persist-dir data --rebuild true --log-level INFO
```

This command will:
- normalize CAB + bulletin data into one canonical corpus
- write `data/rag_corpus.jsonl`
- build the local sparse BM25 index in `data/sparse_index/`
- build and persist the local Chroma vector DB in `data/chroma/`

After that first build, the local vector DB is ready for API queries.

### Incremental Build Commands

Build local dense+sparse retrieval indices if artifacts are missing:

```bash
python3 -m rag.build_index --persist-dir data
```

Build with verbose progress logs:

```bash
python3 -m rag.build_index --persist-dir data --log-level INFO
```

Force a clean rebuild (recommended after changing source data):

```bash
python3 -m rag.build_index --persist-dir data --rebuild true
```

Start API:

```bash
uvicorn app:app --reload
```

Retrieval endpoint:

- `POST /query` with body:
  - `query` (string)
  - `k` (optional int, default 8)
  - `filters` (optional: `source`, `department`, `instructor_name`)

Run tests:

```bash
pytest -q
```
