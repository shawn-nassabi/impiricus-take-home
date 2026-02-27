# CAB Scraper 1

Scrapes Brown Courses @ Brown (CAB) course data into JSON.

## Run From Repo Root

Use the scraper as a Python module from the repository root:

```bash
./venv/bin/python -m etl.cab_scraper_1.scrape_cab --help
```

## Setup

If you need to set up a fresh environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Common Commands

Quick validation run (20 courses, visible browser):

```bash
./venv/bin/python -m etl.cab_scraper_1.scrape_cab \
  --out data/cab_courses.json \
  --workers 4 \
  --resume false \
  --headless false \
  --max-courses 20
```

Full run (all discovered courses, headless):

```bash
./venv/bin/python -m etl.cab_scraper_1.scrape_cab \
  --out data/cab_courses.json \
  --workers 6 \
  --resume false \
  --headless true
```

Resume an interrupted run:

```bash
./venv/bin/python -m etl.cab_scraper_1.scrape_cab \
  --out data/cab_courses.json \
  --workers 6 \
  --resume true \
  --headless true
```

## Outputs

- Course data JSON: `--out` (default project data path)
- Checkpoint JSON: `--checkpoint` (used for resume)
- Run summary JSON: `--summary`

## Notes

- The scraper attempts CAB API discovery first, then browser fallback if needed.
- Meetings are stored as a list of strings per course.
- If debugging selectors/UI behavior, run with `--headless false`.
