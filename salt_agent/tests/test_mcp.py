"""Tests for MCP (Model Context Protocol) integration."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from salt_agent.mcp.config import MCPServerConfig, load_mcp_config
from salt_agent.mcp.tool_bridge import MCPToolBridge
from salt_agent.tools.base import ToolRegistry


# ---------------------------------------------------------------------------
# Config parsing tests
# ---------------------------------------------------------------------------


class TestLoadMCPConfig:
    """Tests for load_mcp_config()."""

    def test_load_valid_config(self, tmp_path):
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "test-server": {
                    "command": "node",
                    "args": ["server.js", "--port", "3000"],
                    "env": {"DB_URL": "postgres://localhost/test"},
                },
                "simple-server": {
                    "command": "python",
                    "args": ["-m", "myserver"],
                },
            }
        }))

        configs = load_mcp_config(str(tmp_path))

        assert len(configs) == 2
        names = {c.name for c in configs}
        assert names == {"test-server", "simple-server"}

        test_server = next(c for c in configs if c.name == "test-server")
        assert test_server.command == "node"
        assert test_server.args == ["server.js", "--port", "3000"]
        assert test_server.env == {"DB_URL": "postgres://localhost/test"}

        simple_server = next(c for c in configs if c.name == "simple-server")
        assert simple_server.command == "python"
        assert simple_server.args == ["-m", "myserver"]
        assert simple_server.env is None

    def test_no_config_file(self, tmp_path):
        """Should return empty list when .mcp.json doesn't exist."""
        configs = load_mcp_config(str(tmp_path))
        assert configs == []

    def test_empty_config(self, tmp_path):
        config_file = tmp_path / ".mcp.json"
        config_file.write_text("{}")

        configs = load_mcp_config(str(tmp_path))
        assert configs == []

    def test_empty_servers(self, tmp_path):
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({"mcpServers": {}}))

        configs = load_mcp_config(str(tmp_path))
        assert configs == []

    def test_invalid_json(self, tmp_path):
        config_file = tmp_path / ".mcp.json"
        config_file.write_text("not valid json {{{")

        configs = load_mcp_config(str(tmp_path))
        assert configs == []

    def test_single_server_minimal(self, tmp_path):
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "echo": {
                    "command": "echo",
                    "args": ["hello"],
                }
            }
        }))

        configs = load_mcp_config(str(tmp_path))
        assert len(configs) == 1
        assert configs[0].name == "echo"
        assert configs[0].command == "echo"
        assert configs[0].args == ["hello"]

    def test_server_with_no_args(self, tmp_path):
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "simple": {"command": "mycommand"}
            }
        }))

        configs = load_mcp_config(str(tmp_path))
        assert len(configs) == 1
        assert configs[0].args == []


# ---------------------------------------------------------------------------
# MCPServerConfig dataclass tests
# ---------------------------------------------------------------------------


class TestMCPServerConfig:
    def test_defaults(self):
        cfg = MCPServerConfig(name="test", command="echo")
        assert cfg.args == []
        assert cfg.env is None

    def test_with_all_fields(self):
        cfg = MCPServerConfig(
            name="pg",
            command="npx",
            args=["-y", "@mcp/server-postgres"],
            env={"DATABASE_URL": "postgres://localhost/db"},
        )
        assert cfg.name == "pg"
        assert cfg.command == "npx"
        assert len(cfg.args) == 2
        assert cfg.env["DATABASE_URL"] == "postgres://localhost/db"


# ---------------------------------------------------------------------------
# MCPToolBridge tests
# ---------------------------------------------------------------------------


