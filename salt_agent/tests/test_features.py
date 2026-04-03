"""Tests for TodoWrite, HookEngine, and Context Compaction."""

import asyncio
from unittest.mock import MagicMock

import pytest

from salt_agent.compaction import (
    compact_context,
    estimate_messages_tokens,
    estimate_tokens,
    needs_compaction,
)
from salt_agent.config import AgentConfig
from salt_agent.events import (
    AgentComplete,
    AgentEvent,
    ContextCompacted,
    TextChunk,
    ToolEnd,
    ToolStart,
    ToolUse,
)
from salt_agent.hooks import HookEngine, HookResult
from salt_agent.tools.todo import TodoWriteTool


# =============================================================================
# TodoWrite Tests
# =============================================================================


class TestTodoWriteTool:
    def test_create_tasks(self):
        """Create tasks and verify they are stored."""
        tool = TodoWriteTool()
        result = tool.execute(tasks=[
            {"content": "Read the file", "status": "pending"},
            {"content": "Edit the code", "status": "in_progress"},
            {"content": "Run tests", "status": "completed"},
        ])
        assert len(tool.tasks) == 3
        assert "1 done" in result
        assert "1 in progress" in result
        assert "1 pending" in result

    def test_replace_all_semantics(self):
        """Each call replaces the entire task list."""
        tool = TodoWriteTool()
        tool.execute(tasks=[
            {"content": "Task A", "status": "pending"},
            {"content": "Task B", "status": "pending"},
        ])
        assert len(tool.tasks) == 2

        # Replace with completely different list
        tool.execute(tasks=[
            {"content": "Task X", "status": "completed"},
        ])
        assert len(tool.tasks) == 1
        assert tool.tasks[0]["content"] == "Task X"
        assert tool.tasks[0]["status"] == "completed"

    def test_empty_tasks(self):
        """Passing empty list clears all tasks."""
        tool = TodoWriteTool()
        tool.execute(tasks=[{"content": "Something", "status": "pending"}])
        assert len(tool.tasks) == 1

        tool.execute(tasks=[])
        assert len(tool.tasks) == 0

    def test_default_status(self):
        """Missing status defaults to pending."""
        tool = TodoWriteTool()
        tool.execute(tasks=[{"content": "No status given"}])
        assert tool.tasks[0]["status"] == "pending"

    def test_context_injection_empty(self):
        """No tasks -> empty injection."""
        tool = TodoWriteTool()
        assert tool.get_context_injection() == ""

    def test_context_injection_with_tasks(self):
        """Tasks produce a formatted context injection."""
        tool = TodoWriteTool()
        tool.execute(tasks=[
            {"content": "Read file", "status": "completed"},
            {"content": "Write code", "status": "in_progress"},
            {"content": "Run tests", "status": "pending"},
        ])
        injection = tool.get_context_injection()
        assert "Current Tasks" in injection
        assert "\u2713 Read file" in injection
        assert "\u25d0 Write code" in injection
        assert "\u25cb Run tests" in injection

    def test_definition(self):
        """Tool definition has correct name and params."""
        tool = TodoWriteTool()
        defn = tool.definition()
        assert defn.name == "todo_write"
        assert len(defn.params) == 1
        assert defn.params[0].name == "tasks"
        assert defn.params[0].type == "array"


# =============================================================================
# Hook Engine Tests
# =============================================================================


