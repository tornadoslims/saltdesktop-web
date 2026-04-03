# API Reference

Full API documentation for the SaltAgent Python library.

## Public API

The main entry points are available directly from the `salt_agent` package:

```python
from salt_agent import (
    # Factory
    create_agent,

    # Core classes
    SaltAgent,
    AgentConfig,

    # Events
    AgentEvent,
    TextChunk,
    ToolUse,
    ToolStart,
    ToolEnd,
    AgentComplete,
    AgentError,
    ContextCompacted,
    SubagentSpawned,
    SubagentComplete,
    FileSnapshotted,

    # Tools
    Tool,
    ToolDefinition,
    ToolParam,
    ToolRegistry,

    # Hooks
    HookEngine,
    HookResult,

    # Memory
    MemorySystem,

    # Permissions
    PermissionRule,
    PermissionSystem,
    SecurityClassifier,

    # Persistence
    SessionPersistence,

    # Subagents & Tasks
    SubagentManager,
    Task,
    TaskManager,
    TaskStatus,

    # Plugins
    PluginManager,
    SaltPlugin,

    # Context
    ContextManager,
    FileHistory,

    # Compaction
    needs_compaction,
    compact_context,

    # Built-in tools
    GitStatusTool,
    GitDiffTool,
    GitCommitTool,
    TodoWriteTool,
)
```

## Module Map

| Module | Contents |
|--------|----------|
| [SaltAgent](salt-agent.md) | Core agent class |
| [AgentConfig](config.md) | Configuration dataclass |
| [Events](events.md) | Event types |
| [Tools](tools.md) | Tool base classes and registry |
| [Hooks](hooks.md) | Hook engine and result types |

## Quick Links

- [Embedding guide](../embedding.md) -- practical usage examples
- [Architecture](../architecture.md) -- how it all fits together
- [Custom Tools](../tools/custom-tools.md) -- build your own tools
- [Custom Providers](../providers/custom-provider.md) -- connect to any LLM
