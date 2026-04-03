# runtime/jb_swarm.py

**Path:** `runtime/jb_swarm.py`
**Purpose:** Read-only view layer that composes task queue, components, signals, and services into the "My AI" dashboard view. No new state is managed here -- purely a join/transform layer.

## Functions

### `get_swarm(mission_id=None) -> dict`
Builds the swarm view with two sections:
- `building`: Workers grouped by mission (active + recently completed tasks)
- `running`: Active services

### `_build_workers_by_mission(mission_id=None) -> list[dict]`
Groups active tasks (running, dispatched, pending, in_progress) plus recently completed tasks (within 30 min) by mission. For each task, resolves:
- Role from task type (via `worker_role()`)
- Component name from payload
- Status mapping (dispatched/in_progress -> running)

Returns list of `{mission_id, mission_name, workers: [{task_id, role, role_icon, component_name, status, ...}], progress: {completed, total, percent}}`.

### `_build_running_services() -> list[dict]`
Lists running services with workspace name, formatted schedule, last_run_ago.

### `_format_schedule(schedule) -> str`
Converts cron expressions to human-friendly text:
- `*/15 * * * *` -> "every 15 minutes"
- `0 * * * *` -> "every hour"
- `0 9 * * *` -> "daily at 9:00 AM"
- `0 9 * * 1` -> "weekly on Monday at 9:00 AM"

### `_relative_time(iso_timestamp) -> str`
Converts ISO timestamp to "5 minutes ago" style string.
