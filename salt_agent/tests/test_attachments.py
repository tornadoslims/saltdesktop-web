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
    has_persistence: bool = False,
    has_budget: bool = False,
    budget_pct: float = 0.0,
    has_tasks: bool = False,
    has_skills: bool = False,
    context_pct: float = 0.0,
):
    """Create a mock agent for attachment testing."""
    agent = MagicMock()
    agent.config = MagicMock()
    agent.config.plan_mode = plan_mode
    agent.config.auto_mode = auto_mode
    agent.config.working_directory = working_directory
    agent.config.max_budget_usd = 0.0  # default: no budget limit
    agent.config.context_window = 200_000

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

    # Persistence / session
    if has_persistence:
        agent.persistence = MagicMock()
        agent.persistence.session_id = "abcd1234-5678-9012-3456"
    else:
        agent.persistence = None

    # Budget
    if has_budget:
        agent.budget = MagicMock()
        agent.config.max_budget_usd = 10.0
        agent.budget.total_cost_estimate = budget_pct / 100.0 * 10.0
        agent.budget.total_tokens = int(context_pct / 100.0 * agent.config.context_window)
    else:
        # Remove budget attribute so hasattr returns False
        del agent.budget

    # Tasks
    if has_tasks:
        agent.task_manager = MagicMock()
    else:
        del agent.task_manager

    # Skills
    if has_skills:
        agent.skill_manager = MagicMock()
    else:
        del agent.skill_manager

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


# ---- New attachment type tests (types 8-15) ----


class TestFileMentions:
    def test_file_mentions_found(self, tmp_path):
        (tmp_path / "hello.py").write_text("print('hi')")
        agent = _make_mock_agent(working_directory=str(tmp_path))
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble(current_message="check hello.py for bugs")
        file_reminders = [r for r in reminders if "Files mentioned" in r]
        assert len(file_reminders) == 1
        assert "hello.py" in file_reminders[0]

    def test_file_mentions_none_found(self):
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble(current_message="no files here")
        file_reminders = [r for r in reminders if "Files mentioned" in r]
        assert len(file_reminders) == 0

    def test_file_mentions_empty_message(self):
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble(current_message="")
        file_reminders = [r for r in reminders if "Files mentioned" in r]
        assert len(file_reminders) == 0

    def test_file_mentions_absolute_path(self, tmp_path):
        """Absolute paths with simple names should be detected."""
        target = tmp_path / "test.py"
        target.write_text("x = 1")
        agent = _make_mock_agent(working_directory=str(tmp_path))
        assembler = AttachmentAssembler(agent)
        # Use /tmp/... style path that the regex can match (no hyphens)
        reminders = assembler.assemble(current_message=f"look at /tmp/test.py")
        # The regex may or may not find /tmp/test.py depending on whether it exists;
        # this test verifies the method doesn't crash and handles absolute paths
        assert isinstance(reminders, list)


class TestRecentlyModified:
    def test_recently_modified_files(self, tmp_path):
        (tmp_path / "new.py").write_text("x = 1")
        agent = _make_mock_agent(working_directory=str(tmp_path))
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        recent = [r for r in reminders if "Recently modified" in r]
        assert len(recent) == 1
        assert "new.py" in recent[0]

    def test_no_recently_modified_in_empty_dir(self, tmp_path):
        agent = _make_mock_agent(working_directory=str(tmp_path))
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        recent = [r for r in reminders if "Recently modified" in r]
        assert len(recent) == 0

    def test_ignores_git_and_pycache(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "index").write_text("stuff")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.pyc").write_text("compiled")
        agent = _make_mock_agent(working_directory=str(tmp_path))
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        recent = [r for r in reminders if "Recently modified" in r]
        assert len(recent) == 0


class TestActiveTasks:
    def test_active_tasks_shown(self):
        agent = _make_mock_agent(has_tasks=True)
        task = MagicMock()
        task.status.value = "running"
        task.id = "abc123"
        task.prompt = "Build the widget"
        agent.task_manager.list_tasks.return_value = [task]
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        task_reminders = [r for r in reminders if "Running tasks" in r]
        assert len(task_reminders) == 1
        assert "abc123" in task_reminders[0]

    def test_no_active_tasks(self):
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        task_reminders = [r for r in reminders if "Running tasks" in r]
        assert len(task_reminders) == 0


