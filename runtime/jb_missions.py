# runtime/jb_missions.py
#
# Mission = the atomic unit of work in JBCP.
# A mission has a goal, items (plan), components, connections, and tasks.
#
# Lifecycle: planning -> planned -> active -> complete/failed
#   planning: user is chatting about what to build, items being generated
#   planned:  items/components/connections are set, ready to approve
#   active:   tasks have been created and are running
#   complete: all tasks done
#   failed:   tasks failed beyond retry
#   cancelled: user cancelled
#   blocked:  waiting on something
#   draft:    legacy/initial state

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from uuid import uuid4

from runtime.jb_common import utc_now_iso, DATA_DIR, JsonStore
from runtime.jb_database import get_db, init_db, _json_dumps, _json_loads

MISSIONS_FILE = DATA_DIR / "jb_missions.json"
_store = JsonStore(MISSIONS_FILE)

VALID_MISSION_STATUSES = {
    "draft",
    "planning",
    "planned",
    "active",
    "blocked",
    "complete",
    "failed",
    "cancelled",
    "deployed",
}

VALID_ITEM_TYPES = {"coding", "research", "document", "analysis", "unknown"}



# -- Normalization helpers ---------------------------------------------------

def _normalize_source_artifacts(source_artifacts: Any) -> list[dict[str, Any]]:
    if source_artifacts is None:
        return []
    if not isinstance(source_artifacts, list):
        raise ValueError("source_artifacts must be a list")
    normalized: list[dict[str, Any]] = []
    for item in source_artifacts:
        if not isinstance(item, dict):
            raise ValueError("Each source_artifact must be a dictionary")
        normalized.append({
            "type": item.get("type", "unknown"),
            "path": item.get("path"),
            "description": item.get("description"),
        })
    return normalized


def _normalize_task_ids(task_ids: Any) -> list[str]:
    if task_ids is None:
        return []
    if not isinstance(task_ids, list):
        raise ValueError("task_ids must be a list")
    return [str(t) for t in task_ids]


def _normalize_constraints(constraints: Any) -> list[str]:
    if constraints is None:
        return []
    if not isinstance(constraints, list):
        raise ValueError("constraints must be a list")
    return [str(c) for c in constraints]


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single plan item (task blueprint)."""
    goal = (item.get("goal") or "").strip()
    if not goal:
        raise ValueError("Plan item goal must be a non-empty string")

    component = (item.get("component") or "").strip()

    return {
        "item_id": item.get("item_id") or str(uuid4()),
        "title": (item.get("title") or goal[:60]).strip(),
        "goal": goal,
        "type": item.get("type", "coding"),
        "component": component,
        "constraints": list(item.get("constraints") or []),
        "dependencies": list(item.get("dependencies") or []),
        "priority": int(item.get("priority", 5)),
    }


def _normalize_items(items: Any) -> list[dict[str, Any]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    return [_normalize_item(i) for i in items]


def _validate_mission(mission: dict[str, Any]) -> None:
    """Validate mission fields."""
    status = mission.get("status", "active")
    if status not in VALID_MISSION_STATUSES:
        raise ValueError(
            f"Invalid mission status '{status}'. "
            f"Valid statuses: {sorted(VALID_MISSION_STATUSES)}"
        )
    goal = (mission.get("goal") or "").strip() or (mission.get("title") or "").strip()
    if not goal:
        raise ValueError("Mission goal must be a non-empty string")


def _normalize_mission(mission: dict[str, Any]) -> dict[str, Any]:
    """Build a normalized mission dict from raw data (used for backward compat)."""
    now = utc_now_iso()
    status = mission.get("status", "active")

    if status not in VALID_MISSION_STATUSES:
        raise ValueError(
            f"Invalid mission status '{status}'. "
            f"Valid statuses: {sorted(VALID_MISSION_STATUSES)}"
        )

    goal = (mission.get("goal") or "").strip() or (mission.get("title") or "").strip()
    if not goal:
        raise ValueError("Mission goal must be a non-empty string")

    return {
        "mission_id": mission.get("mission_id") or str(uuid4()),
        "company_id": mission.get("company_id"),
        "goal": goal,
        "summary": mission.get("summary"),
        "status": status,
        "constraints": _normalize_constraints(mission.get("constraints")),
        "source_artifacts": _normalize_source_artifacts(mission.get("source_artifacts")),
        "task_ids": _normalize_task_ids(mission.get("task_ids")),
        "items": _normalize_items(mission.get("items")),
        "components": list(mission.get("components") or []),
        "connections": list(mission.get("connections") or []),
        "origin": deepcopy(mission.get("origin")) if isinstance(mission.get("origin"), dict) else None,
        "delivery": deepcopy(mission.get("delivery")) if isinstance(mission.get("delivery"), dict) else None,
        "context_path": mission.get("context_path"),
        "_previous_draft": deepcopy(mission.get("_previous_draft")) if isinstance(mission.get("_previous_draft"), dict) else None,
        "_last_diff": deepcopy(mission.get("_last_diff")) if isinstance(mission.get("_last_diff"), list) else None,
        "_last_generated_at": mission.get("_last_generated_at"),
        "created_at": mission.get("created_at") or now,
        "updated_at": mission.get("updated_at") or now,
    }


def _row_to_mission(row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a mission dict, parsing JSON fields."""
    d = dict(row)
    d["constraints"] = _json_loads(d.get("constraints")) or []
    d["source_artifacts"] = _json_loads(d.get("source_artifacts")) or []
    d["task_ids"] = _json_loads(d.get("task_ids")) or []
    d["items"] = _json_loads(d.get("items")) or []
    d["components"] = _json_loads(d.get("components")) or []
    d["connections"] = _json_loads(d.get("connections")) or []
    d["origin"] = _json_loads(d.get("origin"))
    d["delivery"] = _json_loads(d.get("delivery"))
    d["_previous_draft"] = _json_loads(d.get("_previous_draft"))
    d["_last_diff"] = _json_loads(d.get("_last_diff"))
    return d


