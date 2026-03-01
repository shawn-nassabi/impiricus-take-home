# CAB Scraper 2

Scrapes course data from [Courses @ Brown](https://cab.brown.edu) using the FOSE JSON API directly — no browser automation required.

## How it works

The CAB site exposes a JSON API at `https://cab.brown.edu/api/?page=fose`. This scraper:

1. **Collects all sections** via a single `route=search` POST call (returns ~10,800 section-level records for Any Term 2025-26).
2. **Deduplicates** by course code to get ~3,145 unique courses.
3. **Fetches full detail** for each course via a `route=details` POST call.
4. **Parses** each detail response (structured JSON with HTML sub-fields) into a flat record.
5. **Writes** results to `data/cab_courses_v2.json`, saving progress to a checkpoint file so interrupted runs can resume.

## Setup

Activate your virtual environment and install dependencies (if not already done):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Dependencies used by this scraper: `requests`, `beautifulsoup4` (both already in `requirements.txt`).

## Running the scraper

From the repo root:

```bash
# Full scrape (~3,145 courses, ~10-15 min with default settings)
python -m etl.cab_scraper_2.scrape

# Quick test — first 20 courses only
python -m etl.cab_scraper_2.scrape --max-courses 20 --workers 2

# Resume an interrupted run (default behaviour — skips already-fetched courses)
python -m etl.cab_scraper_2.scrape --resume true

# Custom output path and worker count
python -m etl.cab_scraper_2.scrape --out data/my_courses.json --workers 8
```

## CLI options

| Option | Default | Description |
|---|---|---|
| `--out` | `data/cab_courses_v2.json` | Output JSON file path |
| `--checkpoint` | `data/cab_v2_checkpoint.json` | Checkpoint file (tracks completed CRNs) |
| `--srcdb` | `999999` | Term database code (`999999` = Any Term 2025-26) |
| `--workers` | `6` | Number of parallel detail-fetch threads |
| `--delay-ms` | `150` | Milliseconds to sleep between requests per thread |
| `--max-courses` | `0` | Stop after N unique courses (0 = scrape all) |
| `--resume` | `true` | Skip already-completed CRNs from checkpoint |

## Output format

`data/cab_courses_v2.json` is a JSON array. Each element:

```json
{
  "course_code":   "CSCI 0150",
  "title":         "Intro to Object-Oriented Programming",
  "instructor":    [{"name": "Andries van Dam", "email": "andries_van_dam@brown.edu"}],
  "meeting_times": ["TTh 2:30pm-3:50pm"],
  "prerequisites": "Enrollment limited to ...",
  "description":   "An introduction to ...",
  "department":    "CSCI",
  "source":        "CAB",
  "crn":           "18181",
  "srcdb":         "202510"
}
```

## Module overview

| File | Purpose |
|---|---|
| `api_client.py` | `CABClient` — wraps `requests.Session`, handles URL encoding, retries |
| `parse_detail.py` | `parse_detail_json()` — extracts fields from the FOSE detail JSON response |
| `scrape.py` | Orchestration: search → deduplicate → threaded detail fetch → write output |

## Why the previous scraper failed

The original `etl/scrape_cab.py` used Playwright browser automation to drive the CAB UI. CAB renders search results as in-page modals with no stable URLs, so the URL-discovery loop found nothing and the fallback modal crawler was unreliable.

This scraper bypasses the UI entirely by calling the same JSON API the browser uses, identified from `foseConfig` in the page source.
