"""Agent tool -- spawn subagents from within the agent loop."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import TYPE_CHECKING, Callable

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.subagent import SubagentManager


class AgentTool(Tool):
    """Spawn a subagent to handle a focused task.

    The subagent gets its own context and tools but shares the working
    directory.  Use for exploring codebases, verifying code, running
    focused research, or delegating independent subtasks.
    """

    def __init__(
        self,
        subagent_manager: SubagentManager,
        event_callback: Callable | None = None,
    ) -> None:
        self._manager = subagent_manager
        self._event_callback = event_callback

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

    def execute(self, **kwargs) -> str:
        prompt = kwargs["prompt"]
        mode = kwargs.get("mode", "general")

        try:
            # We are inside an async event loop (the agent run loop), so we
            # must run the subagent in a separate thread to avoid blocking.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run,
                        self._manager.spawn_fresh(
                            prompt, mode,
                            event_callback=self._event_callback,
                        ),
                    ).result(timeout=300)
            else:
                result = asyncio.run(
                    self._manager.spawn_fresh(
                        prompt, mode,
                        event_callback=self._event_callback,
                    )
                )

            return result.get("result", "Subagent completed with no output")
        except Exception as e:
            return f"Subagent error: {e}"
