# runtime/jb_events.py

**Path:** `runtime/jb_events.py`
**Purpose:** Append-only JSONL event log for durable event persistence.

## Constants

- `EVENTS_FILE`: `LOG_DIR / "jbcp_events.jsonl"`

## Functions

### `emit_event(event_type, *, mission_id=None, task_id=None, payload=None) -> dict`
Appends a single JSON line to the events file. Each event: `{ts, event_type, mission_id, task_id, payload}`. Creates the log directory and file if needed.

### `read_events() -> list[dict]`
Reads all events from the JSONL file. Returns a list of parsed dicts.

### `filter_events(*, mission_id=None, task_id=None, event_type=None) -> list[dict]`
Reads all events and filters by the provided criteria. All filters are optional; unset filters match everything.
