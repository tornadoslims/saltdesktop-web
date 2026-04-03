"""Multi-edit tool -- apply multiple edits to a single file in one call."""

from __future__ import annotations

from pathlib import Path

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class MultiEditTool(Tool):
    """Apply multiple string replacements to a single file in one call."""

    def __init__(self, read_tool=None, working_directory: str = ".") -> None:
        self._read_tool = read_tool
        self.working_directory = working_directory

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="multi_edit",
            description=(
                "Apply multiple string replacements to a single file. "
                "Each edit replaces old_string with new_string. "
                "The file MUST have been read first."
            ),
            params=[
                ToolParam("file_path", "string", "Path to the file"),
                ToolParam(
                    "edits",
                    "array",
                    "List of edits to apply",
                    items={
                        "type": "object",
                        "properties": {
                            "old_string": {
                                "type": "string",
                                "description": "Text to find",
                            },
                            "new_string": {
                                "type": "string",
                                "description": "Text to replace with",
                            },
                        },
                        "required": ["old_string", "new_string"],
                    },
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        file_path: str = kwargs["file_path"]
        edits: list[dict] = kwargs.get("edits", [])

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(self.working_directory) / path

        if not path.exists():
            return f"Error: File not found: {file_path}"

        resolved = str(path.resolve())
        if self._read_tool and resolved not in self._read_tool.files_read:
            return f"Error: File {file_path} has not been read first."

        content = path.read_text(encoding="utf-8")
        applied = 0
        errors: list[str] = []

        for i, edit in enumerate(edits):
            old = edit.get("old_string", "")
            new = edit.get("new_string", "")
            if old not in content:
                errors.append(f"Edit {i + 1}: old_string not found")
                continue
            if content.count(old) > 1:
                errors.append(
                    f"Edit {i + 1}: old_string not unique ({content.count(old)} matches)"
                )
                continue
            content = content.replace(old, new, 1)
            applied += 1

        path.write_text(content, encoding="utf-8")

        msg = f"Applied {applied}/{len(edits)} edits to {file_path}"
        if errors:
            msg += "\n" + "\n".join(errors)
        return msg
