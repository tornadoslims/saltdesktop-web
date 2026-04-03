"""MCP resource listing tool -- list resources from connected MCP servers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.mcp.manager import MCPManager


class ListMcpResourcesTool(Tool):
    """List resources available from connected MCP servers."""

    def __init__(self, mcp_manager: MCPManager | None = None) -> None:
        self._mcp = mcp_manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="mcp_list_resources",
            description=(
                "List resources available from connected MCP servers. "
                "Resources are data endpoints (files, database entries, etc.) "
                "exposed by MCP servers. Optionally filter by server name."
            ),
            params=[
                ToolParam("server", "string", "Optional server name to filter by", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        if not self._mcp:
            return "No MCP servers configured."

        server_filter = kwargs.get("server")
        resources = self._mcp.get_all_resources()

        if server_filter:
            resources = [r for r in resources if r.get("server") == server_filter]
            if not resources:
                return f"No resources found for server '{server_filter}'."

        if not resources:
            return "No MCP resources available."

        lines = []
        for r in resources:
            name = r.get("name", "unnamed")
            uri = r.get("uri", "")
            server = r.get("server", "unknown")
            desc = r.get("description", "")
            mime = r.get("mimeType", "")
            parts = [f"  {name}"]
            if uri:
                parts.append(f"    URI: {uri}")
            if mime:
                parts.append(f"    Type: {mime}")
            if desc:
                parts.append(f"    {desc}")
            parts.append(f"    Server: {server}")
            lines.append("\n".join(parts))

        return f"{len(resources)} resource(s):\n" + "\n".join(lines)
