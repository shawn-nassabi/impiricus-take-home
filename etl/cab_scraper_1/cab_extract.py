from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from etl.cab_scraper_1.cab_normalize import (
    build_meeting_string,
    extract_email,
    infer_department_from_course_code,
    normalize_whitespace,
    unique_preserve_order,
)
from etl.types import CabCourseRecord, CabInstructor

COURSE_CODE_SELECTORS = [
    ".dtl-course-code",
]
TITLE_SELECTORS = [
    ".text.col-8.detail-title.text--huge",
    ".detail-title",
    "h1",
]
DESCRIPTION_SELECTORS = [
    ".section--description",
    ".course-description",
    ".description",
]
MEETING_SELECTORS = [
    ".meet",
    ".meeting",
    ".meeting-times",
]
SECTION_HEADINGS = {
    "registration restrictions",
    "course description",
    "description",
    "meeting times",
    "instructors",
}
INSTRUCTOR_SPLIT_PATTERN = re.compile(r"\s*(?:,|;| and )\s*")


def parse_course_html(html: str, course_url: str) -> CabCourseRecord:
    soup = BeautifulSoup(html, "html.parser")

    course_code = first_text_for_selectors(soup, COURSE_CODE_SELECTORS) or ""
    title = first_text_for_selectors(soup, TITLE_SELECTORS) or ""
    instructors = extract_instructors(soup)
    meetings = extract_meetings(soup)
    prerequisites = extract_registration_restrictions(soup)
    description = extract_description(soup)
    department = extract_department(soup) or infer_department_from_course_code(course_code)

    return CabCourseRecord(
        course_code=course_code,
        title=title,
        instructor=instructors,
        meetings=meetings,
        prerequisites=prerequisites,
        department=department,
        description=description,
        source="CAB",
        course_url=course_url,
    )


def parse_course_payload(payload: dict[str, Any], course_url: str) -> CabCourseRecord:
    course_code = normalize_whitespace(payload.get("code") if isinstance(payload.get("code"), str) else "") or ""
    title = normalize_whitespace(payload.get("title") if isinstance(payload.get("title"), str) else "") or ""
    description = html_fragment_to_text(payload.get("description"))
    prerequisites = html_fragment_to_text(payload.get("registration_restrictions"))
    department = (
        normalize_whitespace(payload.get("subject") if isinstance(payload.get("subject"), str) else "")
        or normalize_whitespace(payload.get("dept") if isinstance(payload.get("dept"), str) else "")
        or infer_department_from_course_code(course_code)
    )

    instructors = extract_instructors_from_payload(payload)
    meetings = extract_meetings_from_payload(payload)

    return CabCourseRecord(
        course_code=course_code,
        title=title,
        instructor=instructors,
        meetings=meetings,
        prerequisites=prerequisites,
        department=department,
        description=description,
        source="CAB",
        course_url=course_url,
    )


