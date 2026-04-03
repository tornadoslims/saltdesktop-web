"""Tests for stop hooks (post-turn processing)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from salt_agent.stop_hooks import StopHookRunner


def _make_mock_agent(memory_dir: str | None = None, has_persistence: bool = True):
    """Create a mock agent for stop hook testing."""
    agent = MagicMock()

    # Mock provider with quick_query
    agent.provider = MagicMock()
    agent.provider.quick_query = AsyncMock(return_value="NONE")

    # Mock memory system
    agent.memory = MagicMock()
    agent.memory.save_memory_file = MagicMock()
    if memory_dir:
        agent.memory.memory_dir = Path(memory_dir)

    # Mock persistence
    if has_persistence:
        agent.persistence = MagicMock()
        agent.persistence.save_event = MagicMock()
    else:
        agent.persistence = None

    return agent


class TestMemoryExtraction:
    def test_skips_turn_0(self):
        agent = _make_mock_agent()
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "hello"}]
        asyncio.run(
            runner.run_after_turn(messages, 0)
        )
        # quick_query should NOT be called for memory extraction on turn 0
        # (it may be called for session title on turn 1, but not turn 0)
        agent.provider.quick_query.assert_not_called()

    def test_skips_turn_1(self):
        agent = _make_mock_agent(has_persistence=False)
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "hello"}]
        asyncio.run(
            runner.run_after_turn(messages, 1)
        )
        # Turn 1 is not divisible by 5, no memory extraction
        agent.memory.save_memory_file.assert_not_called()

    def test_fires_on_turn_5(self):
        agent = _make_mock_agent()
        agent.provider.quick_query = AsyncMock(return_value=(
            "TYPE: feedback\n"
            "NAME: user_likes_tests\n"
            "DESCRIPTION: User always wants tests\n"
            "CONTENT: User said always write tests first."
        ))
        runner = StopHookRunner(agent)
        messages = [
            {"role": "user", "content": "write tests for everything"},
            {"role": "assistant", "content": "I'll write tests."},
            {"role": "user", "content": "good, always do that"},
            {"role": "assistant", "content": "Noted."},
        ]
        asyncio.run(
            runner.run_after_turn(messages, 5)
        )
        agent.memory.save_memory_file.assert_called_once()
        call_kwargs = agent.memory.save_memory_file.call_args
        assert call_kwargs[1]["name"] == "user_likes_tests" or call_kwargs[0][0] == "user_likes_tests"

    def test_no_save_when_none_response(self):
        agent = _make_mock_agent()
        agent.provider.quick_query = AsyncMock(return_value="NONE")
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "fix the bug"}]
        asyncio.run(
            runner.run_after_turn(messages, 5)
        )
        agent.memory.save_memory_file.assert_not_called()

    def test_fires_on_turn_10(self):
        agent = _make_mock_agent()
        agent.provider.quick_query = AsyncMock(return_value="NONE")
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "hello"}]
        asyncio.run(
            runner.run_after_turn(messages, 10)
        )
        # Should have called quick_query for memory extraction (turn 10 % 5 == 0)
        assert agent.provider.quick_query.call_count >= 1


class TestSessionTitle:
    def test_generated_on_turn_1(self):
        agent = _make_mock_agent(has_persistence=True)
        agent.provider.quick_query = AsyncMock(return_value="Fix Login Bug")
        runner = StopHookRunner(agent)
        messages = [
            {"role": "user", "content": "fix the login page bug where users can't sign in"},
            {"role": "assistant", "content": "I'll fix that."},
        ]
        asyncio.run(
            runner.run_after_turn(messages, 1)
        )
        agent.persistence.save_event.assert_any_call(
            "session_title", {"title": "Fix Login Bug"}
        )

    def test_not_generated_on_turn_2(self):
        agent = _make_mock_agent(has_persistence=True)
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "hello"}]
        asyncio.run(
            runner.run_after_turn(messages, 2)
        )
        # Should not generate title on turn 2
        for call in agent.persistence.save_event.call_args_list:
            assert call[0][0] != "session_title"

    def test_skipped_without_persistence(self):
        agent = _make_mock_agent(has_persistence=False)
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "hello"}]
        asyncio.run(
            runner.run_after_turn(messages, 1)
        )
        # No persistence, no title generation (should not crash)


class TestStopHooksSafety:
    def test_hooks_dont_crash_on_error(self):
        agent = _make_mock_agent()
        # Make quick_query raise an exception
        agent.provider.quick_query = AsyncMock(side_effect=RuntimeError("API down"))
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "hello"}]
        # Should not raise -- stop hooks swallow errors
        asyncio.run(
            runner.run_after_turn(messages, 5)
        )

    def test_hooks_dont_crash_on_memory_save_error(self):
        agent = _make_mock_agent()
        agent.provider.quick_query = AsyncMock(return_value=(
            "TYPE: feedback\nNAME: test\nDESCRIPTION: test\nCONTENT: test"
        ))
        agent.memory.save_memory_file = MagicMock(side_effect=OSError("disk full"))
        runner = StopHookRunner(agent)
        messages = [{"role": "user", "content": "hello"}]
        # Should not raise
        asyncio.run(
            runner.run_after_turn(messages, 5)
        )


class TestParseMemoryEntry:
    def test_parse_valid_entry(self):
        text = (
            "TYPE: feedback\n"
            "NAME: user_prefers_short_responses\n"
            "DESCRIPTION: User wants concise responses\n"
            "CONTENT: User said stop summarizing.\n"
            "They prefer direct communication."
        )
        runner = StopHookRunner(_make_mock_agent())
        entry = runner._parse_memory_entry(text)
        assert entry is not None
        assert entry["type"] == "feedback"
        assert entry["name"] == "user_prefers_short_responses"
        assert entry["description"] == "User wants concise responses"
        assert "stop summarizing" in entry["content"]
        assert "direct communication" in entry["content"]

    def test_parse_incomplete_entry(self):
        text = "TYPE: feedback\nNAME: test\n"  # missing DESCRIPTION and CONTENT
        runner = StopHookRunner(_make_mock_agent())
        entry = runner._parse_memory_entry(text)
        assert entry is None

    def test_parse_empty_text(self):
        runner = StopHookRunner(_make_mock_agent())
        entry = runner._parse_memory_entry("")
        assert entry is None

    def test_parse_multiline_content(self):
        text = (
            "TYPE: project\n"
            "NAME: api_structure\n"
            "DESCRIPTION: API endpoint patterns\n"
            "CONTENT: REST endpoints follow /api/v2.\n"
            "All endpoints require auth.\n"
            "Rate limited to 100 req/min."
        )
        runner = StopHookRunner(_make_mock_agent())
        entry = runner._parse_memory_entry(text)
        assert entry is not None
        assert "Rate limited" in entry["content"]
        assert "All endpoints" in entry["content"]


class TestTurnStats:
    def test_stats_logged_with_persistence(self):
        agent = _make_mock_agent(has_persistence=True)
        runner = StopHookRunner(agent)
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        asyncio.run(
            runner.run_after_turn(messages, 3)
        )
        # Should have logged turn_complete event
        calls = [c for c in agent.persistence.save_event.call_args_list if c[0][0] == "turn_complete"]
        assert len(calls) == 1
        data = calls[0][0][1]
        assert data["turn"] == 3
        assert data["total_messages"] == 2
