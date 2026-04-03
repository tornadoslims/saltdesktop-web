# runtime/jb_missions.py

**Path:** `runtime/jb_missions.py`
**Purpose:** Mission CRUD with company linkage, items (plan tasks), components, connections, and lifecycle management. A mission is the atomic unit of work in JBCP.

## Mission Lifecycle

```
planning -> planned -> active -> complete/failed
                                    |
                                 deployed
```

- **planning**: User is chatting about what to build; items being generated
- **planned**: Items/components/connections are set, ready to approve
- **active**: Tasks have been created and are running
- **complete**: All tasks done
- **failed**: Tasks failed beyond retry
- **cancelled**: User cancelled
- **blocked**: Waiting on something
- **deployed**: Running as a service

## Constants

- `VALID_MISSION_STATUSES`: `{"draft", "planning", "planned", "active", "blocked", "complete", "failed", "cancelled", "deployed"}`
- `VALID_ITEM_TYPES`: `{"coding", "research", "document", "analysis", "unknown"}`

## CRUD Functions

### `list_missions() -> list[dict]`
Returns all missions from SQLite, with JSON fields parsed.

### `get_mission(mission_id: str) -> dict | None`
Fetches a single mission by ID.

### `create_mission(goal, company_id=None, summary=None, constraints=None, source_artifacts=None, origin=None, delivery=None, context_path=None, status="planning") -> str`
Creates a new mission. Validates goal is non-empty and status is valid. Returns the new mission_id (UUID).

### `_update_mission(mission_id: str, updates: dict) -> dict`
Merges updates into existing mission, validates, normalizes all list fields (constraints, source_artifacts, task_ids, items, components, connections), and writes back. Returns the updated mission.

## Task Management

### `attach_task(mission_id, task_id) -> dict`
Appends a task_id to the mission's task_ids list (if not already present).

### `mark_mission_status(mission_id, status) -> dict`
Updates the mission's status field.

### `update_mission_summary(mission_id, summary) -> dict`
Updates the mission's summary field.

### `add_source_artifact(mission_id, artifact_type, path, description=None) -> dict`
Appends a source artifact to the mission.

## Item Management (Plan Tasks)

Items are plan-level task blueprints that live on the mission before approval.

### `add_item(mission_id, goal, title=None, item_type="coding", component="", constraints=None, dependencies=None, priority=5) -> dict`
Adds a plan item to a mission. Only works in "planning" state. Each item has: item_id, title, goal, type, component, constraints, dependencies, priority.

### `remove_item(mission_id, item_id) -> dict`
Removes an item and cleans up dependency references to it.

### `update_item(mission_id, item_id, updates) -> dict`
Updates fields on an existing item.

## Planning Workflow

### `mark_planned(mission_id) -> dict`
Transitions `planning -> planned`. Requires at least one item.

### `reopen_planning(mission_id) -> dict`
Transitions `planned -> planning` for further edits.

### `approve_mission(mission_id) -> dict`
**The critical workflow function.** Transitions `planning/planned -> active`. Step by step:

1. Validates mission is in planning/planned state with items
2. Creates component records in the database from `mission.components`
3. Creates connection records from `mission.connections`
4. Computes dependency depth for priority ordering using `_compute_dep_depth()`
5. Enqueues tasks from items with adjusted priorities
6. Attaches each task to its component
7. Marks mission as active
8. Returns `{mission_id, task_ids, component_name_to_id}`

### `compute_mission_progress(mission_id) -> dict`
Returns `{"completed": N, "total": N, "percent": float}` based on task statuses.

## Deployment Workflow

### `mark_deployed(mission_id) -> dict`
Transitions `complete -> deployed`.

### `mark_undeployed(mission_id) -> dict`
Transitions `deployed -> complete`.

## Internal Helpers

### `_compute_dep_depth(items) -> dict[str, int]`
Computes dependency depth using recursive DFS with cycle detection. Items with deeper dependencies get lower effective priority so they run after their dependencies.

### `_normalize_item(item) -> dict`
Normalizes a single plan item: validates goal is non-empty, generates item_id if missing, clamps fields to expected types.

### `_row_to_mission(row) -> dict`
Converts SQLite row to mission dict, parsing all JSON-stored list fields.
