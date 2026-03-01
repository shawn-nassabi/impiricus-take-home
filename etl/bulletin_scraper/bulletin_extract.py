from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from etl.cab_normalize import normalize_whitespace
from etl.types import BulletinCourseRecord

COURSES_HEADING_PATTERN = re.compile(r"^courses[:\s]*$", re.IGNORECASE)
COURSE_LISTING_PATTERN = re.compile(
    r"^([A-Z]{2,6}\s+\d{3,5}[A-Z]?)\.\s+(.+?)\.?\s*$"
)
PAGE_NUMBER_PATTERN = re.compile(r"^\d+$")
PAGE_LABEL_PATTERN = re.compile(r"^page\s+\d+$", re.IGNORECASE)
BULLETIN_HEADER_PATTERN = re.compile(r"brown university.*bulletin", re.IGNORECASE)


def parse_bulletin_pdf(pdf_path: Path) -> list[BulletinCourseRecord]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Bulletin PDF not found: {pdf_path}")
    lines = extract_pdf_lines(pdf_path)
    return parse_bulletin_lines(lines)


def extract_pdf_lines(pdf_path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for bulletin extraction.") from exc

    reader = PdfReader(str(pdf_path))
    lines: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        for raw_line in page_text.splitlines():
            line = normalize_whitespace(raw_line)
            if not line or is_noise_line(line):
                continue
            lines.append(line)
    return lines


def parse_bulletin_lines(lines: Iterable[str]) -> list[BulletinCourseRecord]:
    records: list[BulletinCourseRecord] = []
    in_courses_section = False
    parsed_course_in_section = False
    active_code: str | None = None
    active_title: str | None = None
    active_description_lines: list[str] = []

    def flush_active() -> None:
        nonlocal active_code, active_title, active_description_lines
        if not active_code or not active_title:
            return
        description = normalize_whitespace(" ".join(active_description_lines))
        records.append(
            BulletinCourseRecord(
                course_code=active_code,
                title=active_title,
                description=description or "No description available.",
            )
        )
        active_code = None
        active_title = None
        active_description_lines = []

    for raw_line in lines:
        line = normalize_whitespace(raw_line)
        if not line or is_noise_line(line):
            continue

        if is_courses_heading(line):
            flush_active()
            in_courses_section = True
            parsed_course_in_section = False
            continue

        if not in_courses_section:
            continue

        listing_match = COURSE_LISTING_PATTERN.match(line)
        if listing_match:
            flush_active()
            active_code = listing_match.group(1)
            active_title = normalize_title(listing_match.group(2))
            parsed_course_in_section = True
            continue

        if should_end_courses_section(line, parsed_course_in_section):
            flush_active()
            in_courses_section = False
            parsed_course_in_section = False
            continue

        if active_code:
            active_description_lines.append(line)

    flush_active()
    return records


def is_noise_line(line: str) -> bool:
    if PAGE_NUMBER_PATTERN.match(line):
        return True
    if PAGE_LABEL_PATTERN.match(line):
        return True
    if BULLETIN_HEADER_PATTERN.search(line):
        return True
    return False


def is_courses_heading(line: str) -> bool:
    return bool(COURSES_HEADING_PATTERN.match(line))


def should_end_courses_section(line: str, parsed_course_in_section: bool) -> bool:
    if not parsed_course_in_section:
        return False
    if line.endswith(":"):
        return True
    if "." in line:
        return False
    if any(char.isdigit() for char in line):
        return False
    words = [word for word in line.split() if word]
    if not words:
        return False
    if line.isupper() and len(words) <= 10:
        return True
    return is_title_case_heading(line)


def is_title_case_heading(line: str) -> bool:
    words = [word.strip("()[]&,/-") for word in line.split()]
    words = [word for word in words if word]
    if len(words) < 2 or len(words) > 5:
        return False
    for word in words:
        if not word[0].isalpha():
            return False
        if not word[0].isupper():
            return False
        tail = word[1:]
        if tail and any(char.isalpha() and not char.islower() for char in tail):
            return False
    return True


def normalize_title(title: str) -> str:
    cleaned = normalize_whitespace(title) or ""
    return cleaned.rstrip(".")
