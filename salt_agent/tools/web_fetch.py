"""Web fetch tool -- retrieve content from a URL."""

from __future__ import annotations

import re
import urllib.request

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class WebFetchTool(Tool):
    """Fetch content from a URL and return as readable text."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_fetch",
            description=(
                "Fetch content from a URL. Returns the page content as text "
                "(HTML converted to readable text)."
            ),
            params=[
                ToolParam("url", "string", "The URL to fetch"),
                ToolParam(
                    "max_chars",
                    "integer",
                    "Maximum characters to return (default 10000)",
                    required=False,
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        url: str = kwargs["url"]
        max_chars: int = kwargs.get("max_chars", 10000) or 10000

        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "SaltAgent/0.1"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")

            # Strip scripts, styles, and HTML tags
            content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
            content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL)
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()

            return content[:max_chars]
        except Exception as e:
            return f"Error fetching {url}: {e}"
