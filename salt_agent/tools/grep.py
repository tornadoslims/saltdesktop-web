"""Grep tool — content search."""

from __future__ import annotations

import subprocess
from pathlib import Path

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class GrepTool(Tool):
    """Search file contents using regex patterns."""

    def __init__(self, working_directory: str = ".") -> None:
        self.working_directory = working_directory

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="grep",
            description="Search file contents for a regex pattern. Uses ripgrep if available, falls back to grep.",
            params=[
                ToolParam("pattern", "string", "Regex pattern to search for."),
                ToolParam("path", "string", "File or directory to search in.", required=False),
                ToolParam("glob", "string", "Glob pattern to filter files (e.g. '*.py').", required=False),
                ToolParam("case_insensitive", "boolean", "Case insensitive search.", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        pattern: str = kwargs["pattern"]
        raw_path: str = kwargs.get("path") or self.working_directory
        search_path = raw_path if Path(raw_path).is_absolute() else str(Path(self.working_directory) / raw_path)
        file_glob: str | None = kwargs.get("glob")
        case_insensitive: bool = kwargs.get("case_insensitive", False)

        # Try ripgrep first, fall back to grep
        for cmd_name in ("rg", "grep"):
            try:
                cmd = [cmd_name]
                if case_insensitive:
                    cmd.append("-i")
                if cmd_name == "rg":
                    cmd.extend(["-n", "--no-heading"])
                    if file_glob:
                        cmd.extend(["--glob", file_glob])
                else:
                    cmd.extend(["-rn"])
                    if file_glob:
                        cmd.extend(["--include", file_glob])
                cmd.extend([pattern, search_path])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=self.working_directory,
                )
                output = result.stdout
                if not output:
                    return f"No matches found for pattern '{pattern}'"
                # Limit output
                lines = output.splitlines()
                if len(lines) > 200:
                    output = "\n".join(lines[:200]) + f"\n... and {len(lines) - 200} more matches"
                return output

            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                return "Error: Search timed out"
            except Exception as e:
                return f"Error: {e}"

        return "Error: Neither rg nor grep found on this system"
