"""CAB course scraper — cab_scraper_2.

Uses the FOSE JSON API directly (no browser automation).

Usage:
    python -m etl.cab_scraper_2.scrape [options]

Options:
    --out PATH          Output JSON file  [default: data/cab_courses_v2.json]
    --checkpoint PATH   Checkpoint file   [default: data/cab_v2_checkpoint.json]
    --srcdb CODE        Term database code [default: 999999 = Any Term 2025-26]
    --workers INT       Parallel detail-fetch threads [default: 6]
    --delay-ms INT      Milliseconds to sleep between requests per thread [default: 150]
    --max-courses INT   Stop after this many unique courses (0 = unlimited) [default: 0]
    --resume BOOL       Skip already-completed CRNs from checkpoint [default: true]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from etl.cab_scraper_2.api_client import ANY_TERM_2025_26, CABClient
from etl.cab_scraper_2.parse_detail import parse_detail_json

DEFAULT_OUT = Path("data/cab_courses_v2.json")
DEFAULT_CHECKPOINT = Path("data/cab_v2_checkpoint.json")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape CAB course data via the FOSE API")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    p.add_argument("--srcdb", default=ANY_TERM_2025_26)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--delay-ms", type=int, default=150)
    p.add_argument("--max-courses", type=int, default=0)
    p.add_argument("--resume", type=_parse_bool, default=True)
    return p.parse_args()


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    if value.strip().lower() in {"1", "true", "t", "yes", "y"}:
        return True
    if value.strip().lower() in {"0", "false", "f", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Cannot parse boolean: {value!r}")


# ------------------------------------------------------------------
# Checkpoint / IO helpers
# ------------------------------------------------------------------


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"completed_crns": [], "failed_crns": {}}


def _save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(checkpoint, fh, indent=2)
    tmp.replace(path)


def _write_output(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, ensure_ascii=False)
    tmp.replace(path)


# ------------------------------------------------------------------
# Phase 1 — collect unique course summaries
# ------------------------------------------------------------------


def collect_unique_courses(
    client: CABClient,
    srcdb: str,
    max_courses: int,
) -> list[dict[str, Any]]:
    """Fetch all section-level results and return one representative per course code.

    The FOSE search returns all sections (10k+) in one response.  We pick the
    first non-cancelled section for each unique ``code``, falling back to
    cancelled sections when no active section exists.
    """
    print("[search] fetching all sections from FOSE API …", flush=True)
    all_sections = client.search_all(srcdb=srcdb)
    print(f"[search] API returned {len(all_sections)} total sections", flush=True)

    if not all_sections:
        return []

    # Build one representative per unique course code.
    # Prefer non-cancelled sections (isCancelled != "1") so we get live data.
    best: dict[str, dict[str, Any]] = {}
    for section in all_sections:
        code = str(section.get("code") or "").strip()
        if not code:
            continue
        if code not in best:
            best[code] = section
        elif section.get("isCancelled") != "1" and best[code].get("isCancelled") == "1":
            best[code] = section

    unique = list(best.values())
    print(f"[search] {len(unique)} unique course codes found", flush=True)

    if max_courses > 0:
        unique = unique[:max_courses]
    return unique


# ------------------------------------------------------------------
# Phase 2 — fetch and parse detail for each course
# ------------------------------------------------------------------


def _fetch_one(
    summary: dict[str, Any],
    delay_s: float,
    delay_ms: int,
) -> dict[str, Any]:
    """Fetch and parse detail for a single course.  Each call creates its own
    CABClient to avoid session sharing across threads."""
    crn = str(summary.get("crn") or "")
    srcdb = str(summary.get("srcdb") or "")
    code = str(summary.get("code") or "")

    with CABClient(delay_ms=delay_ms) as client:
        detail = client.fetch_detail(crn=crn, srcdb=srcdb, group_code=code)

    time.sleep(delay_s)
    return parse_detail_json(detail=detail, search_summary=summary)


def scrape_details(
    unique_courses: list[dict[str, Any]],
    args: argparse.Namespace,
    checkpoint: dict[str, Any],
    existing_records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Fetch and parse detail for all courses, skipping completed ones."""
    completed_crns: set[str] = set(checkpoint.get("completed_crns") or [])
    failed_crns: dict[str, str] = dict(checkpoint.get("failed_crns") or {})
    records_by_crn: dict[str, dict[str, Any]] = dict(existing_records)
    delay_s = args.delay_ms / 1000.0

    pending = [
        s for s in unique_courses
        if str(s.get("crn") or "") not in completed_crns
    ]
    total_pending = len(pending)
    print(
        f"[detail] {len(completed_crns)} already done, {total_pending} pending",
        flush=True,
    )

    if not pending:
        return records_by_crn

    def _worker(summary: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
        crn = str(summary.get("crn") or "")
        for attempt in range(3):
            try:
                record = _fetch_one(summary, delay_s, args.delay_ms)
                return crn, record, None
            except Exception as exc:
                if attempt == 2:
                    return crn, None, str(exc)
                time.sleep(1.5 * (attempt + 1))
        return crn, None, "max retries exceeded"

    done_count = 0
    save_interval = 50

    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
        futures = {pool.submit(_worker, s): s for s in pending}
        for future in as_completed(futures):
            crn, record, error = future.result()
            done_count += 1

            if record:
                records_by_crn[crn] = record
                completed_crns.add(crn)
                failed_crns.pop(crn, None)
            else:
                failed_crns[crn] = error or "unknown error"
                print(f"[detail] FAILED crn={crn}: {error}", flush=True)

            if done_count % save_interval == 0 or done_count == total_pending:
                checkpoint["completed_crns"] = sorted(completed_crns)
                checkpoint["failed_crns"] = failed_crns
                _save_checkpoint(args.checkpoint, checkpoint)

                ordered = _order_records(records_by_crn, unique_courses)
                _write_output(args.out, ordered)
                print(
                    f"[detail] {done_count}/{total_pending} "
                    f"| success={len(completed_crns)} failed={len(failed_crns)}",
                    flush=True,
                )

    return records_by_crn


def _order_records(
    records_by_crn: dict[str, dict[str, Any]],
    unique_courses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return records in the original search-result order."""
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for s in unique_courses:
        crn = str(s.get("crn") or "")
        if crn in records_by_crn and crn not in seen:
            ordered.append(records_by_crn[crn])
            seen.add(crn)
    return ordered


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------


def main() -> None:
    args = _parse_args()

    checkpoint = _load_checkpoint(args.checkpoint) if args.resume else {
        "completed_crns": [],
        "failed_crns": {},
    }

    # Load any already-written output so we don't re-fetch on resume.
    existing_records: dict[str, dict[str, Any]] = {}
    if args.resume and args.out.exists():
        try:
            with args.out.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, list):
                for row in payload:
                    if isinstance(row, dict) and row.get("crn"):
                        existing_records[str(row["crn"])] = row
        except Exception:
            pass

    print(
        f"[run] out={args.out} workers={args.workers} "
        f"delay={args.delay_ms}ms srcdb={args.srcdb}",
        flush=True,
    )

    with CABClient(delay_ms=args.delay_ms) as client:
        unique_courses = collect_unique_courses(
            client=client,
            srcdb=args.srcdb,
            max_courses=args.max_courses,
        )

    if not unique_courses:
        print(
            "[run] ERROR: search returned no courses — check network / API",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[run] {len(unique_courses)} unique courses to scrape", flush=True)

    records_by_crn = scrape_details(
        unique_courses=unique_courses,
        args=args,
        checkpoint=checkpoint,
        existing_records=existing_records,
    )

    final = _order_records(records_by_crn, unique_courses)
    _write_output(args.out, final)

    failed = checkpoint.get("failed_crns") or {}
    print(
        f"[run] complete — records={len(final)} failed={len(failed)} out={args.out}",
        flush=True,
    )
    if failed:
        print(f"[run] {len(failed)} failed CRNs (first 10): {list(failed.keys())[:10]}", flush=True)


if __name__ == "__main__":
    main()
