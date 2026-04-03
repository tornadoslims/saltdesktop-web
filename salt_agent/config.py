"""Agent configuration."""

from dataclasses import dataclass, field


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
