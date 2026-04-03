# runtime/jb_event_bus.py
#
# In-memory event bus for real-time UI updates.
# Single process, single user, no external dependencies.
#
# All JBCP mutations call emit(). The SSE endpoint
# subscribes and streams events to the frontend.

from __future__ import annotations

import asyncio
import json
from typing import Any

from runtime.jb_common import utc_now_iso
from runtime.jb_events import emit_event

_subscribers: list[asyncio.Queue] = []


def emit(event_type: str, **kwargs: Any) -> dict[str, Any]:
    """
    Emit an event to all connected SSE subscribers and the JSONL log.

    Usage:
        emit("mission.created", workspace_id="ws_123", goal="Build bot")
    """
    event = {
        "type": event_type,
        "timestamp": utc_now_iso(),
        **kwargs,
    }

    # Push to all connected subscribers
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Drop event for slow consumers

    # Also write to JSONL for durability
    emit_event(
        event_type,
        mission_id=kwargs.get("mission_id"),
        task_id=kwargs.get("task_id"),
        payload={k: v for k, v in kwargs.items()
                 if k not in ("mission_id", "task_id")},
    )

    # Also write to SQLite for queryability
    try:
        from runtime.jb_database import log_event
        log_event(event_type, **kwargs)
    except Exception:
        pass  # DB logging is best-effort

    return event


def subscribe() -> asyncio.Queue:
    """Subscribe to events. Returns a queue that receives events."""
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    """Remove a subscriber."""
    try:
        _subscribers.remove(q)
    except ValueError:
        pass


def health_check() -> dict[str, Any]:
    """Return event bus status."""
    return {"status": "running", "subscribers": len(_subscribers)}
