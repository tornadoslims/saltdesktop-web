"""
Swarm View — read-only view layer that composes task queue, components,
signals, and services into the "My AI" dashboard view.

No new state is managed here. This is purely a join/transform layer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from runtime.jb_queue import list_tasks, get_running, get_pending, get_dispatched
from runtime.jb_components import get_component
from runtime.jb_services import list_services
from runtime.jb_missions import get_mission, compute_mission_progress
from runtime.jb_labels import worker_role, service_label
from runtime.jb_companies import get_company
from runtime.jb_common import parse_iso, utc_now


def get_swarm(mission_id: str = None) -> dict:
    """
    Build the swarm view for the My AI page.

    Returns:
    {
      "building": [
        {
          "mission_id": "...",
          "mission_name": "Slack Analyzer",
          "workers": [
            {
              "task_id": "...",
              "role": "Coder",
              "role_icon": "hammer",
              "component_name": "Gmail Connector",
              "component_id": "...",
              "status": "running",
              "activity": "writing auth logic",
              "lines_of_code": null,
              "started_at": "...",
            }
          ],
          "progress": {"completed": 3, "total": 5, "percent": 60}
        }
      ],
      "running": [
        {
          "service_id": "...",
          "name": "Gmail Checker",
          "workspace_name": "Work Automation Co.",
          "status_label": "Healthy",
          "schedule_label": "every 15 minutes",
          "run_count": 142,
          "last_run_ago": "8 minutes ago",
        }
      ]
    }

    If mission_id is provided, only return workers for that mission.
    """
    return {
        "building": _build_workers_by_mission(mission_id=mission_id),
        "running": _build_running_services(),
    }


def _build_workers_by_mission(mission_id: str = None) -> list[dict]:
    """Build the "building" section: workers grouped by mission.

    1. Get running + dispatched + pending tasks (optionally filtered by mission_id)
    2. Also get recently completed tasks (status=complete, within last 30 min)
    3. Group by mission_id
    4. For each task: resolve component name, determine role from task type, get activity
    """
    all_tasks = list_tasks()

    # Active tasks: running, dispatched, pending, in_progress
    active_statuses = {"running", "dispatched", "pending", "in_progress"}
    tasks = [t for t in all_tasks if t["status"] in active_statuses]

    # Also include recently completed tasks (within last 30 min)
    now = utc_now()
    for t in all_tasks:
        if t["status"] == "complete":
            updated = parse_iso(t.get("updated_at"))
            if updated and (now - updated).total_seconds() < 1800:
                tasks.append(t)

    # Filter by mission_id if provided
    if mission_id is not None:
        tasks = [t for t in tasks if t.get("mission_id") == mission_id]

    # Group by mission_id
    groups: dict[str, list[dict]] = {}
    for t in tasks:
        mid = t.get("mission_id") or "__none__"
        groups.setdefault(mid, []).append(t)

    building = []
    for mid, group_tasks in groups.items():
        # Resolve mission name
        mission = get_mission(mid) if mid != "__none__" else None
        mission_name = (mission["goal"] if mission else "Unnamed Mission")

        workers = []
        for t in group_tasks:
            # Resolve component
            comp_name = None
            comp_id = None
            comp_loc = t.get("payload", {}).get("component", "")
            lines_of_code = None

            # Try to find component by name from task payload
            if comp_loc:
                comp_name = comp_loc

            # Determine role from task type
            role_info = worker_role(t.get("type", "coding"))

            # Map task status to worker status
            status = t["status"]
            if status in ("dispatched", "in_progress"):
                status = "running"

            workers.append({
                "task_id": t["id"],
                "role": role_info["label"],
                "role_icon": role_info["icon"],
                "component_name": comp_name,
                "component_id": comp_id,
                "status": status,
                "activity": None,
                "lines_of_code": lines_of_code,
                "started_at": t.get("updated_at") if t["status"] in ("running", "dispatched", "in_progress") else None,
            })

        progress = compute_mission_progress(mid) if mid != "__none__" else {"completed": 0, "total": len(group_tasks), "percent": 0}

        building.append({
            "mission_id": mid if mid != "__none__" else None,
            "mission_name": mission_name,
            "workers": workers,
            "progress": progress,
        })

    return building


def _build_running_services() -> list[dict]:
    """Build the "running" section: active services.

    1. Get all services with status=running
    2. For each: look up workspace name, format schedule, compute last_run_ago
    """
    services = list_services()
    running = [s for s in services if s["status"] == "running"]

    result = []
    for svc in running:
        # Look up workspace name
        workspace_name = None
        ws_id = svc.get("workspace_id")
        if ws_id:
            company = get_company(ws_id)
            if company:
                workspace_name = company.get("name")
        if not workspace_name:
            workspace_name = svc.get("name", "Unknown")

        # Format schedule
        schedule = svc.get("schedule")
        schedule_label_text = _format_schedule(schedule) if schedule else None

        # Compute last_run_ago
        last_run = svc.get("last_run")
        last_run_ago = _relative_time(last_run) if last_run else None

        result.append({
            "service_id": svc["service_id"],
            "name": svc["name"],
            "workspace_name": workspace_name,
            "status_label": service_label(svc["status"]),
            "schedule_label": schedule_label_text,
            "run_count": svc.get("run_count", 0),
            "last_run_ago": last_run_ago,
        })

    return result


def _format_schedule(schedule: str) -> str:
    """Convert cron expression to human-friendly text.

    "*/15 * * * *" -> "every 15 minutes"
    "0 * * * *"    -> "every hour"
    "0 9 * * *"    -> "daily at 9:00 AM"
    "0 9 * * 1"    -> "weekly on Monday at 9:00 AM"

    Unknown patterns -> return as-is.
    """
    if not schedule or not schedule.strip():
        return schedule or ""

    parts = schedule.strip().split()
    if len(parts) != 5:
        return schedule

    minute, hour, dom, month, dow = parts

    # "*/N * * * *" -> "every N minutes"
    if minute.startswith("*/") and hour == "*" and dom == "*" and month == "*" and dow == "*":
        try:
            n = int(minute[2:])
            if n == 1:
                return "every minute"
            return f"every {n} minutes"
        except ValueError:
            pass

    # "0 * * * *" -> "every hour"
    if minute == "0" and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return "every hour"

    # "N * * * *" -> "every hour at :NN"
    if minute.isdigit() and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return f"every hour at :{minute.zfill(2)}"

    # "0 */N * * *" -> "every N hours"
    if minute == "0" and hour.startswith("*/") and dom == "*" and month == "*" and dow == "*":
        try:
            n = int(hour[2:])
            if n == 1:
                return "every hour"
            return f"every {n} hours"
        except ValueError:
            pass

    # Format time helper
    def _format_time(h: str, m: str) -> str:
        try:
            hr = int(h)
            mn = int(m)
            ampm = "AM" if hr < 12 else "PM"
            display_hr = hr % 12
            if display_hr == 0:
                display_hr = 12
            return f"{display_hr}:{mn:02d} {ampm}"
        except ValueError:
            return f"{h}:{m}"

    day_names = {
        "0": "Sunday", "7": "Sunday",
        "1": "Monday", "2": "Tuesday", "3": "Wednesday",
        "4": "Thursday", "5": "Friday", "6": "Saturday",
    }

    # "M H * * *" -> "daily at H:MM AM/PM"
    if minute.isdigit() and hour.isdigit() and dom == "*" and month == "*" and dow == "*":
        return f"daily at {_format_time(hour, minute)}"

    # "M H * * D" -> "weekly on DAY at H:MM AM/PM"
    if minute.isdigit() and hour.isdigit() and dom == "*" and month == "*" and dow.isdigit():
        day = day_names.get(dow, dow)
        return f"weekly on {day} at {_format_time(hour, minute)}"

    return schedule


def _relative_time(iso_timestamp: str) -> str:
    """Convert ISO timestamp to relative time string: "5 minutes ago", "2 hours ago", etc."""
    dt = parse_iso(iso_timestamp)
    if dt is None:
        return "unknown"

    now = utc_now()
    delta = now - dt

    total_seconds = int(delta.total_seconds())

    if total_seconds < 0:
        return "just now"

    if total_seconds < 60:
        if total_seconds <= 1:
            return "just now"
        return f"{total_seconds} seconds ago"

    minutes = total_seconds // 60
    if minutes < 60:
        if minutes == 1:
            return "1 minute ago"
        return f"{minutes} minutes ago"

    hours = minutes // 60
    if hours < 24:
        if hours == 1:
            return "1 hour ago"
        return f"{hours} hours ago"

    days = hours // 24
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"
