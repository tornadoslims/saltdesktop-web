# runtime/jb_services.py
#
# Service registry for JBCP.
# Tracks deployed services, their lifecycle, run history, and port allocation.

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from runtime.jb_common import utc_now_iso, DATA_DIR, JsonStore
from runtime.jb_database import get_db, init_db, _json_dumps, _json_loads

SERVICES_FILE = DATA_DIR / "jb_services.json"
RUNS_FILE = DATA_DIR / "jb_service_runs.json"

_service_store = JsonStore(SERVICES_FILE)
_run_store = JsonStore(RUNS_FILE)

VALID_SERVICE_STATUSES = {"stopped", "starting", "running", "error", "paused"}
VALID_SERVICE_TYPES = {"scheduled", "daemon", "webhook", "manual"}
VALID_RUN_STATUSES = {"running", "success", "error"}

_PORT_RANGE_START = 9000



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_service(svc: dict[str, Any]) -> None:
    """Validate service fields."""
    name = (svc.get("name") or "").strip()
    if not name:
        raise ValueError("Service name must be a non-empty string")

    workspace_id = svc.get("workspace_id")
    if not workspace_id:
        raise ValueError("workspace_id must be provided")

    status = svc.get("status", "stopped")
    if status not in VALID_SERVICE_STATUSES:
        raise ValueError(
            f"Invalid service status '{status}'. "
            f"Valid statuses: {sorted(VALID_SERVICE_STATUSES)}"
        )

    svc_type = svc.get("type", "manual")
    if svc_type not in VALID_SERVICE_TYPES:
        raise ValueError(
            f"Invalid service type '{svc_type}'. "
            f"Valid types: {sorted(VALID_SERVICE_TYPES)}"
        )


def _normalize_service(svc: dict[str, Any]) -> dict[str, Any]:
    now = utc_now_iso()

    name = (svc.get("name") or "").strip()
    if not name:
        raise ValueError("Service name must be a non-empty string")

    workspace_id = svc.get("workspace_id")
    if not workspace_id:
        raise ValueError("workspace_id must be provided")

    status = svc.get("status", "stopped")
    if status not in VALID_SERVICE_STATUSES:
        raise ValueError(
            f"Invalid service status '{status}'. "
            f"Valid statuses: {sorted(VALID_SERVICE_STATUSES)}"
        )

    svc_type = svc.get("type", "manual")
    if svc_type not in VALID_SERVICE_TYPES:
        raise ValueError(
            f"Invalid service type '{svc_type}'. "
            f"Valid types: {sorted(VALID_SERVICE_TYPES)}"
        )

    return {
        "service_id": svc.get("service_id") or str(uuid4()),
        "workspace_id": workspace_id,
        "name": name,
        "description": svc.get("description", ""),
        "status": status,
        "type": svc_type,
        "schedule": svc.get("schedule"),
        "directory": svc.get("directory", ""),
        "entry_point": svc.get("entry_point", ""),
        "has_frontend": bool(svc.get("has_frontend", False)),
        "frontend_path": svc.get("frontend_path"),
        "port": svc.get("port"),
        "pid": svc.get("pid"),
        "last_run": svc.get("last_run"),
        "last_run_status": svc.get("last_run_status"),
        "last_run_duration_ms": svc.get("last_run_duration_ms"),
        "next_run": svc.get("next_run"),
        "health": svc.get("health", "unknown"),
        "run_count": int(svc.get("run_count", 0)),
        "mission_id": svc.get("mission_id"),
        "last_run_summary": svc.get("last_run_summary"),
        "error_count": int(svc.get("error_count", 0)),
        "created_at": svc.get("created_at") or now,
        "updated_at": svc.get("updated_at") or now,
    }


