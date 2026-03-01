from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CHECKPOINT = {
    "discovered_urls": [],
    "completed_urls": [],
    "failed_urls": {},
    "detail_targets": {},
}


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
    temp_path.replace(path)


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_checkpoint(path: Path) -> dict[str, Any]:
    existing = read_json(path)
    if not isinstance(existing, dict):
        return DEFAULT_CHECKPOINT.copy()

    checkpoint = DEFAULT_CHECKPOINT.copy()
    checkpoint.update(existing)
    checkpoint["discovered_urls"] = list(checkpoint.get("discovered_urls", []))
    checkpoint["completed_urls"] = list(checkpoint.get("completed_urls", []))
    checkpoint["failed_urls"] = dict(checkpoint.get("failed_urls", {}))
    checkpoint["detail_targets"] = dict(checkpoint.get("detail_targets", {}))
    return checkpoint


def save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    atomic_write_json(path, checkpoint)
