# Tools Overview

SaltAgent ships with 42 built-in tools organized into categories. Tools are the agent's interface to the outside world -- reading files, running commands, searching code, managing git, fetching web content, spawning subagents, and more.

## Tool Categories

| Category | Tools | Description |
|----------|-------|-------------|
| [File Tools](file-tools.md) | `read`, `write`, `edit`, `multi_edit`, `glob`, `grep`, `list_files`, `notebook_edit` | File I/O, search, and editing |
| [Bash](bash.md) | `bash` | Shell command execution with sandbox |
| [Web Tools](web-tools.md) | `web_fetch`, `web_search` | HTTP fetch and DuckDuckGo search |
| [Task Tools](task-tools.md) | `task_create`, `task_list`, `task_get`, `task_output`, `task_stop`, `task_update`, `agent` | Background tasks and subagents |
| [Git Tools](git-tools.md) | `git_status`, `git_diff`, `git_commit` | Native git operations |
| [Custom Tools](custom-tools.md) | User-defined | Build your own tools |

## Additional Tools

Beyond the categories above, SaltAgent includes:

| Tool | Description |
|------|-------------|
| `todo_write` | Manage a todo/checklist that persists across turns |
| `skill` | Invoke a skill by name (markdown prompt injection) |
| `tool_search` | Search and load deferred tool definitions |
| `ask_user` | Prompt the user for input |
| `enter_plan_mode` / `exit_plan_mode` | Toggle plan mode |
| `sleep` | Pause execution (useful in task coordination) |
| `config` | Get/set agent configuration |
| `send_message` | Send messages between agents/tasks |
| `enter_worktree` / `exit_worktree` | Git worktree management |
| `brief` | Emit a brief status message |
| `repl` | Persistent Python REPL session |
| `clipboard` | Read/write system clipboard |
| `open` | Open files/URLs in the default application |
| `cron_create` / `cron_list` / `cron_delete` | Schedule recurring tasks |
| `team_create` / `team_delete` | Multi-agent team coordination |
| `list_mcp_resources` | List MCP server resources |

## Tool Architecture

All tools implement the `Tool` abstract base class:

```python
from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

class MyTool(Tool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="my_tool",
            description="What this tool does",
            params=[
                ToolParam("arg1", "string", "Description of arg1"),
                ToolParam("arg2", "integer", "Optional arg", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        # Execute and return result as a string
        return "result"
```

### Async Tools

Tools that need to yield intermediate events (like the `agent` tool) override `is_async()` and `async_execute()`:

```python
class MyAsyncTool(Tool):
    def is_async(self) -> bool:
        return True

    async def async_execute(self, **kwargs):
        yield {"type": "event", "event": SomeEvent()}
        yield {"type": "result", "content": "final result"}
```

### Tool Registry

Tools are registered in a `ToolRegistry` which handles format conversion for different providers:

```python
registry = ToolRegistry()
registry.register(MyTool())

# Convert for Anthropic API
anthropic_tools = registry.to_anthropic_tools()

# Convert for OpenAI API
openai_tools = registry.to_openai_tools()
```

## Streaming Tool Execution

SaltAgent executes safe, read-only tools **during** the model's response stream, before it finishes generating. This reduces latency for multi-tool turns.

Safe streaming tools: `read`, `glob`, `grep`, `list_files`, `web_fetch`, `web_search`

All other tools (write, edit, bash, etc.) are queued and executed after the stream completes.
