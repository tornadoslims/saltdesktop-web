# Custom Tools

## Creating a Custom Tool

Every tool extends the `Tool` abstract base class and implements two methods:

```python
from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

class MyTool(Tool):
    def definition(self) -> ToolDefinition:
        """Return the tool's schema for the LLM."""
        return ToolDefinition(
            name="my_tool",
            description="What this tool does (shown to the LLM)",
            params=[
                ToolParam("query", "string", "The search query"),
                ToolParam("limit", "integer", "Max results", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        """Execute the tool and return the result as a string."""
        query = kwargs["query"]
        limit = kwargs.get("limit", 10)
        return f"Found {limit} results for '{query}'"
```

## ToolParam Reference

```python
@dataclass
class ToolParam:
    name: str          # Parameter name
    type: str          # "string", "integer", "boolean", "array", "object"
    description: str   # Description shown to the LLM
    required: bool = True
    enum: list[str] | None = None      # Allowed values
    default: Any = None                 # Default value
    items: dict | None = None           # Array item schema
```

### Parameter Types

| Type | JSON Schema | Python |
|------|------------|--------|
| `"string"` | `{"type": "string"}` | `str` |
| `"integer"` | `{"type": "integer"}` | `int` |
| `"boolean"` | `{"type": "boolean"}` | `bool` |
| `"array"` | `{"type": "array", "items": ...}` | `list` |
| `"object"` | `{"type": "object"}` | `dict` |

### Enum Parameters

```python
ToolParam(
    "format", "string", "Output format",
    enum=["json", "csv", "text"],
)
```

### Array Parameters

```python
ToolParam(
    "tags", "array", "List of tags",
    items={"type": "string"},
)
```

## Registering Tools

### At agent creation

```python
from salt_agent import create_agent

agent = create_agent(provider="openai")
agent.tools.register(MyTool())
```

### Via a ToolRegistry

```python
from salt_agent import ToolRegistry

registry = ToolRegistry()
registry.register(MyTool())
registry.register(AnotherTool())

# Use as the entire tool set
from salt_agent import SaltAgent, AgentConfig
agent = SaltAgent(AgentConfig(), tools=registry)
```

### Via Plugins

```python
from salt_agent import SaltPlugin

class MyPlugin(SaltPlugin):
    def name(self):
        return "my-plugin"

    def tools(self):
        return [MyTool(), AnotherTool()]
```

## Async Tools

For tools that need to yield intermediate events (streaming results, subagent coordination):

```python
class MyStreamingTool(Tool):
    def definition(self):
        return ToolDefinition(
            name="streaming_search",
            description="Search with progress updates",
            params=[ToolParam("query", "string", "Search query")],
        )

    def execute(self, **kwargs):
        # Sync fallback
        return "results..."

    def is_async(self) -> bool:
        return True

    async def async_execute(self, **kwargs):
        from salt_agent.events import TextChunk

        # Yield intermediate events
        yield {"type": "event", "event": TextChunk(text="Searching...")}

        # Do async work
        import asyncio
        await asyncio.sleep(1)

        # Yield the final result
        yield {"type": "result", "content": "Found 42 results"}
```

## Tool Format Conversion

The `ToolRegistry` handles converting tool definitions for different providers:

```python
# Anthropic format (input_schema)
anthropic_tools = registry.to_anthropic_tools()
# [{"name": "my_tool", "description": "...", "input_schema": {"type": "object", ...}}]

# OpenAI format (function calling)
openai_tools = registry.to_openai_tools()
# [{"type": "function", "function": {"name": "my_tool", "description": "...", "parameters": {...}}}]
```

## Best Practices

1. **Return strings** -- `execute()` must return a string. Serialize complex data with `json.dumps()`.
2. **Handle errors gracefully** -- return error descriptions as strings rather than raising exceptions.
3. **Keep descriptions clear** -- the LLM uses the description to decide when to use the tool.
4. **Use required=False wisely** -- mark parameters optional only when a sensible default exists.
5. **Respect the working directory** -- if your tool operates on files, resolve paths relative to the working directory.
