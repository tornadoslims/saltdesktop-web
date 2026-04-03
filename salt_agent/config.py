"""Agent configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from salt_agent.permissions import PermissionRule


@dataclass
class AgentConfig:
    provider: str = "anthropic"  # "anthropic" | "openai"
    model: str = ""  # empty = use provider default
    api_key: str = ""  # empty = read from env
    max_turns: int = 30
    max_tokens: int = 4096
    temperature: float = 0.0
    working_directory: str = "."
    system_prompt: str = ""
    context_window: int = 200_000
    bash_timeout: int = 30  # seconds
    max_tool_result_chars: int = 10_000
    # Session persistence
    persist: bool = True
    session_id: str = ""  # auto-generated if empty
    sessions_dir: str = ""  # default: ~/.salt-agent/sessions
    # Memory
    memory_dir: str = ""  # default: ~/.salt-agent/memory
    # Permissions
    permission_rules: list | None = None  # list[PermissionRule] or None for defaults
    permission_ask_callback: object = None  # Callable or None
    # Web tools
    include_web_tools: bool = True  # Include WebFetch and WebSearch tools by default
    web_extractor: str = "trafilatura"  # "trafilatura", "readability", or "regex"
    # Auto mode — skips all permission prompts
    auto_mode: bool = False
    # Model fallback — switch to this model when primary fails
    fallback_model: str = ""
    # Plan mode — agent must write a plan before executing tools
    plan_mode: bool = False
    # Git tools — register native git status/diff/commit tools
    include_git_tools: bool = True
    # Plugin directories — discover and load SaltPlugin subclasses from these dirs
    plugin_dirs: list = field(default_factory=list)
    # MCP (Model Context Protocol) — auto-discover and connect to MCP servers from .mcp.json
    enable_mcp: bool = True
    mcp_config_path: str = ""  # Override .mcp.json location (default: working_directory/.mcp.json)
