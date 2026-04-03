# Events

All events emitted by `SaltAgent.run()` are dataclasses inheriting from `AgentEvent`.

## Base Class

```python
@dataclass
class AgentEvent:
    type: str
    data: dict[str, Any] | None = None
```

## Event Types

### TextChunk

Model-generated text, streamed incrementally.

```python
@dataclass
class TextChunk(AgentEvent):
    type: str = "text_chunk"
    text: str = ""
```

### ToolUse

Tool call detected in the model's response stream.

```python
@dataclass
class ToolUse(AgentEvent):
    type: str = "tool_use"
    tool_id: str = ""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
```

### ToolStart

Tool begins executing (fired after hook checks pass).

```python
@dataclass
class ToolStart(AgentEvent):
    type: str = "tool_start"
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
```

### ToolEnd

Tool finished executing.

```python
@dataclass
class ToolEnd(AgentEvent):
    type: str = "tool_end"
    tool_name: str = ""
    result: str = ""
    success: bool = True
```

### AgentComplete

Agent finished all work.

```python
@dataclass
class AgentComplete(AgentEvent):
    type: str = "complete"
    final_text: str = ""
    turns: int = 0
    tools_used: list[str] = field(default_factory=list)
```

### AgentError

Error occurred during execution.

```python
@dataclass
class AgentError(AgentEvent):
    type: str = "error"
    error: str = ""
    recoverable: bool = True
```

- `recoverable=True` -- the agent will try to continue (retry, fallback)
- `recoverable=False` -- the agent has stopped (budget exceeded, loop, etc.)

### ContextCompacted

Context was compacted to fit the context window.

```python
@dataclass
class ContextCompacted(AgentEvent):
    type: str = "compaction"
    old_tokens: int = 0
    new_tokens: int = 0
```

### SubagentSpawned

A subagent was created and started.

```python
@dataclass
class SubagentSpawned(AgentEvent):
    type: str = "subagent_spawned"
    mode: str = ""
    prompt: str = ""
```

### SubagentComplete

A subagent finished its work.

```python
@dataclass
class SubagentComplete(AgentEvent):
    type: str = "subagent_complete"
    mode: str = ""
    result: str = ""
```

### FileSnapshotted

A file was backed up before modification (for rewind support).

```python
@dataclass
class FileSnapshotted(AgentEvent):
    type: str = "file_snapshotted"
    file_path: str = ""
```

## Consuming Events

```python
async for event in agent.run("Fix the tests"):
    match event.type:
        case "text_chunk":
            print(event.text, end="")
        case "tool_start":
            print(f"[{event.tool_name}]")
        case "tool_end":
            if not event.success:
                print(f"Tool failed: {event.result}")
        case "complete":
            print(f"\nDone in {event.turns} turns")
            print(f"Tools used: {event.tools_used}")
        case "error":
            print(f"Error: {event.error}")
            if not event.recoverable:
                break
        case "compaction":
            print(f"Compacted: {event.old_tokens} -> {event.new_tokens} tokens")
```

## Type Checking

Events can be type-checked with `isinstance`:

```python
from salt_agent import TextChunk, AgentComplete, AgentError

async for event in agent.run(prompt):
    if isinstance(event, TextChunk):
        handle_text(event.text)
    elif isinstance(event, AgentComplete):
        handle_complete(event.final_text, event.turns)
    elif isinstance(event, AgentError) and not event.recoverable:
        handle_fatal_error(event.error)
```