def _row_to_service(row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a service dict."""
    d = dict(row)
    d["has_frontend"] = bool(d.get("has_frontend", 0))
    return d


def _normalize_run(run: dict[str, Any]) -> dict[str, Any]:
    now = utc_now_iso()

    status = run.get("status", "running")
    if status not in VALID_RUN_STATUSES:
        raise ValueError(
            f"Invalid run status '{status}'. "
            f"Valid statuses: {sorted(VALID_RUN_STATUSES)}"
        )

    output_preview = run.get("output_preview")
    if output_preview and len(output_preview) > 500:
        output_preview = output_preview[:500]

    return {
        "run_id": run.get("run_id") or str(uuid4()),
        "service_id": run.get("service_id", ""),
        "started_at": run.get("started_at") or now,
        "completed_at": run.get("completed_at"),
        "status": status,
        "duration_ms": run.get("duration_ms"),
        "output_preview": output_preview,
        "summary_chain": run.get("summary_chain"),
        "error": run.get("error"),
        "tokens_used": int(run.get("tokens_used", 0)),
    }


def _row_to_run(row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a run dict."""
    d = dict(row)
    d["summary_chain"] = _json_loads(d.get("summary_chain"))
    return d


# ---------------------------------------------------------------------------
# Service CRUD
# ---------------------------------------------------------------------------

def list_services(workspace_id: str | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        if workspace_id is not None:
            rows = conn.execute(
                "SELECT * FROM services WHERE workspace_id = ?", (workspace_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM services").fetchall()
    return [_row_to_service(r) for r in rows]


def get_service(service_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM services WHERE service_id = ?", (service_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_service(row)


def create_service(
    workspace_id: str,
    name: str,
    description: str = "",
    type: str = "manual",
    schedule: str | None = None,
    directory: str = "",
    entry_point: str = "",
    has_frontend: bool = False,
    frontend_path: str | None = None,
    port: int | None = None,
    mission_id: str | None = None,
) -> str:
    # Validate
    _validate_service({
        "workspace_id": workspace_id,
        "name": name,
        "type": type,
        "status": "stopped",
    })

    name = name.strip()
    service_id = str(uuid4())
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """INSERT INTO services
               (service_id, workspace_id, name, description, status, type,
                schedule, directory, entry_point, has_frontend, frontend_path,
                port, pid, last_run, last_run_status, last_run_duration_ms,
                next_run, health, run_count, mission_id, last_run_summary,
                error_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (service_id, workspace_id, name, description or "", "stopped", type,
             schedule, directory or "", entry_point or "",
             1 if has_frontend else 0, frontend_path,
             port, None, None, None, None, None,
             "unknown", 0, mission_id, None, 0, now, now),
        )
    return service_id


def update_service(service_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    svc = get_service(service_id)
    if svc is None:
        raise ValueError(f"Service not found: {service_id}")

    merged = {**svc, **updates}
    # Validate
    _validate_service(merged)

    name = (merged.get("name") or "").strip()
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """UPDATE services SET
               workspace_id = ?, name = ?, description = ?, status = ?,
               type = ?, schedule = ?, directory = ?, entry_point = ?,
               has_frontend = ?, frontend_path = ?, port = ?, pid = ?,
               last_run = ?, last_run_status = ?, last_run_duration_ms = ?,
               next_run = ?, health = ?, run_count = ?, mission_id = ?,
               last_run_summary = ?, error_count = ?, updated_at = ?
               WHERE service_id = ?""",
            (merged["workspace_id"], name, merged.get("description", ""),
             merged.get("status", "stopped"), merged.get("type", "manual"),
             merged.get("schedule"), merged.get("directory", ""),
             merged.get("entry_point", ""),
             1 if merged.get("has_frontend") else 0,
             merged.get("frontend_path"),
             merged.get("port"), merged.get("pid"),
             merged.get("last_run"), merged.get("last_run_status"),
             merged.get("last_run_duration_ms"),
             merged.get("next_run"), merged.get("health", "unknown"),
             int(merged.get("run_count", 0)),
             merged.get("mission_id"), merged.get("last_run_summary"),
             int(merged.get("error_count", 0)),
             now, service_id),
        )

    return get_service(service_id)


def mark_service_status(service_id: str, status: str) -> dict[str, Any]:
    if status not in VALID_SERVICE_STATUSES:
        raise ValueError(
            f"Invalid service status '{status}'. "
            f"Valid statuses: {sorted(VALID_SERVICE_STATUSES)}"
        )
    return update_service(service_id, {"status": status})


# ---------------------------------------------------------------------------
# Run tracking
# ---------------------------------------------------------------------------

def record_run(
    service_id: str,
    status: str = "running",
    duration_ms: int | None = None,
    output_preview: str | None = None,
    error: str | None = None,
    tokens_used: int = 0,
) -> str:
    # Verify service exists
    svc = get_service(service_id)
    if svc is None:
        raise ValueError(f"Service not found: {service_id}")

    now = utc_now_iso()
    run = _normalize_run({
        "service_id": service_id,
        "started_at": now,
        "completed_at": now if status in ("success", "error") else None,
        "status": status,
        "duration_ms": duration_ms,
        "output_preview": output_preview,
        "error": error,
        "tokens_used": tokens_used,
    })

    with get_db() as conn:
        conn.execute(
            """INSERT INTO service_runs
               (run_id, service_id, started_at, completed_at, status,
                duration_ms, output_preview, summary_chain, error, tokens_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run["run_id"], service_id, run["started_at"], run["completed_at"],
             run["status"], run["duration_ms"], run["output_preview"],
             _json_dumps(run["summary_chain"]),
             run["error"], run["tokens_used"]),
        )

    # Update service run stats
    svc_updates: dict[str, Any] = {
        "last_run": now,
        "last_run_status": status if status != "running" else svc.get("last_run_status"),
        "last_run_duration_ms": duration_ms,
        "run_count": svc["run_count"] + 1,
    }
    if status == "error":
        svc_updates["error_count"] = svc["error_count"] + 1
    update_service(service_id, svc_updates)

    return run["run_id"]


def list_runs(service_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM service_runs WHERE service_id = ?
               ORDER BY started_at DESC LIMIT ?""",
            (service_id, limit),
        ).fetchall()
    return [_row_to_run(r) for r in rows]


def get_run(run_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM service_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_run(row)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def start_service(service_id: str) -> dict[str, Any]:
    svc = get_service(service_id)
    if svc is None:
        raise ValueError(f"Service not found: {service_id}")
    if svc["status"] == "running":
        raise ValueError(f"Service {service_id} is already running")
    return mark_service_status(service_id, "starting")


def stop_service(service_id: str) -> dict[str, Any]:
    svc = get_service(service_id)
    if svc is None:
        raise ValueError(f"Service not found: {service_id}")
    if svc["status"] == "stopped":
        raise ValueError(f"Service {service_id} is already stopped")
    return update_service(service_id, {"status": "stopped", "pid": None})


def pause_service(service_id: str) -> dict[str, Any]:
    svc = get_service(service_id)
    if svc is None:
        raise ValueError(f"Service not found: {service_id}")
    if svc["status"] != "running":
        raise ValueError(f"Can only pause a running service (current: {svc['status']})")
    return mark_service_status(service_id, "paused")


def resume_service(service_id: str) -> dict[str, Any]:
    svc = get_service(service_id)
    if svc is None:
        raise ValueError(f"Service not found: {service_id}")
    if svc["status"] != "paused":
        raise ValueError(f"Can only resume a paused service (current: {svc['status']})")
    return mark_service_status(service_id, "running")


# ---------------------------------------------------------------------------
# Port management
# ---------------------------------------------------------------------------

def allocate_port(service_id: str) -> int:
    svc = get_service(service_id)
    if svc is None:
        raise ValueError(f"Service not found: {service_id}")

    # If service already has a port, return it
    if svc.get("port") is not None:
        return svc["port"]

    # Gather all currently allocated ports
    with get_db() as conn:
        rows = conn.execute("SELECT port FROM services WHERE port IS NOT NULL").fetchall()
    used_ports = {r["port"] for r in rows}

    # Find next available port starting from _PORT_RANGE_START
    port = _PORT_RANGE_START
    while port in used_ports:
        port += 1

    update_service(service_id, {"port": port})
    return port


def release_port(service_id: str) -> None:
    svc = get_service(service_id)
    if svc is None:
        raise ValueError(f"Service not found: {service_id}")
    update_service(service_id, {"port": None})
