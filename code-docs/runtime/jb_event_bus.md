# runtime/jb_event_bus.py

**Path:** `runtime/jb_event_bus.py`
**Purpose:** In-memory event bus for real-time UI updates. Single process, single user, no external dependencies. All JBCP mutations call `emit()`. The SSE endpoint subscribes and streams events to the frontend.

## Architecture

```
Mutation -> emit() -> asyncio.Queue(s) -> SSE endpoint -> Frontend
                  \-> JSONL file (jb_events.py)
                  \-> SQLite events table (best-effort)
```

## Functions

### `emit(event_type: str, **kwargs) -> dict`
Emits an event to all connected SSE subscribers AND writes to persistent storage. Returns the event dict.

Event format: `{type: str, timestamp: str, ...kwargs}`

Three output channels:
1. **In-memory queues**: Push to all `_subscribers` (non-blocking, drops on full queue)
2. **JSONL file**: Via `jb_events.emit_event()` for durability
3. **SQLite**: Via `jb_database.log_event()` (best-effort, failures swallowed)

### `subscribe() -> asyncio.Queue`
Creates and returns a new asyncio Queue (maxsize=1000) that receives all emitted events. Adds it to `_subscribers` list.

### `unsubscribe(q: asyncio.Queue) -> None`
Removes a subscriber queue from the list.

### `health_check() -> dict`
Returns `{status: "running", subscribers: N}`.
