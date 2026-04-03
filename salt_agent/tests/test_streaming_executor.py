"""Tests for the streaming tool executor."""

import asyncio
import time

import pytest

from salt_agent.events import (
    AgentEvent,
    TextChunk,
    ToolEnd,
    ToolStart,
    ToolUse,
)
from salt_agent.hooks import HookEngine, HookResult
from salt_agent.streaming_executor import (
    SAFE_STREAMING_TOOLS,
    PendingTool,
    StreamingToolExecutor,
)
from salt_agent.tools.base import Tool, ToolDefinition, ToolParam, ToolRegistry


# --- Test tools ---


class ReadTool(Tool):
    """Simulates a read-only tool (safe for streaming)."""

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.call_count = 0

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read",
            description="Read a file.",
            params=[ToolParam("file_path", "string", "Path to read.")],
        )

    def execute(self, **kwargs) -> str:
        if self.delay:
            time.sleep(self.delay)
        self.call_count += 1
        return f"contents of {kwargs.get('file_path', 'unknown')}"


class GrepTool(Tool):
    """Simulates grep (safe for streaming)."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="grep",
            description="Search files.",
            params=[ToolParam("pattern", "string", "Pattern.")],
        )

    def execute(self, **kwargs) -> str:
        return f"grep results for {kwargs.get('pattern', '')}"


class WriteTool(Tool):
    """Simulates a write tool (NOT safe for streaming)."""

    def __init__(self):
        self.call_count = 0

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write",
            description="Write a file.",
            params=[ToolParam("file_path", "string", "Path."),
                    ToolParam("content", "string", "Content.")],
        )

    def execute(self, **kwargs) -> str:
        self.call_count += 1
        return f"wrote {kwargs.get('file_path', 'unknown')}"


class BashTool(Tool):
    """Simulates bash (NOT safe for streaming)."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="bash",
            description="Run a command.",
            params=[ToolParam("command", "string", "Command.")],
        )

    def execute(self, **kwargs) -> str:
        return f"ran: {kwargs.get('command', '')}"


