"""Tests for the compaction module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from salt_agent.compaction import (
    estimate_tokens,
    estimate_messages_tokens,
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
