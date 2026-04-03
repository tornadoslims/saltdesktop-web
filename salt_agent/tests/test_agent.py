"""Tests for the core agent loop."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from salt_agent.agent import SaltAgent
from salt_agent.config import AgentConfig
from salt_agent.context import ContextManager
from salt_agent.events import (
    AgentComplete,
    AgentError,
    AgentEvent,
    TextChunk,
    ToolEnd,
    ToolStart,
    ToolUse,
)
from salt_agent.tools.base import Tool, ToolDefinition, ToolParam, ToolRegistry


# --- Helpers ---

class EchoTool(Tool):
    """A simple tool for testing that echoes its input."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="echo",
            description="Echo the input back.",
            params=[ToolParam("text", "string", "Text to echo.")],
        )

    def execute(self, **kwargs) -> str:
        return f"Echo: {kwargs.get('text', '')}"


class FailTool(Tool):
    """A tool that always raises an exception."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="fail",
            description="Always fails.",
            params=[],
        )

    def execute(self, **kwargs) -> str:
        raise RuntimeError("Tool exploded")


class MockProvider:
    """A mock provider that returns predefined responses."""

    def __init__(self, responses: list[list[AgentEvent]]):
        self._responses = responses
        self._call_count = 0

    async def stream_response(self, system, messages, tools, max_tokens=4096, temperature=0.0):
        if self._call_count < len(self._responses):
            events = self._responses[self._call_count]
            self._call_count += 1
            for event in events:
                yield event
        else:
            # No more responses - just return text
            yield TextChunk(text="Done.")


def _run_agent(agent, prompt):
    """Run the agent and collect all events."""
    events = []

    async def collect():
        async for event in agent.run(prompt):
            events.append(event)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(collect())
    finally:
        loop.close()
    return events


# --- Tests ---

class TestSaltAgent:
    def test_text_only_response(self):
        """Agent returns text with no tool calls -> completes in 1 turn."""
        config = AgentConfig(provider="anthropic", max_turns=5)
        tools = ToolRegistry()
        tools.register(EchoTool())
        agent = SaltAgent(config, tools=tools)

        # Mock provider returns text only
        agent.provider = MockProvider([
            [TextChunk(text="Hello!")]
        ])

        events = _run_agent(agent, "Hi")

        text_events = [e for e in events if isinstance(e, TextChunk)]
        complete_events = [e for e in events if isinstance(e, AgentComplete)]

        assert len(text_events) == 1
        assert text_events[0].text == "Hello!"
        assert len(complete_events) == 1
        assert complete_events[0].turns == 1

    def test_tool_use_and_completion(self):
        """Agent uses a tool then completes."""
        config = AgentConfig(provider="anthropic", max_turns=5)
        tools = ToolRegistry()
        tools.register(EchoTool())
        agent = SaltAgent(config, tools=tools)

        # Turn 1: model requests tool use
        # Turn 2: model returns text (done)
        agent.provider = MockProvider([
            [
                TextChunk(text="Let me echo that."),
                ToolUse(tool_id="t1", tool_name="echo", tool_input={"text": "hello"}),
            ],
            [
                TextChunk(text="The echo returned: hello"),
            ],
        ])

        events = _run_agent(agent, "Echo hello")

        tool_starts = [e for e in events if isinstance(e, ToolStart)]
        tool_ends = [e for e in events if isinstance(e, ToolEnd)]
        completes = [e for e in events if isinstance(e, AgentComplete)]

        assert len(tool_starts) == 1
        assert tool_starts[0].tool_name == "echo"
        assert len(tool_ends) == 1
        assert tool_ends[0].success is True
        assert "Echo: hello" in tool_ends[0].result
        assert len(completes) == 1
        assert completes[0].turns == 2
        assert "echo" in completes[0].tools_used

    def test_unknown_tool(self):
        """Agent requests an unknown tool -> error result sent back."""
        config = AgentConfig(provider="anthropic", max_turns=5)
        tools = ToolRegistry()
        agent = SaltAgent(config, tools=tools)

        agent.provider = MockProvider([
            [ToolUse(tool_id="t1", tool_name="nonexistent", tool_input={})],
            [TextChunk(text="Ok, that tool didn't exist.")],
        ])

        events = _run_agent(agent, "Use nonexistent tool")

        tool_ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(tool_ends) == 1
        assert tool_ends[0].success is False
        assert "does not exist" in tool_ends[0].result

    def test_tool_exception(self):
        """Tool raises exception -> error result sent back, agent continues."""
        config = AgentConfig(provider="anthropic", max_turns=5)
        tools = ToolRegistry()
        tools.register(FailTool())
        agent = SaltAgent(config, tools=tools)

        agent.provider = MockProvider([
            [ToolUse(tool_id="t1", tool_name="fail", tool_input={})],
            [TextChunk(text="That tool failed.")],
        ])

        events = _run_agent(agent, "Use fail tool")

        tool_ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(tool_ends) == 1
        assert tool_ends[0].success is False
        assert "exploded" in tool_ends[0].result

    def test_max_turns_reached(self):
        """Agent exceeds max turns -> error event."""
        config = AgentConfig(provider="anthropic", max_turns=2)
        tools = ToolRegistry()
        tools.register(EchoTool())
        agent = SaltAgent(config, tools=tools)

        # Always request a tool, never stop
        agent.provider = MockProvider([
            [ToolUse(tool_id="t1", tool_name="echo", tool_input={"text": "a"})],
            [ToolUse(tool_id="t2", tool_name="echo", tool_input={"text": "b"})],
            [ToolUse(tool_id="t3", tool_name="echo", tool_input={"text": "c"})],
        ])

        events = _run_agent(agent, "Loop forever")

        errors = [e for e in events if isinstance(e, AgentError)]
        assert len(errors) == 1
        assert "Max turns" in errors[0].error

    def test_system_prompt_set(self):
        """System prompt is stored in context manager."""
        config = AgentConfig(
            provider="anthropic",
            system_prompt="You are a test agent.",
        )
        agent = SaltAgent(config)
        assert "You are a test agent." in agent.context.system_prompt

    def test_fatal_error_stops_loop(self):
        """A non-recoverable error from the provider stops the loop."""
        config = AgentConfig(provider="anthropic", max_turns=5)
        agent = SaltAgent(config)

        agent.provider = MockProvider([
            [AgentError(error="Fatal", recoverable=False)],
        ])

        events = _run_agent(agent, "Test")

        errors = [e for e in events if isinstance(e, AgentError)]
        assert len(errors) == 1
        # Should NOT have a complete event
        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(completes) == 0


class TestConversationPersistence:
    """Tests for conversation history persisting across run() calls."""

    def test_conversation_persists_across_runs(self):
        """Messages from run 1 are available in run 2."""
        config = AgentConfig(provider="anthropic", max_turns=5)
        tools = ToolRegistry()
        tools.register(EchoTool())
        agent = SaltAgent(config, tools=tools)

        # Run 1: simple text response
        agent.provider = MockProvider([
            [TextChunk(text="Hello from run 1!")],
        ])
        _run_agent(agent, "First message")

        # After run 1, conversation should have user + assistant messages
        assert len(agent._conversation_messages) >= 1
        assert agent._conversation_messages[0]["role"] == "user"
        assert agent._conversation_messages[0]["content"] == "First message"

        # Run 2: the provider sees the full history
        call_count = [0]
        original_provider = MockProvider([
            [TextChunk(text="I remember run 1!")],
        ])

        # Wrap to capture what messages are sent
        captured_messages = []
        _orig_stream = original_provider.stream_response

        async def capturing_stream(system, messages, tools, **kw):
            captured_messages.append(list(messages))
            async for event in _orig_stream(system, messages, tools, **kw):
                yield event

        original_provider.stream_response = capturing_stream
        agent.provider = original_provider

        _run_agent(agent, "Second message")

        # The provider should have received messages from BOTH runs
        assert len(captured_messages) == 1
        msgs = captured_messages[0]
        # Should contain at least: user("First message"), user("Second message")
        user_msgs = [m for m in msgs if m.get("role") == "user" and isinstance(m.get("content"), str)]
        assert len(user_msgs) >= 2
        assert user_msgs[0]["content"] == "First message"
        assert user_msgs[1]["content"] == "Second message"

    def test_clear_conversation(self):
        """clear_conversation() resets message history."""
        config = AgentConfig(provider="anthropic", max_turns=5)
        tools = ToolRegistry()
        agent = SaltAgent(config, tools=tools)

        # Run 1
        agent.provider = MockProvider([
            [TextChunk(text="Response 1")],
        ])
        _run_agent(agent, "Message 1")
        assert len(agent._conversation_messages) > 0

        # Clear
        agent.clear_conversation()
        assert len(agent._conversation_messages) == 0

        # Run 2: should start fresh
        captured_messages = []
        provider2 = MockProvider([
            [TextChunk(text="Response 2")],
        ])
        _orig_stream2 = provider2.stream_response

        async def capturing_stream2(system, messages, tools, **kw):
            captured_messages.append(list(messages))
            async for event in _orig_stream2(system, messages, tools, **kw):
                yield event

        provider2.stream_response = capturing_stream2
        agent.provider = provider2

        _run_agent(agent, "Fresh start")

        msgs = captured_messages[0]
        # Should only have the one new message
        user_msgs = [m for m in msgs if m.get("role") == "user" and isinstance(m.get("content"), str)]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "Fresh start"

    def test_one_shot_doesnt_accumulate(self):
        """Each one-shot run with a fresh agent starts clean."""
        config = AgentConfig(provider="anthropic", max_turns=5)
        tools = ToolRegistry()

        # Agent 1
        agent1 = SaltAgent(config, tools=tools)
        agent1.provider = MockProvider([[TextChunk(text="R1")]])
        _run_agent(agent1, "Prompt 1")

        # Agent 2 (fresh) should not have agent1's history
        agent2 = SaltAgent(config, tools=tools)
        assert len(agent2._conversation_messages) == 0

    def test_tool_results_preserved_across_runs(self):
        """Tool results from run 1 are visible in run 2's context."""
        config = AgentConfig(provider="anthropic", max_turns=5)
        tools = ToolRegistry()
        tools.register(EchoTool())
        agent = SaltAgent(config, tools=tools)

        # Run 1: uses a tool
        agent.provider = MockProvider([
            [
                TextChunk(text="Echoing..."),
                ToolUse(tool_id="t1", tool_name="echo", tool_input={"text": "important data"}),
            ],
            [TextChunk(text="Got the echo result.")],
        ])
        _run_agent(agent, "Echo something")

        # Conversation should include tool use and tool result messages
        has_tool_use = any(
            isinstance(m.get("content"), list) and
            any(c.get("type") == "tool_use" for c in m["content"])
            for m in agent._conversation_messages
        )
        has_tool_result = any(
            isinstance(m.get("content"), list) and
            any(c.get("type") == "tool_result" for c in m["content"])
            for m in agent._conversation_messages
        )
        assert has_tool_use, "Tool use should be in conversation history"
        assert has_tool_result, "Tool result should be in conversation history"

        # Run 2: provider should see the full history including tool results
        captured_messages = []
        provider2 = MockProvider([[TextChunk(text="I see the echo.")]])
        _orig = provider2.stream_response

        async def capture(system, messages, tools, **kw):
            captured_messages.append(list(messages))
            async for event in _orig(system, messages, tools, **kw):
                yield event

        provider2.stream_response = capture
        agent.provider = provider2
        _run_agent(agent, "What was the echo result?")

        msgs = captured_messages[0]
        # Should have messages from run 1 (user, assistant with tool_use, user with tool_result, assistant text)
        # plus the new user message
        assert len(msgs) >= 5


