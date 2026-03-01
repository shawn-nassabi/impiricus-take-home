from __future__ import annotations
"""Utilities for parsing and filtering course meeting time strings."""

import re
from dataclasses import dataclass
from datetime import time

_DAY_CODE_PATTERN = re.compile(r"^((?:M|T(?!h)|Th|W|F|S(?!u)|Su)+)\s+", re.IGNORECASE)

_INDIVIDUAL_DAY = re.compile(r"Th|Su|[MTWFS]", re.IGNORECASE)

_TIME_RANGE_PATTERN = re.compile(
    r"(\d{1,2}(?::\d{2})?)\s*(am?|pm?)?\s*[-–]\s*(\d{1,2}(?::\d{2})?)\s*(am?|pm?)?",
    re.IGNORECASE,
)

DAY_CODE_MAP = {
    "M": "Monday",
    "T": "Tuesday",
    "W": "Wednesday",
    "Th": "Thursday",
    "F": "Friday",
    "S": "Saturday",
    "Su": "Sunday",
}

DAY_ALIASES: dict[str, list[str]] = {
    "monday": ["M"],
    "tuesday": ["T"],
    "wednesday": ["W"],
    "thursday": ["Th"],
    "friday": ["F"],
    "saturday": ["S"],
    "sunday": ["Su"],
    "m": ["M"],
    "t": ["T"],
    "w": ["W"],
    "th": ["Th"],
    "f": ["F"],
    "mwf": ["M", "W", "F"],
    "tth": ["T", "Th"],
    "mw": ["M", "W"],
}


@dataclass(frozen=True)
class ParsedMeeting:
    """Structured representation of a single meeting time string."""

    days: list[str]
    start_time: time | None
    end_time: time | None
    raw: str


def parse_meeting_time(meeting_str: str) -> ParsedMeeting | None:
    """Parse a meeting string like 'TTh 1pm-2:20pm' into structured data.

    Also handles pipe-delimited CAB section strings such as
    ``"202510 | Section S01 | TTh 1-2:20p | F. Hamlin"`` by extracting
    the day/time component from the third field.

    Returns None for unparseable strings (TBA, online-only, date ranges).
    """
    s = meeting_str.strip()
    if not s:
        return None

    if s.lower() in ("tba", "tbd", "course offered online"):
        return None
    if s.startswith("("):
        return None

    if "|" in s:
        parts = [p.strip() for p in s.split("|")]
        if len(parts) >= 3:
            time_component = parts[2]
            if time_component.lower() in ("tba", "course offered online", "see details"):
                return None
            s = time_component
        else:
            return None

    day_match = _DAY_CODE_PATTERN.match(s)
    if not day_match:
        return None

    day_block = day_match.group(1)
    days = _INDIVIDUAL_DAY.findall(day_block)
    days = [_normalize_day_code(d) for d in days]

    remainder = s[day_match.end():]
    time_match = _TIME_RANGE_PATTERN.search(remainder)
    start_time = None
    end_time = None

    if time_match:
        start_raw = time_match.group(1)
        start_meridiem = (time_match.group(2) or "").lower()
        end_raw = time_match.group(3)
        end_meridiem = (time_match.group(4) or "").lower()

        if not start_meridiem and end_meridiem:
            start_meridiem = end_meridiem

        start_time = _parse_time_component(start_raw, start_meridiem)
        end_time = _parse_time_component(end_raw, end_meridiem)

    return ParsedMeeting(days=days, start_time=start_time, end_time=end_time, raw=s)


def _normalize_day_code(code: str) -> str:
    """Normalize day codes to canonical form (M, T, W, Th, F, S, Su)."""
    upper = code[0].upper() + code[1:].lower() if len(code) > 1 else code.upper()
    if upper in DAY_CODE_MAP:
        return upper
    return code.upper()


def _normalize_meridiem(raw: str) -> str:
    """Normalize short meridiem markers ('a'->'am', 'p'->'pm')."""
    low = raw.lower()
    if low.startswith("p"):
        return "pm"
    if low.startswith("a"):
        return "am"
    return low


def _parse_time_component(raw: str, meridiem: str) -> time | None:
    """Parse a time like '1:30' with meridiem 'pm' into a time object."""
    if not raw:
        return None

    if meridiem:
        meridiem = _normalize_meridiem(meridiem)

    parts = raw.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return None

    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    return time(hour=hour, minute=minute)


def parse_user_time(raw: str) -> time | None:
    """Parse a user-provided time string into a time object.

    Accepts formats like '3 PM', '3:00 PM', '15:00', '3pm', '3p'.
    """
    s = raw.strip()
    if not s:
        return None

    m = re.match(
        r"(\d{1,2})(?::(\d{2}))?\s*(am?|pm?)?$",
        s,
        re.IGNORECASE,
    )
    if not m:
        return None

    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    meridiem = _normalize_meridiem(m.group(3)) if m.group(3) else ""

    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    return time(hour=hour, minute=minute)


def normalize_day_filter(raw: str) -> list[str]:
    """Convert a user-provided day string into canonical day codes.

    Accepts: 'F', 'Friday', 'MWF', 'TTh', etc.
    """
    s = raw.strip().lower()
    if s in DAY_ALIASES:
        return DAY_ALIASES[s]
    codes = _INDIVIDUAL_DAY.findall(raw.strip())
    return [_normalize_day_code(c) for c in codes] if codes else []


def matches_schedule_filter(
    meetings: list[str],
    day: str | None = None,
    after_time: str | None = None,
    before_time: str | None = None,
) -> bool:
    """Check if any meeting in the list matches the given schedule constraints.

    - day: matches if the meeting occurs on any of the specified day(s)
    - after_time: matches if the meeting starts at or after this time
    - before_time: matches if the meeting starts at or before this time
    """
    target_days: list[str] | None = None
    if day:
        target_days = normalize_day_filter(day)
        if not target_days:
            return False

    target_after: time | None = None
    if after_time:
        target_after = parse_user_time(after_time)

    target_before: time | None = None
    if before_time:
        target_before = parse_user_time(before_time)

    for meeting_str in meetings:
        parsed = parse_meeting_time(meeting_str)
        if parsed is None:
            continue

        if target_days and not any(d in parsed.days for d in target_days):
            continue

        if target_after and parsed.start_time and parsed.start_time < target_after:
            continue

        if target_before and parsed.start_time and parsed.start_time > target_before:
            continue

        return True

    return False