class FailingTool(Tool):
    """A tool that always fails."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read",
            description="Read that fails.",
            params=[ToolParam("file_path", "string", "Path.")],
        )

    def execute(self, **kwargs) -> str:
        raise RuntimeError("File not found")


# --- Helpers ---


def _make_registry(*tools: Tool) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


def _make_tool_use(name: str, tool_id: str = "", **inputs) -> ToolUse:
    return ToolUse(
        tool_id=tool_id or f"tu_{name}_{id(inputs)}",
        tool_name=name,
        tool_input=inputs,
    )


# --- Tests ---


class TestStreamingExecutorBasics:
    """Basic submit/execute/collect flow."""

    def test_safe_tool_starts_during_stream(self):
        async def _inner():
            read = ReadTool()
            registry = _make_registry(read)
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            tu = _make_tool_use("read", tool_id="tu1", file_path="/foo.txt")
            pending = executor.submit(tu)

            assert pending.started_during_stream is True
            assert pending.task is not None
            assert executor.streaming_count == 1

            await executor.collect_results()

        asyncio.run(_inner())

    def test_unsafe_tool_deferred(self):
        async def _inner():
            write = WriteTool()
            registry = _make_registry(write)
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            tu = _make_tool_use("write", tool_id="tu1", file_path="/foo.txt", content="bar")
            pending = executor.submit(tu)

            assert pending.started_during_stream is False
            assert pending.task is None
            assert executor.streaming_count == 0

        asyncio.run(_inner())

    def test_execute_remaining_runs_deferred_tools(self):
        async def _inner():
            write = WriteTool()
            registry = _make_registry(write)
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            tu = _make_tool_use("write", tool_id="tu1", file_path="/foo.txt", content="bar")
            executor.submit(tu)

            await executor.execute_remaining()
            results = await executor.collect_results()

            assert len(results) == 1
            assert results[0].success is True
            assert "wrote /foo.txt" in results[0].result

        asyncio.run(_inner())

    def test_safe_tool_completes_with_result(self):
        async def _inner():
            read = ReadTool()
            registry = _make_registry(read)
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            tu = _make_tool_use("read", tool_id="tu1", file_path="/hello.py")
            executor.submit(tu)

            results = await executor.collect_results()
            assert len(results) == 1
            assert results[0].success is True
            assert "contents of /hello.py" in results[0].result

        asyncio.run(_inner())

    def test_results_in_submission_order(self):
        async def _inner():
            read = ReadTool()
            grep = GrepTool()
            write = WriteTool()
            registry = _make_registry(read, grep, write)
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            tu1 = _make_tool_use("read", tool_id="tu1", file_path="/a.txt")
            tu2 = _make_tool_use("write", tool_id="tu2", file_path="/b.txt", content="x")
            tu3 = _make_tool_use("grep", tool_id="tu3", pattern="foo")

            executor.submit(tu1)
            executor.submit(tu2)
            executor.submit(tu3)

            await executor.execute_remaining()
            results = await executor.collect_results()

            assert len(results) == 3
            assert results[0].tool_use.tool_id == "tu1"
            assert results[1].tool_use.tool_id == "tu2"
            assert results[2].tool_use.tool_id == "tu3"

        asyncio.run(_inner())

    def test_clear_resets_state(self):
        async def _inner():
            read = ReadTool()
            registry = _make_registry(read)
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            tu = _make_tool_use("read", tool_id="tu1", file_path="/a.txt")
            executor.submit(tu)
            await executor.collect_results()

            executor.clear()
            assert executor.pending_count == 0
            assert executor.streaming_count == 0

        asyncio.run(_inner())


class TestStreamingExecutorHooks:
    """Hook integration tests."""

    def test_hook_blocks_safe_tool(self):
        async def _inner():
            read = ReadTool()
            registry = _make_registry(read)
            hooks = HookEngine()

            def block_all(data):
                return HookResult(action="block", reason="denied")

            hooks.on("pre_tool_use", block_all)
            executor = StreamingToolExecutor(registry, hooks)

            tu = _make_tool_use("read", tool_id="tu1", file_path="/secret.txt")
            pending = executor.submit(tu)

            assert pending.hook_blocked is True
            assert pending.started_during_stream is False
            assert "Tool blocked: denied" in pending.result
            assert pending.success is False

        asyncio.run(_inner())

    def test_hook_blocks_unsafe_tool_in_execute_remaining(self):
        async def _inner():
            write = WriteTool()
            registry = _make_registry(write)
            hooks = HookEngine()

            def block_writes(data):
                if data["tool_name"] == "write":
                    return HookResult(action="block", reason="read-only mode")
                return None

            hooks.on("pre_tool_use", block_writes)
            executor = StreamingToolExecutor(registry, hooks)

            tu = _make_tool_use("write", tool_id="tu1", file_path="/x.txt", content="y")
            executor.submit(tu)

            await executor.execute_remaining()
            results = await executor.collect_results()

            assert len(results) == 1
            assert results[0].success is False
            assert "read-only mode" in results[0].result

        asyncio.run(_inner())


class TestStreamingExecutorErrors:
    """Error handling tests."""

    def test_tool_exception_captured(self):
        async def _inner():
            failing = FailingTool()
            registry = _make_registry(failing)
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            tu = _make_tool_use("read", tool_id="tu1", file_path="/missing.txt")
            executor.submit(tu)

            results = await executor.collect_results()
            assert len(results) == 1
            assert results[0].success is False
            assert "File not found" in results[0].result

        asyncio.run(_inner())

    def test_unknown_tool(self):
        async def _inner():
            registry = _make_registry()  # empty
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            tu = _make_tool_use("nonexistent", tool_id="tu1")
            pending = executor.submit(tu)

            assert pending.started_during_stream is False

            await executor.execute_remaining()
            results = await executor.collect_results()

            assert len(results) == 1
            assert results[0].success is False
            assert "does not exist" in results[0].result

        asyncio.run(_inner())


class TestStreamingExecutorConcurrency:
    """Tests that safe tools actually run concurrently."""

    def test_safe_tools_run_in_parallel(self):
        async def _inner():
            read = ReadTool(delay=0.1)
            registry = _make_registry(read)
            grep = GrepTool()
            registry.register(grep)
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            tu1 = _make_tool_use("read", tool_id="tu1", file_path="/a.txt")
            tu2 = _make_tool_use("read", tool_id="tu2", file_path="/b.txt")

            start = time.monotonic()
            executor.submit(tu1)
            executor.submit(tu2)
            results = await executor.collect_results()
            elapsed = time.monotonic() - start

            assert len(results) == 2
            assert all(r.success for r in results)
            assert executor.streaming_count == 2
            # Parallel: < 0.25s. Sequential would be >= 0.2s.
            assert elapsed < 0.25, f"Expected parallel execution but took {elapsed:.2f}s"

        asyncio.run(_inner())

    def test_mixed_safe_and_unsafe_tools(self):
        async def _inner():
            read = ReadTool()
            write = WriteTool()
            registry = _make_registry(read, write)
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            tu_read = _make_tool_use("read", tool_id="tu1", file_path="/a.txt")
            tu_write = _make_tool_use("write", tool_id="tu2", file_path="/b.txt", content="x")

            executor.submit(tu_read)
            executor.submit(tu_write)

            assert executor.streaming_count == 1

            await executor.execute_remaining()
            results = await executor.collect_results()

            assert len(results) == 2
            assert results[0].started_during_stream is True
            assert results[1].started_during_stream is False
            assert results[0].success is True
            assert results[1].success is True

        asyncio.run(_inner())


class TestStreamingExecutorSafeSet:
    """Verify the safe tools set."""

    def test_safe_set_contents(self):
        expected = {"read", "glob", "grep", "list_files", "web_fetch", "web_search"}
        assert SAFE_STREAMING_TOOLS == expected

    def test_write_tools_not_safe(self):
        for tool_name in ("write", "edit", "multi_edit", "bash", "agent", "todo_write"):
            assert tool_name not in SAFE_STREAMING_TOOLS


class TestStreamingExecutorIntegration:
    """Integration-style tests simulating the agent loop pattern."""

    def test_full_streaming_flow(self):
        async def _inner():
            read = ReadTool()
            write = WriteTool()
            bash = BashTool()
            registry = _make_registry(read, write, bash)
            hooks = HookEngine()
            executor = StreamingToolExecutor(registry, hooks)

            stream_events = [
                _make_tool_use("read", tool_id="tu1", file_path="/src/main.py"),
                _make_tool_use("read", tool_id="tu2", file_path="/src/utils.py"),
                _make_tool_use("write", tool_id="tu3", file_path="/out.txt", content="result"),
                _make_tool_use("bash", tool_id="tu4", command="echo done"),
            ]

            started_during = []
            for tu in stream_events:
                pending = executor.submit(tu)
                if pending.started_during_stream:
                    started_during.append(tu.tool_id)

            assert "tu1" in started_during
            assert "tu2" in started_during
            assert "tu3" not in started_during
            assert "tu4" not in started_during

            await executor.execute_remaining()
            results = await executor.collect_results()

            assert len(results) == 4
            assert results[0].tool_use.tool_id == "tu1"
            assert "contents of /src/main.py" in results[0].result
            assert results[1].tool_use.tool_id == "tu2"
            assert "contents of /src/utils.py" in results[1].result
            assert results[2].tool_use.tool_id == "tu3"
            assert "wrote /out.txt" in results[2].result
            assert results[3].tool_use.tool_id == "tu4"
            assert "ran: echo done" in results[3].result
            assert all(r.success for r in results)

        asyncio.run(_inner())
