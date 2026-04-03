# runtime/jb_orchestrator.py

**Path:** `runtime/jb_orchestrator.py`
**Purpose:** 5-phase orchestration loop that manages the task lifecycle: retry failed tasks, dispatch pending ones via Claude Code builder, reconcile stuck tasks, check mission lifecycle, and compact completed work.

## The 5 Phases

### Phase 1: Retry (`retry_failed`)
Finds failed tasks with retries remaining (`get_retryable()`). Moves each back to pending via `retry_task()`. Emits "task_retried" events.

### Phase 2: Dispatch (`dispatch_pending`)
Picks up all pending tasks. For each:
1. Resolves the component (by ID, name, or fuzzy name match)
2. Calls `build_component_sync()` from `jb_builder`
3. Logs success (lines of code) or failure (error)
4. Collects mission IDs that had tasks complete

Returns: set of mission IDs with completed tasks (for compaction).

### Phase 3: Reconcile (`reconcile_running`)
Checks running/dispatched tasks that may be stuck (e.g., from a crashed orchestrator run). For each:
1. Looks for `main.py` in the component's directory
2. If found: marks complete (reconciled)
3. If not found: marks failed ("Build appears to have crashed")

### Phase 4: Lifecycle (`check_lifecycles`)
Checks all active/blocked missions for auto-completion via `check_mission_lifecycle()`.

### Phase 5: Compact (`compact_completed`)
For mission IDs that had newly completed tasks, runs `compact_mission()` to update context files.

## Main Loop

### `run_once(logger)`
Executes all 5 phases in sequence. Prints summary of pending/running/retryable counts.

### `main()`
CLI entry point with `--once` flag (single pass) or continuous loop with `--interval` (default 60 seconds).

## CLI

```bash
python -m runtime.jb_orchestrator --once           # Single pass
python -m runtime.jb_orchestrator --interval 30    # Loop every 30s
```
