"""List files tool."""

from __future__ import annotations

import os
from pathlib import Path

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class ListFilesTool(Tool):
    """List directory contents with file sizes and types."""

    def __init__(self, working_directory: str = ".") -> None:
        self.working_directory = working_directory

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_files",
            description="List files and directories in a given path with sizes and types.",
            params=[
                ToolParam("path", "string", "Directory to list.", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        target: str = kwargs.get("path") or self.working_directory

        path = Path(target)
        if not path.is_absolute():
            path = Path(self.working_directory) / path
        if not path.exists():
            return f"Error: Path not found: {target}"
        if not path.is_dir():
            return f"Error: Not a directory: {target}"

        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return f"Error: Permission denied: {target}"

        lines = []
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    lines.append(f"  {entry.name}/")
                else:
                    size = entry.stat().st_size
                    lines.append(f"  {entry.name}  ({_human_size(size)})")
            except OSError:
                lines.append(f"  {entry.name}  (error reading)")

        if not lines:
            return f"Directory {target} is empty"

        return f"Contents of {target}:\n" + "\n".join(lines)


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
