# Hook Engine

The hook engine provides a pub/sub system for agent lifecycle events. Hooks can observe, block, or modify tool calls and other operations.

## Event Types

### Tool Lifecycle

| Event | Description | Can Block? |
|-------|------------|------------|
| `pre_tool_use` | Before a tool executes | Yes |
| `post_tool_use` | After a tool executes | No |

### API Lifecycle

| Event | Description | Can Block? |
|-------|------------|------------|
| `pre_api_call` | Before an LLM API call | Yes (can modify messages) |
| `post_api_call` | After an LLM response | No |

### Streaming

| Event | Description |
|-------|------------|
| `on_text_chunk` | Text streaming chunk |

### Session Lifecycle

| Event | Description |
|-------|------------|
| `session_start` | Agent session begins |
| `session_end` | Agent session ends |
| `session_resume` | Session resumed from checkpoint |

### Turn Lifecycle

| Event | Description |
|-------|------------|
| `turn_start` | New turn begins |
| `turn_end` | Turn completes |
| `turn_cancel` | Turn cancelled by user |

### Memory

| Event | Description |
|-------|------------|
| `memory_saved` | Memory file was saved |
| `memory_deleted` | Memory file was deleted |
| `memory_surfaced` | Memories surfaced for this turn |

### Subagent

| Event | Description |
|-------|------------|
| `subagent_start` | Subagent spawned |
| `subagent_end` | Subagent completed |

### Task

| Event | Description |
|-------|------------|
| `task_created` | Background task created |
| `task_completed` | Background task finished |
| `task_failed` | Background task failed |

### File

| Event | Description |
|-------|------------|
| `file_written` | File was written |
| `file_edited` | File was edited |
| `file_deleted` | File was deleted |
| `file_snapshot` | File was snapshotted for rewind |

### Context

| Event | Description |
|-------|------------|
| `on_compaction` | Context was compacted |
| `context_compacted` | Alias for on_compaction |
| `context_emergency` | Emergency truncation happened |

### Errors & Completion

| Event | Description |
|-------|------------|
| `on_error` | Error occurred |
| `on_complete` | Agent finished |
| `on_permission_request` | Permission needed |

## Registering Hooks

### Python Callbacks

```python
from salt_agent import HookResult

def my_hook(data: dict) -> HookResult | None:
    tool_name = data.get("tool_name", "")
    if tool_name == "bash" and "rm" in data.get("tool_input", {}).get("command", ""):
        return HookResult(action="block", reason="rm commands are blocked")
    return None  # allow

agent.hooks.on("pre_tool_use", my_hook)
```

### Shell Hooks

Execute a shell command. Input/output via JSON stdin/stdout:

```python
agent.hooks.register_shell_hook("post_tool_use", "python /path/to/logger.py")
```

The shell command receives JSON on stdin:
```json
{"tool_name": "bash", "tool_input": {"command": "ls"}}
```

It can return JSON on stdout to control the action:
```json
{"action": "allow", "reason": "looks safe"}
```

### HTTP Webhooks

POST JSON payload to a URL:

```python
agent.hooks.register_http_hook("post_tool_use", "https://my-app.com/webhooks/agent")
```

The webhook receives the event data as JSON and can return:
```json
{"action": "block", "reason": "policy violation"}
```

Timeout: 5 seconds (configurable).

## HookResult

```python
@dataclass
class HookResult:
    action: str = "allow"       # "allow", "block", "modify"
    reason: str = ""            # Human-readable reason
    modified_input: dict | None = None  # For "modify" action
```

| Action | Effect |
|--------|--------|
| `allow` | Continue normally |
| `block` | Stop the tool/operation, return reason as error |
| `modify` | Replace tool input with `modified_input` |

## Hook Resolution

When multiple hooks are registered for the same event:

1. Hooks fire in registration order
2. The first non-allow result wins
3. If all hooks return `allow` (or `None`), the operation proceeds
4. Exceptions in hooks are silently caught -- hooks must never crash the agent

## Async Hooks

The `fire_async()` method supports async callbacks:

```python
async def my_async_hook(data: dict) -> HookResult | None:
    result = await check_external_policy(data)
    return HookResult(action=result)

agent.hooks.on("pre_tool_use", my_async_hook)
```

## Built-in Hooks

SaltAgent registers these hooks automatically:

1. **Permission hook** -- checks every tool call against the permission system
2. **File history hook** -- snapshots files before writes/edits for rewind support
