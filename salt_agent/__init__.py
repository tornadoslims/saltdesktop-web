"""SaltAgent — a standalone CLI agent for autonomous coding tasks."""

from salt_agent.agent import SaltAgent
from salt_agent.config import AgentConfig
from salt_agent.context import ContextManager
from salt_agent.compaction import compact_context, needs_compaction
from salt_agent.events import (
    AgentComplete,
    AgentError,
    AgentEvent,
    ContextCompacted,
    FileSnapshotted,
    SubagentComplete,
    SubagentSpawned,
    TextChunk,
    ToolEnd,
    ToolStart,
    ToolUse,
)
from salt_agent.file_history import FileHistory
from salt_agent.hooks import HookEngine, HookResult
from salt_agent.memory import MemorySystem
from salt_agent.permissions import PermissionRule, PermissionSystem
from salt_agent.persistence import SessionPersistence
from salt_agent.subagent import SubagentManager
from salt_agent.tasks import Task, TaskManager, TaskStatus
from salt_agent.plugins import PluginManager, SaltPlugin
from salt_agent.security import SecurityClassifier
from salt_agent.tools.base import Tool, ToolDefinition, ToolParam, ToolRegistry
from salt_agent.tools.git import GitCommitTool, GitDiffTool, GitStatusTool
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
    "FileSnapshotted",
    "SubagentSpawned",
    "SubagentComplete",
    "FileHistory",
    "SubagentManager",
    "Task",
    "TaskManager",
    "TaskStatus",
    "Tool",
    "ToolDefinition",
    "ToolParam",
    "ToolRegistry",
    "TodoWriteTool",
    "HookEngine",
    "HookResult",
    "MemorySystem",
    "PermissionRule",
    "PermissionSystem",
    "SecurityClassifier",
    "PluginManager",
    "SaltPlugin",
    "GitStatusTool",
    "GitDiffTool",
    "GitCommitTool",
    "SessionPersistence",
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
