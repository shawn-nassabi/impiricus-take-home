from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from etl.bulletin_extract import parse_bulletin_pdf
from etl.cab_io import atomic_write_json

DEFAULT_PDF_PATH = Path("etl/2025-26-bulletin.pdf")
DEFAULT_OUTPUT_PATH = Path("data/bulletin_courses.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape bulletin course data into JSON")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def run_scraper(pdf_path: Path, out_path: Path) -> dict[str, Any]:
    records = parse_bulletin_pdf(pdf_path)
    payload = [record.to_dict() for record in records]
    atomic_write_json(out_path, payload)

    missing_description_count = sum(
        record.description == "No description available." for record in records
    )
    return {
        "counts": {
            "output_records": len(records),
            "missing_descriptions": missing_description_count,
        },
        "output_path": str(out_path),
        "pdf_path": str(pdf_path),
    }


def main() -> None:
    args = parse_args()
    summary = run_scraper(pdf_path=args.pdf, out_path=args.out)
    print(
        "Completed bulletin scrape:",
        f"records={summary['counts']['output_records']}",
        f"missing_descriptions={summary['counts']['missing_descriptions']}",
        f"out={summary['output_path']}",
    )


if __name__ == "__main__":
    main()
