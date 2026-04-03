"""Tests for the 8 remaining tools: ask_user, plan_mode, sleep, config, message, worktree."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest

from salt_agent.config import AgentConfig
from salt_agent.tools.ask_user import AskUserQuestionTool
from salt_agent.tools.config_tool import ConfigTool
from salt_agent.tools.message_tool import SendMessageTool
from salt_agent.tools.plan_mode_tool import EnterPlanModeTool, ExitPlanModeTool
from salt_agent.tools.sleep_tool import SleepTool
from salt_agent.tools.worktree_tool import EnterWorktreeTool, ExitWorktreeTool


# ---------------------------------------------------------------------------
# AskUserQuestionTool
# ---------------------------------------------------------------------------

class TestAskUserQuestionTool:
    def test_definition(self):
        tool = AskUserQuestionTool()
        defn = tool.definition()
        assert defn.name == "ask_user"
        param_names = [p.name for p in defn.params]
        assert "question" in param_names
        assert "suggestions" in param_names

    def test_execute_simple_answer(self):
        tool = AskUserQuestionTool()
        with patch("builtins.input", return_value="yes"):
            result = tool.execute(question="Continue?")
        assert result == "yes"

    def test_execute_suggestion_by_number(self):
        tool = AskUserQuestionTool()
        with patch("builtins.input", return_value="2"):
            result = tool.execute(
                question="Pick a color",
                suggestions=["red", "blue", "green"],
            )
        assert result == "blue"

    def test_execute_suggestion_invalid_number_returns_raw(self):
        tool = AskUserQuestionTool()
        with patch("builtins.input", return_value="99"):
            result = tool.execute(
                question="Pick",
                suggestions=["a", "b"],
            )
        assert result == "99"

    def test_execute_eof_returns_declined(self):
        tool = AskUserQuestionTool()
        with patch("builtins.input", side_effect=EOFError):
            result = tool.execute(question="Hello?")
        assert "declined" in result

    def test_execute_keyboard_interrupt_returns_declined(self):
        tool = AskUserQuestionTool()
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = tool.execute(question="Hello?")
        assert "declined" in result


# ---------------------------------------------------------------------------
# EnterPlanModeTool / ExitPlanModeTool
# ---------------------------------------------------------------------------

class TestPlanModeTools:
    def test_enter_definition(self):
        config = AgentConfig()
        tool = EnterPlanModeTool(config)
        defn = tool.definition()
        assert defn.name == "enter_plan_mode"
        assert defn.params == []

    def test_exit_definition(self):
        config = AgentConfig()
        tool = ExitPlanModeTool(config)
        defn = tool.definition()
        assert defn.name == "exit_plan_mode"

    def test_enter_sets_plan_mode(self):
        config = AgentConfig(plan_mode=False)
        tool = EnterPlanModeTool(config)
        result = tool.execute()
        assert config.plan_mode is True
        assert "activated" in result.lower()

    def test_exit_clears_plan_mode(self):
        config = AgentConfig(plan_mode=True)
        tool = ExitPlanModeTool(config)
        result = tool.execute()
        assert config.plan_mode is False
        assert "deactivated" in result.lower()


# ---------------------------------------------------------------------------
# SleepTool
# ---------------------------------------------------------------------------

class TestSleepTool:
    def test_definition(self):
        tool = SleepTool()
        defn = tool.definition()
        assert defn.name == "sleep"
        param_names = [p.name for p in defn.params]
        assert "seconds" in param_names
        assert "task_id" in param_names

    def test_sleep_seconds(self):
        tool = SleepTool()
        start = time.monotonic()
        result = tool.execute(seconds=1)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.9
        assert "Waited 1 seconds" in result

    def test_sleep_capped_at_30(self):
        """Should cap at 30, but we patch time.sleep to avoid waiting."""
        tool = SleepTool()
        with patch("salt_agent.tools.sleep_tool.time.sleep") as mock_sleep:
            result = tool.execute(seconds=999)
            mock_sleep.assert_called_once_with(30)
        assert "30" in result

    def test_nothing_to_wait_for(self):
        tool = SleepTool()
        result = tool.execute()
        assert "Nothing" in result

    def test_wait_for_completed_task(self):
        """Mock a task manager with a completed task."""

        @dataclass
        class FakeStatus:
            value: str

        @dataclass
        class FakeTask:
            status: FakeStatus = field(default_factory=lambda: FakeStatus("completed"))

        class FakeTaskManager:
            def get_task(self, task_id):
                return FakeTask()

        tool = SleepTool(task_manager=FakeTaskManager())
        result = tool.execute(task_id="abc123")
        assert "completed" in result

    def test_wait_for_task_no_manager(self):
        tool = SleepTool(task_manager=None)
        result = tool.execute(task_id="abc123")
        assert "Nothing" in result


# ---------------------------------------------------------------------------
# ConfigTool
# ---------------------------------------------------------------------------

class TestConfigTool:
    def test_definition(self):
        config = AgentConfig()
        tool = ConfigTool(config)
        defn = tool.definition()
        assert defn.name == "config"
        param_names = [p.name for p in defn.params]
        assert "action" in param_names
        assert "key" in param_names
        assert "value" in param_names

    def test_get_max_turns(self):
        config = AgentConfig(max_turns=42)
        tool = ConfigTool(config)
        result = tool.execute(action="get", key="max_turns")
        assert "42" in result

    def test_set_max_turns(self):
        config = AgentConfig(max_turns=10)
        tool = ConfigTool(config)
        result = tool.execute(action="set", key="max_turns", value="50")
        assert config.max_turns == 50
        assert "50" in result

    def test_set_auto_mode_true(self):
        config = AgentConfig(auto_mode=False)
        tool = ConfigTool(config)
        tool.execute(action="set", key="auto_mode", value="true")
        assert config.auto_mode is True

    def test_set_auto_mode_false(self):
        config = AgentConfig(auto_mode=True)
        tool = ConfigTool(config)
        tool.execute(action="set", key="auto_mode", value="no")
        assert config.auto_mode is False

    def test_set_temperature(self):
        config = AgentConfig(temperature=0.0)
        tool = ConfigTool(config)
        tool.execute(action="set", key="temperature", value="0.7")
        assert config.temperature == pytest.approx(0.7)

    def test_disallowed_key(self):
        config = AgentConfig()
        tool = ConfigTool(config)
        result = tool.execute(action="get", key="api_key")
        assert "Cannot access" in result

    def test_get_plan_mode(self):
        config = AgentConfig(plan_mode=True)
        tool = ConfigTool(config)
        result = tool.execute(action="get", key="plan_mode")
        assert "True" in result


# ---------------------------------------------------------------------------
# SendMessageTool
# ---------------------------------------------------------------------------

class TestSendMessageTool:
    def test_definition(self):
        tool = SendMessageTool()
        defn = tool.definition()
        assert defn.name == "send_message"
        param_names = [p.name for p in defn.params]
        assert "task_id" in param_names
        assert "message" in param_names

    def test_no_task_manager(self):
        tool = SendMessageTool(task_manager=None)
        result = tool.execute(task_id="abc", message="hello")
        assert "No task manager" in result

    def test_task_not_found(self):
        class FakeTaskManager:
            def get_task(self, task_id):
                return None

        tool = SendMessageTool(task_manager=FakeTaskManager())
        result = tool.execute(task_id="xyz", message="hello")
        assert "not found" in result

    def test_message_sent(self):
        @dataclass
        class FakeTask:
            events: list = field(default_factory=list)

        fake_task = FakeTask()

        class FakeTaskManager:
            def get_task(self, task_id):
                return fake_task

        tool = SendMessageTool(task_manager=FakeTaskManager())
        result = tool.execute(task_id="abc", message="hello world")
        assert "sent" in result.lower()
        assert len(fake_task.events) == 1
        assert fake_task.events[0]["content"] == "hello world"


# ---------------------------------------------------------------------------
# EnterWorktreeTool / ExitWorktreeTool
# ---------------------------------------------------------------------------

class TestWorktreeTools:
    def test_enter_definition(self):
        config = AgentConfig()
        tool = EnterWorktreeTool(config)
        defn = tool.definition()
        assert defn.name == "enter_worktree"
        assert len(defn.params) == 1
        assert defn.params[0].name == "branch_name"

    def test_exit_definition(self):
        config = AgentConfig()
        enter_tool = EnterWorktreeTool(config)
        tool = ExitWorktreeTool(enter_tool)
        defn = tool.definition()
        assert defn.name == "exit_worktree"
        assert defn.params == []

    def test_enter_worktree_success(self):
        config = AgentConfig(working_directory="/original")
        tool = EnterWorktreeTool(config)
        with patch("salt_agent.tools.worktree_tool.subprocess.run") as mock_run:
            mock_run.return_value = None  # check=True doesn't raise
            result = tool.execute(branch_name="feature-x")
        assert "Entered worktree" in result
        assert "feature-x" in result
        assert config.working_directory != "/original"
        assert tool._original_cwd == "/original"

    def test_enter_worktree_failure(self):
        import subprocess as sp

        config = AgentConfig(working_directory="/original")
        tool = EnterWorktreeTool(config)
        with patch(
            "salt_agent.tools.worktree_tool.subprocess.run",
            side_effect=sp.CalledProcessError(1, "git", stderr="branch exists"),
        ):
            result = tool.execute(branch_name="feature-x")
        assert "Failed" in result
        # Working directory should not change on failure
        assert config.working_directory == "/original"

    def test_exit_worktree_restores_cwd(self):
        config = AgentConfig(working_directory="/worktree")
        enter_tool = EnterWorktreeTool(config)
        enter_tool._original_cwd = "/original"
        exit_tool = ExitWorktreeTool(enter_tool)
        result = exit_tool.execute()
        assert "Returned" in result
        assert config.working_directory == "/original"
        assert enter_tool._original_cwd == ""

    def test_exit_worktree_not_in_worktree(self):
        config = AgentConfig()
        enter_tool = EnterWorktreeTool(config)
        exit_tool = ExitWorktreeTool(enter_tool)
        result = exit_tool.execute()
        assert "Not in a worktree" in result
