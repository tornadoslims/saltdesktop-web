"""Bridge MCP tools into SaltAgent's ToolRegistry."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class MCPToolBridge(Tool):
    """Wraps an MCP server tool as a SaltAgent Tool.

    Converts MCP tool schemas into SaltAgent ToolDefinition objects and
    bridges synchronous execute() calls to the async MCP call_tool API.
    """

    def __init__(
        self,
        server_name: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict[str, Any],
        call_fn: Callable[[str, dict], Coroutine[Any, Any, str]],
    ) -> None:
        """
        Args:
            server_name: Name of the MCP server this tool comes from.
            tool_name: The tool's name as reported by the MCP server.
            tool_description: The tool's description.
            input_schema: JSON Schema for the tool's input.
            call_fn: Async callable: call_fn(name, arguments) -> result string.
        """
        self._server_name = server_name
        self._tool_name = tool_name
        self._description = tool_description
        self._input_schema = input_schema
        self._call_fn = call_fn

    def definition(self) -> ToolDefinition:
        """Convert MCP tool schema to SaltAgent ToolDefinition."""
        params: list[ToolParam] = []
        properties = self._input_schema.get("properties", {})
        required = set(self._input_schema.get("required", []))

        for prop_name, prop_schema in properties.items():
            params.append(ToolParam(
                name=prop_name,
                type=prop_schema.get("type", "string"),
                description=prop_schema.get("description", ""),
                required=prop_name in required,
                enum=prop_schema.get("enum"),
                items=prop_schema.get("items"),
            ))

        # Prefix tool name with server name to avoid collisions with built-in tools
        # e.g., "mcp__puppeteer__navigate" or "mcp__postgres__query"
        full_name = f"mcp__{self._server_name}__{self._tool_name}"

        return ToolDefinition(
            name=full_name,
            description=f"[{self._server_name}] {self._description}",
            params=params,
        )

    def execute(self, **kwargs: Any) -> str:
        """Execute the MCP tool, bridging sync to async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an async context (e.g., agent.run()).
            # Use a thread to run asyncio.run() without blocking the event loop.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self._call_fn(self._tool_name, kwargs))
                return future.result(timeout=120)
        else:
            # No running loop — use asyncio.run directly.
            return asyncio.run(self._call_fn(self._tool_name, kwargs))
