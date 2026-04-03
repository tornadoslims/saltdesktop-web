# runtime/jb_compaction.py

**Path:** `runtime/jb_compaction.py`
**Purpose:** Compaction agent that updates `mission_context.md` after tasks complete. Also handles mission lifecycle (auto-complete when all tasks done).

## Functions

### `compact_mission(mission_id) -> dict`
Updates the mission context file based on task progress:
1. Gathers all linked tasks and categorizes as completed/pending/failed
2. Reads current context file
3. Writes updated markdown with sections: Goal, Status (counts), Completed Work, Remaining Work, Failed Tasks
4. Emits "mission_compacted" event

Returns: `{ok, mission_id, compacted}` or `{ok: False, error}`

### `check_mission_lifecycle(mission_id) -> dict`
Checks if a mission should be auto-completed or marked failed:
- All tasks complete -> mission complete
- All tasks terminal (complete/failed) with any failed -> mission failed (unless retries available)
- Any active tasks -> still active

Emits "mission_completed" or "mission_failed" events on transitions.

Returns: `{ok, changed: bool, status}`

### `run_compaction_sweep() -> list[dict]`
Sweeps all active/blocked missions:
1. Checks lifecycle for each (auto-complete/fail)
2. Runs compaction for missions with completed tasks

## CLI

```bash
python -m runtime.jb_compaction --mission-id <UUID>     # Compact one mission
python -m runtime.jb_compaction --sweep                  # Sweep all active missions
python -m runtime.jb_compaction --sweep --lifecycle-only # Only check lifecycle
```
