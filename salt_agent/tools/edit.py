"""Edit file tool — string replacement based."""

from __future__ import annotations

from pathlib import Path

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class EditTool(Tool):
    """Find-and-replace string in a file. Requires the file to have been read first."""

    def __init__(self, read_tool=None, working_directory: str = ".") -> None:
        self._read_tool = read_tool
        self.working_directory = working_directory

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="edit",
            description=(
                "Perform exact string replacement in a file. "
                "old_string must be unique in the file (unless replace_all is true). "
                "The file MUST have been read first."
            ),
            params=[
                ToolParam("file_path", "string", "Absolute path to the file to edit."),
                ToolParam("old_string", "string", "The exact text to find and replace."),
                ToolParam("new_string", "string", "The replacement text."),
                ToolParam("replace_all", "boolean", "Replace all occurrences (default false).", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        file_path: str = kwargs["file_path"]
        old_string: str = kwargs["old_string"]
        new_string: str = kwargs["new_string"]
        replace_all: bool = kwargs.get("replace_all", False)

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(self.working_directory) / path
        resolved = str(path.resolve())

        if not path.exists():
            return f"Error: File not found: {file_path}"

        # Enforce read-before-edit
        if self._read_tool is not None:
            if resolved not in self._read_tool.files_read:
                return f"Error: File {file_path} has not been read yet. Read it first before editing."

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {e}"

        if old_string == new_string:
            return "Error: old_string and new_string are identical."

        count = content.count(old_string)
        if count == 0:
            return f"Error: old_string not found in {file_path}"

        if count > 1 and not replace_all:
            return (
                f"Error: old_string appears {count} times in {file_path}. "
                "Provide more context to make it unique, or set replace_all=true."
            )

        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)

        try:
            path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return f"Error writing file: {e}"

        replaced = count if replace_all else 1
        return f"Successfully replaced {replaced} occurrence(s) in {file_path}"
