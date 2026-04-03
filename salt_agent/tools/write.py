"""Write file tool."""

from __future__ import annotations

from pathlib import Path

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class WriteTool(Tool):
    """Write content to a file. Creates parent directories automatically."""

    def __init__(self, read_tool=None, working_directory: str = ".") -> None:
        self._read_tool = read_tool
        self.working_directory = working_directory
        self.files_written: set[str] = set()

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write",
            description=(
                "Write content to a file. Creates parent directories if needed. "
                "If the file already exists, it MUST have been read first."
            ),
            params=[
                ToolParam("file_path", "string", "Absolute path to the file to write."),
                ToolParam("content", "string", "The content to write to the file."),
            ],
        )

    def execute(self, **kwargs) -> str:
        file_path: str = kwargs["file_path"]
        content: str = kwargs["content"]

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(self.working_directory) / path
        resolved = str(path.resolve())

        # Enforce read-before-write for existing files
        if path.exists() and self._read_tool is not None:
            if resolved not in self._read_tool.files_read:
                return f"Error: File {file_path} exists but has not been read first. Read it before overwriting."

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except Exception as e:
            return f"Error writing file: {e}"

        self.files_written.add(resolved)
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"Successfully wrote {lines} lines to {file_path}"
