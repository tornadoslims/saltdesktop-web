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
    sessions_dir: str = ""  # default: ~/.saltdesktop/sessions
    # Memory
    memory_dir: str = ""  # default: ~/.saltdesktop/memory
    # Permissions
    permission_rules: list | None = None  # list[PermissionRule] or None for defaults
    permission_ask_callback: object = None  # Callable or None
    # Web tools
    include_web_tools: bool = True  # Include WebFetch and WebSearch tools by default
    web_extractor: str = "trafilatura"  # "trafilatura", "readability", or "regex"
