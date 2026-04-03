"""Clipboard tool -- read/write system clipboard."""

from __future__ import annotations

import subprocess

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class ClipboardTool(Tool):
    """Read from or write to the system clipboard."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="clipboard",
            description="Read from or write to the system clipboard.",
            params=[
                ToolParam("action", "string", "read or write", enum=["read", "write"]),
                ToolParam(
                    "content",
                    "string",
                    "Content to write (for write action)",
                    required=False,
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        action = kwargs["action"]
        if action == "write":
            content = kwargs.get("content", "")
            subprocess.run(
                ["pbcopy"],
                input=content.encode(),
                capture_output=True,
                check=False,
            )
            return f"Copied {len(content)} chars to clipboard."
        else:
            proc = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                check=False,
            )
            return proc.stdout or "(clipboard is empty)"
