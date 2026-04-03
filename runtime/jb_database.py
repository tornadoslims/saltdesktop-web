"""
JBCP SQLite Database — Primary data layer.

All JBCP entity storage goes through this module. Uses WAL mode for
concurrent reads/writes and thread-local connections.
"""
import sqlite3
import json
import threading
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from runtime.jb_common import DATA_DIR

DB_PATH = DATA_DIR / "jbcp.db"

# Thread-local storage for connections
_local = threading.local()

# Track which DB paths have been initialized
_initialized_dbs: set[str] = set()

SCHEMA = """
-- Companies/Workspaces
CREATE TABLE IF NOT EXISTS companies (
    company_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active',
    focused_mission_id TEXT,
    mission_ids TEXT DEFAULT '[]',
    company_context_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Company-to-external mappings
CREATE TABLE IF NOT EXISTS company_mappings (
    mapping_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source, external_id)
);

-- Missions
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    company_id TEXT,
    goal TEXT NOT NULL,
    summary TEXT,
    status TEXT DEFAULT 'planning',
    constraints TEXT DEFAULT '[]',
    source_artifacts TEXT DEFAULT '[]',
    task_ids TEXT DEFAULT '[]',
    items TEXT DEFAULT '[]',
    components TEXT DEFAULT '[]',
    connections TEXT DEFAULT '[]',
    origin TEXT,
    delivery TEXT,
    context_path TEXT,
    _previous_draft TEXT,
    _last_diff TEXT,
    _last_generated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    company_id TEXT,
    mission_id TEXT,
    type TEXT DEFAULT 'coding',
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 5,
    assigned_to TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    origin TEXT DEFAULT '{}',
    delivery TEXT DEFAULT '{}',
    openclaw_session_id TEXT,
    parent_session_id TEXT,
    subagent_session_id TEXT,
    external_process TEXT,
    payload TEXT DEFAULT '{}'
);

-- Components
CREATE TABLE IF NOT EXISTS components (
    component_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'processor',
    status TEXT DEFAULT 'planned',
    description TEXT DEFAULT '',
    contract TEXT DEFAULT '{}',
    directory TEXT DEFAULT '',
    files TEXT DEFAULT '[]',
    dependencies TEXT DEFAULT '[]',
    task_ids TEXT DEFAULT '[]',
    lines_of_code INTEGER DEFAULT 0,
    mission_id TEXT,
    built_by_agent TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Component connections
CREATE TABLE IF NOT EXISTS connections (
    connection_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    from_component_id TEXT NOT NULL,
    to_component_id TEXT NOT NULL,
    from_output TEXT DEFAULT '',
    to_input TEXT DEFAULT '',
    type TEXT DEFAULT 'data_flow',
    label TEXT,
    created_at TEXT NOT NULL
);

-- Services
CREATE TABLE IF NOT EXISTS services (
    service_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'stopped',
    type TEXT DEFAULT 'manual',
    schedule TEXT,
    directory TEXT DEFAULT '',
    entry_point TEXT DEFAULT '',
    has_frontend INTEGER DEFAULT 0,
    frontend_path TEXT,
    port INTEGER,
    pid INTEGER,
    last_run TEXT,
    last_run_status TEXT,
    last_run_duration_ms INTEGER,
    next_run TEXT,
    health TEXT DEFAULT 'unknown',
    run_count INTEGER DEFAULT 0,
    mission_id TEXT,
    last_run_summary TEXT,
    error_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Service runs
CREATE TABLE IF NOT EXISTS service_runs (
    run_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT DEFAULT 'running',
    duration_ms INTEGER,
    output_preview TEXT,
    summary_chain TEXT,
    error TEXT,
    tokens_used INTEGER DEFAULT 0
);

-- Connectors (credential metadata)
CREATE TABLE IF NOT EXISTS connectors (
    connector_id TEXT PRIMARY KEY,
    service_type TEXT NOT NULL,
    label TEXT NOT NULL,
    account_id TEXT,
    credential_file TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    scope TEXT,
    connected_at TEXT NOT NULL,
    last_used_at TEXT,
    metadata TEXT DEFAULT '{}'
);

-- Signals
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    signal TEXT NOT NULL,
    session_id TEXT,
    session_key TEXT,
    agent_id TEXT,
    run_id TEXT,
    tool TEXT,
    source TEXT,
    label TEXT,
    model TEXT,
    provider TEXT,
    ok INTEGER,
    error TEXT,
    duration_ms INTEGER,
    result_preview TEXT,
    result_chars INTEGER,
    text_preview TEXT,
    text_chars INTEGER,
    usage TEXT,
    prompt_chars INTEGER,
    history_count INTEGER,
    params TEXT,
    extra TEXT DEFAULT '{}'
);

-- Events
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    mission_id TEXT,
    task_id TEXT,
    workspace_id TEXT,
    payload TEXT DEFAULT '{}'
);

-- Chat messages (planning mode — direct Anthropic API)
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_mission ON chat_messages(mission_id, created_at);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts);
CREATE INDEX IF NOT EXISTS idx_signals_signal ON signals(signal);
CREATE INDEX IF NOT EXISTS idx_signals_agent ON signals(agent_id);
CREATE INDEX IF NOT EXISTS idx_signals_session ON signals(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_mission ON tasks(mission_id);
CREATE INDEX IF NOT EXISTS idx_tasks_company ON tasks(company_id);
CREATE INDEX IF NOT EXISTS idx_missions_company ON missions(company_id);
CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_components_workspace ON components(workspace_id);
CREATE INDEX IF NOT EXISTS idx_connections_workspace ON connections(workspace_id);
CREATE INDEX IF NOT EXISTS idx_services_workspace ON services(workspace_id);
CREATE INDEX IF NOT EXISTS idx_service_runs_service ON service_runs(service_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_company_mappings_lookup ON company_mappings(source, external_id);
"""


