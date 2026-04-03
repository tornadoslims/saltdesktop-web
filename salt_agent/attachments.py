"""Per-turn dynamic context injection via system-reminder blocks.

Inspired by Claude Code's utils/attachments.ts (3998 lines).
Before each model call, assembles dynamic context as <system-reminder> tags
injected into the user message.

Claude Code has ~30 attachment types. We implement 15 of the most impactful ones.

IMPORTANT: System-reminders are injected into a COPY of messages for the API
call. They are NOT saved to _conversation_messages. This prevents accumulation
across turns and avoids compaction of transient context.
"""

from __future__ import annotations

import re as _re
import subprocess
import sys as _sys
import shutil as _shutil
import time as _time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from salt_agent.agent import SaltAgent


class AttachmentAssembler:
    """Assembles per-turn dynamic context as system-reminder blocks."""

    def __init__(self, agent: "SaltAgent") -> None:
        self.agent = agent

    def assemble(self, turn: int = 0, current_message: str = "") -> list[str]:
        """Generate all system-reminder blocks for this turn.

        Args:
            turn: The current turn number (0-indexed). Used for first-turn-only
                  attachments like the skills reminder.
            current_message: The current user message text. Used to extract
                             file mentions.
        """
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

        # 8. File mentions in current message
        r = self._file_mentions(current_message)
        if r:
            reminders.append(r)

        # 9. Recently modified files
        r = self._recently_modified()
        if r:
            reminders.append(r)

        # 10. Active tasks summary
        r = self._active_tasks()
        if r:
            reminders.append(r)

        # 11. Session info
        r = self._session_info()
        if r:
            reminders.append(r)

        # 12. Budget warning
        r = self._budget_warning()
        if r:
            reminders.append(r)

        # 13. Compaction notice
        r = self._compaction_notice()
        if r:
            reminders.append(r)

        # 14. Skills available reminder (first turn only)
        r = self._skills_reminder(turn)
        if r:
            reminders.append(r)

        # 15. Environment context
        r = self._env_context()
        if r:
            reminders.append(r)

        # Working directory (always last)
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

    # --- New attachment types (8-15) ---

    def _file_mentions(self, current_message: str) -> str:
        """Extract file paths mentioned in the user's message and inject context."""
        if not current_message:
            return ""
        paths = _re.findall(r'(?:^|\s)([/~][\w/.]+\.\w+)', current_message)
        paths += _re.findall(r'(?:^|\s)([\w]+\.(?:py|js|ts|md|json|yaml|toml|sh|sql))', current_message)

        existing: list[str] = []
        for p in set(paths):
            full = Path(p).expanduser()
            if not full.is_absolute():
                full = Path(self.agent.config.working_directory) / p
            if full.exists() and full.is_file():
                existing.append(str(full))

        if existing:
            return self._wrap(
                "Files mentioned in message:\n" + "\n".join(f"  - {f}" for f in existing[:5])
            )
        return ""

    def _recently_modified(self) -> str:
        """List files modified in the last 5 minutes in the working directory."""
        wd = Path(self.agent.config.working_directory)
        now = _time.time()
        recent: list[str] = []
        try:
            for f in wd.rglob("*"):
                if f.is_file() and not any(
                    p in str(f) for p in [".git", "__pycache__", "node_modules", ".venv"]
                ):
                    if now - f.stat().st_mtime < 300:  # 5 minutes
                        recent.append(str(f.relative_to(wd)))
        except Exception:
            pass

        if recent:
            return self._wrap(
                "Recently modified files (last 5 min):\n"
                + "\n".join(f"  - {f}" for f in recent[:10])
            )
        return ""

    def _active_tasks(self) -> str:
        """Summarize running and recently completed background tasks."""
        if hasattr(self.agent, "task_manager"):
            tasks = self.agent.task_manager.list_tasks()
            running = [t for t in tasks if t.status.value == "running"]
            completed = [t for t in tasks if t.status.value == "completed"]
            if running or completed:
                lines: list[str] = []
                if running:
                    lines.append(f"Running tasks: {len(running)}")
                    for t in running[:3]:
                        lines.append(f"  - [{t.id}] {t.prompt[:40]}")
                if completed:
                    lines.append(f"Recently completed: {len(completed)}")
                return self._wrap("\n".join(lines))
        return ""

    def _session_info(self) -> str:
        """Inject current session ID."""
        if self.agent.persistence:
            return self._wrap(f"Session: {self.agent.persistence.session_id[:8]}")
        return ""

    def _budget_warning(self) -> str:
        """Warn when budget usage exceeds 80%."""
        if hasattr(self.agent, "budget") and self.agent.config.max_budget_usd > 0:
            cost = self.agent.budget.total_cost_estimate
            budget = self.agent.config.max_budget_usd
            pct = cost / budget * 100
            if pct > 80:
                return self._wrap(
                    f"WARNING: Budget {pct:.0f}% used (${cost:.3f} of ${budget:.2f})"
                )
        return ""

    def _compaction_notice(self) -> str:
        """Warn if context is getting large."""
        if hasattr(self.agent, "budget"):
            tokens = self.agent.budget.total_tokens
            window = self.agent.config.context_window
            pct = tokens / window * 100 if window > 0 else 0
            if pct > 60:
                return self._wrap(
                    f"Context: {pct:.0f}% full ({tokens:,} tokens)"
                )
        return ""

    def _skills_reminder(self, turn: int) -> str:
        """Remind about available skills on the first turn only."""
        if turn == 0 and hasattr(self.agent, "skill_manager"):
            skills = self.agent.skill_manager.list_user_invocable()
            if skills:
                names = ", ".join(s.name for s in skills[:5])
                return self._wrap(
                    f"Available skills: {names}. Use the skill tool to invoke them."
                )
        return ""

    def _env_context(self) -> str:
        """Inject relevant environment info."""
        parts = [f"Python: {_sys.version.split()[0]}"]
        for tool in ["git", "node", "npm", "python3", "pip"]:
            if _shutil.which(tool):
                parts.append(tool)
        return self._wrap(f"Environment: {', '.join(parts)}")
