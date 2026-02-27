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

Build local dense+sparse retrieval indices:

```bash
python3 -m rag.build_index --persist-dir data
```

Verbose progress logs:

```bash
python3 -m rag.build_index --persist-dir data --log-level INFO
```

Rebuild indices (clears old artifacts first):

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
