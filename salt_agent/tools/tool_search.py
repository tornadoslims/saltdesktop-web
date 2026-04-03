"""ToolSearch -- deferred tool loading.

Instead of sending all tool schemas to the model, ToolSearch lets the model
discover and load tools on demand. This reduces prompt size when the tool
count grows large.
"""

from __future__ import annotations

from typing import Any

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam, ToolRegistry


class ToolSearchTool(Tool):
    """Search for available tools by keyword.

    Shows tool names and descriptions for registered tools, plus any
    deferred tools that haven't been loaded yet.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        deferred_tools: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """
        Args:
            registry: The main tool registry (tools already loaded).
            deferred_tools: {name: {"description": str, "definition": dict}}
                            Tools not loaded by default. The "definition" is
                            the full tool schema that can be loaded on demand.
        """
        self._registry = registry
        self._deferred: dict[str, dict[str, Any]] = deferred_tools or {}

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="tool_search",
            description=(
                "Search for available tools by keyword. Returns tool names "
                "and descriptions. Use when you need a tool that isn't in "
                "your current set, or to discover what tools are available."
            ),
            params=[
                ToolParam(
                    "query", "string",
                    'Search query -- keyword to match against tool names and descriptions. '
                    'Use "select:Name1,Name2" to fetch specific tools by name.',
                ),
                ToolParam(
                    "max_results", "integer",
                    "Maximum number of results to return (default 5)",
                    required=False,
                    default=5,
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        query_raw: str = kwargs.get("query", "")
        max_results: int = kwargs.get("max_results", 5) or 5

        # Handle "select:Name1,Name2" syntax for fetching specific deferred tools
        if query_raw.startswith("select:"):
            names = [n.strip() for n in query_raw[7:].split(",") if n.strip()]
            return self._fetch_deferred(names)

        query = query_raw.lower()
        results: list[str] = []

        # Search registered (loaded) tools
        for defn in self._registry.list_definitions():
            if defn.name == "tool_search":
                continue  # Don't list ourselves
            score = self._match_score(query, defn.name, defn.description)
            if score > 0:
                results.append(
                    f"[loaded] {defn.name} -- {defn.description[:120]}"
                )

        # Search deferred (not yet loaded) tools
        for name, info in self._deferred.items():
            desc = info.get("description", "")
            score = self._match_score(query, name, desc)
            if score > 0:
                results.append(
                    f"[deferred] {name} -- {desc[:120]}  "
                    f'(use tool_search with query "select:{name}" to load)'
                )

        if not results:
            all_names = sorted(
                list(self._registry.names()) + list(self._deferred.keys())
            )
            return (
                f"No tools matching '{query_raw}'. "
                f"Available tools: {', '.join(all_names)}"
            )

        return "\n".join(results[:max_results])

    def _fetch_deferred(self, names: list[str]) -> str:
        """Fetch full definitions for deferred tools and register them."""
        results: list[str] = []
        for name in names:
            if name in self._deferred:
                info = self._deferred[name]
                results.append(
                    f"Tool '{name}' definition:\n"
                    f"  Description: {info.get('description', 'N/A')}\n"
                    f"  Schema: {info.get('definition', {})}"
                )
            elif self._registry.get(name):
                results.append(f"Tool '{name}' is already loaded.")
            else:
                results.append(f"Tool '{name}' not found.")
        return "\n\n".join(results) if results else "No tools specified."

    @staticmethod
    def _match_score(query: str, name: str, description: str) -> int:
        """Simple keyword matching. Returns positive score on match, 0 otherwise."""
        if not query:
            return 1  # Empty query matches everything
        score = 0
        name_lower = name.lower()
        desc_lower = description.lower()
        for word in query.split():
            if word in name_lower:
                score += 2  # Name matches are more relevant
            elif word in desc_lower:
                score += 1
        return score
