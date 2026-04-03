# Tools API

## Tool (ABC)

The abstract base class for all tools.

```python
class Tool(ABC):
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool's schema for the LLM."""
        ...

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the tool and return the result as a string."""
        ...

    def is_async(self) -> bool:
        """Override to True for tools that yield events."""
        return False

    async def async_execute(self, **kwargs) -> AsyncIterator[dict]:
        """Async execution that can yield events. Override for streaming tools."""
        yield {"type": "result", "content": self.execute(**kwargs)}
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `definition()` | `ToolDefinition` | Tool schema for LLM |
| `execute(**kwargs)` | `str` | Execute and return result |
| `is_async()` | `bool` | Whether this tool uses async execution |
| `async_execute(**kwargs)` | `AsyncIterator[dict]` | Async execution with events |

### Async Execute Protocol

Async tools yield dicts with two types:

```python
# Intermediate event (forwarded to parent event stream)
yield {"type": "event", "event": SomeAgentEvent()}

# Final result (used as tool_result in messages)
yield {"type": "result", "content": "result text"}
```

## ToolDefinition

```python
@dataclass
class ToolDefinition:
    name: str           # Tool name (used in API calls)
    description: str    # Description shown to the LLM
    params: list[ToolParam]  # Parameter definitions
```

## ToolParam

```python
@dataclass
class ToolParam:
    name: str           # Parameter name
    type: str           # "string", "integer", "boolean", "array", "object"
    description: str    # Description for the LLM
    required: bool = True
    enum: list[str] | None = None      # Allowed values
    default: Any = None                 # Default value
    items: dict[str, Any] | None = None  # Array item schema
```

## ToolRegistry

```python
class ToolRegistry:
    def register(self, tool: Tool) -> None
    def get(self, name: str) -> Tool | None
    def list_definitions(self) -> list[ToolDefinition]
    def names(self) -> list[str]
    def to_anthropic_tools(self) -> list[dict]
    def to_openai_tools(self) -> list[dict]
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `register(tool)` | None | Register a tool |
| `get(name)` | `Tool \| None` | Get a tool by name |
| `list_definitions()` | `list[ToolDefinition]` | All tool definitions |
| `names()` | `list[str]` | All tool names |
| `to_anthropic_tools()` | `list[dict]` | Anthropic API format |
| `to_openai_tools()` | `list[dict]` | OpenAI API format |

### Anthropic Format

```python
{
    "name": "read",
    "description": "Read a file...",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "..."},
        },
        "required": ["file_path"],
    },
}
```

### OpenAI Format

```python
{
    "type": "function",
    "function": {
        "name": "read",
        "description": "Read a file...",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "..."},
            },
            "required": ["file_path"],
        },
    },
}
```

## Built-in Tools

All 42 built-in tools:

| Name | Class | Module |
|------|-------|--------|
| `read` | `ReadTool` | `tools.read` |
| `write` | `WriteTool` | `tools.write` |
| `edit` | `EditTool` | `tools.edit` |
| `multi_edit` | `MultiEditTool` | `tools.multi_edit` |
| `bash` | `BashTool` | `tools.bash` |
| `glob` | `GlobTool` | `tools.glob_tool` |
| `grep` | `GrepTool` | `tools.grep` |
| `list_files` | `ListFilesTool` | `tools.list_files` |
| `todo_write` | `TodoWriteTool` | `tools.todo` |
| `agent` | `AgentTool` | `tools.agent_tool` |
| `task_create` | `TaskCreateTool` | `tools.tasks` |
| `task_list` | `TaskListTool` | `tools.tasks` |
| `task_get` | `TaskGetTool` | `tools.tasks` |
| `task_output` | `TaskOutputTool` | `tools.tasks` |
| `task_stop` | `TaskStopTool` | `tools.tasks` |
| `task_update` | `TaskUpdateTool` | `tools.tasks` |
| `web_fetch` | `WebFetchTool` | `tools.web_fetch` |
| `web_search` | `WebSearchTool` | `tools.web_search` |
| `git_status` | `GitStatusTool` | `tools.git` |
| `git_diff` | `GitDiffTool` | `tools.git` |
| `git_commit` | `GitCommitTool` | `tools.git` |
| `skill` | `SkillTool` | `tools.skill_tool` |
| `tool_search` | `ToolSearchTool` | `tools.tool_search` |
| `ask_user` | `AskUserQuestionTool` | `tools.ask_user` |
| `enter_plan_mode` | `EnterPlanModeTool` | `tools.plan_mode_tool` |
| `exit_plan_mode` | `ExitPlanModeTool` | `tools.plan_mode_tool` |
| `sleep` | `SleepTool` | `tools.sleep_tool` |
| `config` | `ConfigTool` | `tools.config_tool` |
| `send_message` | `SendMessageTool` | `tools.message_tool` |
| `enter_worktree` | `EnterWorktreeTool` | `tools.worktree_tool` |
| `exit_worktree` | `ExitWorktreeTool` | `tools.worktree_tool` |
| `brief` | `BriefTool` | `tools.brief` |
| `repl` | `ReplTool` | `tools.repl` |
| `clipboard` | `ClipboardTool` | `tools.clipboard` |
| `open` | `OpenTool` | `tools.open_tool` |
| `notebook_edit` | `NotebookEditTool` | `tools.notebook_edit` |
| `cron_create` | `CronCreateTool` | `tools.cron` |
| `cron_list` | `CronListTool` | `tools.cron` |
| `cron_delete` | `CronDeleteTool` | `tools.cron` |
| `team_create` | `TeamCreateTool` | `tools.team` |
| `team_delete` | `TeamDeleteTool` | `tools.team` |
| `list_mcp_resources` | `ListMcpResourcesTool` | `tools.mcp_resources` |
