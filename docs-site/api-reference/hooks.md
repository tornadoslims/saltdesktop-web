# Hooks API

## HookEngine

The central event system for agent lifecycle hooks.

```python
class HookEngine:
    def on(self, event: str, callback: HookCallback) -> None
    def off(self, event: str, callback: HookCallback) -> None
    def fire(self, event: str, data: dict) -> HookResult
    async def fire_async(self, event: str, data: dict) -> HookResult
    def register_shell_hook(self, event: str, command: str) -> None
    def register_http_hook(self, event: str, url: str, timeout: float = 5.0) -> None
```

### Methods

| Method | Description |
|--------|-------------|
| `on(event, callback)` | Register a callback for an event |
| `off(event, callback)` | Remove a callback |
| `fire(event, data)` | Fire all hooks synchronously, return first non-allow result |
| `fire_async(event, data)` | Fire hooks with async support |
| `register_shell_hook(event, command)` | Register a shell command as a hook |
| `register_http_hook(event, url, timeout)` | Register an HTTP webhook |

### Callback Signature

```python
HookCallback = Callable[[dict], HookResult | None]

def my_hook(data: dict) -> HookResult | None:
    # Return None or HookResult(action="allow") to allow
    # Return HookResult(action="block", reason="...") to block
    # Return HookResult(action="modify", modified_input={...}) to modify
    return None
```

## HookResult

```python
@dataclass
class HookResult:
    action: str = "allow"           # "allow", "block", "modify"
    reason: str = ""                # Human-readable reason
    modified_input: dict | None = None  # For "modify" action
```

| Action | Effect |
|--------|--------|
| `"allow"` | Continue normally |
| `"block"` | Stop the operation, return reason as error |
| `"modify"` | Replace tool input with `modified_input` |

## ShellHook

```python
class ShellHook:
    def __init__(self, command: str)
    def __call__(self, data: dict) -> HookResult | None
```

Executes a shell command with event data as JSON on stdin. Parses JSON stdout for the response.

**Input (stdin):**
```json
{"tool_name": "bash", "tool_input": {"command": "ls -la"}}
```

**Output (stdout):**
```json
{"action": "allow", "reason": "safe command"}
```

Timeout: 5 seconds. Errors are silently caught.

## HttpHook

```python
class HttpHook:
    def __init__(self, url: str, timeout: float = 5.0)
    def __call__(self, data: dict) -> HookResult | None
```

POSTs event data as JSON to the URL. Parses JSON response.

**Request:**
```http
POST /webhooks/agent HTTP/1.1
Content-Type: application/json

{"tool_name": "bash", "tool_input": {"command": "ls -la"}}
```

**Response:**
```json
{"action": "allow", "reason": "approved"}
```

## Event Types

All 30+ event types:

### Tool Lifecycle
- `pre_tool_use` -- can block
- `post_tool_use` -- informational

### API Lifecycle
- `pre_api_call` -- can modify messages
- `post_api_call` -- informational

### Streaming
- `on_text_chunk` -- text streaming chunk

### Errors & Completion
- `on_error` -- error occurred
- `on_complete` -- agent finished

### Context
- `on_compaction` -- context was compacted
- `context_compacted` -- alias for on_compaction
- `context_emergency` -- emergency truncation

### Permissions
- `on_permission_request` -- permission needed

### Session Lifecycle
- `session_start` -- session begins
- `session_end` -- session ends
- `session_resume` -- session resumed

### Turn Lifecycle
- `turn_start` -- new turn begins
- `turn_end` -- turn completes
- `turn_cancel` -- turn cancelled

### Memory
- `memory_saved` -- memory file saved
- `memory_deleted` -- memory file deleted
- `memory_surfaced` -- memories surfaced for turn

### Subagent
- `subagent_start` -- subagent spawned
- `subagent_end` -- subagent completed

### Task
- `task_created` -- background task created
- `task_completed` -- background task finished
- `task_failed` -- background task failed

### File
- `file_written` -- file was written
- `file_edited` -- file was edited
- `file_deleted` -- file was deleted
- `file_snapshot` -- file was snapshotted

## Event Data

Each event receives a `data` dict with event-specific fields:

### pre_tool_use / post_tool_use
```python
{
    "tool_name": "bash",
    "tool_input": {"command": "ls -la"},
    "result": "...",  # post_tool_use only
}
```

### pre_api_call / post_api_call
```python
{
    "messages": [...],
    "system": "system prompt text",
}
```

### session_start / session_end
```python
{
    "session_id": "abc-123",
}
```

### turn_start / turn_end
```python
{
    "turn": 0,
}
```

### task_created
```python
{
    "task_id": "abc12345",
    "prompt": "Analyze test coverage",
}
```

### on_compaction / context_compacted
```python
{
    "old_tokens": 150000,
    "new_tokens": 45000,
}
```
