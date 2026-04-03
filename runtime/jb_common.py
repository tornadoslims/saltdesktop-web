# runtime/jb_common.py
#
# Shared utilities for all JBCP runtime modules.
# Single source of truth for paths, timestamps, and JSON storage.

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(ts: str | None) -> datetime | None:
    """Parse ISO timestamp string to datetime, returns None on failure."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def age_seconds(ts: str | None) -> float:
    """Return age in seconds from an ISO timestamp, or infinity if missing."""
    dt = parse_iso(ts)
    if dt is None:
        return float("inf")
    return (datetime.now(timezone.utc) - dt).total_seconds()


class JsonStore:
    """Simple JSON list file store. Handles ensure/load/save for any module."""

    def __init__(self, file_path: Path, parent_dir: Path | None = None):
        self.file_path = file_path
        self.parent_dir = parent_dir or file_path.parent

    def ensure(self) -> None:
        self.parent_dir.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text("[]", encoding="utf-8")

    def load(self) -> list[dict[str, Any]]:
        self.ensure()
        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"File must contain a JSON list: {self.file_path}")
        return data

    def save(self, data: list[dict[str, Any]]) -> None:
        self.ensure()
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
