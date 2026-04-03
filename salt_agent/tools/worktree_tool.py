"""Worktree tools -- isolated git worktrees for parallel work."""

from __future__ import annotations

import subprocess
import tempfile
from typing import TYPE_CHECKING

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.config import AgentConfig


class EnterWorktreeTool(Tool):
    """Create and enter an isolated git worktree for parallel work."""

    def __init__(self, agent_config: AgentConfig) -> None:
        self._config = agent_config
        self._original_cwd: str = ""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="enter_worktree",
            description="Create an isolated git worktree. All file changes happen in the worktree, not the main repo.",
            params=[
                ToolParam("branch_name", "string", "Branch name for the worktree"),
            ],
        )

    def execute(self, **kwargs) -> str:
        branch = kwargs["branch_name"]
        worktree_dir = tempfile.mkdtemp(prefix=f"salt-wt-{branch}-")
        try:
            subprocess.run(
                ["git", "worktree", "add", worktree_dir, "-b", branch],
                cwd=self._config.working_directory,
                check=True,
                capture_output=True,
                text=True,
            )
            self._original_cwd = self._config.working_directory
            self._config.working_directory = worktree_dir
            return f"Entered worktree at {worktree_dir} on branch {branch}."
        except subprocess.CalledProcessError as e:
            return f"Failed to create worktree: {e.stderr}"


class ExitWorktreeTool(Tool):
    """Exit the current worktree and return to the main repo."""

    def __init__(self, enter_tool: EnterWorktreeTool) -> None:
        self._enter = enter_tool

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="exit_worktree",
            description="Exit the current worktree and return to the main repo.",
            params=[],
        )

    def execute(self, **kwargs) -> str:
        if self._enter._original_cwd:
            self._enter._config.working_directory = self._enter._original_cwd
            self._enter._original_cwd = ""
            return "Returned to main repo."
        return "Not in a worktree."
