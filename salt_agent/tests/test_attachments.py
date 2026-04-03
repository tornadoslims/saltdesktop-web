"""Tests for per-turn system-reminder injection (attachments)."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from salt_agent.attachments import AttachmentAssembler


def _make_mock_agent(
    plan_mode: bool = False,
    auto_mode: bool = False,
    working_directory: str = "/tmp/test_project",
    has_todo_tasks: bool = False,
    has_mcp: bool = False,
):
    """Create a mock agent for attachment testing."""
    agent = MagicMock()
    agent.config = MagicMock()
    agent.config.plan_mode = plan_mode
    agent.config.auto_mode = auto_mode
    agent.config.working_directory = working_directory

    # Mock tools registry
    if has_todo_tasks:
        todo_tool = MagicMock()
        todo_tool.tasks = [
            {"content": "Write tests", "status": "in_progress"},
            {"content": "Fix bug", "status": "pending"},
        ]
        todo_tool.get_context_injection.return_value = (
            "## Current Tasks\n  \u25d0 Write tests\n  \u25cb Fix bug"
        )
        agent.tools = MagicMock()
        agent.tools.get = lambda name: todo_tool if name == "todo_write" else None
    else:
        agent.tools = MagicMock()
        agent.tools.get = lambda name: None

    # MCP
    if has_mcp:
        agent.mcp_manager = MagicMock()
        agent.mcp_manager.server_names = ["puppeteer", "filesystem"]
        agent._mcp_started = True
    else:
        agent.mcp_manager = None
        agent._mcp_started = False

    return agent


class TestDateReminder:
    def test_date_reminder_always_present(self):
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        # Date reminder should always be first
        assert any("<system-reminder>" in r and "Current date:" in r for r in reminders)

    def test_date_reminder_format(self):
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        date_reminder = reminders[0]
        assert "<system-reminder>" in date_reminder
        assert "</system-reminder>" in date_reminder
        # Should contain today's date
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in date_reminder


class TestTodoReminder:
    def test_todo_reminder_when_tasks_exist(self):
        agent = _make_mock_agent(has_todo_tasks=True)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        todo_reminders = [r for r in reminders if "Current Tasks" in r]
        assert len(todo_reminders) == 1
        assert "Write tests" in todo_reminders[0]

    def test_todo_reminder_empty_when_no_tasks(self):
        agent = _make_mock_agent(has_todo_tasks=False)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        todo_reminders = [r for r in reminders if "Current Tasks" in r]
        assert len(todo_reminders) == 0


class TestPlanModeReminder:
    def test_plan_mode_reminder(self):
        agent = _make_mock_agent(plan_mode=True)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        plan_reminders = [r for r in reminders if "PLAN MODE" in r]
        assert len(plan_reminders) == 1

    def test_no_plan_mode_reminder_when_off(self):
        agent = _make_mock_agent(plan_mode=False)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        plan_reminders = [r for r in reminders if "PLAN MODE" in r]
        assert len(plan_reminders) == 0


class TestAutoModeReminder:
    def test_auto_mode_reminder(self):
        agent = _make_mock_agent(auto_mode=True)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        auto_reminders = [r for r in reminders if "AUTO MODE" in r]
        assert len(auto_reminders) == 1

    def test_no_auto_mode_reminder_when_off(self):
        agent = _make_mock_agent(auto_mode=False)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        auto_reminders = [r for r in reminders if "AUTO MODE" in r]
        assert len(auto_reminders) == 0


class TestGitStatus:
    def test_git_status_in_git_repo(self, tmp_path):
        # Initialize a git repo
        subprocess.run(
            ["git", "init"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        # Create and commit a file so we have a branch
        (tmp_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        # Create an untracked file
        (tmp_path / "new_file.txt").write_text("new")

        agent = _make_mock_agent(working_directory=str(tmp_path))
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        git_reminders = [r for r in reminders if "Git:" in r]
        assert len(git_reminders) == 1
        assert "1 changed file(s)" in git_reminders[0]

    def test_no_git_status_outside_repo(self, tmp_path):
        agent = _make_mock_agent(working_directory=str(tmp_path))
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        git_reminders = [r for r in reminders if "Git:" in r]
        # Non-git directory: either empty or error, either way no git reminder
        assert len(git_reminders) == 0


class TestMCPStatus:
    def test_mcp_status_when_connected(self):
        agent = _make_mock_agent(has_mcp=True)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        mcp_reminders = [r for r in reminders if "MCP servers" in r]
        assert len(mcp_reminders) == 1
        assert "puppeteer" in mcp_reminders[0]
        assert "filesystem" in mcp_reminders[0]

    def test_no_mcp_status_when_not_connected(self):
        agent = _make_mock_agent(has_mcp=False)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        mcp_reminders = [r for r in reminders if "MCP servers" in r]
        assert len(mcp_reminders) == 0


class TestWorkingDirectory:
    def test_working_directory_always_present(self):
        agent = _make_mock_agent(working_directory="/my/project")
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        wd_reminders = [r for r in reminders if "Working directory:" in r]
        assert len(wd_reminders) == 1
        assert "/my/project" in wd_reminders[0]


class TestRemindersNotSavedToConversation:
    """Verify the design principle: reminders are per-turn, not persisted."""

    def test_reminders_are_strings_not_dicts(self):
        """Reminders are strings (system-reminder blocks), not message dicts."""
        agent = _make_mock_agent(plan_mode=True, auto_mode=True)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        for r in reminders:
            assert isinstance(r, str)
            assert "<system-reminder>" in r
            assert "</system-reminder>" in r

    def test_wrap_produces_valid_tags(self):
        assembler = AttachmentAssembler(_make_mock_agent())
        wrapped = assembler._wrap("test content")
        assert wrapped == "<system-reminder>\ntest content\n</system-reminder>"
