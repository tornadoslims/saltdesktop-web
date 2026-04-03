# runtime/jb_events.py

from __future__ import annotations

import json
from typing import Any

from runtime.jb_common import utc_now_iso, LOG_DIR

EVENTS_FILE = LOG_DIR / "jbcp_events.jsonl"


def _ensure_storage() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not EVENTS_FILE.exists():
        EVENTS_FILE.touch()


def emit_event(
    event_type: str,
    *,
    mission_id: str | None = None,
    task_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ensure_storage()

    event = {
        "ts": utc_now_iso(),
        "event_type": event_type,
        "mission_id": mission_id,
        "task_id": task_id,
        "payload": payload or {},
    }

    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    return event


def read_events() -> list[dict[str, Any]]:
    _ensure_storage()

    events: list[dict[str, Any]] = []
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))

    return events


def filter_events(
    *,
    mission_id: str | None = None,
    task_id: str | None = None,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    events = read_events()

    results: list[dict[str, Any]] = []
    for event in events:
        if mission_id is not None and event.get("mission_id") != mission_id:
            continue
        if task_id is not None and event.get("task_id") != task_id:
            continue
        if event_type is not None and event.get("event_type") != event_type:
            continue
        results.append(event)

    return results
