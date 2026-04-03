# MCP Integration

SaltAgent supports the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) for connecting to external tool servers.

## What is MCP?

MCP is a protocol that lets AI agents connect to external servers that provide tools, resources, and prompts. For example:

- A PostgreSQL MCP server provides `query`, `list_tables`, and `describe_table` tools
- A filesystem MCP server provides file access tools
- A GitHub MCP server provides repository management tools

## Configuration

Create a `.mcp.json` file in your project root (same format as Claude Code):

```json
{
    "mcpServers": {
        "postgres": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"],
            "env": {
                "DATABASE_URL": "postgresql://localhost/mydb"
            }
        },
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"]
        }
    }
}
```

### Config Fields

| Field | Description |
|-------|-------------|
| `command` | Executable to start the server |
| `args` | Command-line arguments |
| `env` | Environment variables for the server process |

## How It Works

1. On first `agent.run()` call, the `MCPManager` reads `.mcp.json`
2. Each server is started as a subprocess via `stdio_client`
3. The manager connects via `ClientSession` and discovers tools
4. MCP tools are wrapped as `MCPToolBridge` objects and registered in the agent's `ToolRegistry`
5. When the LLM calls an MCP tool, the bridge forwards the call to the MCP server session
6. On agent shutdown, all MCP servers are stopped

## MCPToolBridge

Each MCP tool is wrapped in an `MCPToolBridge` that:

- Converts MCP tool definitions to SaltAgent's `ToolDefinition` format
- Routes `execute()` calls to the MCP server's `call_tool()` method
- Handles errors from the MCP server

## Lifecycle Management

The MCP manager handles the full lifecycle:

```python
# Manager keeps context managers alive for the session
manager = MCPManager(working_directory=".")

# Start all servers, discover tools
tools = await manager.start_servers()

# Tools are now callable through the session
# ... agent runs and calls MCP tools ...

# Shutdown all servers
await manager.shutdown()
```

## Listing MCP Resources

The `list_mcp_resources` tool lets the LLM discover what MCP servers are connected and what resources they provide:

```
salt> /mcp
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `enable_mcp` | `True` | Enable MCP server discovery |
| `mcp_config_path` | `""` | Override .mcp.json location (default: working_directory) |

To disable MCP:

```python
agent = create_agent(enable_mcp=False)
```

## State

The agent state tracks MCP information:

```python
state = agent.state.snapshot()
print(state["mcp_servers"])     # ["postgres", "filesystem"]
print(state["mcp_tools_count"]) # 6
```

## Notes

- MCP requires the `mcp` Python package to be installed
- If the package is not installed, MCP is silently disabled
- Servers that fail to start are logged as warnings and skipped
- The lazy startup (first `run()` call) avoids slow agent construction
