# runtime/jb_builder.py

**Path:** `runtime/jb_builder.py`
**Purpose:** Component builder that uses Claude Code CLI to build components. Spawns `claude` in `--print` mode with JSON output, parses results, and updates component/task status.

## Constants

- `CLAUDE_CLI`: `"claude"` -- the CLI binary name
- `COMPONENTS_DIR`: `BASE_DIR / "components"` -- where built component files are written
- `BUILD_TIMEOUT`: `300` (5 minutes)
- `BUILDER_SYSTEM_PROMPT`: Multi-line prompt instructing Claude Code to create `main.py`, `contract.py`, and `test_main.py` with specific conventions (run() function, summary key, CredentialStore usage)

## Functions

### `build_component_sync(task, component, mission) -> dict`

**The core builder function.** Spawns Claude Code CLI synchronously to build a single component. Detailed flow:

1. Slugifies the component name for the directory
2. Creates target directory under `COMPONENTS_DIR`
3. Builds prompt via `_build_prompt()`
4. Updates task status to "running" and component status to "building"
5. Emits "task.building" event
6. Runs CLI: `claude -p <prompt> --output-format json --dangerously-skip-permissions --append-system-prompt <system>`
7. On success (main.py exists): counts lines, lists files, extracts decisions, updates component to "built", task to "complete", emits "task.complete"
8. On failure (no main.py, timeout, exception): marks both task and component as failed, emits "task.failed"

Returns: `{"status": "complete"|"failed", "output": str, "decisions": str, "files": list, "lines": int, "directory": str}`

### `dispatch_build_tasks(mission_id) -> list[dict]`
Dispatches all pending/dispatched tasks for a mission. For each task:
1. Resolves the matching component (by component_id, name, or fuzzy name match)
2. Calls `build_component_sync()`
3. If all complete, emits "mission.built" event

### `_slugify(name) -> str`
Converts component name to directory-safe slug (lowercase, spaces/hyphens to underscores).

### `_extract_decisions(output) -> str`
Searches Claude Code output for a "DECISIONS:" section and extracts up to 1000 chars.

### `_build_prompt(task, component, mission, target_dir) -> str`
Constructs the prompt sent to Claude Code CLI. Includes: goal, component type, contract details (input/output types, config fields, schemas), mission context, constraints.

### `_mark_build_failed(task_id, component_id, comp_name, error) -> None`
Marks both the task (status="failed") and component (status="failing") as failed. Emits "task.failed" event.
