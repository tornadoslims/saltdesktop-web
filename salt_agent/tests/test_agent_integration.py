"""Integration tests for the agent loop with mocked LLM responses."""

import asyncio
from pathlib import Path

import pytest

from salt_agent.agent import SaltAgent
from salt_agent.config import AgentConfig
from salt_agent.events import (
    AgentComplete,
    AgentError,
    AgentEvent,
    TextChunk,
    ToolEnd,
    ToolStart,
    ToolUse,
)
from salt_agent.providers.base import ProviderAdapter
from salt_agent.tools.base import Tool, ToolDefinition, ToolParam, ToolRegistry
from salt_agent.tools.read import ReadTool
from salt_agent.tools.write import WriteTool
from salt_agent.tools.edit import EditTool


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------

class MockProvider(ProviderAdapter):
    """A mock provider that returns scripted responses in sequence."""

    def __init__(self, responses: list[list[AgentEvent]]):
        self._responses = responses
        self.call_count = 0

    async def stream_response(
        self, system, messages, tools, max_tokens=4096, temperature=0.0
    ):
        if self.call_count < len(self._responses):
            events = self._responses[self.call_count]
            self.call_count += 1
            for event in events:
                yield event
        else:
            yield TextChunk(text="Done.")

    async def quick_query(self, prompt: str, system: str = "", max_tokens: int = 500) -> str:
        """Side-queries (memory ranking, etc.) return empty -- don't consume scripted responses."""
        return ""


# ---------------------------------------------------------------------------
# Helper tools
# ---------------------------------------------------------------------------

class EchoTool(Tool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="echo",
            description="Echo input.",
            params=[ToolParam("text", "string", "Text to echo.")],
        )

    def execute(self, **kwargs) -> str:
        return f"Echo: {kwargs.get('text', '')}"


class CounterTool(Tool):
    """Tool that tracks how many times it's been called."""

    def __init__(self):
        self.call_count = 0

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="counter",
            description="Increment counter.",
            params=[],
        )

    def execute(self, **kwargs) -> str:
        self.call_count += 1
        return f"Count: {self.call_count}"


class FailOnceTool(Tool):
    """Tool that fails on first call, succeeds on subsequent calls."""

    def __init__(self):
        self.call_count = 0

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="fail_once",
            description="Fails first time.",
            params=[],
        )

    def execute(self, **kwargs) -> str:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("First call fails")
        return "Success on retry"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_events(agent, prompt) -> list[AgentEvent]:
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


def _make_agent(
    responses: list[list[AgentEvent]],
    tools: ToolRegistry | None = None,
    max_turns: int = 10,
) -> SaltAgent:
    config = AgentConfig(provider="anthropic", max_turns=max_turns)
    agent = SaltAgent(config, tools=tools or ToolRegistry())
    agent.provider = MockProvider(responses)
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAgentCompletesOnTextOnly:
    def test_text_only_response(self):
        """Agent returns text with no tool calls -> completes in 1 turn."""
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = _make_agent(
            responses=[[TextChunk(text="Hello, world!")]],
            tools=registry,
        )
        events = _collect_events(agent, "Hi")

        text_chunks = [e for e in events if isinstance(e, TextChunk)]
        completes = [e for e in events if isinstance(e, AgentComplete)]

        assert len(text_chunks) == 1
        assert text_chunks[0].text == "Hello, world!"
        assert len(completes) == 1
        assert completes[0].turns == 1
        assert completes[0].tools_used == []


class TestAgentExecutesOneTool:
    def test_one_tool_then_complete(self):
        """Agent uses a tool, gets result, then returns text."""
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = _make_agent(
            responses=[
                [ToolUse(tool_id="t1", tool_name="echo", tool_input={"text": "ping"})],
                [TextChunk(text="Got: Echo: ping")],
            ],
            tools=registry,
        )
        events = _collect_events(agent, "Echo ping")

        starts = [e for e in events if isinstance(e, ToolStart)]
        ends = [e for e in events if isinstance(e, ToolEnd)]
        completes = [e for e in events if isinstance(e, AgentComplete)]

        assert len(starts) == 1
        assert starts[0].tool_name == "echo"
        assert len(ends) == 1
        assert ends[0].success is True
        assert "Echo: ping" in ends[0].result
        assert len(completes) == 1
        assert completes[0].turns == 2
        assert "echo" in completes[0].tools_used


class TestAgentMultipleToolsInSequence:
    def test_three_tools_in_sequence(self):
        registry = ToolRegistry()
        counter = CounterTool()
        registry.register(counter)
        agent = _make_agent(
            responses=[
                [ToolUse(tool_id="t1", tool_name="counter", tool_input={})],
                [ToolUse(tool_id="t2", tool_name="counter", tool_input={})],
                [ToolUse(tool_id="t3", tool_name="counter", tool_input={})],
                [TextChunk(text="Done after 3 tool calls.")],
            ],
            tools=registry,
        )
        events = _collect_events(agent, "Count three times")

        starts = [e for e in events if isinstance(e, ToolStart)]
        ends = [e for e in events if isinstance(e, ToolEnd)]
        completes = [e for e in events if isinstance(e, AgentComplete)]

        assert len(starts) == 3
        assert len(ends) == 3
        assert counter.call_count == 3
        assert len(completes) == 1
        assert completes[0].turns == 4


