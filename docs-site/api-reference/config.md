# AgentConfig

Configuration dataclass for SaltAgent.

## Definition

```python
@dataclass
class AgentConfig:
    provider: str = "anthropic"
    model: str = ""
    api_key: str = ""
    max_turns: int = 30
    max_tokens: int = 4096
    temperature: float = 0.0
    working_directory: str = "."
    system_prompt: str = ""
    context_window: int = 200_000
    bash_timeout: int = 30
    max_tool_result_chars: int = 10_000
    persist: bool = True
    session_id: str = ""
    sessions_dir: str = ""
    memory_dir: str = ""
    permission_rules: list | None = None
    permission_ask_callback: object = None
    include_web_tools: bool = True
    web_extractor: str = "trafilatura"
    auto_mode: bool = False
    fallback_model: str = ""
    plan_mode: bool = False
    coordinator_mode: bool = False
    include_git_tools: bool = True
    plugin_dirs: list = field(default_factory=list)
    enable_mcp: bool = True
    mcp_config_path: str = ""
    skill_dirs: list = field(default_factory=list)
    max_budget_usd: float = 0.0
    show_suggestions: bool = False
    bash_sandbox: object = None
```

## Fields

### Provider & Model

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | str | `"anthropic"` | LLM provider: `"anthropic"` or `"openai"` |
| `model` | str | `""` | Model name. Empty = provider default (`claude-sonnet-4-20250514` or `gpt-4o`) |
| `api_key` | str | `""` | API key. Empty = read from `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` env var |
| `fallback_model` | str | `""` | Switch to this model when the primary fails |

### Limits

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_turns` | int | `30` | Maximum turns per `run()` call |
| `max_tokens` | int | `4096` | Max output tokens per LLM call |
| `temperature` | float | `0.0` | Sampling temperature |
| `context_window` | int | `200000` | Context window size in tokens |
| `bash_timeout` | int | `30` | Bash command timeout in seconds |
| `max_tool_result_chars` | int | `10000` | Max characters per tool result |
| `max_budget_usd` | float | `0.0` | Budget limit in USD (0 = unlimited) |

### Paths

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `working_directory` | str | `"."` | Working directory for file tools and bash |
| `sessions_dir` | str | `""` | Session storage dir (default: `~/.s_code/sessions`) |
| `memory_dir` | str | `""` | Memory storage dir (default: `~/.s_code/memory`) |
| `mcp_config_path` | str | `""` | Override `.mcp.json` location |

### Mode Flags

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `auto_mode` | bool | `False` | Skip all permission prompts |
| `plan_mode` | bool | `False` | Agent must plan before executing tools |
| `coordinator_mode` | bool | `False` | Strips write/execute tools, keeps delegation only |

### Feature Toggles

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `persist` | bool | `True` | Enable session persistence |
| `session_id` | str | `""` | Session ID (auto-generated UUID if empty) |
| `include_web_tools` | bool | `True` | Register WebFetch and WebSearch tools |
| `web_extractor` | str | `"trafilatura"` | HTML extraction: `"trafilatura"`, `"readability"`, or `"regex"` |
| `include_git_tools` | bool | `True` | Register git_status, git_diff, git_commit tools |
| `enable_mcp` | bool | `True` | Auto-discover MCP servers from `.mcp.json` |
| `show_suggestions` | bool | `False` | Show follow-up suggestions after each turn |

### Extensibility

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `system_prompt` | str | `""` | Additional system prompt text |
| `permission_rules` | list\|None | `None` | Custom `PermissionRule` list (None = defaults) |
| `permission_ask_callback` | callable\|None | `None` | Callback for permission prompts |
| `plugin_dirs` | list | `[]` | Directories to scan for plugins |
| `skill_dirs` | list | `[]` | Additional skill directories |
| `bash_sandbox` | BashSandbox\|None | `None` | Bash execution sandbox configuration |

## Usage

```python
from salt_agent import AgentConfig, SaltAgent

# Direct construction
config = AgentConfig(
    provider="openai",
    model="gpt-4o",
    working_directory="/my/project",
    auto_mode=True,
    max_budget_usd=5.0,
)
agent = SaltAgent(config)

# Via create_agent (all fields passed as kwargs)
from salt_agent import create_agent
agent = create_agent(provider="openai", model="gpt-4o", auto_mode=True)
```
