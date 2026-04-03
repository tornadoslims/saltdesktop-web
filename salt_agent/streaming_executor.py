"""Execute tools as they're detected in the model stream.

Manages concurrent execution of safe-to-parallelize tools while
buffering results in the correct order for the API response.

Safe tools (read-only, no side effects) start executing immediately
when their tool_use block is detected mid-stream. Unsafe tools are
queued and executed after the stream completes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from salt_agent.events import ToolUse
from salt_agent.hooks import HookEngine, HookResult
from salt_agent.tools.base import Tool, ToolRegistry

# Tools that are safe to execute while the model is still streaming.
# These are read-only / side-effect-free and can run concurrently.
SAFE_STREAMING_TOOLS = frozenset({
    "read", "glob", "grep", "list_files", "web_fetch", "web_search",
})


@dataclass
class PendingTool:
    """A tool queued for execution during or after streaming."""
    tool_use: ToolUse
    task: asyncio.Task | None = None
    result: str = ""
    success: bool = True
    started_during_stream: bool = False
    hook_blocked: bool = False


class StreamingToolExecutor:
    """Queues and executes tools as they arrive from the model stream.

    Usage:
        executor = StreamingToolExecutor(tools, hooks)

        # During streaming:
        for event in stream:
            if isinstance(event, ToolUse):
                executor.submit(event)

        # After stream ends:
        await executor.execute_remaining()
        results = await executor.collect_results()
    """

    def __init__(
        self,
        tools: ToolRegistry,
        hooks: HookEngine,
    ) -> None:
        self.tools = tools
        self.hooks = hooks
        self._pending: list[PendingTool] = []
        self._started_ids: set[str] = set()

    def submit(self, tool_use: ToolUse, loop: asyncio.AbstractEventLoop | None = None) -> PendingTool:
        """Queue a tool for execution. Starts immediately if safe.

        Pre-tool hooks are checked synchronously before starting.
        If a hook blocks the tool, the result is set immediately.

        Args:
            tool_use: The tool use event from the stream.
            loop: The running event loop (for creating tasks). If not provided,
                  attempts to get the running loop.
        """
        pending = PendingTool(tool_use=tool_use)
        self._pending.append(pending)

        # Check hooks synchronously (fire, not fire_async, to avoid blocking the stream)
        hook_result = self.hooks.fire("pre_tool_use", {
            "tool_name": tool_use.tool_name,
            "tool_input": tool_use.tool_input,
        })
        if hook_result.action == "block":
            pending.result = f"Tool blocked: {hook_result.reason}"
            pending.success = False
            pending.hook_blocked = True
            return pending

        # Start immediately if safe to run during streaming
        if tool_use.tool_name in SAFE_STREAMING_TOOLS:
            pending.started_during_stream = True
            if loop is None:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # No running loop -- cannot create task (shouldn't happen in production)
                    pending.started_during_stream = False
                    return pending
            pending.task = loop.create_task(self._execute_one(pending))
            self._started_ids.add(tool_use.tool_id)

        return pending

    async def _execute_one(self, pending: PendingTool) -> None:
        """Execute a single tool (runs in executor for sync tools)."""
        tu = pending.tool_use
        tool = self.tools.get(tu.tool_name)

        if not tool:
            available = ", ".join(self.tools.names())
            pending.result = (
                f"Error: Tool '{tu.tool_name}' does not exist. "
                f"Available tools: {available}. "
                f"Do NOT try to simulate this tool with bash echo or other workarounds. "
                f"If you cannot accomplish the task with available tools, say so."
            )
            pending.success = False
            return

        if tool.is_async():
            # Async tools (like agent tool) must be run sequentially and yield events.
            # They are NOT safe for streaming execution -- they'll be handled in
            # execute_remaining with special async handling.
            result = ""
            success = True
            try:
                async for item in tool.async_execute(**tu.tool_input):
                    if item["type"] == "result":
                        result = item["content"]
            except Exception as e:
                result = f"Error: {str(e)}"
                success = False

            if result.startswith("Error"):
                success = False

            pending.result = result
            pending.success = success
            return

        # Sync tool -- run in thread executor
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: tool.execute(**tu.tool_input)
            )
            pending.result = result
            pending.success = True
        except Exception as e:
            pending.result = f"Error: {str(e)}"
            pending.success = False

    async def execute_remaining(self) -> None:
        """Execute any tools that were NOT started during streaming.

        This runs after the stream completes. Unsafe tools (write, edit,
        bash, etc.) are executed here sequentially.
        """
        for pending in self._pending:
            if pending.hook_blocked:
                continue  # Already has a result
            if pending.tool_use.tool_id in self._started_ids:
                continue  # Already running or finished

            # For remaining tools, run pre_tool_use hook async (we're no longer in the stream)
            hook_result = await self.hooks.fire_async("pre_tool_use", {
                "tool_name": pending.tool_use.tool_name,
                "tool_input": pending.tool_use.tool_input,
            })
            if hook_result.action == "block":
                pending.result = f"Tool blocked: {hook_result.reason}"
                pending.success = False
                pending.hook_blocked = True
                continue

            await self._execute_one(pending)

    async def collect_results(self) -> list[PendingTool]:
        """Wait for all in-flight tasks and return results in order."""
        tasks = [p.task for p in self._pending if p.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Check for task exceptions and update results
        for pending in self._pending:
            if pending.task is not None and pending.task.done():
                exc = pending.task.exception()
                if exc is not None:
                    pending.result = f"Error: {exc}"
                    pending.success = False

        return self._pending

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def streaming_count(self) -> int:
        """Number of tools that started during streaming."""
        return len(self._started_ids)

    def clear(self) -> None:
        """Reset state for next turn."""
        self._pending.clear()
        self._started_ids.clear()
