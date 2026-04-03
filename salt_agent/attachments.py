"""Per-turn dynamic context injection via system-reminder blocks.

Inspired by Claude Code's utils/attachments.ts (3998 lines).
Before each model call, assembles dynamic context as <system-reminder> tags
injected into the user message.

Claude Code has ~30 attachment types. We implement the most impactful ones.

IMPORTANT: System-reminders are injected into a COPY of messages for the API
call. They are NOT saved to _conversation_messages. This prevents accumulation
across turns and avoids compaction of transient context.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from salt_agent.agent import SaltAgent


class AttachmentAssembler:
    """Assembles per-turn dynamic context as system-reminder blocks."""

    def __init__(self, agent: "SaltAgent") -> None:
        self.agent = agent

    def assemble(self) -> list[str]:
        """Generate all system-reminder blocks for this turn."""
        reminders: list[str] = []

        # 1. Date/time (always)
        reminders.append(self._date_reminder())

        # 2. Todo state
        r = self._todo_reminder()
        if r:
            reminders.append(r)

        # 3. Plan mode
        if self.agent.config.plan_mode:
            reminders.append(self._wrap(
                "You are in PLAN MODE. Create a plan using todo_write before taking action. "
                "Wait for the user to type /approve before executing."
            ))

        # 4. Auto mode
        if self.agent.config.auto_mode:
            reminders.append(self._wrap(
                "AUTO MODE is active. You have permission to execute all tools without asking."
            ))

        # 5. Git status
        r = self._git_status()
        if r:
            reminders.append(r)

        # 6. Modified files warning
        r = self._modified_files_warning()
        if r:
            reminders.append(r)

        # 7. MCP server status
        r = self._mcp_status()
        if r:
            reminders.append(r)

        # 8. Working directory
        reminders.append(self._wrap(
            f"Working directory: {self.agent.config.working_directory}"
        ))

        return reminders

    @staticmethod
    def _wrap(content: str) -> str:
        """Wrap content in system-reminder tags."""
        return f"<system-reminder>\n{content}\n</system-reminder>"

    def _date_reminder(self) -> str:
        now = datetime.now()
        return self._wrap(
            f"Current date: {now.strftime('%Y-%m-%d')}. "
            f"Current time: {now.strftime('%H:%M %Z')}."
        )

    def _todo_reminder(self) -> str:
        todo_tool = self.agent.tools.get("todo_write")
        if todo_tool and hasattr(todo_tool, "tasks") and todo_tool.tasks:
            injection = todo_tool.get_context_injection()
            if injection:
                return self._wrap(injection)
        return ""

    def _git_status(self) -> str:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "--branch"],
                cwd=self.agent.config.working_directory,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                if len(lines) > 1:  # More than just the branch line
                    branch = lines[0].replace("## ", "")
                    changes = lines[1:]
                    summary = f"Git: {branch}"
                    if changes:
                        summary += f"\n{len(changes)} changed file(s):"
                        for c in changes[:10]:
                            summary += f"\n  {c}"
                        if len(changes) > 10:
                            summary += f"\n  ... and {len(changes) - 10} more"
                    return self._wrap(summary)
        except Exception:
            pass
        return ""

    def _modified_files_warning(self) -> str:
        """Warn if files were modified externally since the agent read them."""
        read_tool = self.agent.tools.get("read")
        if not read_tool or not hasattr(read_tool, "_read_mtimes"):
            return ""
        modified = []
        for path, read_mtime in read_tool._read_mtimes.items():
            try:
                current_mtime = Path(path).stat().st_mtime
                if current_mtime > read_mtime:
                    modified.append(path)
            except (OSError, FileNotFoundError):
                pass
        if modified:
            return self._wrap(
                "WARNING: Files modified since you last read them:\n"
                + "\n".join(f"  - {f}" for f in modified)
            )
        return ""

    def _mcp_status(self) -> str:
        if hasattr(self.agent, "mcp_manager") and self.agent.mcp_manager:
            if hasattr(self.agent, "_mcp_started") and self.agent._mcp_started:
                if hasattr(self.agent.mcp_manager, "server_names"):
                    names = self.agent.mcp_manager.server_names
                    if names:
                        return self._wrap(f"Active MCP servers: {', '.join(names)}")
        return ""
