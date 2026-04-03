"""Tests for provider adapters — using mocks (no real API calls)."""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from salt_agent.events import TextChunk, ToolUse, AgentError
from salt_agent.providers.anthropic import AnthropicAdapter
from salt_agent.providers.openai_provider import OpenAIAdapter


def _run_async(coro_fn):
    """Helper to run an async generator and collect results."""
    events = []

    async def collect():
        async for event in coro_fn():
            events.append(event)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(collect())
    finally:
        loop.close()
    return events


def _make_mock_stream(event_list):
    """Create a mock context manager that yields events."""
    mock_stream_ctx = MagicMock()
    mock_stream_obj = MagicMock()
    mock_stream_obj.__iter__ = MagicMock(return_value=iter(event_list))
    mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_obj)
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)
    return mock_stream_ctx


# --- Anthropic Adapter ---

class TestAnthropicAdapter:
    def test_default_model(self):
        adapter = AnthropicAdapter(api_key="test-key")
        assert adapter.model == AnthropicAdapter.DEFAULT_MODEL

    def test_custom_model(self):
        adapter = AnthropicAdapter(api_key="test-key", model="claude-haiku-4-20250514")
        assert adapter.model == "claude-haiku-4-20250514"

    def test_stream_response_text_only(self):
        """Mock Anthropic streaming to return text only."""
        adapter = AnthropicAdapter(api_key="test-key")

        text_start = MagicMock()
        text_start.type = "content_block_start"
        text_start.content_block = MagicMock(type="text")

        delta1 = MagicMock()
        delta1.type = "content_block_delta"
        delta1.delta = MagicMock(text="Hello ", partial_json=None)
        delta1.delta.partial_json = None

        delta2 = MagicMock()
        delta2.type = "content_block_delta"
        delta2.delta = MagicMock(text="world!", partial_json=None)
        delta2.delta.partial_json = None

        block_stop = MagicMock()
        block_stop.type = "content_block_stop"

        mock_stream = _make_mock_stream([text_start, delta1, delta2, block_stop])
        # Mock get_final_message for usage tracking
        mock_stream_obj = mock_stream.__enter__.return_value
        mock_final = MagicMock()
        mock_final.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_stream_obj.get_final_message.return_value = mock_final

        # Patch the client on the adapter instance (client created in __init__)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream
        adapter.client = mock_client

        events = _run_async(
            lambda: adapter.stream_response(system="test", messages=[], tools=[])
        )

        text_events = [e for e in events if isinstance(e, TextChunk)]
        assert len(text_events) == 2
        assert text_events[0].text == "Hello "
        assert text_events[1].text == "world!"

    def test_stream_response_with_tool_use(self):
        """Mock Anthropic streaming to return a tool use."""
        adapter = AnthropicAdapter(api_key="test-key")

        tool_start = MagicMock()
        tool_start.type = "content_block_start"
        mock_block = MagicMock(type="tool_use", id="tool_1")
        mock_block.name = "read"
        tool_start.content_block = mock_block

        delta = MagicMock()
        delta.type = "content_block_delta"
        delta.delta = MagicMock(text=None, partial_json='{"file_path": "/tmp/test.txt"}')
        delta.delta.text = None

        block_stop = MagicMock()
        block_stop.type = "content_block_stop"

        mock_stream = _make_mock_stream([tool_start, delta, block_stop])
        mock_stream_obj = mock_stream.__enter__.return_value
        mock_final = MagicMock()
        mock_final.usage = MagicMock(input_tokens=20, output_tokens=15)
        mock_stream_obj.get_final_message.return_value = mock_final

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream
        adapter.client = mock_client

        events = _run_async(
            lambda: adapter.stream_response(
                system="test", messages=[], tools=[{"name": "read"}]
            )
        )

        tool_events = [e for e in events if isinstance(e, ToolUse)]
        assert len(tool_events) == 1
        assert tool_events[0].tool_name == "read"
        assert tool_events[0].tool_input == {"file_path": "/tmp/test.txt"}

    def test_api_error_yields_error_event(self):
        adapter = AnthropicAdapter(api_key="test-key")

        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(side_effect=Exception("API down"))
        mock_stream.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream
        adapter.client = mock_client

        events = _run_async(
            lambda: adapter.stream_response(system="test", messages=[], tools=[])
        )

        error_events = [e for e in events if isinstance(e, AgentError)]
        assert len(error_events) == 1
        assert "API down" in error_events[0].error


# --- OpenAI Adapter ---

class TestOpenAIAdapter:
    def test_default_model(self):
        adapter = OpenAIAdapter(api_key="test-key")
        assert adapter.model == OpenAIAdapter.DEFAULT_MODEL

    def test_convert_simple_message(self):
        msg = {"role": "user", "content": "hello"}
        result = OpenAIAdapter._convert_message(msg)
        assert result == {"role": "user", "content": "hello"}

    def test_convert_assistant_with_tool_use(self):
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me read that."},
                {"type": "tool_use", "id": "t1", "name": "read", "input": {"file_path": "/tmp/x"}},
            ],
        }
        result = OpenAIAdapter._convert_message(msg)
        assert result["role"] == "assistant"
        assert result["content"] == "Let me read that."
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "read"

    def test_convert_tool_result(self):
        msg = {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "file contents"},
            ],
        }
        result = OpenAIAdapter._convert_message(msg)
        assert result["role"] == "tool"
        assert result["tool_call_id"] == "t1"
        assert result["content"] == "file contents"
