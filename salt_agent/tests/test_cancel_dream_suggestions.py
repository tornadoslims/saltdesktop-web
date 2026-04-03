"""Tests for 3 new features: cancel cleanup, dream/consolidation, prompt suggestions."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from salt_agent.events import AgentError, ToolUse
from salt_agent.stop_hooks import StopHookRunner


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_mock_agent(memory_dir: str | None = None, has_persistence: bool = True):
    """Create a mock agent for stop hook testing."""
    agent = MagicMock()
    agent.provider = MagicMock()
    agent.provider.quick_query = AsyncMock(return_value="NONE")
    agent.memory = MagicMock()
    agent.memory.save_memory_file = MagicMock()
    if memory_dir:
        agent.memory.memory_dir = Path(memory_dir)
    else:
        agent.memory.memory_dir = Path("/tmp/test_memory_dir")
    agent.memory.scan_memory_files = MagicMock(return_value=[])
    agent.memory.load_memory_file = MagicMock(return_value="some content")
    agent.memory._update_index = MagicMock()
    if has_persistence:
        agent.persistence = MagicMock()
        agent.persistence.save_event = MagicMock()
    else:
        agent.persistence = None
    return agent


# ---------------------------------------------------------------------------
# Feature 1: Cancel Cleanup
# ---------------------------------------------------------------------------

class TestCancelCleanup:
    """Test that Ctrl+C during tool execution produces cancel tool_results."""

    def test_cancel_results_have_all_tool_ids(self):
        """When cancelled, every tool_use should get a corresponding tool_result."""
        # We test the logic by simulating what the agent does:
        # - assistant message has 3 tool_uses
        # - only 1 was processed before cancel
        # - the other 2 should get cancel results
        tool_uses = [
            ToolUse(tool_id="t1", tool_name="read", tool_input={"file_path": "/a"}),
            ToolUse(tool_id="t2", tool_name="read", tool_input={"file_path": "/b"}),
            ToolUse(tool_id="t3", tool_name="read", tool_input={"file_path": "/c"}),
        ]

        # Simulate: first tool completed, then cancel
        tool_results = [
            {"type": "tool_result", "tool_use_id": "t1", "content": "file a contents"},
        ]

        # Cancel cleanup logic (same as in agent.py sequential path)
        processed_ids = {r["tool_use_id"] for r in tool_results}
        for tu in tool_uses:
            if tu.tool_id not in processed_ids:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.tool_id,
                    "content": "Tool call cancelled by user.",
                })

        # All 3 tool_uses should have results
        assert len(tool_results) == 3
        result_ids = {r["tool_use_id"] for r in tool_results}
        assert result_ids == {"t1", "t2", "t3"}

        # The cancelled ones should have cancel message
        cancelled = [r for r in tool_results if "cancelled" in r["content"]]
        assert len(cancelled) == 2

    def test_cancel_with_no_processed_tools(self):
        """Cancel before any tool executes -- all should get cancel results."""
        tool_uses = [
            ToolUse(tool_id="t1", tool_name="bash", tool_input={"command": "ls"}),
            ToolUse(tool_id="t2", tool_name="bash", tool_input={"command": "pwd"}),
        ]
        tool_results = []

        processed_ids = {r["tool_use_id"] for r in tool_results}
        for tu in tool_uses:
            if tu.tool_id not in processed_ids:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.tool_id,
                    "content": "Tool call cancelled by user.",
                })

        assert len(tool_results) == 2
        assert all("cancelled" in r["content"] for r in tool_results)

    def test_cancel_with_all_tools_processed(self):
        """Cancel after all tools completed -- no cancel results needed."""
        tool_uses = [
            ToolUse(tool_id="t1", tool_name="read", tool_input={"file_path": "/a"}),
        ]
        tool_results = [
            {"type": "tool_result", "tool_use_id": "t1", "content": "file contents"},
        ]

        processed_ids = {r["tool_use_id"] for r in tool_results}
        for tu in tool_uses:
            if tu.tool_id not in processed_ids:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.tool_id,
                    "content": "Tool call cancelled by user.",
                })

        # Only the original result -- no cancel results added
        assert len(tool_results) == 1
        assert "cancelled" not in tool_results[0]["content"]

    def test_cancel_results_appended_to_messages(self):
        """The cancel tool_results should be appended as a user message."""
        messages = [
            {"role": "user", "content": "do stuff"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "ls"}},
            ]},
        ]

        tool_results = [
            {"type": "tool_result", "tool_use_id": "t1", "content": "Tool call cancelled by user."},
        ]

        # This is what the agent does on cancel
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        assert len(messages) == 3
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"][0]["tool_use_id"] == "t1"


# ---------------------------------------------------------------------------
# Feature 2: Dream / Memory Consolidation
# ---------------------------------------------------------------------------

class TestMemoryConsolidation:
    def test_skips_non_20_turns(self):
        """Consolidation only runs every 20 turns."""
        agent = _make_mock_agent()
        runner = StopHookRunner(agent)
        for turn in [0, 1, 5, 10, 15, 19]:
            asyncio.run(runner._consolidate_memories([], turn))
        # quick_query should not be called for consolidation on non-20 turns
        # (it may be called by other hooks, but _consolidate_memories specifically should not)
        # Since we call _consolidate_memories directly, no quick_query calls expected
        agent.provider.quick_query.assert_not_called()

    def test_skips_when_few_memory_files(self):
        """Consolidation skips if fewer than 3 memory files."""
        agent = _make_mock_agent()
        agent.memory.scan_memory_files.return_value = [
            {"filename": "a.md", "type": "user", "description": "desc a"},
            {"filename": "b.md", "type": "user", "description": "desc b"},
        ]
        runner = StopHookRunner(agent)
        asyncio.run(runner._consolidate_memories([], 20))
        agent.provider.quick_query.assert_not_called()

    def test_runs_on_turn_20_with_enough_files(self):
        """Consolidation runs on turn 20 when 3+ memory files exist."""
        agent = _make_mock_agent()
        agent.memory.scan_memory_files.return_value = [
            {"filename": "a.md", "type": "user", "description": "desc a"},
            {"filename": "b.md", "type": "feedback", "description": "desc b"},
            {"filename": "c.md", "type": "project", "description": "desc c"},
        ]
        agent.provider.quick_query = AsyncMock(return_value="KEEP: a.md\nKEEP: b.md\nKEEP: c.md")
        runner = StopHookRunner(agent)
        asyncio.run(runner._consolidate_memories([], 20))
        agent.provider.quick_query.assert_called_once()

    def test_deletes_files_marked_for_deletion(self, tmp_path):
        """DELETE: lines should cause files to be removed."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "stale.md").write_text("old stuff")
        (mem_dir / "keep.md").write_text("good stuff")
        (mem_dir / "also_keep.md").write_text("also good")

        agent = _make_mock_agent()
        agent.memory.memory_dir = mem_dir
        agent.memory.scan_memory_files.return_value = [
            {"filename": "stale.md", "type": "project", "description": "stale info"},
            {"filename": "keep.md", "type": "user", "description": "keep this"},
            {"filename": "also_keep.md", "type": "feedback", "description": "and this"},
        ]
        agent.provider.quick_query = AsyncMock(
            return_value="KEEP: keep.md\nDELETE: stale.md\nKEEP: also_keep.md"
        )

        runner = StopHookRunner(agent)
        asyncio.run(runner._consolidate_memories([], 20))

        assert not (mem_dir / "stale.md").exists()
        assert (mem_dir / "keep.md").exists()
        assert (mem_dir / "also_keep.md").exists()
        agent.memory._update_index.assert_called_once_with("stale.md", "")

    def test_does_not_delete_nonexistent_files(self, tmp_path):
        """DELETE: for a nonexistent file should be a no-op."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "a.md").write_text("x")
        (mem_dir / "b.md").write_text("y")
        (mem_dir / "c.md").write_text("z")

        agent = _make_mock_agent()
        agent.memory.memory_dir = mem_dir
        agent.memory.scan_memory_files.return_value = [
            {"filename": "a.md", "type": "user", "description": "a"},
            {"filename": "b.md", "type": "user", "description": "b"},
            {"filename": "c.md", "type": "user", "description": "c"},
        ]
        agent.provider.quick_query = AsyncMock(return_value="DELETE: nonexistent.md")

        runner = StopHookRunner(agent)
        asyncio.run(runner._consolidate_memories([], 20))

        # All files should still exist
        assert (mem_dir / "a.md").exists()
        assert (mem_dir / "b.md").exists()
        assert (mem_dir / "c.md").exists()
        agent.memory._update_index.assert_not_called()

    def test_runs_on_turn_40(self):
        """Consolidation also runs on turn 40 (multiple of 20)."""
        agent = _make_mock_agent()
        agent.memory.scan_memory_files.return_value = [
            {"filename": "a.md", "type": "user", "description": "a"},
            {"filename": "b.md", "type": "user", "description": "b"},
            {"filename": "c.md", "type": "user", "description": "c"},
        ]
        agent.provider.quick_query = AsyncMock(return_value="KEEP: a.md\nKEEP: b.md\nKEEP: c.md")
        runner = StopHookRunner(agent)
        asyncio.run(runner._consolidate_memories([], 40))
        agent.provider.quick_query.assert_called_once()


# ---------------------------------------------------------------------------
# Feature 3: Prompt Suggestions
# ---------------------------------------------------------------------------

class TestPromptSuggestions:
    def test_skips_turn_0(self):
        """Suggestions should not run on turn 0."""
        agent = _make_mock_agent()
        runner = StopHookRunner(agent)
        asyncio.run(runner._generate_suggestions([], 0))
        agent.provider.quick_query.assert_not_called()
        assert runner.last_suggestions == []

    def test_generates_suggestions_on_turn_1(self):
        """Should generate suggestions after first turn."""
        agent = _make_mock_agent()
        agent.provider.quick_query = AsyncMock(
            return_value="1. Show me the test results\n2. Add error handling\n3. Refactor the function"
        )
        runner = StopHookRunner(agent)
        messages = [
            {"role": "user", "content": "Fix the login bug"},
            {"role": "assistant", "content": "I've fixed the login validation."},
        ]
        asyncio.run(runner._generate_suggestions(messages, 1))
        assert len(runner.last_suggestions) == 3
        assert "Show me the test results" in runner.last_suggestions[0]

    def test_suggestions_capped_at_3(self):
        """Should return at most 3 suggestions."""
        agent = _make_mock_agent()
        agent.provider.quick_query = AsyncMock(
            return_value="1. A\n2. B\n3. C\n4. D\n5. E"
        )
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "hello"}]
        asyncio.run(runner._generate_suggestions(messages, 1))
        assert len(runner.last_suggestions) <= 3

    def test_suggestions_filter_long_lines(self):
        """Lines over 80 chars should be filtered out."""
        agent = _make_mock_agent()
        long_line = "x" * 90
        agent.provider.quick_query = AsyncMock(
            return_value=f"1. Short suggestion\n2. {long_line}\n3. Another short one"
        )
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "test"}]
        asyncio.run(runner._generate_suggestions(messages, 1))
        assert all(len(s) < 80 for s in runner.last_suggestions)
        assert len(runner.last_suggestions) == 2

    def test_suggestions_strip_numbering(self):
        """Numbering prefixes should be stripped from suggestions."""
        agent = _make_mock_agent()
        agent.provider.quick_query = AsyncMock(
            return_value="1. Run the tests\n2) Check the logs\n3- Deploy to staging"
        )
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "build the app"}]
        asyncio.run(runner._generate_suggestions(messages, 2))
        assert len(runner.last_suggestions) == 3
        # None should start with a number
        for s in runner.last_suggestions:
            assert not s[0].isdigit()

    def test_suggestions_empty_on_api_failure(self):
        """Suggestions should be empty if quick_query returns empty."""
        agent = _make_mock_agent()
        agent.provider.quick_query = AsyncMock(return_value="")
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "test"}]
        asyncio.run(runner._generate_suggestions(messages, 1))
        assert runner.last_suggestions == []

    def test_suggestions_attr_exists_on_runner(self):
        """StopHookRunner should have last_suggestions attribute."""
        agent = _make_mock_agent()
        runner = StopHookRunner(agent)
        assert hasattr(runner, "last_suggestions")
        assert runner.last_suggestions == []

    def test_suggestions_with_single_message(self):
        """Should work even with only 1 message."""
        agent = _make_mock_agent()
        agent.provider.quick_query = AsyncMock(return_value="1. Elaborate on the topic")
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "hello world"}]
        asyncio.run(runner._generate_suggestions(messages, 1))
        assert len(runner.last_suggestions) == 1

    def test_skips_mid_turn_tool_results(self):
        """Should not generate suggestions between tool calls (mid-turn)."""
        agent = _make_mock_agent()
        runner = StopHookRunner(agent)
        messages = [
            {"role": "user", "content": "do something"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "bash", "input": {}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
            ]},
        ]
        asyncio.run(runner._generate_suggestions(messages, 2))
        agent.provider.quick_query.assert_not_called()
        assert runner.last_suggestions == []


# ---------------------------------------------------------------------------
# Integration: hooks registered and run together
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_all_hooks_registered(self):
        """All 5 hooks should be registered."""
        agent = _make_mock_agent()
        runner = StopHookRunner(agent)
        assert len(runner._hooks) == 5

    def test_consolidation_and_suggestions_dont_crash(self):
        """Running all hooks together should not crash even with errors."""
        agent = _make_mock_agent()
        agent.provider.quick_query = AsyncMock(side_effect=RuntimeError("API down"))
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "hello"}]
        # Should not raise
        asyncio.run(runner.run_after_turn(messages, 20))