class TestContextManager:
    def test_truncate_short(self):
        cm = ContextManager(max_tool_result_chars=100)
        assert cm.truncate_tool_result("short") == "short"

    def test_truncate_long(self):
        cm = ContextManager(max_tool_result_chars=100)
        long_text = "x" * 500
        result = cm.truncate_tool_result(long_text)
        assert "truncated" in result
        assert len(result) < 500

    def test_estimate_tokens(self):
        cm = ContextManager()
        assert cm.estimate_tokens("hello world") == len("hello world") // 4

    def test_manage_pressure_short(self):
        cm = ContextManager(context_window=200_000)
        msgs = [{"role": "user", "content": "hi"}]
        result = cm.manage_pressure(msgs)
        assert result == msgs  # No change needed

    def test_file_tracking(self):
        cm = ContextManager()
        cm.mark_file_read("/tmp/test.txt")
        assert cm.was_file_read("/tmp/test.txt")
        assert not cm.was_file_read("/tmp/other.txt")

    def test_manage_pressure_reduces(self):
        cm = ContextManager(context_window=100)  # Very small window
        msgs = [{"role": "user", "content": "x" * 200}]
        for i in range(20):
            msgs.append({"role": "assistant", "content": f"response {i}" * 50})
            msgs.append({"role": "user", "content": f"query {i}" * 50})
        result = cm.manage_pressure(msgs)
        assert len(result) < len(msgs)


class TestCreateAgent:
    def test_create_default(self):
        """create_agent returns a SaltAgent with default tools."""
        from salt_agent import create_agent
        agent = create_agent(provider="anthropic")
        assert isinstance(agent, SaltAgent)
        assert len(agent.tools.names()) == 12  # read, write, edit, multi_edit, bash, glob, grep, list_files, todo_write, agent, web_search, web_fetch

    def test_create_with_custom_config(self):
        from salt_agent import create_agent
        agent = create_agent(
            provider="anthropic",
            model="claude-haiku-4-20250514",
            max_turns=10,
            system_prompt="Test",
        )
        assert agent.config.model == "claude-haiku-4-20250514"
        assert agent.config.max_turns == 10
        assert "Test" in agent.context.system_prompt