# -- CRUD -------------------------------------------------------------------

def list_missions() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM missions").fetchall()
    return [_row_to_mission(r) for r in rows]


def get_mission(mission_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM missions WHERE mission_id = ?", (mission_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_mission(row)


def create_mission(
    goal: str,
    company_id: str | None = None,
    summary: str | None = None,
    constraints: list[str] | None = None,
    source_artifacts: list[dict[str, Any]] | None = None,
    origin: dict[str, Any] | None = None,
    delivery: dict[str, Any] | None = None,
    context_path: str | None = None,
    status: str = "planning",
) -> str:
    # Validate
    _validate_mission({"goal": goal, "status": status})
    goal = goal.strip()

    mission_id = str(uuid4())
    now = utc_now_iso()

    normalized_constraints = _normalize_constraints(constraints)
    normalized_artifacts = _normalize_source_artifacts(source_artifacts)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO missions
               (mission_id, company_id, goal, summary, status,
                constraints, source_artifacts, task_ids, items,
                components, connections, origin, delivery,
                context_path, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (mission_id, company_id, goal, summary, status,
             _json_dumps(normalized_constraints),
             _json_dumps(normalized_artifacts),
             "[]", "[]", "[]", "[]",
             _json_dumps(origin), _json_dumps(delivery),
             context_path, now, now),
        )
    return mission_id


def _update_mission(mission_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")

    merged = {**mission, **updates}

    # Validate status
    status = merged.get("status", "active")
    if status not in VALID_MISSION_STATUSES:
        raise ValueError(
            f"Invalid mission status '{status}'. "
            f"Valid statuses: {sorted(VALID_MISSION_STATUSES)}"
        )

    goal = (merged.get("goal") or "").strip()
    if not goal:
        raise ValueError("Mission goal must be a non-empty string")

    now = utc_now_iso()

    # Normalize list fields
    normalized_constraints = _normalize_constraints(merged.get("constraints"))
    normalized_artifacts = _normalize_source_artifacts(merged.get("source_artifacts"))
    task_ids = _normalize_task_ids(merged.get("task_ids"))
    items = _normalize_items(merged.get("items"))
    components = list(merged.get("components") or [])
    connections = list(merged.get("connections") or [])

    with get_db() as conn:
        conn.execute(
            """UPDATE missions SET
               company_id = ?, goal = ?, summary = ?, status = ?,
               constraints = ?, source_artifacts = ?, task_ids = ?,
               items = ?, components = ?, connections = ?,
               origin = ?, delivery = ?, context_path = ?,
               _previous_draft = ?, _last_diff = ?, _last_generated_at = ?,
               updated_at = ?
               WHERE mission_id = ?""",
            (merged.get("company_id"), goal, merged.get("summary"), status,
             _json_dumps(normalized_constraints),
             _json_dumps(normalized_artifacts),
             _json_dumps(task_ids),
             _json_dumps(items),
             _json_dumps(components),
             _json_dumps(connections),
             _json_dumps(merged.get("origin")) if isinstance(merged.get("origin"), dict) else None,
             _json_dumps(merged.get("delivery")) if isinstance(merged.get("delivery"), dict) else None,
             merged.get("context_path"),
             _json_dumps(merged.get("_previous_draft")) if isinstance(merged.get("_previous_draft"), dict) else None,
             _json_dumps(merged.get("_last_diff")) if isinstance(merged.get("_last_diff"), list) else None,
             merged.get("_last_generated_at"),
             now,
             mission_id),
        )

    return get_mission(mission_id)


# -- Task management --------------------------------------------------------

def attach_task(mission_id: str, task_id: str) -> dict[str, Any]:
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")
    task_ids = list(mission.get("task_ids", []))
    if task_id not in task_ids:
        task_ids.append(task_id)
    return _update_mission(mission_id, {"task_ids": task_ids})


def mark_mission_status(mission_id: str, status: str) -> dict[str, Any]:
    return _update_mission(mission_id, {"status": status})


def update_mission_summary(mission_id: str, summary: str | None) -> dict[str, Any]:
    return _update_mission(mission_id, {"summary": summary})


def add_source_artifact(
    mission_id: str,
    artifact_type: str,
    path: str,
    description: str | None = None,
) -> dict[str, Any]:
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")
    source_artifacts = list(mission.get("source_artifacts", []))
    source_artifacts.append({
        "type": artifact_type,
        "path": path,
        "description": description,
    })
    return _update_mission(mission_id, {"source_artifacts": source_artifacts})


# -- Item management (was in jb_plans.py) -----------------------------------

def add_item(
    mission_id: str,
    goal: str,
    title: str | None = None,
    item_type: str = "coding",
    component: str = "",
    constraints: list[str] | None = None,
    dependencies: list[str] | None = None,
    priority: int = 5,
) -> dict[str, Any]:
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")
    if mission["status"] != "planning":
        raise ValueError(f"Cannot add items to mission in '{mission['status']}' state")

    item = _normalize_item({
        "title": title,
        "goal": goal,
        "type": item_type,
        "component": component,
        "constraints": constraints or [],
        "dependencies": dependencies or [],
        "priority": priority,
    })

    items = list(mission["items"])
    items.append(item)
    _update_mission(mission_id, {"items": items})
    return item


def remove_item(mission_id: str, item_id: str) -> dict[str, Any]:
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")
    if mission["status"] != "planning":
        raise ValueError(f"Cannot remove items from mission in '{mission['status']}' state")

    items = [i for i in mission["items"] if i["item_id"] != item_id]
    if len(items) == len(mission["items"]):
        raise ValueError(f"Item not found: {item_id}")

    for item in items:
        item["dependencies"] = [d for d in item["dependencies"] if d != item_id]

    return _update_mission(mission_id, {"items": items})


def update_item(mission_id: str, item_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")
    if mission["status"] != "planning":
        raise ValueError(f"Cannot update items in mission in '{mission['status']}' state")

    items = list(mission["items"])
    found = False
    for i, item in enumerate(items):
        if item["item_id"] == item_id:
            merged = {**item, **updates}
            merged["item_id"] = item_id
            items[i] = _normalize_item(merged)
            found = True
            break

    if not found:
        raise ValueError(f"Item not found: {item_id}")

    return _update_mission(mission_id, {"items": items})


# -- Planning workflow -------------------------------------------------------

def mark_planned(mission_id: str) -> dict[str, Any]:
    """Transition planning -> planned (items ready for approval)."""
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")
    if mission["status"] != "planning":
        raise ValueError(f"Can only mark planned from 'planning' state, got '{mission['status']}'")
    if not mission["items"]:
        raise ValueError("Cannot mark planned with no items")
    return _update_mission(mission_id, {"status": "planned"})


def reopen_planning(mission_id: str) -> dict[str, Any]:
    """Transition planned -> planning (for edits)."""
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")
    if mission["status"] != "planned":
        raise ValueError(f"Can only reopen from 'planned' state, got '{mission['status']}'")
    return _update_mission(mission_id, {"status": "planning"})


def approve_mission(mission_id: str) -> dict[str, Any]:
    """
    Approve a mission: create component records and enqueue tasks from items.

    Transitions planning/planned -> active.
    Returns dict with mission_id, task_ids, component_name_to_id.
    """
    from runtime.jb_queue import enqueue
    from runtime.jb_components import (
        create_component as _create_component,
        create_connection as _create_connection,
        attach_task as _attach_task_to_component,
    )

    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")
    if mission["status"] not in ("planning", "planned"):
        raise ValueError(f"Can only approve from 'planning' or 'planned' state, got '{mission['status']}'")
    if not mission.get("items"):
        raise ValueError("Mission has no items to approve")

    company_id = mission.get("company_id")
    workspace_id = company_id or mission_id

    # Create component records
    plan_components = mission.get("components") or []
    plan_connections = mission.get("connections") or []
    component_name_to_id: dict[str, str] = {}

    for comp_spec in plan_components:
        comp_name = comp_spec.get("name", "")
        comp_type = comp_spec.get("type", "processor")
        comp_desc = comp_spec.get("description", "")

        contract = {
            "input_type": comp_spec.get("input_type"),
            "output_type": comp_spec.get("output_type"),
            "config_fields": dict(comp_spec.get("config_fields") or {}),
            "output_schema": dict(comp_spec.get("output_fields") or {}),
        }

        dep_names = comp_spec.get("dependencies") or []
        dep_ids = [component_name_to_id[d] for d in dep_names if d in component_name_to_id]

        comp_id = _create_component(
            workspace_id=workspace_id,
            name=comp_name,
            type=comp_type,
            description=comp_desc,
            contract=contract,
            dependencies=dep_ids,
        )
        component_name_to_id[comp_name] = comp_id

    # Create connections
    for conn_spec in plan_connections:
        from_name = conn_spec.get("from", "")
        to_name = conn_spec.get("to", "")
        label = conn_spec.get("label")
        from_id = component_name_to_id.get(from_name)
        to_id = component_name_to_id.get(to_name)
        if from_id and to_id:
            _create_connection(
                workspace_id=workspace_id,
                from_id=from_id,
                to_id=to_id,
                label=label,
            )

    # Compute dependency depth for priority ordering
    dep_depth = _compute_dep_depth(mission["items"])

    # Enqueue tasks
    task_ids = []
    for item in mission["items"]:
        effective_priority = max(1, item["priority"] - dep_depth.get(item["item_id"], 0))

        task = {
            "company_id": company_id,
            "mission_id": mission_id,
            "type": item["type"],
            "status": "pending",
            "priority": effective_priority,
            "payload": {
                "goal": item["goal"],
                "item_id": item["item_id"],
                "constraints": item["constraints"],
                "component": item.get("component", ""),
            },
        }
        task_id = enqueue(task)
        attach_task(mission_id, task_id)
        task_ids.append(task_id)

        comp_name = item.get("component", "")
        if comp_name and comp_name in component_name_to_id:
            _attach_task_to_component(component_name_to_id[comp_name], task_id)

    # Mark active
    _update_mission(mission_id, {"status": "active"})

    return {
        "mission_id": mission_id,
        "task_ids": task_ids,
        "component_name_to_id": component_name_to_id,
    }


def compute_mission_progress(mission_id: str) -> dict:
    """Compute mission build progress from task statuses.
    Returns: {"completed": N, "total": N, "percent": float}
    """
    from runtime.jb_queue import list_tasks

    tasks = [t for t in list_tasks() if t.get("mission_id") == mission_id]
    total = len(tasks)
    completed = sum(1 for t in tasks if t.get("status") == "complete")
    percent = (completed / total * 100) if total > 0 else 0
    return {"completed": completed, "total": total, "percent": round(percent, 1)}


def _compute_dep_depth(items: list[dict[str, Any]]) -> dict[str, int]:
    """Compute dependency depth for priority ordering."""
    item_ids = {i["item_id"] for i in items}
    deps = {i["item_id"]: [d for d in i.get("dependencies", []) if d in item_ids] for i in items}

    depth: dict[str, int] = {}

    def _depth(item_id: str, visited: set[str] | None = None) -> int:
        if item_id in depth:
            return depth[item_id]
        if visited is None:
            visited = set()
        if item_id in visited:
            return 0
        visited.add(item_id)
        if not deps.get(item_id):
            depth[item_id] = 0
        else:
            depth[item_id] = 1 + max(_depth(d, visited) for d in deps[item_id])
        return depth[item_id]

    for item in items:
        _depth(item["item_id"])

    return depth


# -- Deployment workflow -----------------------------------------------------

def mark_deployed(mission_id: str) -> dict[str, Any]:
    """Transition mission to deployed status. Only from 'complete'."""
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")
    if mission["status"] != "complete":
        raise ValueError(
            f"Can only deploy from 'complete' state, got '{mission['status']}'"
        )
    return _update_mission(mission_id, {"status": "deployed"})


def mark_undeployed(mission_id: str) -> dict[str, Any]:
    """Transition mission back to complete from deployed."""
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")
    if mission["status"] != "deployed":
        raise ValueError(
            f"Can only undeploy from 'deployed' state, got '{mission['status']}'"
        )
    return _update_mission(mission_id, {"status": "complete"})
