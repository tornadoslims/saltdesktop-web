"""Tests for ToolSearch (deferred tool loading)."""

from __future__ import annotations

import pytest

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam, ToolRegistry
from salt_agent.tools.tool_search import ToolSearchTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DummyTool(Tool):
    def __init__(self, name: str, description: str):
        self._name = name
        self._description = description

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description=self._description,
            params=[],
        )

    def execute(self, **kwargs) -> str:
        return "ok"


def _make_registry(*tools: tuple[str, str]) -> ToolRegistry:
    reg = ToolRegistry()
    for name, desc in tools:
        reg.register(DummyTool(name, desc))
    return reg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToolSearchRegistered:
    def test_search_finds_registered_tools(self):
        reg = _make_registry(
            ("bash", "Execute shell commands"),
            ("read", "Read a file from disk"),
            ("write", "Write a file to disk"),
        )
        ts = ToolSearchTool(reg)
        result = ts.execute(query="file")
        assert "read" in result
        assert "write" in result

    def test_search_by_name(self):
        reg = _make_registry(
            ("bash", "Execute shell commands"),
            ("grep", "Search file contents"),
        )
        ts = ToolSearchTool(reg)
        result = ts.execute(query="bash")
        assert "bash" in result
        assert "grep" not in result

    def test_search_no_results(self):
        reg = _make_registry(
            ("bash", "Execute shell commands"),
        )
        ts = ToolSearchTool(reg)
        result = ts.execute(query="nonexistent_xyz_tool")
        assert "No tools matching" in result

    def test_search_empty_query_matches_all(self):
        reg = _make_registry(
            ("bash", "Execute shell commands"),
            ("read", "Read a file from disk"),
        )
        ts = ToolSearchTool(reg)
        result = ts.execute(query="")
        assert "bash" in result
        assert "read" in result

    def test_max_results_limits_output(self):
        reg = _make_registry(
            ("tool_a", "Alpha tool"),
            ("tool_b", "Beta tool"),
            ("tool_c", "Charlie tool"),
            ("tool_d", "Delta tool"),
        )
        ts = ToolSearchTool(reg)
        result = ts.execute(query="tool", max_results=2)
        lines = [l for l in result.strip().split("\n") if l.strip()]
        assert len(lines) <= 2


class TestToolSearchDeferred:
    def test_search_deferred_tools(self):
        reg = _make_registry(("bash", "Execute shell commands"))
        deferred = {
            "notebook_edit": {
                "description": "Edit Jupyter notebook cells",
                "definition": {"name": "notebook_edit"},
            },
        }
        ts = ToolSearchTool(reg, deferred_tools=deferred)
        result = ts.execute(query="notebook")
        assert "notebook_edit" in result
        assert "deferred" in result.lower()

    def test_select_syntax_fetches_deferred(self):
        reg = _make_registry()
        deferred = {
            "lsp_tool": {
                "description": "Language server diagnostics",
                "definition": {"name": "lsp_tool", "params": []},
            },
        }
        ts = ToolSearchTool(reg, deferred_tools=deferred)
        result = ts.execute(query="select:lsp_tool")
        assert "lsp_tool" in result
        assert "Language server" in result

    def test_select_already_loaded(self):
        reg = _make_registry(("bash", "Execute shell commands"))
        ts = ToolSearchTool(reg)
        result = ts.execute(query="select:bash")
        assert "already loaded" in result

    def test_select_not_found(self):
        reg = _make_registry()
        ts = ToolSearchTool(reg)
        result = ts.execute(query="select:nonexistent")
        assert "not found" in result


class TestToolSearchDefinition:
    def test_definition_schema(self):
        reg = _make_registry()
        ts = ToolSearchTool(reg)
        defn = ts.definition()
        assert defn.name == "tool_search"
        param_names = [p.name for p in defn.params]
        assert "query" in param_names
        assert "max_results" in param_names

    def test_does_not_list_itself_in_results(self):
        reg = _make_registry(
            ("bash", "Execute shell commands"),
            ("grep", "Search file contents with regex"),
        )
        ts = ToolSearchTool(reg)
        reg.register(ts)  # Register tool_search itself
        result = ts.execute(query="search")
        # tool_search should not appear as a search result entry
        # (grep should match "Search" in its description)
        lines = [l for l in result.strip().split("\n") if l.strip()]
        for line in lines:
            # Each result line starts with [loaded] or [deferred]
            if line.startswith("["):
                assert "tool_search" not in line
