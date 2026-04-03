"""Agent tool -- spawn subagents from within the agent loop.

When the model calls this tool, the agent loop detects ``is_async() == True``
and iterates ``async_execute()`` which yields subagent events interleaved
with the parent's event stream.  No callbacks, no ThreadPoolExecutor hacks.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import TYPE_CHECKING, AsyncIterator

from salt_agent.events import AgentComplete, SubagentComplete, SubagentSpawned, TextChunk
from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.subagent import SubagentManager


class AgentTool(Tool):
    """Spawn a subagent to handle a focused task.

    The subagent gets its own context and tools but shares the working
    directory.  Use for exploring codebases, verifying code, running
    focused research, or delegating independent subtasks.
    """

    def __init__(self, subagent_manager: SubagentManager) -> None:
        self._manager = subagent_manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="agent",
            description=(
                "Spawn a subagent to handle a focused task. Use for: exploring codebases, "
                "verifying code, running focused research, or delegating independent subtasks. "
                "The subagent has its own context and tools but shares the working directory."
            ),
            params=[
                ToolParam("prompt", "string", "What the subagent should do"),
                ToolParam(
                    "mode",
                    "string",
                    "Agent mode: explore, verify, worker, general",
                    required=False,
                    enum=["explore", "verify", "worker", "general"],
                ),
            ],
        )

    # -- Async path (preferred -- used by the agent loop) --------------------

    def is_async(self) -> bool:
        return True

    async def async_execute(self, **kwargs) -> AsyncIterator[dict]:
        """Async execution — yields subagent events, then the final result.

        The agent loop iterates this generator, forwarding events from the
        child agent into the parent's event stream.  The final ``result``
        dict is used as the ``tool_result`` message.
        """
        prompt = kwargs["prompt"]
        mode = kwargs.get("mode", "general")

        # Create the child agent via the manager
        child = self._manager.create_fresh(mode=mode)

        result_text = ""

        # Signal that a subagent is starting
        yield {"type": "event", "event": SubagentSpawned(mode=mode, prompt=prompt[:100])}

        # Run the child and forward its events
        async for event in child.run(prompt):
            yield {"type": "event", "event": event}

            if isinstance(event, AgentComplete) and event.final_text:
                result_text = event.final_text
            elif isinstance(event, TextChunk):
                # Accumulate in case AgentComplete isn't emitted
                result_text += event.text

        # Signal completion
        yield {"type": "event", "event": SubagentComplete(result=result_text[:200])}

        # Final result goes back as tool_result content
        yield {"type": "result", "content": result_text or "Subagent completed with no output"}

    # -- Sync fallback (for contexts that don't support async tools) ---------

    def execute(self, **kwargs) -> str:
        """Sync fallback — used if the agent loop doesn't support async tools."""
        prompt = kwargs["prompt"]
        mode = kwargs.get("mode", "general")

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run,
                        self._run_sync(prompt, mode),
                    ).result(timeout=300)
            else:
                result = asyncio.run(self._run_sync(prompt, mode))

            return result
        except Exception as e:
            return f"Subagent error: {e}"

    async def _run_sync(self, prompt: str, mode: str) -> str:
        """Helper for the sync fallback path."""
        child = self._manager.create_fresh(mode=mode)
        result_text = ""
        async for event in child.run(prompt):
            if isinstance(event, AgentComplete) and event.final_text:
                result_text = event.final_text
            elif isinstance(event, TextChunk):
                result_text += event.text
        return result_text or "Subagent completed with no output"
