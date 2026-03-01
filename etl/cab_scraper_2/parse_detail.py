from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

_WHITESPACE = re.compile(r"\s+")
_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_DEPT_FROM_CODE = re.compile(r"^([A-Z]{2,6})\s+\d")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _WHITESPACE.sub(" ", text).strip()


def _strip_html(html: str) -> str:
    """Strip all HTML tags and return plain text."""
    soup = BeautifulSoup(html, "html.parser")
    return _clean(soup.get_text(" ", strip=True))


def _extract_email(text: str) -> str | None:
    match = _EMAIL.search(text)
    return match.group(0) if match else None


def parse_detail_json(
    detail: dict[str, Any],
    search_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured course record from a FOSE ``details`` response.

    The FOSE detail route returns a JSON object with dedicated fields rather
    than a single HTML blob.  Notable fields used here:

    - ``code``                   — course code string  (e.g. ``"CSCI 0150"``)
    - ``title``                  — course title (plain text)
    - ``description``            — course description (plain text)
    - ``registration_restrictions`` — prerequisites HTML
    - ``meeting_html``           — meeting-times HTML
    - ``instructordetail_html``  — instructor HTML

    Falls back to ``search_summary`` values for anything missing.
    """
    summary = search_summary or {}

    course_code = _clean(detail.get("code") or summary.get("code") or "")
    title = _clean(detail.get("title") or summary.get("title") or "")
    description = _clean(detail.get("description") or "")
    prerequisites = _parse_prerequisites(detail.get("registration_restrictions") or "")
    meeting_times = _parse_meetings(
        detail.get("meeting_html") or "",
        summary,
    )
    instructor = _parse_instructors(
        detail.get("instructordetail_html") or "",
        summary,
    )
    department = _infer_department(course_code)

    return {
        "course_code": course_code,
        "title": title,
        "instructor": instructor,
        "meeting_times": meeting_times,
        "prerequisites": prerequisites,
        "description": description,
        "department": department,
        "source": "CAB",
        "crn": str(detail.get("crn") or summary.get("crn") or ""),
        "srcdb": str(detail.get("srcdb") or summary.get("srcdb") or ""),
    }


# ------------------------------------------------------------------
# Field parsers
# ------------------------------------------------------------------


def _parse_prerequisites(html: str) -> str | None:
    if not html or not html.strip():
        return None
    text = _strip_html(html)
    return text or None


def _parse_meetings(html: str, summary: dict[str, Any]) -> list[str]:
    """Extract meeting time strings from the ``meeting_html`` fragment."""
    meetings: list[str] = []

    if html and html.strip():
        soup = BeautifulSoup(html, "html.parser")

        # Each .meet div may contain a table or plain text.
        for meet_block in soup.select(".meet"):
            rows = meet_block.select("tr")
            if rows:
                for row in rows:
                    # Skip header-only rows.
                    if row.select("th") and not row.select("td"):
                        continue
                    parts = [
                        _clean(cell.get_text(" ", strip=True))
                        for cell in row.select("th, td")
                        if _clean(cell.get_text(" ", strip=True))
                    ]
                    if parts:
                        meetings.append(" | ".join(parts))
            else:
                text = _clean(meet_block.get_text(" ", strip=True))
                if text:
                    meetings.append(text)

    # Fall back to search summary's ``meets`` field (e.g. "TTh 2:30-3:50pm").
    if not meetings:
        raw = _clean(summary.get("meets") or summary.get("meet") or "")
        if raw and raw.upper() not in {"TBA", ""}:
            meetings.append(raw)

    return _dedupe(meetings)


def _parse_instructors(
    html: str, summary: dict[str, Any]
) -> list[dict[str, str | None]]:
    """Extract instructor name/email pairs from ``instructordetail_html``."""
    instructors: list[dict[str, str | None]] = []
    seen: set[str] = set()

    if html and html.strip():
        soup = BeautifulSoup(html, "html.parser")

        for block in soup.select(".instructor"):
            names = [
                _clean(n.get_text(" ", strip=True))
                for n in block.select(".instructor-name")
                if _clean(n.get_text(" ", strip=True))
            ]
            emails: list[str | None] = [
                _extract_email(_clean(a.get("href", "") or a.get_text()))
                for a in block.select("a[href^='mailto:']")
            ]
            # Strip the "mailto:" prefix if present in href.
            emails = [
                e.replace("mailto:", "") if e and e.startswith("mailto:") else e
                for e in emails
            ]

            if not names:
                fallback = _clean(block.get_text(" ", strip=True))
                if fallback and fallback.upper() not in {"TBD", "STAFF", "TEAM"}:
                    names = [fallback]

            for i, name in enumerate(names):
                if name.upper() in {"TBD", "STAFF", "TEAM"}:
                    continue
                if name in seen:
                    continue
                seen.add(name)
                email = emails[i] if i < len(emails) else (emails[0] if emails else None)
                instructors.append({"name": name, "email": email})

    # Fall back to search summary instructor string.
    if not instructors:
        raw = _clean(summary.get("instr") or "")
        if raw and raw.upper() not in {"TBD", "STAFF", "TEAM", ""}:
            instructors.append({"name": raw, "email": None})

    return instructors


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _infer_department(course_code: str) -> str | None:
    match = _DEPT_FROM_CODE.match(course_code.strip())
    return match.group(1) if match else None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
