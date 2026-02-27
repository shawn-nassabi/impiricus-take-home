from __future__ import annotations

import re
from typing import Iterable

WHITESPACE_PATTERN = re.compile(r"\s+")
EMAIL_PATTERN = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)
COURSE_CODE_DEPT_PATTERN = re.compile(r"^([A-Z]{2,6})\s+\d+[A-Z]?$")


def normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = WHITESPACE_PATTERN.sub(" ", value).strip()
    return collapsed or None


def extract_email(value: str | None) -> str | None:
    cleaned = normalize_whitespace(value)
    if not cleaned:
        return None
    match = EMAIL_PATTERN.search(cleaned)
    return match.group(0) if match else None


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values:
        value = normalize_whitespace(raw)
        if not value or value in seen:
            continue
        ordered.append(value)
        seen.add(value)
    return ordered


def build_meeting_string(parts: Iterable[str]) -> str | None:
    cleaned_parts = unique_preserve_order(parts)
    if not cleaned_parts:
        return None
    return " | ".join(cleaned_parts)


def infer_department_from_course_code(course_code: str | None) -> str | None:
    cleaned = normalize_whitespace(course_code)
    if not cleaned:
        return None
    match = COURSE_CODE_DEPT_PATTERN.match(cleaned)
    if not match:
        return None
    return match.group(1)

