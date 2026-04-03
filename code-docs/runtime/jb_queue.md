# runtime/jb_queue.py

**Path:** `runtime/jb_queue.py`
**Purpose:** Task queue CRUD. Tasks flow through statuses: pending -> dispatched -> running -> complete/failed. Priority-sorted dispatch.

## Imports

| Import | Used For |
|--------|----------|
| `json`, `deepcopy` | Payload handling |
| `uuid4` | Task ID generation |
| `utc_now_iso`, `DATA_DIR`, `JsonStore` | Timestamps, paths, legacy storage |
| `get_db`, `_json_dumps`, `_json_loads` | SQLite operations |

## Constants

- `QUEUE_FILE`: Legacy JSON file path (`DATA_DIR / "jb_queue.json"`)
- `VALID_STATUSES`: `{"pending", "dispatched", "running", "in_progress", "complete", "failed", "suspect", "needs_review"}`

## Key Functions

### `list_tasks() -> list[dict]`
Returns all tasks from the `tasks` table, parsing JSON fields (origin, delivery, external_process, payload).

### `get_task(task_id: str) -> dict | None`
Fetches a single task by ID. Returns `None` if not found.

### `enqueue(task: dict) -> str`
Validates and normalizes a task dict, inserts it into the database. Returns the new task ID (UUID). Sets `created_at` and `updated_at` to now.

### `get_pending() -> list[dict]`
Returns tasks with status `"pending"`, ordered by `priority DESC, created_at ASC` (highest priority first, then oldest).

### `get_dispatched() -> list[dict]` / `get_running() -> list[dict]`
Returns tasks filtered by the respective status.

### `_update_task(task_id: str, updates: dict) -> dict`
Merges updates into the existing task, re-normalizes, and writes back. Preserves original `id` and `created_at`. Updates `updated_at` to now.

### Status transition functions:
- **`mark_dispatched(task_id, assigned_to=None)`** -- Sets status to "dispatched"
- **`mark_running(task_id)`** -- Sets status to "running"
- **`mark_in_progress(task_id, assigned_to=None)`** -- Sets status to "in_progress"
- **`mark_complete(task_id)`** -- Sets status to "complete", clears error
- **`mark_failed(task_id, error=None, increment_retry=True)`** -- Sets status to "failed", increments retry_count
- **`mark_suspect(task_id, error=None)`** -- Sets status to "suspect"
- **`mark_needs_review(task_id, error=None)`** -- Sets status to "needs_review"

### `get_retryable() -> list[dict]`
Returns failed tasks where `retry_count < max_retries`.

### `retry_task(task_id: str) -> dict`
Moves a failed task back to pending. Validates it is failed and has retries remaining. Clears error, assigned_to, and openclaw_session_id.

### `attach_subagent_session(task_id, subagent_session_id, parent_session_id=None) -> dict`
Links a subagent session to a task for tracking.

### `attach_external_process(task_id, process_type, pid=None, status="running") -> dict`
Attaches external process metadata (type, pid, status, timestamps) to a task.

### `touch_external_process(task_id, status=None) -> dict`
Updates `last_seen` timestamp on the task's external process. Optionally updates status.

## Normalization Helpers

- **`_normalize_origin(origin)`**: Ensures origin has `surface`, `session_id`, `thread_id` fields
- **`_normalize_delivery(delivery)`**: Ensures delivery has `mode` field (default: "reply_to_origin")
- **`_normalize_external_process(external_process)`**: Ensures process has `type`, `pid`, `status`, `started_at`, `last_seen`
- **`_normalize_task(task)`**: Full task normalization with all fields, status validation
- **`_row_to_task(row)`**: Converts SQLite row to dict, parsing JSON fields
