# SaltAgent

The core agent class that implements the iterative LLM + tool execution loop.

## Constructor

```python
class SaltAgent:
    def __init__(
        self,
        config: AgentConfig,
        tools: ToolRegistry | None = None,
    ) -> None
```

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `config` | `AgentConfig` | Agent configuration |
| `tools` | `ToolRegistry \| None` | Custom tool registry (None = default 42 tools) |

**Attributes set during construction:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `AgentConfig` | Configuration |
| `provider` | `ProviderAdapter` | LLM provider |
| `context` | `ContextManager` | Context window manager |
| `hooks` | `HookEngine` | Hook event system |
| `state` | `StateStore` | Reactive state store |
| `memory` | `MemorySystem` | Memory system |
| `persistence` | `SessionPersistence \| None` | Session persistence |
| `permissions` | `PermissionSystem` | Permission checker |
| `subagent_manager` | `SubagentManager` | Subagent factory |
| `task_manager` | `TaskManager` | Background task manager |
| `file_history` | `FileHistory` | File rewind support |
| `skill_manager` | `SkillManager` | Skill system |
| `budget` | `BudgetTracker` | Token/cost tracker |
| `tools` | `ToolRegistry` | Registered tools |
| `plugin_manager` | `PluginManager \| None` | Plugin system |
| `mcp_manager` | `MCPManager \| None` | MCP server manager |

## run()

```python
async def run(self, prompt: str) -> AsyncIterator[AgentEvent]
```

Run the agent loop, yielding events as they occur. This is the primary method for executing tasks.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `prompt` | `str` | The user's message/task |

**Yields:** `AgentEvent` subclasses:

- `TextChunk` -- model-generated text
- `ToolStart` -- tool begins executing
- `ToolEnd` -- tool finishes
- `ToolUse` -- tool call detected in stream
- `AgentComplete` -- agent finished
- `AgentError` -- error occurred
- `ContextCompacted` -- context was compacted
- `SubagentSpawned` -- subagent started
- `SubagentComplete` -- subagent finished

**Conversation persistence:** When called multiple times, messages accumulate in `_conversation_messages`, maintaining context across turns.

## resume() (classmethod)

```python
@classmethod
def resume(
    cls,
    session_id: str,
    config: AgentConfig | None = None,
    tools: ToolRegistry | None = None,
) -> tuple[SaltAgent, list[dict], str]
```

Resume a session from a persisted checkpoint.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `session_id` | `str` | Session ID to resume |
| `config` | `AgentConfig \| None` | Config override (None = defaults) |
| `tools` | `ToolRegistry \| None` | Tool override (None = defaults) |

**Returns:** `(agent, messages, system_prompt)` tuple.

**Raises:** `ValueError` if no checkpoint found.

## create_agent() (module-level factory)

```python
def create_agent(
    provider: str = "anthropic",
    model: str = "",
    working_directory: str = ".",
    system_prompt: str = "",
    **kwargs,
) -> SaltAgent
```

Convenience function to create an agent with all built-in tools.

**Parameters:**

All `AgentConfig` fields can be passed as keyword arguments. See [AgentConfig](config.md) for the full list.

**Returns:** A configured `SaltAgent` instance.

**Example:**

```python
from salt_agent import create_agent

agent = create_agent(
    provider="openai",
    model="gpt-4o",
    working_directory="/my/project",
    auto_mode=True,
    max_budget_usd=5.0,
)
```
