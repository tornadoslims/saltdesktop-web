"""Open tool -- open files/URLs in the default application."""

from __future__ import annotations

import subprocess
import sys

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class OpenTool(Tool):
    """Open a file or URL in the default application."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="open",
            description="Open a file or URL in the default application (browser, editor, etc.)",
            params=[
                ToolParam("target", "string", "File path or URL to open"),
            ],
        )

    def execute(self, **kwargs) -> str:
        target = kwargs["target"]
        if sys.platform == "darwin":
            subprocess.Popen(["open", target])  # noqa: S603
        elif sys.platform == "linux":
            subprocess.Popen(["xdg-open", target])  # noqa: S603
        else:
            subprocess.Popen(["start", target], shell=True)  # noqa: S602
        return f"Opened {target}"
