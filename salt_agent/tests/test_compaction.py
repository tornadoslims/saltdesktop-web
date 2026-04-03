"""Tests for the compaction module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from salt_agent.compaction import (
    context_collapse,
    estimate_tokens,
    estimate_messages_tokens,
    history_snip,
    needs_compaction,
    compact_context,
)
from salt_agent.config import AgentConfig
from salt_agent.events import TextChunk


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_known_string(self):
        # 12 chars -> 3 tokens
        assert estimate_tokens("hello world!") == 3

    def test_long_string(self):
        assert estimate_tokens("a" * 4000) == 1000

    def test_reasonable_range(self):
        text = "The quick brown fox jumps over the lazy dog."  # 44 chars
        tokens = estimate_tokens(text)
        assert 5 <= tokens <= 20  # Rough range for ~44 chars


class TestEstimateMessagesTokens:
    def test_simple_string_content(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        tokens = estimate_messages_tokens(msgs)
        assert tokens > 0

    def test_list_content_with_text(self):
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "some response text"},
                ],
            },
        ]
        tokens = estimate_messages_tokens(msgs)
        assert tokens > 0

    def test_list_content_with_tool_result(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "file contents here"},
                ],
            },
        ]
        tokens = estimate_messages_tokens(msgs)
        assert tokens > 0

    def test_empty_messages(self):
        assert estimate_messages_tokens([]) == 0

    def test_mixed_content_types(self):
        msgs = [
            {"role": "user", "content": "prompt"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me read that."},
                    {"type": "tool_use", "input": {"file_path": "/tmp/x"}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "x" * 200},
                ],
            },
        ]
        tokens = estimate_messages_tokens(msgs)
        assert tokens > 0


class TestNeedsCompaction:
    def test_under_threshold(self):
        config = AgentConfig(context_window=200_000)
        msgs = [{"role": "user", "content": "short"}]
        assert needs_compaction(msgs, config) is False

    def test_over_threshold(self):
        config = AgentConfig(context_window=100)  # Tiny window
        msgs = [{"role": "user", "content": "x" * 500}]
        assert needs_compaction(msgs, config) is True

    def test_at_80_percent_boundary(self):
        config = AgentConfig(context_window=1000)
        # 80% of 1000 = 800 tokens = 3200 chars
        msgs = [{"role": "user", "content": "x" * 3300}]
        assert needs_compaction(msgs, config) is True


class TestCompactContext:
    def test_too_few_messages_unchanged(self):
        """Less than 4 messages should not be compacted."""
        config = AgentConfig()

        async def run():
            msgs = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]
            result = await compact_context(msgs, "system", config, None)
            return result

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run())
        finally:
            loop.close()

        assert len(result) == 2

    def test_compact_with_mock_provider(self):
        """Compaction with a mock provider that returns a summary."""
        config = AgentConfig()

        class MockSummarizer:
            async def stream_response(self, system, messages, tools, max_tokens):
                yield TextChunk(text="Summary of previous conversation.")

        async def run():
            msgs = [
                {"role": "user", "content": "first task"},
                {"role": "assistant", "content": "working on it"},
                {"role": "user", "content": "second task"},
                {"role": "assistant", "content": "done with second"},
                {"role": "user", "content": "third task"},
                {"role": "assistant", "content": "done with third"},
            ]
            return await compact_context(
                msgs, "system prompt", config, MockSummarizer()
            )

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run())
        finally:
            loop.close()

        # Should be compacted: summary + assistant ack + last 2 messages
        assert len(result) == 4
        assert "Summary" in result[0]["content"] or "Context Summary" in result[0]["content"]

    def test_compact_preserves_last_two_messages(self):
        config = AgentConfig()

        class MockSummarizer:
            async def stream_response(self, system, messages, tools, max_tokens):
                yield TextChunk(text="Summarized.")

        async def run():
            msgs = [
                {"role": "user", "content": "msg1"},
                {"role": "assistant", "content": "msg2"},
                {"role": "user", "content": "msg3"},
                {"role": "assistant", "content": "msg4"},
                {"role": "user", "content": "LAST_USER"},
                {"role": "assistant", "content": "LAST_ASSISTANT"},
            ]
            return await compact_context(msgs, "sys", config, MockSummarizer())

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run())
        finally:
            loop.close()

        # Last 2 messages should be preserved
        assert result[-2]["content"] == "LAST_USER"
        assert result[-1]["content"] == "LAST_ASSISTANT"

    def test_compact_fallback_on_empty_summary(self):
        """If provider returns empty summary, fallback to truncation."""
        config = AgentConfig()

        class EmptyProvider:
            async def stream_response(self, system, messages, tools, max_tokens):
                # Yield nothing
                return
                yield  # Make it an async generator

        async def run():
            msgs = [{"role": "user", "content": f"msg{i}"} for i in range(20)]
            return await compact_context(msgs, "sys", config, EmptyProvider())

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run())
        finally:
            loop.close()

        # Fallback keeps last 6
        assert len(result) <= 6

    def test_compact_includes_files_read(self):
        config = AgentConfig()
        received_prompt = []

        class CapturingProvider:
            async def stream_response(self, system, messages, tools, max_tokens):
                received_prompt.append(messages[0]["content"])
                yield TextChunk(text="Summary.")

        async def run():
            msgs = [
                {"role": "user", "content": "do stuff"},
                {"role": "assistant", "content": "ok"},
                {"role": "user", "content": "more stuff"},
                {"role": "assistant", "content": "done"},
            ]
            return await compact_context(
                msgs, "sys", config, CapturingProvider(),
                files_read={"/tmp/a.py", "/tmp/b.py"},
            )

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()

        # The summarization prompt should mention the files
        assert any("a.py" in p or "b.py" in p for p in received_prompt)


class TestHistorySnip:
    def test_no_snip_under_threshold(self):
        """Messages under 60% threshold should not be snipped."""
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "x" * 500},
        ]
        result = history_snip(msgs, context_window=200_000)
        assert result[1]["content"] == "x" * 500  # unchanged

    def test_snips_old_assistant_text(self):
        """Old assistant text over 300 chars should be snipped at 60%."""
        long_text = "a" * 1000
        msgs = [
            {"role": "assistant", "content": long_text},
            {"role": "user", "content": "x" * 500},
            {"role": "assistant", "content": "recent response"},
            {"role": "user", "content": "latest"},
        ]
        # context_window=100 so even small messages exceed 60% (60 tokens = 240 chars)
        result = history_snip(msgs, context_window=100)
        # First assistant msg should be snipped
        assert "[...snipped for context]" in result[0]["content"]
        assert len(result[0]["content"]) < len(long_text)

    def test_preserves_recent_half(self):
        """Messages in the second half should not be snipped."""
        msgs = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "short"},
            {"role": "user", "content": "mid"},
            {"role": "assistant", "content": "b" * 1000},  # in second half
        ]
        result = history_snip(msgs, context_window=100)
        # Message at index 3 (second half, midpoint=2) should be untouched
        assert result[3]["content"] == "b" * 1000

    def test_snips_list_content_text_blocks(self):
        """List-style assistant content should have text blocks snipped."""
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "z" * 500},
                    {"type": "tool_use", "name": "read", "input": {}},
                ],
            },
            {"role": "user", "content": "x" * 500},
            {"role": "assistant", "content": "recent"},
            {"role": "user", "content": "latest"},
        ]
        result = history_snip(msgs, context_window=100)
        content = result[0]["content"]
        # text block should be snipped
        assert "[...snipped]" in content[0]["text"]
        # tool_use block should be preserved
        assert content[1]["type"] == "tool_use"

    def test_leaves_short_text_blocks_alone(self):
        """Text blocks under 300 chars should not be snipped."""
        msgs = [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "short"}],
            },
            {"role": "user", "content": "x" * 500},
            {"role": "assistant", "content": "r"},
            {"role": "user", "content": "l"},
        ]
        result = history_snip(msgs, context_window=100)
        assert result[0]["content"][0]["text"] == "short"

    def test_skips_user_messages(self):
        """User messages should never be snipped."""
        msgs = [
            {"role": "user", "content": "u" * 1000},
            {"role": "assistant", "content": "a" * 1000},
            {"role": "user", "content": "latest"},
            {"role": "assistant", "content": "done"},
        ]
        result = history_snip(msgs, context_window=100)
        assert result[0]["content"] == "u" * 1000  # user msg untouched


class TestContextCollapse:
    def test_no_collapse_under_threshold(self):
        """Messages under 70% threshold should not be collapsed."""
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        result = context_collapse(msgs, context_window=200_000)
        assert len(result) == 2

    def test_collapses_tool_pairs(self):
        """Tool use + result pairs in first half should be collapsed."""
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "read_file", "input": {"path": "/a"}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "file contents " * 100},
                ],
            },
            {"role": "user", "content": "x" * 500},
            {"role": "assistant", "content": "y" * 500},
        ]
        result = context_collapse(msgs, context_window=100)
        # First two messages should be collapsed into one summary
        assert len(result) < len(msgs)
        assert "[Tool calls: read_file]" in result[0]["content"]

    def test_preserves_second_half(self):
        """Messages in the second half should never be collapsed."""
        msgs = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old reply"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "bash", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "content": "output"}],
            },
        ]
        result = context_collapse(msgs, context_window=100)
        # midpoint=2, so msgs at index 2,3 are in second half
        # They should be preserved as-is
        assert any(
            isinstance(m.get("content"), list)
            for m in result
            if m.get("role") == "assistant"
        )

    def test_multiple_tool_names_in_summary(self):
        """Collapsed summary should list all tool names."""
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "read", "input": {}},
                    {"type": "tool_use", "name": "write", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "content": "ok"}],
            },
            {"role": "user", "content": "x" * 500},
            {"role": "assistant", "content": "y" * 500},
        ]
        result = context_collapse(msgs, context_window=100)
        collapsed = result[0]["content"]
        assert "read" in collapsed
        assert "write" in collapsed

    def test_non_tool_messages_preserved(self):
        """Non-tool messages in first half should pass through."""
        msgs = [
            {"role": "user", "content": "hello " * 100},
            {"role": "assistant", "content": "world " * 100},
            {"role": "user", "content": "more " * 100},
            {"role": "assistant", "content": "done " * 100},
        ]
        result = context_collapse(msgs, context_window=100)
        assert len(result) == 4  # no tool pairs, nothing to collapse
