"""Coordinator mode -- a delegation-only agent that never writes code directly.

The coordinator keeps read, search, delegation, and communication tools but
strips anything that directly modifies files or runs commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from salt_agent.tools.base import ToolRegistry

# Tools allowed in coordinator mode (read-only + delegation + communication)
COORDINATOR_TOOLS = frozenset({
    "task_create", "task_list", "task_get", "task_output", "task_stop", "task_update",
    "send_message", "ask_user",
    "todo_write",
    "read", "glob", "grep", "list_files",
    "web_search", "web_fetch",
    "skill", "tool_search",
    "enter_plan_mode", "exit_plan_mode",
    "config", "sleep",
})

# Tools EXCLUDED in coordinator mode:
# write, edit, multi_edit, bash, agent, git_status, git_diff, git_commit
# (anything that directly modifies files or runs arbitrary commands)


def apply_coordinator_mode(registry: "ToolRegistry") -> None:
    """Remove non-coordinator tools from the registry in-place."""
    to_remove = [name for name in registry.names() if name not in COORDINATOR_TOOLS]
    for name in to_remove:
        registry._tools.pop(name, None)
