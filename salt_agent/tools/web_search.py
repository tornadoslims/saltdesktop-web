"""Web search tool -- DuckDuckGo HTML search (no API key needed)."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class WebSearchTool(Tool):
    """Search the web using DuckDuckGo (no API key needed)."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_search",
            description=(
                "Search the web. Returns a list of results with titles, URLs, and snippets."
            ),
            params=[
                ToolParam("query", "string", "The search query"),
                ToolParam(
                    "max_results",
                    "integer",
                    "Maximum results to return (default 5)",
                    required=False,
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        query: str = kwargs["query"]
        max_results: int = kwargs.get("max_results", 5) or 5

        try:
            encoded = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            req = urllib.request.Request(
                url, headers={"User-Agent": "SaltAgent/0.1"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            results: list[str] = []
            links = re.findall(
                r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html
            )
            snippets = re.findall(
                r'class="result__snippet">(.*?)</span>', html, re.DOTALL
            )

            for i, (link_url, title) in enumerate(links[:max_results]):
                title = re.sub(r"<[^>]+>", "", title).strip()
                snippet = (
                    re.sub(r"<[^>]+>", "", snippets[i]).strip()
                    if i < len(snippets)
                    else ""
                )
                # Decode DuckDuckGo redirect URL
                if "uddg=" in link_url:
                    actual_url = urllib.parse.unquote(
                        link_url.split("uddg=")[1].split("&")[0]
                    )
                else:
                    actual_url = link_url
                results.append(
                    f"{i + 1}. {title}\n   {actual_url}\n   {snippet}"
                )

            if not results:
                return f"No results found for: {query}"
            return "\n\n".join(results)
        except Exception as e:
            return f"Search error: {e}"