class TestHookEngine:
    def test_register_and_fire(self):
        """Register a hook and fire it."""
        engine = HookEngine()
        called = []

        def my_hook(data):
            called.append(data)
            return HookResult(action="allow")

        engine.on("pre_tool_use", my_hook)
        result = engine.fire("pre_tool_use", {"tool_name": "bash"})

        assert result.action == "allow"
        assert len(called) == 1
        assert called[0]["tool_name"] == "bash"

    def test_block_tool(self):
        """A hook can block a tool execution."""
        engine = HookEngine()

        def blocker(data):
            if data.get("tool_name") == "bash":
                return HookResult(action="block", reason="Not allowed")
            return None

        engine.on("pre_tool_use", blocker)

        result = engine.fire("pre_tool_use", {"tool_name": "bash"})
        assert result.action == "block"
        assert result.reason == "Not allowed"

        # Other tools should pass
        result = engine.fire("pre_tool_use", {"tool_name": "read"})
        assert result.action == "allow"

    def test_first_block_wins(self):
        """When multiple hooks are registered, first block wins."""
        engine = HookEngine()

        def hook1(data):
            return HookResult(action="block", reason="Hook 1 blocked")

        def hook2(data):
            return HookResult(action="block", reason="Hook 2 blocked")

        engine.on("pre_tool_use", hook1)
        engine.on("pre_tool_use", hook2)

        result = engine.fire("pre_tool_use", {"tool_name": "test"})
        assert result.action == "block"
        assert result.reason == "Hook 1 blocked"

    def test_hook_exception_doesnt_crash(self):
        """Hooks that raise exceptions are silently ignored."""
        engine = HookEngine()

        def bad_hook(data):
            raise RuntimeError("Hook exploded")

        def good_hook(data):
            return HookResult(action="allow")

        engine.on("pre_tool_use", bad_hook)
        engine.on("pre_tool_use", good_hook)

        # Should not raise
        result = engine.fire("pre_tool_use", {"tool_name": "test"})
        assert result.action == "allow"

    def test_off_removes_hook(self):
        """off() removes a registered hook."""
        engine = HookEngine()
        called = []

        def my_hook(data):
            called.append(True)
            return None

        engine.on("test_event", my_hook)
        engine.fire("test_event", {})
        assert len(called) == 1

        engine.off("test_event", my_hook)
        engine.fire("test_event", {})
        assert len(called) == 1  # not called again

    def test_fire_no_hooks(self):
        """Firing an event with no hooks returns allow."""
        engine = HookEngine()
        result = engine.fire("nonexistent", {})
        assert result.action == "allow"

    def test_fire_async(self):
        """fire_async works with sync callbacks."""
        engine = HookEngine()

        def sync_hook(data):
            return HookResult(action="block", reason="Blocked async")

        engine.on("test", sync_hook)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(engine.fire_async("test", {}))
        finally:
            loop.close()

        assert result.action == "block"

    def test_fire_async_with_coroutine(self):
        """fire_async works with async callbacks."""
        engine = HookEngine()

        async def async_hook(data):
            return HookResult(action="block", reason="Async blocked")

        engine.on("test", async_hook)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(engine.fire_async("test", {}))
        finally:
            loop.close()

        assert result.action == "block"
        assert result.reason == "Async blocked"


# =============================================================================
# Compaction Tests
# =============================================================================


class TestCompaction:
    def test_estimate_tokens(self):
        """Token estimation is roughly 4 chars per token."""
        assert estimate_tokens("") == 0
        assert estimate_tokens("hello world") == len("hello world") // 4
        assert estimate_tokens("a" * 400) == 100

    def test_estimate_messages_tokens(self):
        """Message token estimation handles various content formats."""
        messages = [
            {"role": "user", "content": "Hello " * 100},
            {"role": "assistant", "content": "World " * 100},
        ]
        tokens = estimate_messages_tokens(messages)
        assert tokens > 0

    def test_estimate_messages_tokens_list_content(self):
        """Token estimation handles list content blocks."""
        messages = [
            {"role": "assistant", "content": [
                {"type": "text", "text": "some text here"},
                {"type": "tool_use", "name": "bash", "input": {"command": "ls"}},
            ]},
        ]
        tokens = estimate_messages_tokens(messages)
        assert tokens > 0

    def test_needs_compaction_false(self):
        """Short conversations don't need compaction."""
        config = AgentConfig(context_window=200_000)
        messages = [{"role": "user", "content": "hi"}]
        assert needs_compaction(messages, config) is False

    def test_needs_compaction_true(self):
        """Long conversations trigger compaction."""
        config = AgentConfig(context_window=100)  # Very small window
        messages = [{"role": "user", "content": "x" * 500}]
        assert needs_compaction(messages, config) is True

    def test_compact_too_few_messages(self):
        """compact_context returns messages unchanged if < 4 messages."""
        config = AgentConfig()
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                compact_context(messages, "", config, None)
            )
        finally:
            loop.close()

        assert result == messages

    def test_compact_preserves_recent(self):
        """Compacted result preserves the most recent messages."""

        class FakeSummarizer:
            async def stream_response(self, system, messages, tools, max_tokens=2000):
                yield TextChunk(text="Summary of previous conversation.")

        config = AgentConfig()
        messages = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
            {"role": "assistant", "content": "Second answer"},
            {"role": "user", "content": "Third question"},
            {"role": "assistant", "content": "Third answer"},
        ]

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                compact_context(messages, "system", config, FakeSummarizer())
            )
        finally:
            loop.close()

        # Should have: summary user msg, ack assistant msg, last 2 original msgs
        assert len(result) == 4
        assert "Context Summary" in result[0]["content"]
        assert "Understood" in result[1]["content"]
        # Last two messages preserved
        assert result[2]["content"] == "Third question"
        assert result[3]["content"] == "Third answer"

    def test_compact_fallback_on_empty_summary(self):
        """If summarizer returns nothing, fallback to last 6 messages."""

        class EmptySummarizer:
            async def stream_response(self, system, messages, tools, max_tokens=2000):
                # Yield nothing useful
                return
                yield  # make it an async generator

        config = AgentConfig()
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(20)]

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                compact_context(messages, "system", config, EmptySummarizer())
            )
        finally:
            loop.close()

        assert len(result) == 6  # fallback keeps last 6

    def test_compact_with_todo_state(self):
        """Todo state is included in the summarization prompt."""

        captured_messages = []

        class CapturingSummarizer:
            async def stream_response(self, system, messages, tools, max_tokens=2000):
                captured_messages.extend(messages)
                yield TextChunk(text="Summary with todos.")

        config = AgentConfig()
        messages = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ]

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                compact_context(
                    messages, "system", config, CapturingSummarizer(),
                    todo_state="## Tasks\n- Build feature",
                    files_read={"src/main.py", "tests/test.py"},
                )
            )
        finally:
            loop.close()

        # The summarization prompt should contain the todo state and files
        prompt_content = captured_messages[0]["content"]
        assert "Tasks" in prompt_content
        assert "Build feature" in prompt_content


