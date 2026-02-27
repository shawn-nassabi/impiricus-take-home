from __future__ import annotations
"""Normalization utilities for building a single canonical retrieval corpus."""

import hashlib
import json
from pathlib import Path
from typing import Any

from rag.models import CanonicalCourseDocument


def load_json_records(path: Path) -> list[dict[str, Any]]:
    """Load a JSON array from disk and keep only object-shaped records."""
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON list in {path}")
    return [item for item in payload if isinstance(item, dict)]


def normalize_source_label(raw_source: str | None) -> tuple[str, str]:
    """Return both a normalized source key and a display-friendly label."""
    source_label = (raw_source or "").strip()
    lowered = source_label.lower()
    if lowered == "cab":
        return "cab", "CAB"
    if lowered == "bulletin":
        return "bulletin", "bulletin"
    if lowered:
        return lowered, source_label
    return "unknown", "unknown"


def normalize_department(value: str | None) -> str | None:
    """Normalize department values so filter comparisons stay consistent."""
    if value is None:
        return None
    cleaned = value.strip().upper()
    return cleaned or None


def instructor_names_from_record(record: dict[str, Any]) -> list[str]:
    """Extract unique instructor names while preserving the original order."""
    instructors = record.get("instructor")
    names: list[str] = []
    seen_lower: set[str] = set()
    if isinstance(instructors, list):
        for instructor in instructors:
            if not isinstance(instructor, dict):
                continue
            name = str(instructor.get("name") or "").strip()
            lowered = name.lower()
            if name and lowered not in seen_lower:
                names.append(name)
                seen_lower.add(lowered)
    return names


def _join_non_empty(parts: list[str | None]) -> str:
    """Join only populated text parts into the final embedded document string."""
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return "\n".join(cleaned)


def _hash_id(source: str, course_code: str, title: str, text: str) -> str:
    """Create a short deterministic content hash for stable document ids."""
    digest = hashlib.sha1(f"{source}|{course_code}|{title}|{text}".encode("utf-8")).hexdigest()
    return digest[:12]


def _canonical_text(
    course_code: str,
    title: str,
    description: str | None,
    prerequisites: str | None,
    meetings: list[str],
    instructor_names: list[str],
) -> str:
    """Build the exact text used for both embeddings and sparse keyword search.

    The text is intentionally labeled line-by-line so the embedding model sees
    explicit field semantics instead of one unlabeled paragraph blob.
    """
    meetings_text = "; ".join(meetings)
    instructors_text = "; ".join(instructor_names)
    return _join_non_empty(
        [
            f"Course code: {course_code}",
            f"Title: {title}",
            f"Description: {description}" if description else None,
            f"Prerequisites: {prerequisites}" if prerequisites else None,
            f"Meetings: {meetings_text}" if meetings_text else None,
            f"Instructors: {instructors_text}" if instructors_text else None,
        ]
    )


def normalize_course_record(record: dict[str, Any]) -> CanonicalCourseDocument:
    """Map a raw CAB or bulletin record into the canonical retrieval schema."""
    source, source_label = normalize_source_label(str(record.get("source") or ""))
    course_code = str(record.get("course_code") or "").strip()
    title = str(record.get("title") or "").strip()

    description_value = record.get("description")
    description = str(description_value).strip() if isinstance(description_value, str) else None
    description = description or None

    prereq_value = record.get("prerequisites")
    prerequisites = str(prereq_value).strip() if isinstance(prereq_value, str) else None
    prerequisites = prerequisites or None

    department = normalize_department(record.get("department") if isinstance(record.get("department"), str) else None)

    meetings_raw = record.get("meetings")
    meetings = [str(item).strip() for item in meetings_raw] if isinstance(meetings_raw, list) else []
    meetings = [item for item in meetings if item]

    instructors = instructor_names_from_record(record)

    course_url = record.get("course_url")
    if not isinstance(course_url, str):
        course_url = None
    if course_url is not None:
        course_url = course_url.strip() or None

    text = _canonical_text(
        course_code=course_code,
        title=title,
        description=description,
        prerequisites=prerequisites,
        meetings=meetings,
        instructor_names=instructors,
    )

    # Including the rendered text in the hash means an id changes whenever the
    # searchable course content changes, which keeps rebuilds deterministic.
    doc_hash = _hash_id(source=source, course_code=course_code, title=title, text=text)
    doc_id = f"{source}:{course_code}:{doc_hash}"

    return CanonicalCourseDocument(
        doc_id=doc_id,
        source=source,
        source_label=source_label,
        course_code=course_code,
        title=title,
        description=description,
        prerequisites=prerequisites,
        department=department,
        instructor_names=instructors,
        meetings=meetings,
        course_url=course_url,
        text=text,
    )


def normalize_records(
    cab_records: list[dict[str, Any]],
    bulletin_records: list[dict[str, Any]],
) -> list[CanonicalCourseDocument]:
    """Normalize both sources into one unified list of canonical documents."""
    canonical: list[CanonicalCourseDocument] = []

    for record in cab_records:
        canonical.append(normalize_course_record(record))

    for record in bulletin_records:
        bulletin = dict(record)
        # Bulletin rows are intentionally padded to match the CAB-oriented schema
        # so both sources can share one index and one retrieval pipeline.
        bulletin.setdefault("department", None)
        bulletin.setdefault("prerequisites", None)
        bulletin.setdefault("meetings", [])
        bulletin.setdefault("instructor", [])
        bulletin.setdefault("course_url", None)
        canonical.append(normalize_course_record(bulletin))

    return canonical


def write_corpus_jsonl(documents: list[CanonicalCourseDocument], path: Path) -> None:
    """Persist the canonical corpus in a line-delimited JSON format."""
    lines = [json.dumps(document.to_json_dict(), ensure_ascii=True) for document in documents]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def read_corpus_jsonl(path: Path) -> list[CanonicalCourseDocument]:
    """Load the persisted canonical corpus back into memory."""
    if not path.exists():
        raise FileNotFoundError(path)

    documents: list[CanonicalCourseDocument] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            continue
        documents.append(CanonicalCourseDocument.from_json_dict(payload))
    return documents
