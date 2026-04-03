# runtime/jb_components.py
#
# Component registry and connection graph for JBCP workspaces.
# Components are logical pieces of software (connectors, processors, etc.).
# Connections define data/control flow between components.

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from runtime.jb_common import utc_now_iso, DATA_DIR, JsonStore
from runtime.jb_database import get_db, init_db, _json_dumps, _json_loads
from runtime.jb_labels import component_label

COMPONENTS_FILE = DATA_DIR / "jb_components.json"
CONNECTIONS_FILE = DATA_DIR / "jb_connections.json"

_comp_store = JsonStore(COMPONENTS_FILE)
_conn_store = JsonStore(CONNECTIONS_FILE)

VALID_COMPONENT_TYPES = {
    "connector", "processor", "ai", "output", "scheduler", "storage", "config",
}
VALID_COMPONENT_STATUSES = {
    "planned", "building", "built", "testing", "passing", "failing", "deployed",
}
VALID_CONNECTION_TYPES = {"data_flow", "control_flow"}



# -- Internal helpers --------------------------------------------------------

def _normalize_contract(contract: dict[str, Any] | None) -> dict[str, Any]:
    if contract is None:
        contract = {}

    output_schema = dict(contract.get("output_schema") or {})

    # Soft requirement: warn if output_schema lacks a summary field
    if output_schema and "properties" in output_schema:
        props = output_schema.get("properties", {})
        if "summary" not in props:
            import logging
            logging.getLogger("jb_components").warning(
                "Component output_schema missing recommended 'summary' field"
            )

    return {
        "input_type": contract.get("input_type"),
        "output_type": contract.get("output_type", "Any"),
        "config_fields": dict(contract.get("config_fields") or {}),
        "input_schema": dict(contract.get("input_schema") or {}),
        "output_schema": output_schema,
    }


def _validate_component(comp: dict[str, Any]) -> None:
    """Validate component fields."""
    name = (comp.get("name") or "").strip()
    if not name:
        raise ValueError("Component name must be a non-empty string")

    workspace_id = comp.get("workspace_id")
    if not workspace_id:
        raise ValueError("workspace_id must be provided")

    comp_type = comp.get("type", "processor")
    if comp_type not in VALID_COMPONENT_TYPES:
        raise ValueError(
            f"Invalid component type '{comp_type}'. "
            f"Valid types: {sorted(VALID_COMPONENT_TYPES)}"
        )

    status = comp.get("status", "planned")
    if status not in VALID_COMPONENT_STATUSES:
        raise ValueError(
            f"Invalid component status '{status}'. "
            f"Valid statuses: {sorted(VALID_COMPONENT_STATUSES)}"
        )

    files = comp.get("files")
    if files is not None and not isinstance(files, list):
        raise ValueError("files must be a list")

    dependencies = comp.get("dependencies")
    if dependencies is not None and not isinstance(dependencies, list):
        raise ValueError("dependencies must be a list")

    task_ids = comp.get("task_ids")
    if task_ids is not None and not isinstance(task_ids, list):
        raise ValueError("task_ids must be a list")


def _normalize_component(comp: dict[str, Any]) -> dict[str, Any]:
    """Build a normalized component dict."""
    now = utc_now_iso()

    name = (comp.get("name") or "").strip()
    if not name:
        raise ValueError("Component name must be a non-empty string")

    workspace_id = comp.get("workspace_id")
    if not workspace_id:
        raise ValueError("workspace_id must be provided")

    comp_type = comp.get("type", "processor")
    if comp_type not in VALID_COMPONENT_TYPES:
        raise ValueError(
            f"Invalid component type '{comp_type}'. "
            f"Valid types: {sorted(VALID_COMPONENT_TYPES)}"
        )

    status = comp.get("status", "planned")
    if status not in VALID_COMPONENT_STATUSES:
        raise ValueError(
            f"Invalid component status '{status}'. "
            f"Valid statuses: {sorted(VALID_COMPONENT_STATUSES)}"
        )

    files = comp.get("files")
    if files is None:
        files = []
    if not isinstance(files, list):
        raise ValueError("files must be a list")

    dependencies = comp.get("dependencies")
    if dependencies is None:
        dependencies = []
    if not isinstance(dependencies, list):
        raise ValueError("dependencies must be a list")

    task_ids = comp.get("task_ids")
    if task_ids is None:
        task_ids = []
    if not isinstance(task_ids, list):
        raise ValueError("task_ids must be a list")

    return {
        "component_id": comp.get("component_id") or str(uuid4()),
        "workspace_id": workspace_id,
        "name": name,
        "type": comp_type,
        "description": (comp.get("description") or "").strip(),
        "status": status,
        "contract": _normalize_contract(comp.get("contract")),
        "directory": (comp.get("directory") or "").strip(),
        "files": list(files),
        "dependencies": list(dependencies),
        "task_ids": list(task_ids),
        "lines_of_code": comp.get("lines_of_code", 0) or 0,
        "mission_id": comp.get("mission_id"),
        "built_by_agent": comp.get("built_by_agent"),
        "created_at": comp.get("created_at") or now,
        "updated_at": comp.get("updated_at") or now,
    }


