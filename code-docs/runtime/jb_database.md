# runtime/jb_database.py

**Path:** `runtime/jb_database.py`
**Purpose:** Primary SQLite data layer for all JBCP entity storage. Uses WAL mode for concurrent reads/writes and context-managed connections.

## Imports

| Import | Used For |
|--------|----------|
| `sqlite3` | SQLite database connections and queries |
| `json` | Serializing/deserializing JSON fields stored as TEXT columns |
| `threading` | Thread-local connection storage |
| `Path` (pathlib) | File path for the database |
| `contextmanager` | The `get_db()` context manager |
| `datetime`, `timezone` | Timestamp generation for events and signals |
| `DATA_DIR` (jb_common) | Location of the database file |

## Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `DB_PATH` | `DATA_DIR / "jbcp.db"` | Default path to the SQLite database file |
| `_local` | `threading.local()` | Thread-local storage for connections (not currently used for caching) |
| `_initialized_dbs` | `set[str]` | Tracks which DB paths have had their schema created |
| `SCHEMA` | Multi-line SQL string | Complete DDL for all 11 tables and 15 indexes |

## Schema (11 Tables)

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| `companies` | `company_id TEXT` | Workspaces with name, description, status, focused mission |
| `company_mappings` | `mapping_id TEXT` | Maps external IDs (e.g., Discord channels) to company IDs |
| `missions` | `mission_id TEXT` | Missions with goal, status, items (JSON), components (JSON), connections (JSON) |
| `tasks` | `id TEXT` | Task queue with status, priority, payload (JSON), retry tracking |
| `components` | `component_id TEXT` | Component registry with type, status, contract (JSON), file tracking |
| `connections` | `connection_id TEXT` | Data/control flow edges between components |
| `services` | `service_id TEXT` | Deployed services with lifecycle, scheduling, port allocation |
| `service_runs` | `run_id TEXT` | Run history for services with duration, output, errors |
| `connectors` | `connector_id TEXT` | External service credential metadata (Gmail, Slack, etc.) |
| `signals` | `id INTEGER AUTOINCREMENT` | Agent activity signals (tool calls, LLM events) |
| `events` | `id INTEGER AUTOINCREMENT` | System events (mission created, task completed, etc.) |
| `chat_messages` | `message_id TEXT` | Planning chat history stored per mission |

## Functions

### `get_db(db_path: Path | str | None = None)` (context manager)
Returns a SQLite connection with WAL mode, `row_factory=sqlite3.Row`, and auto-commit/rollback. Auto-initializes the schema on first use for each path. On exception, rolls back; otherwise commits. Always closes the connection.

**Pragmas set:** `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`

### `_do_init(path: str)`
Internal function that creates all tables by executing the `SCHEMA` SQL. Called once per unique DB path.

### `init_db(db_path: Path | str | None = None)`
Public entry point to force-initialize the database. Called at API server startup.

### `_json_dumps(obj: Any) -> str`
Serializes a Python object to JSON string. Handles `None` by returning `"null"`. Uses `default=str` for non-serializable types.

### `_json_loads(s: str | None) -> Any`
Deserializes a JSON string. Returns `None` for empty strings, `None` inputs, or JSON decode errors.

### `log_signal(signal_data: dict[str, Any]) -> None`
Inserts a signal record into the `signals` table. Extracts ~20 known fields from the signal dict and stores remaining fields in an `extra` JSON column. The `ok` field is stored as integer (1/0/NULL).

**SQL:** `INSERT INTO signals (ts, signal, session_id, ..., extra) VALUES (?, ?, ?, ..., ?)`

### `log_event(event_type: str, **kwargs) -> None`
Inserts a system event into the `events` table. Extracts `mission_id`, `task_id`, `workspace_id` from kwargs; everything else goes into a `payload` JSON column.

**SQL:** `INSERT INTO events (ts, event_type, mission_id, task_id, workspace_id, payload) VALUES (?, ?, ?, ?, ?, ?)`

### `save_chat_message(mission_id: str, role: str, content: str) -> str`
Saves a chat message (user or assistant) to the `chat_messages` table. Returns the generated `message_id` (UUID).

### `get_chat_messages(mission_id: str, limit: int = 50) -> list[dict]`
Returns chat messages for a mission, ordered by `created_at ASC`, limited to `limit` rows.

### `clear_chat_messages(mission_id: str)`
Deletes all chat messages for a given mission.

### `query_signals(limit: int = 100, signal_type: str = None, agent_id: str = None, since: str = None) -> list[dict]`
Queries signals with optional filters. Returns results ordered by `id DESC` (newest first).
