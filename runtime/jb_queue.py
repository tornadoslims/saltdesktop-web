# runtime/jb_queue.py

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from uuid import uuid4

from runtime.jb_common import utc_now_iso, DATA_DIR, JsonStore
from runtime.jb_database import get_db, init_db, _json_dumps, _json_loads

QUEUE_FILE = DATA_DIR / "jb_queue.json"
_store = JsonStore(QUEUE_FILE)

VALID_STATUSES = {"pending", "dispatched", "running", "in_progress", "complete", "failed", "suspect", "needs_review"}



def _normalize_origin(origin: Any) -> dict[str, Any]:
    if origin is None:
        return {
            "surface": None,
            "session_id": None,
            "thread_id": None,
        }
    if not isinstance(origin, dict):
        raise ValueError("Task origin must be a dictionary or null")

    return {
        "surface": origin.get("surface"),
        "session_id": origin.get("session_id"),
        "thread_id": origin.get("thread_id"),
    }


def _normalize_delivery(delivery: Any) -> dict[str, Any]:
    if delivery is None:
        return {
            "mode": "reply_to_origin",
        }
    if not isinstance(delivery, dict):
        raise ValueError("Task delivery must be a dictionary or null")

    return {
        "mode": delivery.get("mode", "reply_to_origin"),
    }


def _normalize_external_process(external_process: Any) -> dict[str, Any] | None:
    if external_process is None:
        return None
    if not isinstance(external_process, dict):
        raise ValueError("external_process must be a dictionary or null")

    return {
        "type": external_process.get("type"),
        "pid": external_process.get("pid"),
        "status": external_process.get("status"),
        "started_at": external_process.get("started_at"),
        "last_seen": external_process.get("last_seen"),
    }


def _validate_task(task: dict[str, Any]) -> None:
    """Validate task fields, raising ValueError on problems."""
    payload = task.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("Task payload must be a dictionary")

    status = task.get("status", "pending")
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid task status '{status}'. "
            f"Valid statuses: {sorted(VALID_STATUSES)}"
        )


def _normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    """Build a normalized task dict from raw data."""
    now = utc_now_iso()

    created_at = task.get("created_at") or now
    updated_at = task.get("updated_at") or now

    payload = deepcopy(task.get("payload", {}))
    if not isinstance(payload, dict):
        raise ValueError("Task payload must be a dictionary")

    normalized = {
        "id": task.get("id") or str(uuid4()),
        "company_id": task.get("company_id"),
        "mission_id": task.get("mission_id"),
        "type": task.get("type", "unknown"),
        "status": task.get("status", "pending"),
        "priority": int(task.get("priority", 5)),
        "assigned_to": task.get("assigned_to"),
        "retry_count": int(task.get("retry_count", 0)),
        "max_retries": int(task.get("max_retries", 3)),
        "error": task.get("error"),
        "created_at": created_at,
        "updated_at": updated_at,
        "origin": _normalize_origin(task.get("origin")),
        "delivery": _normalize_delivery(task.get("delivery")),
        "openclaw_session_id": task.get("openclaw_session_id"),
        "parent_session_id": task.get("parent_session_id"),
        "subagent_session_id": task.get("subagent_session_id"),
        "external_process": _normalize_external_process(task.get("external_process")),
        "payload": payload,
    }

    if normalized["status"] not in VALID_STATUSES:
        raise ValueError(
            f"Invalid task status '{normalized['status']}'. "
            f"Valid statuses: {sorted(VALID_STATUSES)}"
        )

    return normalized


def _row_to_task(row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a task dict, parsing JSON fields."""
    d = dict(row)
    d["origin"] = _json_loads(d.get("origin")) or {"surface": None, "session_id": None, "thread_id": None}
    d["delivery"] = _json_loads(d.get("delivery")) or {"mode": "reply_to_origin"}
    d["external_process"] = _json_loads(d.get("external_process"))
    d["payload"] = _json_loads(d.get("payload")) or {}
    return d


def list_tasks() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks").fetchall()
    return [_row_to_task(r) for r in rows]


def get_task(task_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    return _row_to_task(row)


def enqueue(task: dict[str, Any]) -> str:
    _validate_task(task)

    normalized = _normalize_task(task)
    now = utc_now_iso()
    normalized["created_at"] = now
    normalized["updated_at"] = now

    with get_db() as conn:
        conn.execute(
            """INSERT INTO tasks
               (id, company_id, mission_id, type, status, priority,
                assigned_to, retry_count, max_retries, error,
                created_at, updated_at, origin, delivery,
                openclaw_session_id, parent_session_id, subagent_session_id,
                external_process, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (normalized["id"], normalized["company_id"], normalized["mission_id"],
             normalized["type"], normalized["status"], normalized["priority"],
             normalized["assigned_to"], normalized["retry_count"], normalized["max_retries"],
             normalized["error"],
             normalized["created_at"], normalized["updated_at"],
             _json_dumps(normalized["origin"]),
             _json_dumps(normalized["delivery"]),
             normalized["openclaw_session_id"], normalized["parent_session_id"],
             normalized["subagent_session_id"],
             _json_dumps(normalized["external_process"]),
             _json_dumps(normalized["payload"])),
        )
    return normalized["id"]


def get_pending() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY priority DESC, created_at ASC"
        ).fetchall()
    return [_row_to_task(r) for r in rows]