@contextmanager
def get_db(db_path: Path | str | None = None):
    """Get a SQLite connection with WAL mode, row_factory, and auto-commit/rollback."""
    path = str(db_path or DB_PATH)

    # Auto-initialize on first use for this path
    if path not in _initialized_dbs:
        _do_init(path)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _do_init(path: str):
    """Internal: create tables for a given DB path."""
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    _initialized_dbs.add(path)


def init_db(db_path: Path | str | None = None):
    """Create all tables if they don't exist."""
    path = str(db_path or DB_PATH)
    _do_init(path)


def _json_dumps(obj: Any) -> str:
    """Serialize to JSON string, handling None."""
    if obj is None:
        return "null"
    return json.dumps(obj, default=str)


def _json_loads(s: str | None) -> Any:
    """Deserialize JSON string, handling None and empty."""
    if s is None or s == "":
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Signal and event helpers (kept from original for backward compat)
# ---------------------------------------------------------------------------

def log_signal(signal_data: dict[str, Any]) -> None:
    """Insert a signal into the database."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO signals (ts, signal, session_id, session_key, agent_id, run_id,
                tool, source, label, model, provider, ok, error, duration_ms,
                result_preview, result_chars, text_preview, text_chars, usage,
                prompt_chars, history_count, params, extra)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal_data.get("ts", datetime.now(timezone.utc).isoformat()),
            signal_data.get("signal", ""),
            signal_data.get("session_id"),
            signal_data.get("session_key"),
            signal_data.get("agent_id"),
            signal_data.get("run_id"),
            signal_data.get("tool"),
            signal_data.get("source"),
            signal_data.get("label"),
            signal_data.get("model"),
            signal_data.get("provider"),
            1 if signal_data.get("ok") else (0 if signal_data.get("ok") is False else None),
            signal_data.get("error"),
            signal_data.get("duration_ms"),
            signal_data.get("result_preview"),
            signal_data.get("result_chars"),
            signal_data.get("text_preview"),
            signal_data.get("text_chars"),
            json.dumps(signal_data.get("usage")) if signal_data.get("usage") else None,
            signal_data.get("prompt_chars"),
            signal_data.get("history_count"),
            json.dumps(signal_data.get("params")) if signal_data.get("params") else None,
            json.dumps({k: v for k, v in signal_data.items()
                       if k not in ("ts", "signal", "session_id", "session_key", "agent_id",
                                   "run_id", "tool", "source", "label", "model", "provider",
                                   "ok", "error", "duration_ms", "result_preview", "result_chars",
                                   "text_preview", "text_chars", "usage", "prompt_chars",
                                   "history_count", "params")}),
        ))


def log_event(event_type: str, **kwargs) -> None:
    """Insert a system event into the database."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO events (ts, event_type, mission_id, task_id, workspace_id, payload)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            event_type,
            kwargs.get("mission_id"),
            kwargs.get("task_id"),
            kwargs.get("workspace_id"),
            json.dumps({k: v for k, v in kwargs.items()
                       if k not in ("mission_id", "task_id", "workspace_id")}, default=str),
        ))


# ---------------------------------------------------------------------------
# Chat message helpers (planning mode — direct Anthropic API)
# ---------------------------------------------------------------------------

def save_chat_message(mission_id: str, role: str, content: str) -> str:
    """Save a chat message and return its ID."""
    from uuid import uuid4
    message_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO chat_messages (message_id, mission_id, role, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (message_id, mission_id, role, content, now),
        )
    return message_id


def get_chat_messages(mission_id: str, limit: int = 50) -> list[dict]:
    """Get chat messages for a mission, ordered by created_at."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT message_id, mission_id, role, content, created_at
               FROM chat_messages
               WHERE mission_id = ?
               ORDER BY created_at ASC
               LIMIT ?""",
            (mission_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def clear_chat_messages(mission_id: str):
    """Delete all messages for a mission."""
    with get_db() as conn:
        conn.execute("DELETE FROM chat_messages WHERE mission_id = ?", (mission_id,))


def query_signals(limit: int = 100, signal_type: str = None,
                  agent_id: str = None, since: str = None) -> list[dict]:
    """Query signals with optional filters."""
    with get_db() as conn:
        query = "SELECT * FROM signals WHERE 1=1"
        params = []
        if signal_type:
            query += " AND signal = ?"
            params.append(signal_type)
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if since:
            query += " AND ts > ?"
            params.append(since)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
