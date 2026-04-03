"""Read file tool."""

from __future__ import annotations

from pathlib import Path

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class ReadTool(Tool):
    """Read a file from the filesystem with optional offset and limit."""

    def __init__(self, working_directory: str = ".") -> None:
        self.working_directory = working_directory
        self.files_read: set[str] = set()

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read",
            description="Read a file from the filesystem. Returns file content with line numbers.",
            params=[
                ToolParam("file_path", "string", "Absolute path to the file to read."),
                ToolParam("offset", "integer", "Line number to start reading from (0-based).", required=False),
                ToolParam("limit", "integer", "Maximum number of lines to read.", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        file_path: str = kwargs["file_path"]
        offset: int = kwargs.get("offset", 0) or 0
        limit: int | None = kwargs.get("limit")

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(self.working_directory) / path
        if not path.exists():
            return f"Error: File not found: {file_path}"
        if not path.is_file():
            return f"Error: Not a file: {file_path}"

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading file: {e}"

        lines = text.splitlines()
        total = len(lines)

        if offset > 0:
            lines = lines[offset:]
        if limit is not None and limit > 0:
            lines = lines[:limit]

        # Track that this file has been read
        resolved = str(path.resolve())
        self.files_read.add(resolved)

        # Format with line numbers (1-based display)
        numbered = []
        for i, line in enumerate(lines, start=offset + 1):
            numbered.append(f"{i}\t{line}")

        result = "\n".join(numbered)
        if not result:
            result = "(empty file)"

        header = f"File: {file_path} ({total} lines total)"
        if offset > 0 or limit is not None:
            shown = len(numbered)
            header += f", showing lines {offset + 1}-{offset + shown}"
        return header + "\n" + result
