"""Tests for the background task system."""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from salt_agent.tasks.manager import Task, TaskManager, TaskStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parent_agent():
    """Create a minimal mock parent agent with the fields TaskManager needs."""
    parent = MagicMock()
    parent.config.provider = "anthropic"
    parent.config.model = "test-model"
    parent.config.api_key = "test-key"
    parent.config.working_directory = "/tmp/test"
    return parent


def _make_fake_agent_that_returns(text: str):
    """Create a mock agent whose run() yields TextChunk + AgentComplete."""
    from salt_agent.events import AgentComplete, TextChunk

    agent = MagicMock()

    async def fake_run(prompt):
        yield TextChunk(text=text)
        yield AgentComplete(final_text=text, turns=1, tools_used=[])

    agent.run = fake_run
    return agent


def _make_fake_agent_that_fails(error_msg: str):
    """Create a mock agent whose run() raises an exception."""
    agent = MagicMock()

    async def fake_run(prompt):
        raise RuntimeError(error_msg)
        yield  # make it a generator  # noqa: E501

    agent.run = fake_run
    return agent


def _make_slow_agent(delay: float = 0.5):
    """Create a mock agent that takes some time to complete."""
    from salt_agent.events import AgentComplete, TextChunk

    agent = MagicMock()

    async def fake_run(prompt):
        await asyncio.sleep(delay)
        yield TextChunk(text="slow result")
        yield AgentComplete(final_text="slow result", turns=1, tools_used=[])

    agent.run = fake_run
    return agent


