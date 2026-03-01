# Impiricus Take-Home

This repository contains a local-first course-search stack:

- FastAPI backend in [app.py](/Users/shawn.n/github_repos/impiricus-take-home/app.py)
- hybrid retrieval (`Chroma` + `BM25`) in [rag](/Users/shawn.n/github_repos/impiricus-take-home/rag)
- Streamlit UI in [ui/app.py](/Users/shawn.n/github_repos/impiricus-take-home/ui/app.py)
- source course data in [data](/Users/shawn.n/github_repos/impiricus-take-home/data)

The important local setup detail is that the source JSON data is already checked into the repo. After cloning, you do not need to re-run the CAB or Bulletin scrapers just to get the app running. You do still need to install dependencies and build the local retrieval artifacts (the sparse index and Chroma vector store).

## Local Setup

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

`playwright` is included in `requirements.txt`, but you only need to run `python -m playwright install chromium` if you plan to re-run the CAB scraper. It is not required for normal local app setup.

### 3. Add environment variables

Create a `.env` file in the repo root:

```bash
OPENAI_API_KEY=your_key_here
```

`OPENAI_API_KEY` is required for the chatbot API (`/query` and `/evaluate`) and for the Streamlit UI. The app loads `.env` automatically when `python-dotenv` is installed.

Optional overrides:

- `RAG_PERSIST_DIR` (defaults to `data`)
- `RAG_EMBEDDING_MODEL` (defaults to `mixedbread-ai/mxbai-embed-large-v1`)
- `RAG_CHROMA_COLLECTION` (defaults to `courses`)
- `CHATBOT_API_BASE_URL` for the Streamlit app (defaults to `http://localhost:8000`)

### 4. Build the local retrieval artifacts

The checked-in data files:

- [data/cab_courses.json](/Users/shawn.n/github_repos/impiricus-take-home/data/cab_courses.json)
- [data/bulletin_courses.json](/Users/shawn.n/github_repos/impiricus-take-home/data/bulletin_courses.json)

are the inputs for indexing. Build the local indices with:

```bash
python3 -m rag.build_index --persist-dir data --log-level INFO
```

This step:

- reads the existing CAB and Bulletin JSON files
- writes [data/rag_corpus.jsonl](/Users/shawn.n/github_repos/impiricus-take-home/data/rag_corpus.jsonl)
- creates `data/sparse_index/`
- creates `data/chroma/`

On the first run, `sentence-transformers` may download the embedding model weights into your local cache. That is expected.

If you change the source JSON and want to regenerate everything from scratch, run:

```bash
python3 -m rag.build_index --persist-dir data --rebuild true --log-level INFO
```

## Run Locally

### Start the API

```bash
uvicorn app:app --reload
```

The API will be available at `http://localhost:8000`.

Useful endpoints:

- `GET /health` for a simple liveness check
- `POST /query` for the streaming chatbot response (SSE)
- `POST /evaluate` for a synchronous diagnostics response

Example request body:

```json
{
  "q": "What are some machine learning courses?",
  "department": "CSCI"
}
```

### Start the Streamlit UI

In a second terminal, with the same virtual environment activated:

```bash
streamlit run ui/app.py
```

By default, the UI talks to `http://localhost:8000`. If your API is running somewhere else, set `CHATBOT_API_BASE_URL` before starting Streamlit.

## Test

Run the test suite with:

```bash
pytest -q
```

## Notes

- Fresh clones already contain the source course data in `data/`; you do not need to scrape again for normal development.
- Fresh clones do not necessarily contain the built retrieval indices, so `python3 -m rag.build_index ...` should be part of first-time setup.
- If `data/sparse_index/` or `data/chroma/` are missing, the API will return a `503` until you build the indices.
- If `OPENAI_API_KEY` is missing, the chatbot endpoints will return a `503`.

## Optional: Rebuild Source Data

Only do this if you intentionally want to refresh the checked-in source JSON files. It is not part of the normal local setup flow.

- CAB scraping code lives under [etl/cab_scraper_1](/Users/shawn.n/github_repos/impiricus-take-home/etl/cab_scraper_1) and [etl/cab_scraper_2](/Users/shawn.n/github_repos/impiricus-take-home/etl/cab_scraper_2)
- Bulletin extraction code lives under [etl/bulletin_scraper](/Users/shawn.n/github_repos/impiricus-take-home/etl/bulletin_scraper)

If you go down that path, install the browser dependency first:

```bash
python -m playwright install chromium
```
