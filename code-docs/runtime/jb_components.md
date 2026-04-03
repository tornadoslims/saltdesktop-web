# runtime/jb_components.py

**Path:** `runtime/jb_components.py`
**Purpose:** Component registry and connection graph. Components are logical software pieces (connectors, processors, AI modules, etc.). Connections define data/control flow between them.

## Constants

- `VALID_COMPONENT_TYPES`: `{"connector", "processor", "ai", "output", "scheduler", "storage", "config"}`
- `VALID_COMPONENT_STATUSES`: `{"planned", "building", "built", "testing", "passing", "failing", "deployed"}`
- `VALID_CONNECTION_TYPES`: `{"data_flow", "control_flow"}`

## Component CRUD

### `list_components(workspace_id=None) -> list[dict]`
Lists all components, optionally filtered by workspace.

### `get_component(component_id) -> dict | None`
Fetches a single component.

### `create_component(workspace_id, name, type, description="", contract=None, directory="", files=None, dependencies=None, task_ids=None, status="planned") -> str`
Creates a new component. Returns component_id (UUID).

### `update_component(component_id, updates) -> dict`
Merges and writes back. Validates all fields.

### `mark_component_status(component_id, status) -> dict`
### `attach_task(component_id, task_id) -> dict`
### `add_file(component_id, file_path) -> dict`

## Connection CRUD

### `list_connections(workspace_id=None) -> list[dict]`
### `create_connection(workspace_id, from_id, to_id, from_output="", to_input="", type="data_flow", label=None) -> str`
### `delete_connection(connection_id) -> bool`

## Graph Generation

### `build_graph(workspace_id) -> dict`
Builds a complete graph representation with `nodes` and `edges` lists. For each component node, computes:
- `progress_percent` from linked task statuses (complete/total * 100)
- `is_active` flag (any task running/dispatched)
- `display_status` via `component_label()`
- `contract` summary (input_type, output_type, config field names)
- `metadata` (lines_of_code, file count, build progress, test status)

For each edge, auto-derives the label from the source component's `output_type` if no explicit label is set.

## Component Lifecycle

### `check_component_lifecycle(component_id) -> dict`
Checks if all linked tasks are complete and updates status accordingly. Returns `{component_id, previous_status, new_status, reason}`. Transitions `planned/building -> built` when all tasks complete.

## Contract Normalization

### `_normalize_contract(contract) -> dict`
Ensures contract has: `input_type`, `output_type` (default "Any"), `config_fields` (dict), `input_schema` (dict), `output_schema` (dict). Logs a warning if output_schema lacks a "summary" field.
