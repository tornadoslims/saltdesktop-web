"""Tests for the subagent system."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from salt_agent.subagent import SubagentManager, _mode_system_prompt, _run_agent
from salt_agent.tools.agent_tool import AgentTool


# --- SubagentManager ---


class TestSubagentManager:
    def _make_parent(self):
        parent = MagicMock()
        parent.config.provider = "anthropic"
        parent.config.model = "test-model"
        parent.config.api_key = "test-key"
        parent.config.working_directory = "/tmp"
        parent.context.system_prompt = "You are a test agent."
        return parent

    def test_init(self):
        parent = self._make_parent()
        mgr = SubagentManager(parent)
        assert mgr.parent is parent
        assert mgr.children == []

    def test_spawn_fresh_records_child(self):
        parent = self._make_parent()
        mgr = SubagentManager(parent)

        mock_agent = MagicMock()

        async def fake_run(prompt):
            from salt_agent.events import AgentComplete
            yield AgentComplete(final_text="done")

        mock_agent.run = fake_run

        with patch("salt_agent.subagent._get_create_agent", return_value=lambda **kw: mock_agent):
            result = asyncio.get_event_loop().run_until_complete(
                mgr.spawn_fresh("Do something", mode="explore")
            )

        assert result["type"] == "fresh"
        assert result["mode"] == "explore"
        assert "Do something" in result["prompt"]
        assert result["result"] == "done"
        assert len(mgr.children) == 1

    def test_fork_records_child(self):
        parent = self._make_parent()
        mgr = SubagentManager(parent)

        mock_agent = MagicMock()
        mock_agent.context = MagicMock()

        async def fake_run(prompt):
            from salt_agent.events import AgentComplete
            yield AgentComplete(final_text="forked result")

        mock_agent.run = fake_run

        with patch("salt_agent.subagent._get_create_agent", return_value=lambda **kw: mock_agent):
            result = asyncio.get_event_loop().run_until_complete(
                mgr.fork("Continue work", messages=[{"role": "user", "content": "hello"}])
            )

        assert result["type"] == "fork"
        assert result["result"] == "forked result"
        assert len(mgr.children) == 1

    def test_spawn_fresh_truncates_long_prompt(self):
        parent = self._make_parent()
        mgr = SubagentManager(parent)

        mock_agent = MagicMock()

        async def fake_run(prompt):
            from salt_agent.events import AgentComplete
            yield AgentComplete(final_text="ok")

        mock_agent.run = fake_run

        long_prompt = "x" * 500
        with patch("salt_agent.subagent._get_create_agent", return_value=lambda **kw: mock_agent):
            result = asyncio.get_event_loop().run_until_complete(
                mgr.spawn_fresh(long_prompt)
            )

        assert len(result["prompt"]) == 200

    def test_spawn_fresh_truncates_long_result(self):
        parent = self._make_parent()
        mgr = SubagentManager(parent)

        mock_agent = MagicMock()
        long_result = "y" * 5000

        async def fake_run(prompt):
            from salt_agent.events import AgentComplete
            yield AgentComplete(final_text=long_result)

        mock_agent.run = fake_run

        with patch("salt_agent.subagent._get_create_agent", return_value=lambda **kw: mock_agent):
            result = asyncio.get_event_loop().run_until_complete(
                mgr.spawn_fresh("test")
            )

        assert len(result["result"]) == 2000

    def test_multiple_children_tracked(self):
        parent = self._make_parent()
        mgr = SubagentManager(parent)

        mock_agent = MagicMock()

        async def fake_run(prompt):
            from salt_agent.events import AgentComplete
            yield AgentComplete(final_text="done")

        mock_agent.run = fake_run

        with patch("salt_agent.subagent._get_create_agent", return_value=lambda **kw: mock_agent):
            asyncio.get_event_loop().run_until_complete(mgr.spawn_fresh("task1"))
            asyncio.get_event_loop().run_until_complete(mgr.spawn_fresh("task2"))
            asyncio.get_event_loop().run_until_complete(
                mgr.fork("task3", messages=[])
            )

        assert len(mgr.children) == 3


class TestModeSystemPrompt:
    def test_explore_mode(self):
        prompt = _mode_system_prompt("explore")
        assert "exploration" in prompt.lower()

    def test_verify_mode(self):
        prompt = _mode_system_prompt("verify")
        assert "verification" in prompt.lower()

    def test_worker_mode(self):
        prompt = _mode_system_prompt("worker")
        assert "worker" in prompt.lower()

    def test_general_mode(self):
        prompt = _mode_system_prompt("general")
        assert "subagent" in prompt.lower()

    def test_unknown_mode_falls_back(self):
        prompt = _mode_system_prompt("unknown_mode")
        assert prompt == _mode_system_prompt("general")


class TestRunAgent:
    def test_collects_final_text(self):
        mock_agent = MagicMock()

        async def fake_run(prompt):
            from salt_agent.events import AgentComplete
            yield AgentComplete(final_text="Final answer")

        mock_agent.run = fake_run

        result = asyncio.get_event_loop().run_until_complete(
            _run_agent(mock_agent, "test")
        )
        assert result == "Final answer"

    def test_collects_text_chunks(self):
        mock_agent = MagicMock()

        async def fake_run(prompt):
            from salt_agent.events import TextChunk
            yield TextChunk(text="Hello ")
            yield TextChunk(text="World")

        mock_agent.run = fake_run

        result = asyncio.get_event_loop().run_until_complete(
            _run_agent(mock_agent, "test")
        )
        assert result == "Hello World"


# --- AgentTool ---


class TestAgentTool:
    def test_definition(self):
        mgr = MagicMock()
        tool = AgentTool(mgr)
        defn = tool.definition()
        assert defn.name == "agent"
        assert len(defn.params) == 2

    def test_execute_calls_spawn_fresh(self):
        mgr = MagicMock()

        async def fake_spawn(prompt, mode):
            return {"result": "Subagent says hello"}

        mgr.spawn_fresh = fake_spawn
        tool = AgentTool(mgr)

        result = tool.execute(prompt="Do something", mode="explore")
        assert result == "Subagent says hello"

    def test_execute_handles_error(self):
        mgr = MagicMock()

        async def failing_spawn(prompt, mode):
            raise RuntimeError("API error")

        mgr.spawn_fresh = failing_spawn
        tool = AgentTool(mgr)

        result = tool.execute(prompt="Do something")
        assert "Subagent error" in result

    def test_execute_default_mode(self):
        mgr = MagicMock()

        async def fake_spawn(prompt, mode):
            return {"result": f"mode={mode}"}

        mgr.spawn_fresh = fake_spawn
        tool = AgentTool(mgr)

        result = tool.execute(prompt="test")
        assert "mode=general" in result