class TestMCPToolBridge:
    """Tests for the MCP-to-SaltAgent tool bridge."""

    def _make_bridge(self, call_fn=None, **kwargs):
        if call_fn is None:
            async def call_fn(name, arguments):
                return f"Result for {name}: {arguments}"

        defaults = {
            "server_name": "test",
            "tool_name": "query",
            "tool_description": "Run a database query",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query to execute"},
                    "limit": {"type": "integer", "description": "Max rows"},
                },
                "required": ["sql"],
            },
        }
        defaults.update(kwargs)
        return MCPToolBridge(**defaults, call_fn=call_fn)

    def test_definition_name_prefixed(self):
        bridge = self._make_bridge()
        defn = bridge.definition()
        assert defn.name == "mcp__test__query"

    def test_definition_description(self):
        bridge = self._make_bridge()
        defn = bridge.definition()
        assert "[test]" in defn.description
        assert "database query" in defn.description.lower()

    def test_definition_params(self):
        bridge = self._make_bridge()
        defn = bridge.definition()

        assert len(defn.params) == 2
        sql_param = next(p for p in defn.params if p.name == "sql")
        assert sql_param.type == "string"
        assert sql_param.required is True

        limit_param = next(p for p in defn.params if p.name == "limit")
        assert limit_param.type == "integer"
        assert limit_param.required is False

    def test_definition_empty_schema(self):
        bridge = self._make_bridge(input_schema={})
        defn = bridge.definition()
        assert defn.params == []

    def test_definition_with_enum(self):
        bridge = self._make_bridge(input_schema={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Output format",
                    "enum": ["json", "csv", "text"],
                }
            },
        })
        defn = bridge.definition()
        assert len(defn.params) == 1
        assert defn.params[0].enum == ["json", "csv", "text"]

    def test_execute_calls_function(self):
        results = []

        async def mock_call(name, arguments):
            results.append((name, arguments))
            return f"OK: {name}"

        bridge = self._make_bridge(call_fn=mock_call)
        result = bridge.execute(sql="SELECT 1")

        assert result == "OK: query"
        assert len(results) == 1
        assert results[0] == ("query", {"sql": "SELECT 1"})

    def test_different_server_names_avoid_collision(self):
        bridge_a = self._make_bridge(server_name="postgres", tool_name="query")
        bridge_b = self._make_bridge(server_name="mysql", tool_name="query")

        assert bridge_a.definition().name == "mcp__postgres__query"
        assert bridge_b.definition().name == "mcp__mysql__query"
        assert bridge_a.definition().name != bridge_b.definition().name

    def test_execute_handles_exception(self):
        async def failing_call(name, arguments):
            raise RuntimeError("Connection lost")

        bridge = self._make_bridge(call_fn=failing_call)
        with pytest.raises(RuntimeError, match="Connection lost"):
            bridge.execute(sql="SELECT 1")


# ---------------------------------------------------------------------------
# ToolRegistry integration tests
# ---------------------------------------------------------------------------


class TestMCPToolRegistration:
    """Verify MCP tools integrate correctly with the ToolRegistry."""

    def test_register_mcp_tool(self):
        async def mock_call(name, arguments):
            return "ok"

        bridge = MCPToolBridge(
            server_name="pg",
            tool_name="query",
            tool_description="Run SQL",
            input_schema={"type": "object", "properties": {"sql": {"type": "string"}}},
            call_fn=mock_call,
        )

        registry = ToolRegistry()
        registry.register(bridge)

        assert "mcp__pg__query" in registry.names()
        tool = registry.get("mcp__pg__query")
        assert tool is bridge

    def test_mcp_tools_in_anthropic_format(self):
        async def mock_call(name, arguments):
            return "ok"

        bridge = MCPToolBridge(
            server_name="test",
            tool_name="do_thing",
            tool_description="Does a thing",
            input_schema={
                "type": "object",
                "properties": {"input": {"type": "string", "description": "The input"}},
                "required": ["input"],
            },
            call_fn=mock_call,
        )

        registry = ToolRegistry()
        registry.register(bridge)
        anthropic_tools = registry.to_anthropic_tools()

        mcp_tool = next(t for t in anthropic_tools if t["name"] == "mcp__test__do_thing")
        assert mcp_tool["description"] == "[test] Does a thing"
        assert "input" in mcp_tool["input_schema"]["properties"]
        assert "input" in mcp_tool["input_schema"]["required"]

    def test_mcp_tools_in_openai_format(self):
        async def mock_call(name, arguments):
            return "ok"

        bridge = MCPToolBridge(
            server_name="test",
            tool_name="do_thing",
            tool_description="Does a thing",
            input_schema={
                "type": "object",
                "properties": {"input": {"type": "string", "description": "The input"}},
                "required": ["input"],
            },
            call_fn=mock_call,
        )

        registry = ToolRegistry()
        registry.register(bridge)
        openai_tools = registry.to_openai_tools()

        mcp_tool = next(t for t in openai_tools if t["function"]["name"] == "mcp__test__do_thing")
        assert mcp_tool["type"] == "function"
        assert "input" in mcp_tool["function"]["parameters"]["properties"]

    def test_multiple_mcp_tools_coexist(self):
        async def mock_call(name, arguments):
            return "ok"

        registry = ToolRegistry()
        for server, tool in [("pg", "query"), ("pg", "list_tables"), ("redis", "get")]:
            bridge = MCPToolBridge(
                server_name=server,
                tool_name=tool,
                tool_description=f"{server} {tool}",
                input_schema={"type": "object", "properties": {}},
                call_fn=mock_call,
            )
            registry.register(bridge)

        assert len(registry.names()) == 3
        assert "mcp__pg__query" in registry.names()
        assert "mcp__pg__list_tables" in registry.names()
        assert "mcp__redis__get" in registry.names()