# =============================================================================
# Agent Integration Tests
# =============================================================================


class TestAgentHookIntegration:
    """Test that hooks are properly wired into the agent loop."""

    def _make_agent(self):
        from salt_agent.agent import SaltAgent
        from salt_agent.tools.base import Tool, ToolDefinition, ToolParam, ToolRegistry

        class EchoTool(Tool):
            def definition(self):
                return ToolDefinition(
                    name="echo",
                    description="Echo input.",
                    params=[ToolParam("text", "string", "Text to echo.")],
                )
            def execute(self, **kwargs):
                return f"Echo: {kwargs.get('text', '')}"

        config = AgentConfig(provider="anthropic", max_turns=5)
        tools = ToolRegistry()
        tools.register(EchoTool())
        agent = SaltAgent(config, tools=tools)
        return agent

    def test_hook_blocks_tool(self):
        """A pre_tool_use hook can block tool execution in the agent loop."""
        agent = self._make_agent()

        def block_echo(data):
            if data.get("tool_name") == "echo":
                return HookResult(action="block", reason="No echoing allowed")
            return None

        agent.hooks.on("pre_tool_use", block_echo)

        # Mock provider: request echo tool, then finish
        class MockProv:
            _call = 0
            async def stream_response(self, system, messages, tools, max_tokens=4096, temperature=0.0):
                if self._call == 0:
                    self._call += 1
                    yield ToolUse(tool_id="t1", tool_name="echo", tool_input={"text": "hi"})
                else:
                    yield TextChunk(text="Done")
        agent.provider = MockProv()

        events = []
        loop = asyncio.new_event_loop()
        try:
            async def collect():
                async for ev in agent.run("test"):
                    events.append(ev)
            loop.run_until_complete(collect())
        finally:
            loop.close()

        tool_ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(tool_ends) == 1
        assert tool_ends[0].success is False
        assert "blocked" in tool_ends[0].result.lower()

    def test_hooks_fire_on_complete(self):
        """on_complete hook fires when agent finishes."""
        agent = self._make_agent()
        completed = []

        def on_complete(data):
            completed.append(data)
            return None

        agent.hooks.on("on_complete", on_complete)

        class MockProv:
            async def stream_response(self, system, messages, tools, max_tokens=4096, temperature=0.0):
                yield TextChunk(text="Done")
        agent.provider = MockProv()

        loop = asyncio.new_event_loop()
        try:
            async def collect():
                async for _ in agent.run("test"):
                    pass
            loop.run_until_complete(collect())
        finally:
            loop.close()

        assert len(completed) == 1
        assert completed[0]["turns"] == 1


class TestAgentTodoIntegration:
    """Test that TodoWrite is registered and injected into context."""

    def test_default_tools_include_todo(self):
        """Default tools include todo_write."""
        from salt_agent import create_agent
        agent = create_agent(provider="anthropic")
        assert "todo_write" in agent.tools.names()

    def test_todo_count(self):
        """Default tools now include 35 tools (10 original + web_search + web_fetch + 3 git + 6 task + skill + tool_search + ask_user + 2 plan_mode + sleep + config + send_message + 2 worktree + brief + python_repl + clipboard + open)."""
        from salt_agent import create_agent
        agent = create_agent(provider="anthropic")
        assert len(agent.tools.names()) == 35


class TestContextCompactedEvent:
    def test_event_fields(self):
        """ContextCompacted event has the right fields."""
        event = ContextCompacted(old_tokens=10000, new_tokens=2000)
        assert event.type == "compaction"
        assert event.old_tokens == 10000
        assert event.new_tokens == 2000
