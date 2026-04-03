# runtime/jb_services.py

**Path:** `runtime/jb_services.py`
**Purpose:** Service registry for deployed workspaces. Tracks lifecycle, run history, and port allocation.

## Constants

- `VALID_SERVICE_STATUSES`: `{"stopped", "starting", "running", "error", "paused"}`
- `VALID_SERVICE_TYPES`: `{"scheduled", "daemon", "webhook", "manual"}`
- `VALID_RUN_STATUSES`: `{"running", "success", "error"}`
- `_PORT_RANGE_START`: `9000` -- Starting port for auto-allocation

## Service CRUD

### `list_services(workspace_id=None) -> list[dict]`
### `get_service(service_id) -> dict | None`
### `create_service(workspace_id, name, description="", type="manual", schedule=None, directory="", entry_point="", has_frontend=False, frontend_path=None, port=None, mission_id=None) -> str`
### `update_service(service_id, updates) -> dict`
### `mark_service_status(service_id, status) -> dict`

## Run Tracking

### `record_run(service_id, status="running", duration_ms=None, output_preview=None, error=None, tokens_used=0) -> str`
Records a service run in `service_runs` table. Also updates the service's `last_run`, `last_run_status`, `run_count`, and `error_count`. Output preview is truncated to 500 chars.

### `list_runs(service_id, limit=20) -> list[dict]`
Returns recent runs ordered by `started_at DESC`.

### `get_run(run_id) -> dict | None`

## Lifecycle

### `start_service(service_id) -> dict`
Transitions to "starting". Rejects if already running.

### `stop_service(service_id) -> dict`
Sets status to "stopped" and clears PID. Rejects if already stopped.

### `pause_service(service_id) -> dict`
Only from "running" state.

### `resume_service(service_id) -> dict`
Only from "paused" state.

## Port Management

### `allocate_port(service_id) -> int`
Returns existing port if already assigned. Otherwise finds the next available port starting from 9000 by querying all allocated ports.

### `release_port(service_id) -> None`
Sets the service's port to `None`.
