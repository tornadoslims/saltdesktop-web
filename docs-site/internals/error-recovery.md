# Error Recovery

SaltAgent includes multiple error recovery mechanisms to handle failures gracefully.

## Loop Detection

The agent detects when it's stuck repeating the same tool calls.

### How It Works

Each tool call is hashed as `tool_name:md5(input)[:8]`. The agent checks the last 6+ signatures for repeating patterns of length 1-4.

**Example detected patterns:**

- `[A, A, A, A, A, A]` -- same tool called 6 times (pattern length 1, 6 repeats)
- `[A, B, A, B, A, B]` -- alternating tools (pattern length 2, 3 repeats)
- `[A, B, C, A, B, C, A, B, C]` -- 3-tool cycle (pattern length 3, 3 repeats)

### Recovery Strategy

1. **First detection:** Inject a warning message telling the model to stop and reassess
2. **Clear signatures** so the model gets a fresh start
3. **Second detection:** Hard stop with `AgentError(recoverable=False)`

## Prompt-Too-Long Recovery

If the LLM returns a "prompt too long" error (context exceeds the model's window):

1. Emergency truncate messages to 50% of context window
2. Invalidate compaction cache
3. Retry the turn with reduced context
4. If it fails again, yield `AgentError` and stop

## API Retry

Both providers implement retry with exponential backoff:

- **Retriable errors:** Rate limits, connection errors, server errors
- **Schedule:** 1s, 2s, 4s (3 attempts)
- **During retry:** A recoverable `AgentError` is yielded so callers know what's happening

## Model Fallback

If all retries fail and `fallback_model` is configured:

1. Switch to the fallback model
2. Retry the API call
3. If the fallback also fails, yield `AgentError`

## Crash Recovery (Session Persistence)

Before every API call, a checkpoint is saved to JSONL:

1. Process crashes mid-turn
2. User restarts with `--session <id>` or `/resume <id>`
3. `SaltAgent.resume()` loads the last checkpoint
4. Conversation continues from the checkpoint

## File History (Rewind)

Before every file write/edit:

1. The original file content is snapshotted (content-addressed backup)
2. New files are tracked as "created during session"
3. `/undo` restores all files to their pre-session state and deletes created files

## Hook Safety

All hooks are wrapped in try/except:

```python
try:
    result = callback(data)
except Exception:
    pass  # hooks should not crash the agent
```

This applies to:

- `HookEngine.fire()` and `fire_async()`
- State store subscribers
- Stop hooks (memory extraction, title generation, etc.)
- Task completion callbacks

## Budget Protection

When `max_budget_usd` is set:

1. Cost is tracked from real API token counts
2. Before each API call, the budget is checked
3. If exceeded, the agent stops with `AgentError`

## Concurrent Session Protection

The persistence layer detects other running SaltAgent instances:

1. Check for a lock file with a live PID
2. If found, warn the user
3. Otherwise, write our own lock
4. Release the lock on exit

## Error Events

All errors yield `AgentError` events:

```python
@dataclass
class AgentError(AgentEvent):
    type: str = "error"
    error: str = ""
    recoverable: bool = True
```

- `recoverable=True` -- the agent will try to continue (retry, fallback, etc.)
- `recoverable=False` -- the agent has stopped (budget exceeded, loop detected, etc.)

Hooks are fired for all errors: `on_error` event with the error details.