def first_text_for_selectors(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            value = normalize_whitespace(node.get_text(" ", strip=True))
            if value:
                return value
    return None


def extract_instructors(soup: BeautifulSoup) -> list[CabInstructor]:
    instructor_blocks = soup.select(".instructor")
    instructors: list[CabInstructor] = []
    seen: set[tuple[str, str | None]] = set()

    for block in instructor_blocks:
        names = [normalize_whitespace(node.get_text(" ", strip=True)) for node in block.select(".instructor-name")]
        names = [name for name in names if name]

        emails = [extract_email(node.get_text(" ", strip=True)) for node in block.select(".truncate")]
        emails = [email for email in emails if email]

        if not names:
            fallback_name = normalize_whitespace(block.get_text(" ", strip=True))
            if fallback_name:
                names = [fallback_name]

        if not names:
            continue

        for index, name in enumerate(names):
            email = emails[index] if index < len(emails) else (emails[0] if emails else None)
            key = (name, email)
            if key in seen:
                continue
            seen.add(key)
            instructors.append(CabInstructor(name=name, email=email))

    return instructors


def extract_instructors_from_payload(payload: dict[str, Any]) -> list[CabInstructor]:
    html = payload.get("instructordetail_html")
    instructors: list[CabInstructor] = []

    if isinstance(html, str) and html.strip():
        soup = BeautifulSoup(f"<div>{html}</div>", "html.parser")
        instructors.extend(extract_instructors(soup))
        if not instructors:
            raw_text = normalize_whitespace(soup.get_text(" ", strip=True))
            if raw_text:
                for name in split_instructor_names(raw_text):
                    instructors.append(CabInstructor(name=name, email=None))

    # Fall back to section-level instructor strings if detail HTML is absent.
    for section in payload.get("allInGroup", []) or []:
        if not isinstance(section, dict):
            continue
        instr_text = normalize_whitespace(section.get("instr") if isinstance(section.get("instr"), str) else "")
        if not instr_text:
            continue
        for name in split_instructor_names(instr_text):
            instructor = CabInstructor(name=name, email=None)
            if instructor not in instructors:
                instructors.append(instructor)

    return instructors


def split_instructor_names(raw_text: str) -> list[str]:
    names: list[str] = []
    for chunk in INSTRUCTOR_SPLIT_PATTERN.split(raw_text):
        name = normalize_whitespace(chunk)
        if not name:
            continue
        if name.lower() in {"tbd", "team"}:
            continue
        names.append(name)
    return unique_preserve_order(names)


def extract_meetings(soup: BeautifulSoup) -> list[str]:
    meetings: list[str] = []
    nodes = list(meeting_nodes(soup))
    for node in nodes:
        meetings.extend(meeting_strings_from_node(node))

    if meetings:
        return unique_preserve_order(meetings)

    # Fallback for pages where meetings are rendered outside `.meet` blocks.
    meeting_heading = find_heading_text(soup, {"meeting times", "scheduled meeting times", "meetings"})
    if not meeting_heading:
        return []

    fallback_text = collect_section_text(meeting_heading, limit=12)
    fallback_lines = [normalize_whitespace(line) for line in fallback_text.split("\n")]
    return unique_preserve_order(line for line in fallback_lines if line)


def extract_meetings_from_payload(payload: dict[str, Any]) -> list[str]:
    meetings: list[str] = []

    for section in payload.get("allInGroup", []) or []:
        if not isinstance(section, dict):
            continue
        parts = []
        section_no = normalize_whitespace(section.get("no") if isinstance(section.get("no"), str) else "")
        meets = normalize_whitespace(section.get("meets") if isinstance(section.get("meets"), str) else "")
        instr = normalize_whitespace(section.get("instr") if isinstance(section.get("instr"), str) else "")
        term = normalize_whitespace(section.get("srcdb") if isinstance(section.get("srcdb"), str) else "")
        if term:
            parts.append(term)
        if section_no:
            parts.append(f"Section {section_no}")
        if meets:
            parts.append(meets)
        if instr:
            parts.append(instr)
        meeting = build_meeting_string(parts)
        if meeting:
            meetings.append(meeting)

    meeting_html = payload.get("meeting_html")
    if isinstance(meeting_html, str) and meeting_html.strip():
        meetings.extend(extract_meeting_strings_from_fragment(meeting_html))

    return unique_preserve_order(meetings)


def extract_meeting_strings_from_fragment(html: str) -> list[str]:
    soup = BeautifulSoup(f"<div>{html}</div>", "html.parser")
    meetings: list[str] = []

    rows = soup.select("tr")
    if rows:
        for row in rows:
            if row.select("th") and not row.select("td"):
                continue
            cells = [
                normalize_whitespace(cell.get_text(" ", strip=True))
                for cell in row.select("th,td")
            ]
            meeting = build_meeting_string(cell for cell in cells if cell)
            if meeting:
                meetings.append(meeting)
        if meetings:
            return unique_preserve_order(meetings)

    list_items = soup.select("li")
    if list_items:
        for item in list_items:
            line = normalize_whitespace(item.get_text(" ", strip=True))
            if line:
                meetings.append(line)
        if meetings:
            return unique_preserve_order(meetings)

    text = soup.get_text("\n", strip=True)
    lines = [normalize_whitespace(line) for line in text.split("\n")]
    return unique_preserve_order(line for line in lines if line)


def meeting_nodes(soup: BeautifulSoup) -> Iterable[Tag]:
    seen: set[int] = set()
    for selector in MEETING_SELECTORS:
        for node in soup.select(selector):
            ident = id(node)
            if ident not in seen:
                seen.add(ident)
                yield node


def meeting_strings_from_node(node: Tag) -> list[str]:
    meetings: list[str] = []
    # Prefer explicit rows if present.
    rows = node.select("tr")
    if rows:
        for row in rows:
            if row.select("th") and not row.select("td"):
                continue
            parts = []
            for cell in row.select("th,td"):
                cell_text = normalize_whitespace(cell.get_text(" ", strip=True))
                if cell_text:
                    parts.append(cell_text)
            meeting_string = build_meeting_string(parts)
            if meeting_string:
                meetings.append(meeting_string)
        return unique_preserve_order(meetings)

    # Some pages use list items for each meeting.
    list_items = node.select("li")
    if list_items:
        for item in list_items:
            line = normalize_whitespace(item.get_text(" ", strip=True))
            if line:
                meetings.append(line)
        return unique_preserve_order(meetings)

    # General fallback: preserve chunk text lines.
    raw = node.get_text("\n", strip=True)
    lines = [normalize_whitespace(line) for line in raw.split("\n")]
    return unique_preserve_order(line for line in lines if line)


def extract_registration_restrictions(soup: BeautifulSoup) -> str | None:
    heading = find_heading_text(soup, {"registration restrictions"})
    if not heading:
        return None
    text = collect_section_text(heading)
    return normalize_whitespace(text)


def html_fragment_to_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    soup = BeautifulSoup(f"<div>{cleaned}</div>", "html.parser")
    text = normalize_whitespace(soup.get_text(" ", strip=True))
    return text


def extract_description(soup: BeautifulSoup) -> str | None:
    description = first_text_for_selectors(soup, DESCRIPTION_SELECTORS)
    if description:
        return description

    heading = find_heading_text(soup, {"course description", "description"})
    if not heading:
        return None
    text = collect_section_text(heading, limit=8)
    return normalize_whitespace(text)


def extract_department(soup: BeautifulSoup) -> str | None:
    candidates = [
        extract_labeled_value(soup, "department"),
        extract_labeled_value(soup, "subject"),
    ]
    for value in candidates:
        normalized = normalize_whitespace(value)
        if normalized:
            return normalized
    return None


def extract_labeled_value(soup: BeautifulSoup, label: str) -> str | None:
    lowered = label.lower()
    label_nodes = soup.find_all(
        lambda tag: isinstance(tag, Tag)
        and tag.name in {"dt", "th", "strong", "span", "div", "label"}
        and normalize_whitespace(tag.get_text(" ", strip=True)) is not None
        and normalize_whitespace(tag.get_text(" ", strip=True)).lower().rstrip(":") == lowered
    )
    for node in label_nodes:
        if node.name in {"dt", "th"}:
            sibling = node.find_next_sibling(["dd", "td"])
            if sibling:
                value = normalize_whitespace(sibling.get_text(" ", strip=True))
                if value:
                    return value

        sibling = node.find_next_sibling()
        if sibling:
            value = normalize_whitespace(sibling.get_text(" ", strip=True))
            if value and value.lower().rstrip(":") != lowered:
                return value

        parent = node.parent
        if parent:
            text_parts = [normalize_whitespace(part) for part in parent.stripped_strings]
            text_parts = [part for part in text_parts if part]
            if len(text_parts) >= 2:
                candidate = text_parts[1]
                if candidate.lower().rstrip(":") != lowered:
                    return candidate

    return None


def find_heading_text(soup: BeautifulSoup, names: set[str]) -> Tag | None:
    normalized_names = {name.lower() for name in names}
    heading_tags = ("h1", "h2", "h3", "h4", "h5", "h6", "strong", "b")
    for node in soup.find_all(heading_tags):
        text = normalize_whitespace(node.get_text(" ", strip=True))
        if not text:
            continue
        lowered = text.lower().rstrip(":")
        if lowered in normalized_names:
            return node
    return None


def collect_section_text(heading: Tag, limit: int = 10) -> str:
    chunks: list[str] = []
    cursor: Any = heading
    steps = 0
    while steps < limit:
        cursor = cursor.next_sibling
        if cursor is None:
            break
        steps += 1

        if isinstance(cursor, NavigableString):
            value = normalize_whitespace(str(cursor))
            if value:
                chunks.append(value)
            continue

        if not isinstance(cursor, Tag):
            continue

        heading_text = normalize_whitespace(cursor.get_text(" ", strip=True))
        if cursor.name in {"h1", "h2", "h3", "h4", "h5", "h6"} and heading_text:
            break

        lowered = (heading_text or "").lower().rstrip(":")
        if lowered in SECTION_HEADINGS:
            break

        value = normalize_whitespace(cursor.get_text(" ", strip=True))
        if value:
            chunks.append(value)

    return "\n".join(chunks)