def _row_to_component(row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a component dict, parsing JSON fields."""
    d = dict(row)
    d["contract"] = _json_loads(d.get("contract")) or {}
    d["files"] = _json_loads(d.get("files")) or []
    d["dependencies"] = _json_loads(d.get("dependencies")) or []
    d["task_ids"] = _json_loads(d.get("task_ids")) or []
    return d


def _validate_connection(conn: dict[str, Any]) -> None:
    """Validate connection fields."""
    workspace_id = conn.get("workspace_id")
    if not workspace_id:
        raise ValueError("workspace_id must be provided for connection")

    from_component_id = conn.get("from_component_id")
    to_component_id = conn.get("to_component_id")
    if not from_component_id or not to_component_id:
        raise ValueError("from_component_id and to_component_id are required")

    conn_type = conn.get("type", "data_flow")
    if conn_type not in VALID_CONNECTION_TYPES:
        raise ValueError(
            f"Invalid connection type '{conn_type}'. "
            f"Valid types: {sorted(VALID_CONNECTION_TYPES)}"
        )


def _normalize_connection(conn: dict[str, Any]) -> dict[str, Any]:
    workspace_id = conn.get("workspace_id")
    if not workspace_id:
        raise ValueError("workspace_id must be provided for connection")

    from_component_id = conn.get("from_component_id")
    to_component_id = conn.get("to_component_id")
    if not from_component_id or not to_component_id:
        raise ValueError("from_component_id and to_component_id are required")

    conn_type = conn.get("type", "data_flow")
    if conn_type not in VALID_CONNECTION_TYPES:
        raise ValueError(
            f"Invalid connection type '{conn_type}'. "
            f"Valid types: {sorted(VALID_CONNECTION_TYPES)}"
        )

    return {
        "connection_id": conn.get("connection_id") or str(uuid4()),
        "workspace_id": workspace_id,
        "from_component_id": from_component_id,
        "to_component_id": to_component_id,
        "from_output": (conn.get("from_output") or "").strip(),
        "to_input": (conn.get("to_input") or "").strip(),
        "type": conn_type,
        "label": conn.get("label"),
    }


def _row_to_connection(row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a connection dict."""
    return dict(row)


# -- Component CRUD ---------------------------------------------------------

def list_components(workspace_id: str | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        if workspace_id is not None:
            rows = conn.execute(
                "SELECT * FROM components WHERE workspace_id = ?", (workspace_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM components").fetchall()
    return [_row_to_component(r) for r in rows]


def get_component(component_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM components WHERE component_id = ?", (component_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_component(row)


def create_component(
    workspace_id: str,
    name: str,
    type: str,
    description: str = "",
    contract: dict[str, Any] | None = None,
    directory: str = "",
    files: list[str] | None = None,
    dependencies: list[str] | None = None,
    task_ids: list[str] | None = None,
    status: str = "planned",
) -> str:
    # Validate
    _validate_component({
        "workspace_id": workspace_id,
        "name": name,
        "type": type,
        "status": status,
        "files": files,
        "dependencies": dependencies,
        "task_ids": task_ids,
    })

    name = name.strip()
    description = (description or "").strip()
    directory = (directory or "").strip()

    component_id = str(uuid4())
    now = utc_now_iso()
    normalized_contract = _normalize_contract(contract)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO components
               (component_id, workspace_id, name, type, status, description,
                contract, directory, files, dependencies, task_ids,
                lines_of_code, mission_id, built_by_agent, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (component_id, workspace_id, name, type, status, description,
             _json_dumps(normalized_contract), directory,
             _json_dumps(files or []),
             _json_dumps(dependencies or []),
             _json_dumps(task_ids or []),
             0, None, None, now, now),
        )
    return component_id


def update_component(component_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    comp = get_component(component_id)
    if comp is None:
        raise ValueError(f"Component not found: {component_id}")

    merged = {**comp, **updates}
    # Validate the merged result
    _validate_component(merged)

    name = (merged.get("name") or "").strip()
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """UPDATE components SET
               workspace_id = ?, name = ?, type = ?, status = ?,
               description = ?, contract = ?, directory = ?,
               files = ?, dependencies = ?, task_ids = ?,
               lines_of_code = ?, mission_id = ?, built_by_agent = ?,
               updated_at = ?
               WHERE component_id = ?""",
            (merged["workspace_id"], name, merged.get("type", "processor"),
             merged.get("status", "planned"),
             (merged.get("description") or "").strip(),
             _json_dumps(_normalize_contract(merged.get("contract"))),
             (merged.get("directory") or "").strip(),
             _json_dumps(merged.get("files", [])),
             _json_dumps(merged.get("dependencies", [])),
             _json_dumps(merged.get("task_ids", [])),
             merged.get("lines_of_code", 0) or 0,
             merged.get("mission_id"),
             merged.get("built_by_agent"),
             now, component_id),
        )

    return get_component(component_id)


def mark_component_status(component_id: str, status: str) -> dict[str, Any]:
    if status not in VALID_COMPONENT_STATUSES:
        raise ValueError(
            f"Invalid component status '{status}'. "
            f"Valid statuses: {sorted(VALID_COMPONENT_STATUSES)}"
        )
    return update_component(component_id, {"status": status})


def attach_task(component_id: str, task_id: str) -> dict[str, Any]:
    comp = get_component(component_id)
    if comp is None:
        raise ValueError(f"Component not found: {component_id}")

    task_ids = list(comp.get("task_ids", []))
    if task_id not in task_ids:
        task_ids.append(task_id)

    return update_component(component_id, {"task_ids": task_ids})


def add_file(component_id: str, file_path: str) -> dict[str, Any]:
    comp = get_component(component_id)
    if comp is None:
        raise ValueError(f"Component not found: {component_id}")

    files = list(comp.get("files", []))
    if file_path not in files:
        files.append(file_path)

    return update_component(component_id, {"files": files})


# -- Connection CRUD --------------------------------------------------------

def list_connections(workspace_id: str | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        if workspace_id is not None:
            rows = conn.execute(
                "SELECT * FROM connections WHERE workspace_id = ?", (workspace_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM connections").fetchall()
    return [_row_to_connection(r) for r in rows]


def create_connection(
    workspace_id: str,
    from_id: str,
    to_id: str,
    from_output: str = "",
    to_input: str = "",
    type: str = "data_flow",
    label: str | None = None,
) -> str:
    # Validate
    _validate_connection({
        "workspace_id": workspace_id,
        "from_component_id": from_id,
        "to_component_id": to_id,
        "type": type,
    })

    connection_id = str(uuid4())
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """INSERT INTO connections
               (connection_id, workspace_id, from_component_id, to_component_id,
                from_output, to_input, type, label, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (connection_id, workspace_id, from_id, to_id,
             (from_output or "").strip(), (to_input or "").strip(),
             type, label, now),
        )
    return connection_id


def delete_connection(connection_id: str) -> bool:
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM connections WHERE connection_id = ?", (connection_id,)
        )
    return cursor.rowcount > 0


# -- Graph generation -------------------------------------------------------

def build_graph(workspace_id: str) -> dict[str, Any]:
    """
    Build a graph representation of all components and connections
    in a workspace.

    Returns dict with "nodes" and "edges" lists.
    """
    from runtime.jb_queue import get_task

    components = list_components(workspace_id)
    connections = list_connections(workspace_id)

    # Pre-build a map from component_id -> component for edge label derivation
    comp_by_id: dict[str, dict[str, Any]] = {
        c["component_id"]: c for c in components
    }

    nodes = []
    for comp in components:
        # Compute metadata
        file_count = len(comp.get("files", []))
        task_ids = comp.get("task_ids", [])
        status = comp.get("status", "planned")

        # Build progress heuristic based on status
        progress_map = {
            "planned": 0,
            "building": 25,
            "built": 50,
            "testing": 65,
            "passing": 85,
            "failing": 60,
            "deployed": 100,
        }

        # Compute real progress_percent from linked tasks
        task_statuses = []
        for tid in task_ids:
            task = get_task(tid)
            if task is not None:
                task_statuses.append(task.get("status", "unknown"))

        if task_statuses:
            complete_count = sum(1 for s in task_statuses if s == "complete")
            progress_percent = round(complete_count / len(task_statuses) * 100, 1)
        else:
            progress_percent = progress_map.get(status, 0)

        is_active = any(
            s in ("running", "dispatched") for s in task_statuses
        )

        # Contract summary
        contract = comp.get("contract", {})
        contract_summary = {
            "input_type": contract.get("input_type"),
            "output_type": contract.get("output_type", "Any"),
            "config_fields": list(contract.get("config_fields", {}).keys())
            if isinstance(contract.get("config_fields"), dict)
            else list(contract.get("config_fields") or []),
        }

        nodes.append({
            "id": comp["component_id"],
            "type": comp["type"],
            "label": comp["name"],
            "status": status,
            "mission_id": comp.get("mission_id"),
            "description": comp.get("description", ""),
            "contract": contract_summary,
            "is_active": is_active,
            "active_agent": None,  # placeholder
            "built_by": comp.get("built_by_agent"),
            "progress_percent": progress_percent,
            "display_status": component_label(status),
            "metadata": {
                "lines_of_code": comp.get("lines_of_code", 0),
                "files": file_count,
                "assigned_agents": None,
                "build_progress_percent": progress_map.get(status, 0),
                "test_status": status if status in ("passing", "failing", "testing") else None,
            },
        })

    edges = []
    for conn in connections:
        source_id = conn["from_component_id"]
        label = conn.get("label")

        # Auto-derive label from source component's output_type when null
        if label is None:
            source_comp = comp_by_id.get(source_id)
            if source_comp:
                source_contract = source_comp.get("contract", {})
                derived = source_contract.get("output_type")
                if derived and derived != "Any":
                    label = derived

        # Build display_label: human-friendly version
        display_label = label.replace("_", " ").title() if label else None

        edges.append({
            "from": source_id,
            "to": conn["to_component_id"],
            "source": source_id,
            "target": conn["to_component_id"],
            "type": conn["type"],
            "label": label,
            "display_label": display_label,
        })

    return {"nodes": nodes, "edges": edges}


# -- Component lifecycle ----------------------------------------------------

def check_component_lifecycle(component_id: str) -> dict[str, Any]:
    """
    Check whether a component's tasks are all complete and update status
    accordingly.

    Returns a dict with component_id, previous_status, new_status, and reason.
    """
    comp = get_component(component_id)
    if comp is None:
        raise ValueError(f"Component not found: {component_id}")

    task_ids = comp.get("task_ids", [])
    previous_status = comp["status"]

    if not task_ids:
        return {
            "component_id": component_id,
            "previous_status": previous_status,
            "new_status": previous_status,
            "reason": "no tasks linked",
        }

    # Load tasks to check their statuses
    try:
        from runtime.jb_queue import get_task
    except ImportError:
        return {
            "component_id": component_id,
            "previous_status": previous_status,
            "new_status": previous_status,
            "reason": "task queue not available",
        }

    task_statuses = []
    for tid in task_ids:
        task = get_task(tid)
        if task is not None:
            task_statuses.append(task.get("status", "unknown"))

    if not task_statuses:
        return {
            "component_id": component_id,
            "previous_status": previous_status,
            "new_status": previous_status,
            "reason": "no tasks found",
        }

    # If any task failed, keep current status
    if "failed" in task_statuses:
        return {
            "component_id": component_id,
            "previous_status": previous_status,
            "new_status": previous_status,
            "reason": "one or more tasks failed",
        }

    # If all tasks complete, mark as built
    all_complete = all(s == "complete" for s in task_statuses)
    if all_complete and previous_status in ("planned", "building"):
        updated = mark_component_status(component_id, "built")
        return {
            "component_id": component_id,
            "previous_status": previous_status,
            "new_status": "built",
            "reason": "all tasks complete",
        }

    return {
        "component_id": component_id,
        "previous_status": previous_status,
        "new_status": previous_status,
        "reason": f"tasks in progress: {task_statuses}",
    }