def _make_cancellable_agent():
    """Create a mock agent that yields multiple events with delays."""
    from salt_agent.events import AgentComplete, TextChunk

    agent = MagicMock()

    async def fake_run(prompt):
        for i in range(10):
            await asyncio.sleep(0.05)
            yield TextChunk(text=f"chunk-{i} ")
        yield AgentComplete(final_text="full result", turns=1, tools_used=[])

    agent.run = fake_run
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTaskCreation:
    def test_create_task_returns_task(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("hello")
            task = mgr.create_task("Say hello")

        assert isinstance(task, Task)
        assert task.id
        assert len(task.id) == 8
        assert task.prompt == "Say hello"
        assert task.status == TaskStatus.RUNNING
        assert task.created_at
        assert task.started_at

    def test_create_task_has_unique_ids(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("x")
            t1 = mgr.create_task("Task 1")
            t2 = mgr.create_task("Task 2")

        assert t1.id != t2.id


class TestTaskCompletion:
    def test_task_runs_to_completion(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("done!")
            task = mgr.create_task("Do something")

        # Wait for thread to finish
        task._thread.join(timeout=5)

        assert task.status == TaskStatus.COMPLETED
        assert task.output == "done!"
        assert task.completed_at
        assert len(task.events) > 0

    def test_task_output_available_after_completion(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("result text")
            task = mgr.create_task("Get result")

        task._thread.join(timeout=5)

        output = mgr.get_output(task.id)
        assert output == "result text"


class TestTaskList:
    def test_list_empty(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)
        assert mgr.list_tasks() == []

    def test_list_shows_all_tasks(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("x")
            mgr.create_task("Task A")
            mgr.create_task("Task B")
            mgr.create_task("Task C")

        tasks = mgr.list_tasks()
        assert len(tasks) == 3
        prompts = {t.prompt for t in tasks}
        assert prompts == {"Task A", "Task B", "Task C"}


class TestTaskGet:
    def test_get_existing_task(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("x")
            task = mgr.create_task("Find it")

        found = mgr.get_task(task.id)
        assert found is task

    def test_get_nonexistent_task(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)
        assert mgr.get_task("nonexistent") is None


class TestTaskOutput:
    def test_output_running_task(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_slow_agent(delay=2.0)
            task = mgr.create_task("Slow task")

        # Don't wait -- check immediately
        output = mgr.get_output(task.id)
        assert "still running" in output

        # Clean up
        task._cancel = True
        task._thread.join(timeout=5)

    def test_output_nonexistent_task(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)
        output = mgr.get_output("nope")
        assert "not found" in output


class TestTaskStop:
    def test_stop_running_task(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_cancellable_agent()
            task = mgr.create_task("Long running")

        # Give it a moment to start
        time.sleep(0.1)

        result = mgr.stop_task(task.id)
        assert "Stopping" in result

        task._thread.join(timeout=5)
        assert task.status == TaskStatus.STOPPED

    def test_stop_nonexistent_task(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)
        result = mgr.stop_task("nope")
        assert "not found" in result

    def test_stop_already_completed_task(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("done")
            task = mgr.create_task("Quick task")

        task._thread.join(timeout=5)

        result = mgr.stop_task(task.id)
        assert "not running" in result


class TestMultipleTasks:
    def test_multiple_tasks_run_in_parallel(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        start = time.time()

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_slow_agent(delay=0.2)
            t1 = mgr.create_task("Parallel 1")
            t2 = mgr.create_task("Parallel 2")
            t3 = mgr.create_task("Parallel 3")

        # Wait for all
        t1._thread.join(timeout=5)
        t2._thread.join(timeout=5)
        t3._thread.join(timeout=5)

        elapsed = time.time() - start

        # If sequential, would take >= 0.6s. Parallel should be ~0.2s + overhead
        assert elapsed < 0.5, f"Tasks took {elapsed:.2f}s -- should be parallel"

        assert t1.status == TaskStatus.COMPLETED
        assert t2.status == TaskStatus.COMPLETED
        assert t3.status == TaskStatus.COMPLETED


class TestTaskFailure:
    def test_task_failure_captured(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_fails("boom!")
            task = mgr.create_task("Will fail")

        task._thread.join(timeout=5)

        assert task.status == TaskStatus.FAILED
        assert "boom!" in task.error
        assert task.completed_at

    def test_failed_task_output(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_fails("crash")
            task = mgr.create_task("Will crash")

        task._thread.join(timeout=5)

        output = mgr.get_output(task.id)
        assert "failed" in output.lower() or "crash" in output.lower()


class TestTaskUpdate:
    def test_update_status(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("x")
            task = mgr.create_task("Updatable")

        task._thread.join(timeout=5)

        result = mgr.update_task(task.id, status="stopped")
        assert "updated" in result
        assert task.status == TaskStatus.STOPPED

    def test_update_invalid_status(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("x")
            task = mgr.create_task("Updatable")

        task._thread.join(timeout=5)

        result = mgr.update_task(task.id, status="banana")
        assert "Invalid status" in result

    def test_update_nonexistent_task(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)
        result = mgr.update_task("nope", status="completed")
        assert "not found" in result


class TestTaskCallback:
    def test_completion_callback_fires(self):
        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        completed = []
        mgr.on_complete(lambda t: completed.append(t))

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("cb test")
            task = mgr.create_task("Callback test")

        task._thread.join(timeout=5)

        assert len(completed) == 1
        assert completed[0].id == task.id


# ---------------------------------------------------------------------------
# Tool tests
# ---------------------------------------------------------------------------

class TestTaskTools:
    def test_task_create_tool(self):
        from salt_agent.tools.tasks import TaskCreateTool

        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("tool")
            tool = TaskCreateTool(mgr)
            result = tool.execute(prompt="Test prompt")

        assert "created" in result
        assert "running" in result.lower() or "background" in result.lower()

    def test_task_list_tool_empty(self):
        from salt_agent.tools.tasks import TaskListTool

        parent = _make_parent_agent()
        mgr = TaskManager(parent)
        tool = TaskListTool(mgr)
        result = tool.execute()
        assert result == "No tasks."

    def test_task_list_tool_with_tasks(self):
        from salt_agent.tools.tasks import TaskListTool

        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("x")
            mgr.create_task("Alpha")
            mgr.create_task("Beta")

        tool = TaskListTool(mgr)
        result = tool.execute()
        assert "Alpha" in result
        assert "Beta" in result

    def test_task_get_tool(self):
        from salt_agent.tools.tasks import TaskGetTool

        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("x")
            task = mgr.create_task("Get me")

        task._thread.join(timeout=5)

        tool = TaskGetTool(mgr)
        result = tool.execute(task_id=task.id)
        assert "Get me" in result
        assert "completed" in result.lower()

    def test_task_output_tool(self):
        from salt_agent.tools.tasks import TaskOutputTool

        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("output text")
            task = mgr.create_task("Produce output")

        task._thread.join(timeout=5)

        tool = TaskOutputTool(mgr)
        result = tool.execute(task_id=task.id)
        assert result == "output text"

    def test_task_stop_tool(self):
        from salt_agent.tools.tasks import TaskStopTool

        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_cancellable_agent()
            task = mgr.create_task("Stoppable")

        time.sleep(0.1)

        tool = TaskStopTool(mgr)
        result = tool.execute(task_id=task.id)
        assert "Stopping" in result

        task._thread.join(timeout=5)

    def test_task_update_tool(self):
        from salt_agent.tools.tasks import TaskUpdateTool

        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            mock_factory.return_value = lambda **kw: _make_fake_agent_that_returns("x")
            task = mgr.create_task("Update me")

        task._thread.join(timeout=5)

        tool = TaskUpdateTool(mgr)
        result = tool.execute(task_id=task.id, status="stopped")
        assert "updated" in result

    def test_tool_definitions(self):
        """All 6 task tools have valid definitions."""
        from salt_agent.tools.tasks import (
            TaskCreateTool,
            TaskGetTool,
            TaskListTool,
            TaskOutputTool,
            TaskStopTool,
            TaskUpdateTool,
        )

        parent = _make_parent_agent()
        mgr = TaskManager(parent)

        tools = [
            TaskCreateTool(mgr),
            TaskListTool(mgr),
            TaskGetTool(mgr),
            TaskOutputTool(mgr),
            TaskStopTool(mgr),
            TaskUpdateTool(mgr),
        ]

        names = set()
        for tool in tools:
            defn = tool.definition()
            assert defn.name
            assert defn.description
            names.add(defn.name)

        assert names == {
            "task_create", "task_list", "task_get",
            "task_output", "task_stop", "task_update",
        }
