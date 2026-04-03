"""End-to-end tests with mock providers that test the FULL agent flow.

Every test uses a MockProvider so no real API calls are made.
File operations use tmp_path for isolation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from salt_agent.agent import SaltAgent
from salt_agent.config import AgentConfig
from salt_agent.events import (
    AgentComplete,
    AgentError,
    AgentEvent,
    ContextCompacted,
    FileSnapshotted,
    SubagentComplete,
    SubagentSpawned,
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
from salt_agent.tools.bash import BashTool


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------


class MockProvider(ProviderAdapter):
    """A mock provider that returns scripted responses in sequence."""

    def __init__(self, responses: list[list[AgentEvent]]):
        self._responses = responses
        self.call_count = 0
        self.received_messages: list[list[dict]] = []

    async def stream_response(
        self, system, messages, tools, max_tokens=4096, temperature=0.0
    ):
        self.received_messages.append(list(messages))
        if self.call_count < len(self._responses):
            events = self._responses[self.call_count]
            self.call_count += 1
            for event in events:
                yield event
        else:
            yield TextChunk(text="Done.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_events(agent: SaltAgent, prompt: str) -> list[AgentEvent]:
    """Run the agent and collect all emitted events."""
    events: list[AgentEvent] = []

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
    working_directory: str = ".",
    persist: bool = False,
) -> tuple[SaltAgent, MockProvider]:
    """Create a SaltAgent with a MockProvider."""
    config = AgentConfig(
        provider="anthropic",
        api_key="sk-test-mock",
        max_turns=max_turns,
        working_directory=working_directory,
        persist=persist,
        include_web_tools=False,
    )
    agent = SaltAgent(config, tools=tools or ToolRegistry())
    provider = MockProvider(responses)
    agent.provider = provider
    return agent, provider


def _make_file_tools(tmp_path: Path) -> tuple[ToolRegistry, ReadTool, WriteTool, EditTool]:
    """Create a registry with file-based tools rooted at tmp_path."""
    read_tool = ReadTool(working_directory=str(tmp_path))
    write_tool = WriteTool(read_tool=read_tool, working_directory=str(tmp_path))
    edit_tool = EditTool(read_tool=read_tool, working_directory=str(tmp_path))
    registry = ToolRegistry()
    registry.register(read_tool)
    registry.register(write_tool)
    registry.register(edit_tool)
    return registry, read_tool, write_tool, edit_tool


# ---------------------------------------------------------------------------
# E2E Tests
# ---------------------------------------------------------------------------


class TestE2EWriteAndRun:
    """Agent writes a file and runs it -- full flow with mock provider."""

    def test_write_then_bash(self, tmp_path):
        target = tmp_path / "hello.py"
        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)
        bash_tool = BashTool(timeout=10, working_directory=str(tmp_path))
        registry.register(bash_tool)

        agent, provider = _make_agent(
            responses=[
                # Turn 1: write a file
                [ToolUse(
                    tool_id="t1",
                    tool_name="write",
                    tool_input={
                        "file_path": str(target),
                        "content": "print('Hello from test!')\n",
                    },
                )],
                # Turn 2: run it
                [ToolUse(
                    tool_id="t2",
                    tool_name="bash",
                    tool_input={"command": f"python {target}"},
                )],
                # Turn 3: summarize
                [TextChunk(text="Script ran successfully.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Write and run a hello script")

        # File was created
        assert target.exists()
        assert "Hello from test!" in target.read_text()

        # Bash tool ran
        bash_ends = [e for e in events if isinstance(e, ToolEnd) and e.tool_name == "bash"]
        assert len(bash_ends) == 1
        assert bash_ends[0].success is True
        assert "Hello from test!" in bash_ends[0].result

        # Completed
        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(completes) == 1
        assert completes[0].turns == 3


class TestE2EReadEditFlow:
    """Agent reads a file, then edits it -- enforces read-before-edit."""

    def test_read_then_edit(self, tmp_path):
        target = tmp_path / "config.txt"
        target.write_text("debug=false\nverbose=true\n")
        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)

        agent, provider = _make_agent(
            responses=[
                # Read first
                [ToolUse(
                    tool_id="t1",
                    tool_name="read",
                    tool_input={"file_path": str(target)},
                )],
                # Edit after read
                [ToolUse(
                    tool_id="t2",
                    tool_name="edit",
                    tool_input={
                        "file_path": str(target),
                        "old_string": "debug=false",
                        "new_string": "debug=true",
                    },
                )],
                # Summarize
                [TextChunk(text="Config updated.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Enable debug mode")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 2
        assert ends[0].success is True  # read
        assert ends[1].success is True  # edit

        assert "debug=true" in target.read_text()

    def test_edit_without_read_fails(self, tmp_path):
        """Edit without prior read should fail with an error."""
        target = tmp_path / "config.txt"
        target.write_text("debug=false\n")
        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)

        agent, provider = _make_agent(
            responses=[
                # Try edit without read
                [ToolUse(
                    tool_id="t1",
                    tool_name="edit",
                    tool_input={
                        "file_path": str(target),
                        "old_string": "debug=false",
                        "new_string": "debug=true",
                    },
                )],
                [TextChunk(text="Failed as expected.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Edit without reading")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 1
        # The edit tool returns an error about not having read the file
        assert "not been read" in ends[0].result

        # File unchanged
        assert "debug=false" in target.read_text()


class TestE2EMaxTurnsReached:
    """Agent hits max turns and stops cleanly."""

    def test_max_turns(self):
        registry = ToolRegistry()

        class IncrTool(Tool):
            def __init__(self):
                self.count = 0

            def definition(self):
                return ToolDefinition(name="incr", description="Increment.", params=[])

            def execute(self, **kwargs):
                self.count += 1
                return f"count={self.count}"

        incr = IncrTool()
        registry.register(incr)

        # Create 20 responses that all request the tool, but max_turns=3
        responses = [
            [ToolUse(tool_id=f"t{i}", tool_name="incr", tool_input={})]
            for i in range(20)
        ]
        agent, provider = _make_agent(responses=responses, tools=registry, max_turns=3)
        events = _collect_events(agent, "Keep incrementing")

        errors = [e for e in events if isinstance(e, AgentError)]
        assert len(errors) == 1
        assert "Max turns" in errors[0].error
        assert errors[0].recoverable is False

        # Should have done exactly 3 tool calls
        assert incr.count == 3


class TestE2ELoopDetection:
    """Agent enters a tool loop and gets warned then stopped."""

    def test_loop_detected(self):
        registry = ToolRegistry()

        class NopTool(Tool):
            def __init__(self):
                self.count = 0

            def definition(self):
                return ToolDefinition(name="nop", description="No-op.", params=[])

            def execute(self, **kwargs):
                self.count += 1
                return "ok"

        nop = NopTool()
        registry.register(nop)

        # Same tool call pattern repeated many times -> triggers loop detection
        responses = [
            [ToolUse(tool_id=f"t{i}", tool_name="nop", tool_input={})]
            for i in range(30)
        ]
        agent, provider = _make_agent(responses=responses, tools=registry, max_turns=25)
        events = _collect_events(agent, "Do the same thing forever")

        # Should eventually get an error about loop or max turns
        errors = [e for e in events if isinstance(e, AgentError)]
        assert len(errors) >= 1
        # Either loop detection or max turns
        error_text = " ".join(e.error for e in errors)
        assert "loop" in error_text.lower() or "max turns" in error_text.lower()


class TestE2EUnknownTool:
    """LLM requests a nonexistent tool, gets error with available tools."""

    def test_unknown_tool_handled(self):
        registry = ToolRegistry()

        class EchoTool(Tool):
            def definition(self):
                return ToolDefinition(
                    name="echo", description="Echo.", params=[ToolParam("text", "string", "text")]
                )

            def execute(self, **kwargs):
                return kwargs.get("text", "")

        registry.register(EchoTool())

        agent, provider = _make_agent(
            responses=[
                # LLM requests a tool that doesn't exist
                [ToolUse(tool_id="t1", tool_name="nonexistent_tool", tool_input={"x": 1})],
                # After error, LLM completes
                [TextChunk(text="Sorry, that tool doesn't exist.")],
            ],
            tools=registry,
        )
        events = _collect_events(agent, "Use a fake tool")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 1
        assert ends[0].success is False
        assert "does not exist" in ends[0].result
        assert "echo" in ends[0].result  # available tools listed


class TestE2EPermissionBlocked:
    """Dangerous bash command is blocked by permission system."""

    def test_rm_rf_blocked(self, tmp_path):
        registry = ToolRegistry()
        bash_tool = BashTool(timeout=10, working_directory=str(tmp_path))
        registry.register(bash_tool)

        agent, provider = _make_agent(
            responses=[
                [ToolUse(
                    tool_id="t1",
                    tool_name="bash",
                    tool_input={"command": "rm -rf /important"},
                )],
                [TextChunk(text="Command was blocked.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Delete everything")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 1
        assert ends[0].success is False
        assert "blocked" in ends[0].result.lower() or "Tool blocked" in ends[0].result

    def test_sudo_blocked(self, tmp_path):
        registry = ToolRegistry()
        bash_tool = BashTool(timeout=10, working_directory=str(tmp_path))
        registry.register(bash_tool)

        agent, provider = _make_agent(
            responses=[
                [ToolUse(
                    tool_id="t1",
                    tool_name="bash",
                    tool_input={"command": "sudo rm -rf /"},
                )],
                [TextChunk(text="Blocked.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Sudo delete")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 1
        assert ends[0].success is False


class TestE2EFileHistoryRewind:
    """Agent modifies files, rewind restores originals."""

    def test_rewind_restores_file(self, tmp_path):
        target = tmp_path / "original.txt"
        target.write_text("original content")

        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)

        agent, provider = _make_agent(
            responses=[
                # Read file
                [ToolUse(
                    tool_id="t1",
                    tool_name="read",
                    tool_input={"file_path": str(target)},
                )],
                # Overwrite file
                [ToolUse(
                    tool_id="t2",
                    tool_name="write",
                    tool_input={
                        "file_path": str(target),
                        "content": "modified content",
                    },
                )],
                [TextChunk(text="Modified.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Modify the file")

        # File should be modified
        assert "modified content" in target.read_text()

        # Rewind
        agent.file_history.rewind()

        # File should be restored
        assert "original content" in target.read_text()

    def test_rewind_deletes_created_file(self, tmp_path):
        new_file = tmp_path / "created_by_agent.txt"
        assert not new_file.exists()

        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)

        agent, provider = _make_agent(
            responses=[
                [ToolUse(
                    tool_id="t1",
                    tool_name="write",
                    tool_input={
                        "file_path": str(new_file),
                        "content": "new file content",
                    },
                )],
                [TextChunk(text="Created.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Create a new file")

        assert new_file.exists()

        # Rewind should delete the created file
        agent.file_history.rewind()
        assert not new_file.exists()


class TestE2EMultipleToolsSameTurn:
    """Agent requests multiple tools in a single turn (parallel tools)."""

    def test_parallel_reads(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content_a")
        f2.write_text("content_b")

        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)

        agent, provider = _make_agent(
            responses=[
                # Both reads in one turn
                [
                    ToolUse(tool_id="t1", tool_name="read", tool_input={"file_path": str(f1)}),
                    ToolUse(tool_id="t2", tool_name="read", tool_input={"file_path": str(f2)}),
                ],
                [TextChunk(text="Read both files.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Read two files")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 2
        assert all(e.success for e in ends)

        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(completes) == 1
        assert completes[0].turns == 2


class TestE2EToolError:
    """Agent encounters a tool error and model can recover."""

    def test_tool_error_recovery(self, tmp_path):
        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)

        # Reading a non-existent file should fail
        agent, provider = _make_agent(
            responses=[
                [ToolUse(
                    tool_id="t1",
                    tool_name="read",
                    tool_input={"file_path": str(tmp_path / "nonexistent.txt")},
                )],
                [TextChunk(text="File not found, I'll try something else.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Read a missing file")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 1
        # ReadTool returns the error as text in the result (success=True)
        # but the result contains an error message
        assert "Error" in ends[0].result or "not found" in ends[0].result.lower()

        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(completes) == 1


class TestE2ETextOnlyResponse:
    """Agent responds with text only -- no tools needed."""

    def test_text_only(self):
        agent, provider = _make_agent(
            responses=[
                [TextChunk(text="Hello! "), TextChunk(text="I can help with that.")],
            ],
        )
        events = _collect_events(agent, "Hi there")

        text_chunks = [e for e in events if isinstance(e, TextChunk)]
        assert len(text_chunks) == 2

        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(completes) == 1
        assert completes[0].turns == 1
        assert completes[0].tools_used == []


class TestE2EFatalError:
    """Fatal error from provider stops the agent."""

    def test_fatal_error_stops(self):
        agent, provider = _make_agent(
            responses=[
                [AgentError(error="API rate limit exceeded", recoverable=False)],
            ],
        )
        events = _collect_events(agent, "Do something")

        errors = [e for e in events if isinstance(e, AgentError)]
        assert len(errors) == 1
        assert "rate limit" in errors[0].error.lower()

        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(completes) == 0


class TestE2EBashExecution:
    """Agent uses bash tool to execute commands."""

    def test_bash_echo(self, tmp_path):
        registry = ToolRegistry()
        bash_tool = BashTool(timeout=10, working_directory=str(tmp_path))
        registry.register(bash_tool)

        agent, provider = _make_agent(
            responses=[
                [ToolUse(
                    tool_id="t1",
                    tool_name="bash",
                    tool_input={"command": "echo 'hello world'"},
                )],
                [TextChunk(text="The command output hello world.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Echo hello world")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 1
        assert ends[0].success is True
        assert "hello world" in ends[0].result

    def test_bash_failure(self, tmp_path):
        registry = ToolRegistry()
        bash_tool = BashTool(timeout=10, working_directory=str(tmp_path))
        registry.register(bash_tool)

        agent, provider = _make_agent(
            responses=[
                [ToolUse(
                    tool_id="t1",
                    tool_name="bash",
                    tool_input={"command": "false"},  # exits with 1
                )],
                [TextChunk(text="Command failed.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Run a failing command")

        # bash tool may still "succeed" in tool execution but return exit code info
        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(completes) == 1


class TestE2EWriteReadCycle:
    """Full write -> read -> verify cycle."""

    def test_write_then_read(self, tmp_path):
        target = tmp_path / "output.txt"
        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)

        agent, provider = _make_agent(
            responses=[
                # Write
                [ToolUse(
                    tool_id="t1",
                    tool_name="write",
                    tool_input={
                        "file_path": str(target),
                        "content": "generated content\nline 2\n",
                    },
                )],
                # Read it back
                [ToolUse(
                    tool_id="t2",
                    tool_name="read",
                    tool_input={"file_path": str(target)},
                )],
                # Confirm
                [TextChunk(text="File verified.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Write and verify")

        ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(ends) == 2
        assert ends[0].success is True  # write
        assert ends[1].success is True  # read
        assert "generated content" in ends[1].result


class TestE2EEventOrdering:
    """Events must come in the correct order."""

    def test_correct_ordering(self, tmp_path):
        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)
        target = tmp_path / "test.txt"
        target.write_text("hello")

        agent, provider = _make_agent(
            responses=[
                [
                    TextChunk(text="Let me read that. "),
                    ToolUse(tool_id="t1", tool_name="read", tool_input={"file_path": str(target)}),
                ],
                [TextChunk(text="The file says hello.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Read test.txt")

        types = [type(e).__name__ for e in events]
        assert types[0] == "TextChunk"
        assert types[1] == "ToolUse"
        assert types[2] == "ToolStart"
        assert types[3] == "ToolEnd"
        assert types[4] == "TextChunk"
        assert types[5] == "AgentComplete"


class TestE2EProviderReceivesContext:
    """Verify that the provider receives properly structured messages."""

    def test_messages_include_tool_results(self, tmp_path):
        registry = ToolRegistry()

        class PingTool(Tool):
            def definition(self):
                return ToolDefinition(name="ping", description="Pong.", params=[])

            def execute(self, **kwargs):
                return "pong"

        registry.register(PingTool())

        agent, provider = _make_agent(
            responses=[
                [ToolUse(tool_id="t1", tool_name="ping", tool_input={})],
                [TextChunk(text="Got pong.")],
            ],
            tools=registry,
        )
        _collect_events(agent, "Ping")

        # Provider should have been called twice
        assert provider.call_count == 2

        # Second call should include tool result
        second_messages = provider.received_messages[1]
        # Last message should be user message with tool_result
        last_msg = second_messages[-1]
        assert last_msg["role"] == "user"
        assert isinstance(last_msg["content"], list)
        assert any("tool_result" in str(item.get("type", "")) for item in last_msg["content"])


class TestE2ELongToolChain:
    """Agent chains many tools together before completing."""

    def test_five_tool_chain(self, tmp_path):
        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)
        bash_tool = BashTool(timeout=10, working_directory=str(tmp_path))
        registry.register(bash_tool)

        f = tmp_path / "counter.txt"
        f.write_text("0")

        agent, provider = _make_agent(
            responses=[
                [ToolUse(tool_id="t1", tool_name="read", tool_input={"file_path": str(f)})],
                [ToolUse(tool_id="t2", tool_name="write", tool_input={"file_path": str(f), "content": "1"})],
                [ToolUse(tool_id="t3", tool_name="read", tool_input={"file_path": str(f)})],
                [ToolUse(tool_id="t4", tool_name="write", tool_input={"file_path": str(f), "content": "2"})],
                [ToolUse(tool_id="t5", tool_name="read", tool_input={"file_path": str(f)})],
                [TextChunk(text="Counted to 2.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Count up")

        starts = [e for e in events if isinstance(e, ToolStart)]
        assert len(starts) == 5

        completes = [e for e in events if isinstance(e, AgentComplete)]
        assert len(completes) == 1
        assert completes[0].turns == 6
        assert f.read_text() == "2"


class TestE2EParallelToolExecution:
    """Parallel-safe tools should have all ToolStarts before any ToolEnd."""

    def test_parallel_reads_event_ordering(self, tmp_path):
        """Multiple read calls should execute in parallel: all starts before all ends."""
        f1 = tmp_path / "x.txt"
        f2 = tmp_path / "y.txt"
        f3 = tmp_path / "z.txt"
        f1.write_text("alpha")
        f2.write_text("beta")
        f3.write_text("gamma")

        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)

        agent, provider = _make_agent(
            responses=[
                # Three reads in one turn -> parallel
                [
                    ToolUse(tool_id="t1", tool_name="read", tool_input={"file_path": str(f1)}),
                    ToolUse(tool_id="t2", tool_name="read", tool_input={"file_path": str(f2)}),
                    ToolUse(tool_id="t3", tool_name="read", tool_input={"file_path": str(f3)}),
                ],
                [TextChunk(text="Read all three.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Read three files")

        # Extract just starts and ends
        start_end = [e for e in events if isinstance(e, (ToolStart, ToolEnd))]
        assert len(start_end) == 6  # 3 starts + 3 ends

        # All ToolStarts must come before any ToolEnd (parallel pattern)
        types = [type(e).__name__ for e in start_end]
        assert types == ["ToolStart", "ToolStart", "ToolStart", "ToolEnd", "ToolEnd", "ToolEnd"]

        # All succeeded
        ends = [e for e in start_end if isinstance(e, ToolEnd)]
        assert all(e.success for e in ends)

    def test_sequential_for_write_tools(self, tmp_path):
        """Write tools should always be sequential: Start/End pairs interleaved."""
        f1 = tmp_path / "out1.txt"
        f2 = tmp_path / "out2.txt"

        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)

        agent, provider = _make_agent(
            responses=[
                # Two writes in one turn -> must be sequential
                [
                    ToolUse(tool_id="t1", tool_name="write", tool_input={
                        "file_path": str(f1), "content": "file1",
                    }),
                    ToolUse(tool_id="t2", tool_name="write", tool_input={
                        "file_path": str(f2), "content": "file2",
                    }),
                ],
                [TextChunk(text="Wrote both.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Write two files")

        # Extract starts and ends
        start_end = [e for e in events if isinstance(e, (ToolStart, ToolEnd))]
        assert len(start_end) == 4  # 2 starts + 2 ends

        # Sequential: Start, End, Start, End (interleaved pairs)
        types = [type(e).__name__ for e in start_end]
        assert types == ["ToolStart", "ToolEnd", "ToolStart", "ToolEnd"]

        # Both files written
        assert f1.read_text() == "file1"
        assert f2.read_text() == "file2"

    def test_mixed_tools_stay_sequential(self, tmp_path):
        """Mixed parallel-safe and unsafe tools should stay sequential."""
        f1 = tmp_path / "data.txt"
        f1.write_text("hello")

        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)
        bash_tool = BashTool(timeout=10, working_directory=str(tmp_path))
        registry.register(bash_tool)

        agent, provider = _make_agent(
            responses=[
                # read + bash in one turn -> sequential (mixed)
                [
                    ToolUse(tool_id="t1", tool_name="read", tool_input={"file_path": str(f1)}),
                    ToolUse(tool_id="t2", tool_name="bash", tool_input={"command": "echo hi"}),
                ],
                [TextChunk(text="Done.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Read and bash")

        start_end = [e for e in events if isinstance(e, (ToolStart, ToolEnd))]
        types = [type(e).__name__ for e in start_end]
        # Sequential: Start, End, Start, End
        assert types == ["ToolStart", "ToolEnd", "ToolStart", "ToolEnd"]

    def test_single_tool_stays_sequential(self, tmp_path):
        """A single tool call should use the sequential path (no parallel overhead)."""
        f1 = tmp_path / "solo.txt"
        f1.write_text("alone")

        registry, read_tool, write_tool, edit_tool = _make_file_tools(tmp_path)

        agent, provider = _make_agent(
            responses=[
                [ToolUse(tool_id="t1", tool_name="read", tool_input={"file_path": str(f1)})],
                [TextChunk(text="Read it.")],
            ],
            tools=registry,
            working_directory=str(tmp_path),
        )
        events = _collect_events(agent, "Read one file")

        start_end = [e for e in events if isinstance(e, (ToolStart, ToolEnd))]
        types = [type(e).__name__ for e in start_end]
        # Single tool: sequential Start, End
        assert types == ["ToolStart", "ToolEnd"]
