# Session Persistence

SaltAgent saves conversation checkpoints to JSONL files for crash recovery and session resume.

## How It Works

Before every LLM API call, a checkpoint is written to `~/.s_code/sessions/{session_id}.jsonl`. If the process crashes mid-turn, the conversation can be resumed from the last checkpoint.

### Checkpoint Format

```json
{"type": "checkpoint", "messages": [...], "system": "...", "metadata": {}, "timestamp": "2026-03-30T12:00:00Z"}
```

### Event Format

Tool uses, completions, and other events are also logged:

```json
{"type": "tool_use", "data": {"tool_name": "read", "file_path": "/app.py"}, "timestamp": "..."}
```

## Session Resume

```python
from salt_agent import SaltAgent, AgentConfig

# Resume by session ID
agent, messages, system = SaltAgent.resume("abc-123-def")

# Continue the conversation
async for event in agent.run("Continue from where we left off"):
    ...
```

From the CLI:

```
salt> /resume abc-123-def
```

## Session Listing

```python
persistence = agent.persistence
sessions = persistence.list_sessions()
for s in sessions:
    print(f"{s['session_id']} -- {s['size']} bytes")
```

From the CLI:

```
salt> /sessions
```

## Session Search

Search across all sessions for matching content:

```python
results = persistence.search_sessions("FastAPI endpoint", max_results=5)
for r in results:
    print(f"Session {r['session_id']} line {r['line']}: {r['preview']}")
```

From the CLI:

```
salt> /search FastAPI endpoint
```

The search uses an inverted index (`SessionSearchIndex`) for fast full-text search across all session files.

## Concurrent Session Detection

SaltAgent detects when another instance is using the same sessions directory:

1. On startup, it checks `~/.s_code/sessions/.lock`
2. If a lock exists with a live PID, a warning is issued
3. Otherwise, it writes its own lock

```python
conflict = persistence.check_concurrent_session()
if conflict:
    print(f"Another session is running (PID {conflict['pid']})")
```

The lock is released automatically on exit:

```python
persistence.release_lock()
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `persist` | `True` | Enable session persistence |
| `session_id` | auto-generated UUID | Session identifier |
| `sessions_dir` | `~/.s_code/sessions` | Storage directory |

To disable persistence:

```python
agent = create_agent(persist=False)
```

## Events

| Event | When |
|-------|------|
| `session_start` | New session begins |
| `session_resume` | Session resumed from checkpoint |
| `session_end` | Session ends |
