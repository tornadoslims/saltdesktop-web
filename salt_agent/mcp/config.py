"""Parse MCP server configuration from .mcp.json files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None


def load_mcp_config(working_directory: str = ".") -> list[MCPServerConfig]:
    """Load MCP server configs from .mcp.json in the working directory.

    The config format matches Claude Code's .mcp.json:
    {
        "mcpServers": {
            "server-name": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-postgres"],
                "env": {"DATABASE_URL": "postgres://..."}
            }
        }
    }

    Returns an empty list if the file doesn't exist or is invalid.
    """
    config_path = Path(working_directory) / ".mcp.json"
    if not config_path.exists():
        return []

    try:
        with open(config_path) as f:
            data = json.load(f)

        servers = []
        for name, cfg in data.get("mcpServers", {}).items():
            servers.append(MCPServerConfig(
                name=name,
                command=cfg.get("command", ""),
                args=cfg.get("args", []),
                env=cfg.get("env"),
            ))
        return servers
    except Exception:
        return []
