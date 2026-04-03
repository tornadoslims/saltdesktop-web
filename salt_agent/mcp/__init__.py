"""MCP (Model Context Protocol) integration for SaltAgent."""

from salt_agent.mcp.config import MCPServerConfig, load_mcp_config
from salt_agent.mcp.manager import MCPManager
from salt_agent.mcp.tool_bridge import MCPToolBridge

__all__ = ["MCPManager", "MCPToolBridge", "MCPServerConfig", "load_mcp_config"]
