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

Run tests:

```bash
pytest -q
```
