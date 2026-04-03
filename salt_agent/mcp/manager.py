"""MCP server lifecycle manager.

Manages the full lifecycle of MCP servers: start, tool discovery, execution,
and shutdown. The key challenge is keeping the stdio_client and ClientSession
context managers alive for the entire agent session, since tools need to be
callable at any time.

We solve this by manually entering the context managers (__aenter__) during
start_servers() and exiting them (__aexit__) during shutdown().
"""

from __future__ import annotations

import logging
from typing import Any

from salt_agent.mcp.config import MCPServerConfig, load_mcp_config
from salt_agent.mcp.tool_bridge import MCPToolBridge
from salt_agent.tools.base import Tool

logger = logging.getLogger(__name__)


class MCPServer:
    """A running MCP server instance with its session and tools."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.session = None  # ClientSession once connected
        self.tools: list[Tool] = []
        self.resources: list[dict] = []
        self.prompts: list[dict] = []
        # Context managers we need to clean up
        self._transport_cm = None  # stdio_client context manager
        self._session_cm = None  # ClientSession context manager


class MCPManager:
    """Manages MCP server lifecycle: start, tool discovery, execution, shutdown.

    Usage:
        manager = MCPManager(working_directory=".")
        tools = await manager.start_servers()  # returns list[Tool]
        # ... tools are now registered in ToolRegistry and callable ...
        await manager.shutdown()
    """

    def __init__(self, working_directory: str = ".") -> None:
        self.working_directory = working_directory
        self._servers: dict[str, MCPServer] = {}
        self._started = False

    async def start_servers(self) -> list[Tool]:
        """Start all configured MCP servers and discover their tools.

        Returns a list of Tool objects ready to be registered in a ToolRegistry.
        Servers that fail to start are logged as warnings and skipped.
        """
        if self._started:
            return self.get_all_tools()

        configs = load_mcp_config(self.working_directory)
        all_tools: list[Tool] = []

        for config in configs:
            try:
                tools = await self._start_server(config)
                all_tools.extend(tools)
                logger.info(
                    "MCP server '%s' started: %d tools",
                    config.name,
                    len(tools),
                )
            except Exception as e:
                logger.warning("Failed to start MCP server '%s': %s", config.name, e)

        self._started = True
        return all_tools

    async def _start_server(self, config: MCPServerConfig) -> list[Tool]:
        """Start a single MCP server and discover its tools."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server = MCPServer(config)

        server_params = StdioServerParameters(
            command=config.command,
            args=config.args or [],
            env=config.env,
        )

        # Manually enter the stdio_client context manager so it stays alive.
        # stdio_client is an @asynccontextmanager that spawns a subprocess
        # and yields (read_stream, write_stream).
        transport_cm = stdio_client(server_params)
        read_stream, write_stream = await transport_cm.__aenter__()
        server._transport_cm = transport_cm

        # Manually enter the ClientSession context manager.
        # ClientSession.__aenter__ starts a task group with a receive loop.
        session = ClientSession(read_stream, write_stream)
        await session.__aenter__()
        server._session_cm = session
        server.session = session

        # Initialize the MCP protocol (capabilities exchange)
        await session.initialize()

        # Discover tools from the server
        tools_response = await session.list_tools()

        for tool_info in tools_response.tools:
            input_schema = {}
            if hasattr(tool_info, "inputSchema"):
                input_schema = tool_info.inputSchema
            elif hasattr(tool_info, "input_schema"):
                input_schema = tool_info.input_schema

            bridge = MCPToolBridge(
                server_name=config.name,
                tool_name=tool_info.name,
                tool_description=tool_info.description or "",
                input_schema=input_schema,
                call_fn=self._make_call_fn(session),
            )
            server.tools.append(bridge)

        # Discover resources (optional MCP capability)
        try:
            resources_response = await session.list_resources()
            for resource in resources_response.resources:
                server.resources.append({
                    "uri": str(resource.uri),
                    "name": resource.name,
                    "description": getattr(resource, "description", "") or "",
                    "mime_type": getattr(resource, "mimeType", "text/plain") or "text/plain",
                })
        except Exception:
            pass  # Resources are optional

        # Discover prompts (optional MCP capability)
        try:
            prompts_response = await session.list_prompts()
            for prompt in prompts_response.prompts:
                server.prompts.append({
                    "name": prompt.name,
                    "description": getattr(prompt, "description", "") or "",
                    "arguments": [
                        {"name": a.name, "required": getattr(a, "required", False)}
                        for a in (getattr(prompt, "arguments", None) or [])
                    ],
                })
        except Exception:
            pass  # Prompts are optional

        self._servers[config.name] = server
        return server.tools

    @staticmethod
    def _make_call_fn(session: Any):
        """Create an async tool-call function bound to a session.

        Returns an async callable: call_fn(tool_name, arguments) -> str
        """

        async def call_tool(name: str, arguments: dict) -> str:
            result = await session.call_tool(name, arguments=arguments)
            # Extract text content from the result
            texts = []
            for content in result.content:
                if hasattr(content, "text"):
                    texts.append(content.text)
            return "\n".join(texts) if texts else str(result)

        return call_tool

    async def shutdown(self) -> None:
        """Shutdown all MCP servers, cleaning up context managers.

        This exits the ClientSession and stdio_client context managers in
        reverse order, which closes the subprocess connections.
        """
        for name in list(self._servers.keys()):
            server = self._servers[name]
            try:
                # Exit ClientSession context manager
                if server._session_cm is not None:
                    try:
                        await server._session_cm.__aexit__(None, None, None)
                    except Exception as e:
                        logger.debug("Error closing session for '%s': %s", name, e)

                # Exit stdio_client context manager (terminates subprocess)
                if server._transport_cm is not None:
                    try:
                        await server._transport_cm.__aexit__(None, None, None)
                    except Exception as e:
                        logger.debug("Error closing transport for '%s': %s", name, e)
            except Exception as e:
                logger.warning("Error shutting down MCP server '%s': %s", name, e)

        self._servers.clear()
        self._started = False

    def get_all_tools(self) -> list[Tool]:
        """Get all tools from all running MCP servers."""
        tools: list[Tool] = []
        for server in self._servers.values():
            tools.extend(server.tools)
        return tools

    def get_all_resources(self) -> list[dict]:
        """Get all resources from all running MCP servers."""
        resources: list[dict] = []
        for server in self._servers.values():
            for r in server.resources:
                r_copy = dict(r)
                r_copy["server"] = server.config.name
                resources.append(r_copy)
        return resources

    def get_all_prompts(self) -> list[dict]:
        """Get all prompts from all running MCP servers."""
        prompts: list[dict] = []
        for server in self._servers.values():
            for p in server.prompts:
                p_copy = dict(p)
                p_copy["server"] = server.config.name
                prompts.append(p_copy)
        return prompts

    @property
    def server_names(self) -> list[str]:
        """Names of all running MCP servers."""
        return list(self._servers.keys())

    @property
    def is_started(self) -> bool:
        return self._started