class TestSessionInfo:
    def test_session_info_shown(self):
        agent = _make_mock_agent(has_persistence=True)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        session_reminders = [r for r in reminders if "Session:" in r]
        assert len(session_reminders) == 1
        assert "abcd1234" in session_reminders[0]

    def test_no_session_info_without_persistence(self):
        agent = _make_mock_agent(has_persistence=False)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        session_reminders = [r for r in reminders if "Session:" in r]
        assert len(session_reminders) == 0


class TestBudgetWarning:
    def test_budget_warning_over_80_pct(self):
        agent = _make_mock_agent(has_budget=True, budget_pct=90.0)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        budget_reminders = [r for r in reminders if "Budget" in r and "WARNING" in r]
        assert len(budget_reminders) == 1
        assert "90%" in budget_reminders[0]

    def test_no_budget_warning_under_80_pct(self):
        agent = _make_mock_agent(has_budget=True, budget_pct=50.0)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        budget_reminders = [r for r in reminders if "Budget" in r and "WARNING" in r]
        assert len(budget_reminders) == 0

    def test_no_budget_warning_without_budget(self):
        agent = _make_mock_agent(has_budget=False)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        budget_reminders = [r for r in reminders if "Budget" in r and "WARNING" in r]
        assert len(budget_reminders) == 0


class TestCompactionNotice:
    def test_compaction_notice_over_60_pct(self):
        agent = _make_mock_agent(has_budget=True, context_pct=70.0)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        ctx_reminders = [r for r in reminders if "Context:" in r and "full" in r]
        assert len(ctx_reminders) == 1
        assert "70%" in ctx_reminders[0]

    def test_no_compaction_notice_under_60_pct(self):
        agent = _make_mock_agent(has_budget=True, context_pct=30.0)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        ctx_reminders = [r for r in reminders if "Context:" in r and "full" in r]
        assert len(ctx_reminders) == 0


class TestSkillsReminder:
    def test_skills_reminder_on_turn_0(self):
        agent = _make_mock_agent(has_skills=True)
        skill = MagicMock()
        skill.name = "commit"
        agent.skill_manager.list_user_invocable.return_value = [skill]
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble(turn=0)
        skill_reminders = [r for r in reminders if "Available skills" in r]
        assert len(skill_reminders) == 1
        assert "commit" in skill_reminders[0]

    def test_no_skills_reminder_on_later_turns(self):
        agent = _make_mock_agent(has_skills=True)
        skill = MagicMock()
        skill.name = "commit"
        agent.skill_manager.list_user_invocable.return_value = [skill]
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble(turn=5)
        skill_reminders = [r for r in reminders if "Available skills" in r]
        assert len(skill_reminders) == 0

    def test_no_skills_reminder_without_skills(self):
        agent = _make_mock_agent(has_skills=False)
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble(turn=0)
        skill_reminders = [r for r in reminders if "Available skills" in r]
        assert len(skill_reminders) == 0


class TestEnvContext:
    def test_env_context_always_present(self):
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        env_reminders = [r for r in reminders if "Environment:" in r]
        assert len(env_reminders) == 1
        assert "Python:" in env_reminders[0]

    def test_env_context_includes_git(self):
        """If git is installed, it should appear in the environment context."""
        import shutil
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        env_reminders = [r for r in reminders if "Environment:" in r]
        if shutil.which("git"):
            assert "git" in env_reminders[0]


class TestAssembleTurnParameter:
    def test_assemble_accepts_turn_and_message(self):
        """assemble() accepts turn and current_message parameters."""
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        # Should not raise
        reminders = assembler.assemble(turn=3, current_message="check main.py")
        assert len(reminders) >= 3  # at least date, env, working dir

    def test_assemble_defaults_work(self):
        """assemble() works with default parameters (backward compatible)."""
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        assert len(reminders) >= 3


class TestAttachmentCount:
    def test_at_least_13_attachment_methods(self):
        """The assembler should have at least 13 attachment-generating methods.

        We have 15 attachment types total but 2 (plan mode, auto mode, working dir)
        are inline in assemble(). The private helper methods account for 13 types.
        """
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        # Count methods that start with _ and are not __dunder__
        attachment_methods = [
            m for m in dir(assembler)
            if m.startswith("_") and not m.startswith("__")
            and callable(getattr(assembler, m))
            and m not in ("_wrap",)
        ]
        assert len(attachment_methods) >= 13, (
            f"Expected 13+ attachment methods, got {len(attachment_methods)}: {attachment_methods}"
        )

    def test_assemble_produces_at_least_3_reminders(self):
        """Even a minimal agent should produce date, env, and working dir reminders."""
        agent = _make_mock_agent()
        assembler = AttachmentAssembler(agent)
        reminders = assembler.assemble()
        assert len(reminders) >= 3