# ---------------------------------------------------------------------------
# MCPManager tests (unit-level, no real subprocesses)
# ---------------------------------------------------------------------------


class TestMCPManager:
    """Tests for MCPManager using mocks (no real server processes)."""

    def test_no_config_returns_no_tools(self, tmp_path):
        """Manager with no .mcp.json should return empty tools."""
        from salt_agent.mcp.manager import MCPManager

        manager = MCPManager(working_directory=str(tmp_path))
        tools = asyncio.run(manager.start_servers())
        assert tools == []
        assert manager.server_names == []
        assert manager.is_started is True

    def test_server_names_empty_initially(self, tmp_path):
        from salt_agent.mcp.manager import MCPManager

        manager = MCPManager(working_directory=str(tmp_path))
        assert manager.server_names == []
        assert manager.is_started is False

    def test_get_all_tools_empty(self, tmp_path):
        from salt_agent.mcp.manager import MCPManager

        manager = MCPManager(working_directory=str(tmp_path))
        assert manager.get_all_tools() == []

    def test_shutdown_without_start(self, tmp_path):
        """Shutdown on a clean manager should be safe."""
        from salt_agent.mcp.manager import MCPManager

        manager = MCPManager(working_directory=str(tmp_path))
        asyncio.run(manager.shutdown())
        assert manager.server_names == []

    def test_start_with_failing_server(self, tmp_path):
        """If a server fails to start, manager should log warning and continue."""
        from salt_agent.mcp.manager import MCPManager

        # Create a config that references a non-existent command
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "nonexistent": {
                    "command": "/nonexistent/binary/that/doesnt/exist",
                    "args": [],
                }
            }
        }))

        manager = MCPManager(working_directory=str(tmp_path))
        # Should not raise — just log a warning
        tools = asyncio.run(manager.start_servers())
        assert tools == []
        assert manager.is_started is True

    def test_double_start_returns_cached_tools(self, tmp_path):
        """Starting servers twice should return cached tools."""
        from salt_agent.mcp.manager import MCPManager

        manager = MCPManager(working_directory=str(tmp_path))
        tools1 = asyncio.run(manager.start_servers())
        tools2 = asyncio.run(manager.start_servers())
        assert tools1 == tools2


# ---------------------------------------------------------------------------
# AgentConfig integration tests
# ---------------------------------------------------------------------------


class TestMCPServerResourcesPrompts:
    """Tests for MCPServer resources and prompts fields."""

    def test_server_has_resources_list(self):
        from salt_agent.mcp.manager import MCPServer
        server = MCPServer(MCPServerConfig(name="test", command="echo"))
        assert server.resources == []

    def test_server_has_prompts_list(self):
        from salt_agent.mcp.manager import MCPServer
        server = MCPServer(MCPServerConfig(name="test", command="echo"))
        assert server.prompts == []