def get_dispatched() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks WHERE status = 'dispatched'").fetchall()
    return [_row_to_task(r) for r in rows]


def get_running() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks WHERE status = 'running'").fetchall()
    return [_row_to_task(r) for r in rows]


def _update_task(task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")

    merged = {**task, **updates}
    normalized = _normalize_task(merged)

    normalized["id"] = task["id"]
    normalized["created_at"] = task["created_at"]
    normalized["updated_at"] = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """UPDATE tasks SET
               company_id = ?, mission_id = ?, type = ?, status = ?,
               priority = ?, assigned_to = ?, retry_count = ?, max_retries = ?,
               error = ?, updated_at = ?, origin = ?, delivery = ?,
               openclaw_session_id = ?, parent_session_id = ?, subagent_session_id = ?,
               external_process = ?, payload = ?
               WHERE id = ?""",
            (normalized["company_id"], normalized["mission_id"],
             normalized["type"], normalized["status"], normalized["priority"],
             normalized["assigned_to"], normalized["retry_count"], normalized["max_retries"],
             normalized["error"], normalized["updated_at"],
             _json_dumps(normalized["origin"]),
             _json_dumps(normalized["delivery"]),
             normalized["openclaw_session_id"], normalized["parent_session_id"],
             normalized["subagent_session_id"],
             _json_dumps(normalized["external_process"]),
             _json_dumps(normalized["payload"]),
             task_id),
        )

    return get_task(task_id)


def mark_dispatched(task_id: str, assigned_to: str | None = None) -> dict[str, Any]:
    updates: dict[str, Any] = {"status": "dispatched"}
    if assigned_to is not None:
        updates["assigned_to"] = assigned_to
    return _update_task(task_id, updates)


def mark_running(task_id: str) -> dict[str, Any]:
    return _update_task(task_id, {"status": "running"})


def mark_in_progress(task_id: str, assigned_to: str | None = None) -> dict[str, Any]:
    updates: dict[str, Any] = {"status": "in_progress"}
    if assigned_to is not None:
        updates["assigned_to"] = assigned_to
    return _update_task(task_id, updates)


def mark_complete(task_id: str) -> dict[str, Any]:
    return _update_task(
        task_id,
        {
            "status": "complete",
            "error": None,
        },
    )


def mark_failed(task_id: str, error: str | None = None, increment_retry: bool = True) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")

    retry_count = int(task.get("retry_count", 0))
    if increment_retry:
        retry_count += 1

    return _update_task(
        task_id,
        {
            "status": "failed",
            "error": error,
            "retry_count": retry_count,
        },
    )


def get_retryable() -> list[dict[str, Any]]:
    """Get failed tasks that haven't exceeded max_retries."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'failed' AND retry_count < max_retries"
        ).fetchall()
    return [_row_to_task(r) for r in rows]


def retry_task(task_id: str) -> dict[str, Any]:
    """Move a failed task back to pending for another attempt."""
    task = get_task(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")
    if task["status"] != "failed":
        raise ValueError(f"Can only retry failed tasks, got: {task['status']}")
    if task["retry_count"] >= task.get("max_retries", 3):
        raise ValueError(f"Task has exhausted retries ({task['retry_count']}/{task.get('max_retries', 3)})")

    return _update_task(task_id, {
        "status": "pending",
        "error": None,
        "assigned_to": None,
        "openclaw_session_id": None,
    })


def attach_subagent_session(
    task_id: str,
    subagent_session_id: str,
    parent_session_id: str | None = None,
) -> dict[str, Any]:
    updates = {"subagent_session_id": subagent_session_id}
    if parent_session_id is not None:
        updates["parent_session_id"] = parent_session_id
    return _update_task(task_id, updates)


def attach_external_process(
    task_id: str,
    process_type: str,
    pid: int | None = None,
    status: str | None = "running",
) -> dict[str, Any]:
    return _update_task(
        task_id,
        {
            "external_process": {
                "type": process_type,
                "pid": pid,
                "status": status,
                "started_at": utc_now_iso(),
                "last_seen": utc_now_iso(),
            }
        },
    )


def touch_external_process(task_id: str, status: str | None = None) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")

    current = task.get("external_process")
    if current is None:
        raise ValueError(f"Task has no external_process: {task_id}")

    updated = dict(current)
    updated["last_seen"] = utc_now_iso()
    if status is not None:
        updated["status"] = status

    return _update_task(task_id, {"external_process": updated})


def mark_suspect(task_id: str, error: str | None = None) -> dict[str, Any]:
    return _update_task(
        task_id,
        {
            "status": "suspect",
            "error": error,
        },
    )


def mark_needs_review(task_id: str, error: str | None = None) -> dict[str, Any]:
    return _update_task(
        task_id,
        {
            "status": "needs_review",
            "error": error,
        },
    )
