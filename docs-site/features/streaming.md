# Streaming Execution

SaltAgent executes safe, read-only tools **during** the LLM's response stream, before the model finishes generating. This reduces latency for multi-tool turns.

## How It Works

The `StreamingToolExecutor` manages concurrent tool execution:

1. As the LLM streams its response, `ToolUse` events are detected
2. Safe tools are submitted immediately and start running in parallel
3. Unsafe tools are queued for execution after the stream completes
4. After the stream ends, remaining tools execute
5. Results are collected in order regardless of completion time

## Safe Streaming Tools

These read-only tools can execute during the stream:

| Tool | Why It's Safe |
|------|--------------|
| `read` | Read-only file access |
| `glob` | Read-only file search |
| `grep` | Read-only content search |
| `list_files` | Read-only directory listing |
| `web_fetch` | Read-only HTTP request |
| `web_search` | Read-only search query |

All other tools (write, edit, bash, agent, etc.) are queued and executed sequentially after the stream completes.

## Usage

The streaming executor is used automatically by the agent loop:

```python
# Inside agent.run():
streaming_executor = StreamingToolExecutor(self.tools, self.hooks)

# During streaming, as ToolUse events arrive:
streaming_executor.submit(tool_use_event)

# After stream ends:
await streaming_executor.execute_remaining()
results = await streaming_executor.collect_results()
```

## PendingTool

Each queued tool is tracked as a `PendingTool`:

```python
@dataclass
class PendingTool:
    tool_use: ToolUse
    task: asyncio.Task | None = None
    result: str = ""
    success: bool = True
    started_during_stream: bool = False
    hook_blocked: bool = False
```

## Hook Integration

Hooks still fire for streaming tools:

- `pre_tool_use` fires before submission (can block)
- If blocked, the tool is marked as `hook_blocked` and a denial message is returned as the result
- `post_tool_use` fires after completion

## Benefits

- **Reduced latency:** If the model calls `read`, `grep`, and `glob` in one turn, they all start executing as soon as detected in the stream, potentially finishing before the model finishes generating
- **Maintained correctness:** Write tools still execute sequentially after the stream, ensuring proper ordering of side effects
- **Transparent:** Callers see the same event stream regardless of execution timing