class TestAgentRetriesAfterToolError:
    def test_tool_error_then_retry(self):
        registry = ToolRegistry()
        registry.register(FailOnceTool())
        agent = _make_agent(
            responses=[
                [ToolUse(tool_id="t1", tool_name="fail_once", tool_input={})],
                # After getting error result, model retries
                [ToolUse(tool_id="t2", tool_name="fail_once", tool_input={})],
                [TextChunk(text="Recovered.")],
            ],
            tools=registry,
        )
        events = _collect_events(agent, "Try the tool")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 2
        assert ends[0].success is False
        assert "First call fails" in ends[0].result
        assert ends[1].success is True

        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(completes) == 1


class TestAgentMaxTurnsLimit:
    def test_max_turns_reached(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = _make_agent(
            responses=[
                [ToolUse(tool_id=f"t{i}", tool_name="echo", tool_input={"text": str(i)})]
                for i in range(10)
            ],
            tools=registry,
            max_turns=3,
        )
        events = _collect_events(agent, "Loop forever")

        errors = [e for e in events if isinstance(e, AgentError)]
        assert len(errors) == 1
        assert "Max turns" in errors[0].error
        assert errors[0].recoverable is False

        # Should not have a complete event
        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(completes) == 0


class TestAgentEventSequence:
    def test_correct_event_ordering(self):
        """Events should come in order: ToolUse, ToolStart, ToolEnd, ..., TextChunk, AgentComplete."""
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = _make_agent(
            responses=[
                [
                    TextChunk(text="Thinking..."),
                    ToolUse(tool_id="t1", tool_name="echo", tool_input={"text": "hi"}),
                ],
                [TextChunk(text="All done.")],
            ],
            tools=registry,
        )
        events = _collect_events(agent, "Test order")

        types = [type(e).__name__ for e in events]
        # Should see: TextChunk, ToolUse, ToolStart, ToolEnd, TextChunk, AgentComplete
        assert types[0] == "TextChunk"
        assert types[1] == "ToolUse"
        assert types[2] == "ToolStart"
        assert types[3] == "ToolEnd"
        assert types[4] == "TextChunk"
        assert types[5] == "AgentComplete"


class TestAgentReadEditFlow:
    def test_edit_requires_read_first(self, tmp_path):
        """Integration test: edit tool fails if file not read, succeeds after read."""
        f = tmp_path / "target.txt"
        f.write_text("old content here")

        read_tool = ReadTool(working_directory=str(tmp_path))
        edit_tool = EditTool(read_tool=read_tool, working_directory=str(tmp_path))

        registry = ToolRegistry()
        registry.register(read_tool)
        registry.register(edit_tool)

        agent = _make_agent(
            responses=[
                # First: try edit without read -> will get error
                [ToolUse(tool_id="t1", tool_name="edit", tool_input={
                    "file_path": str(f),
                    "old_string": "old",
                    "new_string": "new",
                })],
                # Second: read the file
                [ToolUse(tool_id="t2", tool_name="read", tool_input={
                    "file_path": str(f),
                })],
                # Third: edit after read -> should succeed
                [ToolUse(tool_id="t3", tool_name="edit", tool_input={
                    "file_path": str(f),
                    "old_string": "old",
                    "new_string": "new",
                })],
                [TextChunk(text="Edit complete.")],
            ],
            tools=registry,
        )
        events = _collect_events(agent, "Edit the file")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 3
        # First edit returns error string (tool didn't raise, but result contains error)
        assert "not been read" in ends[0].result
        # Read succeeds
        assert ends[1].success is True
        # Second edit succeeds
        assert "Successfully" in ends[2].result

        # Verify the file was actually edited
        assert "new content here" in f.read_text()


class TestAgentWorkingDirectory:
    def test_working_directory_passed_to_tools(self, tmp_path):
        """Agent's working directory is used by tools for relative path resolution."""
        (tmp_path / "test.txt").write_text("wd content")

        read_tool = ReadTool(working_directory=str(tmp_path))
        registry = ToolRegistry()
        registry.register(read_tool)

        agent = _make_agent(
            responses=[
                [ToolUse(tool_id="t1", tool_name="read", tool_input={
                    "file_path": "test.txt",
                })],
                [TextChunk(text="Read it.")],
            ],
            tools=registry,
        )
        events = _collect_events(agent, "Read test.txt")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 1
        assert ends[0].success is True
        assert "wd content" in ends[0].result


class TestAgentMultipleToolsSameTurn:
    def test_parallel_tool_calls(self):
        """Agent can request multiple tools in a single turn."""
        registry = ToolRegistry()
        registry.register(EchoTool())

        agent = _make_agent(
            responses=[
                [
                    ToolUse(tool_id="t1", tool_name="echo", tool_input={"text": "first"}),
                    ToolUse(tool_id="t2", tool_name="echo", tool_input={"text": "second"}),
                ],
                [TextChunk(text="Both done.")],
            ],
            tools=registry,
        )
        events = _collect_events(agent, "Echo two things")

        starts = [e for e in events if isinstance(e, ToolStart)]
        ends = [e for e in events if isinstance(e, ToolEnd)]
        completes = [e for e in events if isinstance(e, AgentComplete)]

        assert len(starts) == 2
        assert len(ends) == 2
        assert all(e.success for e in ends)
        assert len(completes) == 1
        assert completes[0].turns == 2
        assert completes[0].tools_used == ["echo", "echo"]


class TestAgentFatalError:
    def test_non_recoverable_error_stops(self):
        agent = _make_agent(
            responses=[[AgentError(error="Fatal crash", recoverable=False)]],
        )
        events = _collect_events(agent, "Test")

        errors = [e for e in events if isinstance(e, AgentError)]
        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(errors) == 1
        assert errors[0].error == "Fatal crash"
        assert len(completes) == 0
