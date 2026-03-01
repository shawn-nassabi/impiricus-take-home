# Repository Guidelines

## Project Structure & Module Organization
This repository currently contains `README.md` and the take-home prompt PDF. As implementation is added, keep a simple layout:
- `app.py`: FastAPI entrypoint and route wiring.
- `etl/`: scraping, normalization, and merge logic for CAB and Bulletin data.
- `rag/`: embeddings, retrieval, ranking, and answer-generation pipeline.
- `data/`: local generated artifacts (for example `courses.json`), excluded from Git when large.
- `ui/`: Streamlit app (`ui/app.py`) for query input and result display.
- `tests/`: unit and integration tests.

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`: create and activate local environment.
- `pip install -r requirements.txt`: install backend and UI dependencies.
- `uvicorn app:app --reload`: run API locally with hot reload.
- `streamlit run ui/app.py`: run local UI against the API.
- `pytest -q`: run tests quickly; use before opening a PR.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation. Use type hints for public functions and return values. Use:
- `snake_case` for files, variables, and functions.
- `PascalCase` for classes.
- descriptive module names such as `rag/retrieval.py` and `etl/normalize.py`.
Keep functions small and single-purpose, especially in ETL and ranking logic.

## Testing Guidelines
Use `pytest` and name tests as `tests/test_<module>.py`. Prioritize:
- ETL normalization correctness across sources.
- retrieval filtering (department/source) and ranking behavior.
- API response shape for `/query` including retrieved metadata and generated answer.
Add regression tests for every bug fix.

## Commit & Pull Request Guidelines
Write concise imperative commit subjects (example: `Add hybrid retrieval scoring`). Keep subject lines under 72 characters when possible. PRs should include:
- purpose and scope summary.
- test evidence (`pytest -q` output summary).
- sample query/response or screenshot for UI changes.
- linked issue or prompt section when applicable.

## Security & Configuration Tips
Store secrets in `.env` (for example API keys) and load them via environment variables. Never commit credentials, session tokens, or large raw scrape dumps.