class TestMCPManagerResourcesPrompts:
    """Tests for MCPManager get_all_resources and get_all_prompts."""

    def test_get_all_resources_empty(self, tmp_path):
        from salt_agent.mcp.manager import MCPManager
        manager = MCPManager(working_directory=str(tmp_path))
        assert manager.get_all_resources() == []

    def test_get_all_prompts_empty(self, tmp_path):
        from salt_agent.mcp.manager import MCPManager
        manager = MCPManager(working_directory=str(tmp_path))
        assert manager.get_all_prompts() == []

    def test_get_all_resources_includes_server_name(self, tmp_path):
        from salt_agent.mcp.manager import MCPManager, MCPServer
        manager = MCPManager(working_directory=str(tmp_path))
        # Manually add a server with resources
        server = MCPServer(MCPServerConfig(name="test-srv", command="echo"))
        server.resources.append({
            "uri": "file:///tmp/data.json",
            "name": "data",
            "description": "Test data",
            "mime_type": "application/json",
        })
        manager._servers["test-srv"] = server

        resources = manager.get_all_resources()
        assert len(resources) == 1
        assert resources[0]["server"] == "test-srv"
        assert resources[0]["uri"] == "file:///tmp/data.json"
        assert resources[0]["name"] == "data"

    def test_get_all_prompts_includes_server_name(self, tmp_path):
        from salt_agent.mcp.manager import MCPManager, MCPServer
        manager = MCPManager(working_directory=str(tmp_path))
        server = MCPServer(MCPServerConfig(name="prompt-srv", command="echo"))
        server.prompts.append({
            "name": "code-review",
            "description": "Review code",
            "arguments": [{"name": "file", "required": True}],
        })
        manager._servers["prompt-srv"] = server

        prompts = manager.get_all_prompts()
        assert len(prompts) == 1
        assert prompts[0]["server"] == "prompt-srv"
        assert prompts[0]["name"] == "code-review"
        assert prompts[0]["arguments"][0]["name"] == "file"

    def test_resources_from_multiple_servers(self, tmp_path):
        from salt_agent.mcp.manager import MCPManager, MCPServer
        manager = MCPManager(working_directory=str(tmp_path))

        for name in ["srv-a", "srv-b"]:
            server = MCPServer(MCPServerConfig(name=name, command="echo"))
            server.resources.append({
                "uri": f"file:///tmp/{name}.json",
                "name": f"{name}-data",
                "description": "",
                "mime_type": "text/plain",
            })
            manager._servers[name] = server

        resources = manager.get_all_resources()
        assert len(resources) == 2
        servers = {r["server"] for r in resources}
        assert servers == {"srv-a", "srv-b"}

    def test_prompts_from_multiple_servers(self, tmp_path):
        from salt_agent.mcp.manager import MCPManager, MCPServer
        manager = MCPManager(working_directory=str(tmp_path))

        for name in ["srv-x", "srv-y"]:
            server = MCPServer(MCPServerConfig(name=name, command="echo"))
            server.prompts.append({
                "name": f"{name}-prompt",
                "description": "",
                "arguments": [],
            })
            manager._servers[name] = server

        prompts = manager.get_all_prompts()
        assert len(prompts) == 2

    def test_resources_does_not_mutate_server_data(self, tmp_path):
        from salt_agent.mcp.manager import MCPManager, MCPServer
        manager = MCPManager(working_directory=str(tmp_path))
        server = MCPServer(MCPServerConfig(name="srv", command="echo"))
        server.resources.append({
            "uri": "file:///x",
            "name": "x",
            "description": "",
            "mime_type": "text/plain",
        })
        manager._servers["srv"] = server

        resources = manager.get_all_resources()
        # The returned dict has "server" key but original should not
        assert "server" not in server.resources[0]
        assert "server" in resources[0]


class TestConfigIntegration:
    """Verify MCP config fields exist and have correct defaults."""

    def test_enable_mcp_default(self):
        from salt_agent.config import AgentConfig
        config = AgentConfig()
        assert config.enable_mcp is True

    def test_disable_mcp(self):
        from salt_agent.config import AgentConfig
        config = AgentConfig(enable_mcp=False)
        assert config.enable_mcp is False

    def test_mcp_config_path_default(self):
        from salt_agent.config import AgentConfig
        config = AgentConfig()
        assert config.mcp_config_path == ""
