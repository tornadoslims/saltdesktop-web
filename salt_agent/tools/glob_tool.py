"""Glob tool — file pattern matching."""

from __future__ import annotations

from pathlib import Path

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class GlobTool(Tool):
    """Find files matching a glob pattern."""

    def __init__(self, working_directory: str = ".") -> None:
        self.working_directory = working_directory

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="glob",
            description='Find files matching a glob pattern (e.g. "**/*.py", "src/**/*.ts").',
            params=[
                ToolParam("pattern", "string", "The glob pattern to match files against."),
                ToolParam("path", "string", "Directory to search in. Defaults to working directory.", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        pattern: str = kwargs["pattern"]
        search_path: str = kwargs.get("path") or self.working_directory

        base = Path(search_path)
        if not base.is_absolute():
            base = Path(self.working_directory) / base
        if not base.exists():
            return f"Error: Directory not found: {search_path}"
        if not base.is_dir():
            return f"Error: Not a directory: {search_path}"

        try:
            matches = list(base.glob(pattern))
            # Filter out hidden dirs and common noise
            matches = [m for m in matches if not any(p.startswith(".") for p in m.relative_to(base).parts[:-1])]
            # Sort by modification time (newest first), matching Claude Code behavior
            matches = sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception as e:
            return f"Error: {e}"

        if not matches:
            return f"No files matched pattern '{pattern}' in {search_path}"

        lines = [str(m) for m in matches[:500]]
        result = "\n".join(lines)
        if len(matches) > 500:
            result += f"\n... and {len(matches) - 500} more"
        return result
