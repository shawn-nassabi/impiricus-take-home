from __future__ import annotations
"""Small helpers for readable, colorized backend logs."""

from typing import Any

COLOR_RESET = "\033[0m"
COLOR_CYAN = "\033[36m"
COLOR_BLUE = "\033[34m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"


def format_log(event: str, color: str, **fields: Any) -> str:
    """Build one compact, colorized log line."""
    parts = [f"{color}{event}{COLOR_RESET}"]
    for key, value in fields.items():
        parts.append(f"{key}={value!r}")
    return " ".join(parts)
