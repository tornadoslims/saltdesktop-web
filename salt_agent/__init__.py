"""SaltAgent — Salt Desktop's general-purpose agent execution engine."""

from salt_agent.agent import SaltAgent
from salt_agent.config import AgentConfig
from salt_agent.context import ContextManager
from salt_agent.compaction import compact_context, needs_compaction
from salt_agent.events import (
    AgentComplete,
    AgentError,
    AgentEvent,
    ContextCompacted,
    TextChunk,
    ToolEnd,
    ToolStart,
    ToolUse,
)
from salt_agent.hooks import HookEngine, HookResult
from salt_agent.tools.base import Tool, ToolDefinition, ToolParam, ToolRegistry
from salt_agent.tools.todo import TodoWriteTool

__all__ = [
    "SaltAgent",
    "AgentConfig",
    "ContextManager",
    "AgentEvent",
    "TextChunk",
    "ToolUse",
    "ToolStart",
    "ToolEnd",
    "AgentComplete",
    "AgentError",
    "ContextCompacted",
    "Tool",
    "ToolDefinition",
    "ToolParam",
    "ToolRegistry",
    "TodoWriteTool",
    "HookEngine",
    "HookResult",
    "needs_compaction",
    "compact_context",
    "create_agent",
]


def create_agent(
    provider: str = "anthropic",
    model: str = "",
    working_directory: str = ".",
    system_prompt: str = "",
    **kwargs,
) -> SaltAgent:
    """Convenience function to create a default agent with all built-in tools."""
    config = AgentConfig(
        provider=provider,
        model=model,
        working_directory=working_directory,
        system_prompt=system_prompt,
        **kwargs,
    )
    return SaltAgent(config)
