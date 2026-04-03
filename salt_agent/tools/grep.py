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
            description=(
                "Search file contents for a regex pattern. Uses ripgrep if available, "
                "falls back to grep. Returns file paths by default; use output_mode='content' "
                "to see matching lines with context."
            ),
            params=[
                ToolParam("pattern", "string", "Regex pattern to search for."),
                ToolParam("path", "string", "File or directory to search in.", required=False),
                ToolParam("glob", "string", "Glob pattern to filter files (e.g. '*.py').", required=False),
                ToolParam("case_insensitive", "boolean", "Case insensitive search.", required=False),
                ToolParam(
                    "output_mode", "string",
                    "Output mode: 'files_with_matches' (file paths, default), 'content' (matching lines), 'count' (match counts).",
                    required=False,
                    enum=["files_with_matches", "content", "count"],
                    default="files_with_matches",
                ),
                ToolParam("context", "integer", "Number of context lines around matches (requires output_mode='content').", required=False),
                ToolParam("-A", "integer", "Lines to show after each match.", required=False),
                ToolParam("-B", "integer", "Lines to show before each match.", required=False),
                ToolParam("-C", "integer", "Alias for context.", required=False),
                ToolParam("head_limit", "integer", "Max results to return (default 250).", required=False, default=250),
                ToolParam("offset", "integer", "Skip first N results (default 0).", required=False, default=0),
                ToolParam("multiline", "boolean", "Enable multiline matching (pattern can span lines).", required=False),
                ToolParam("type", "string", "Filter by file type (e.g. 'py', 'js', 'ts', 'rust').", required=False),
                ToolParam("-n", "boolean", "Show line numbers (default true for content mode).", required=False),
                ToolParam("-i", "boolean", "Case insensitive search (alias for case_insensitive).", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        pattern: str = kwargs["pattern"]
        raw_path: str = kwargs.get("path") or self.working_directory
        search_path = raw_path if Path(raw_path).is_absolute() else str(Path(self.working_directory) / raw_path)
        file_glob: str | None = kwargs.get("glob")
        case_insensitive: bool = kwargs.get("case_insensitive", False) or kwargs.get("-i", False)
        output_mode: str = kwargs.get("output_mode", "files_with_matches")
        context: int | None = kwargs.get("context") or kwargs.get("-C")
        after: int | None = kwargs.get("-A")
        before: int | None = kwargs.get("-B")
        head_limit: int = kwargs.get("head_limit", 250) or 250
        offset: int = kwargs.get("offset", 0) or 0
        multiline: bool = kwargs.get("multiline", False)
        file_type: str | None = kwargs.get("type")
        line_numbers: bool = kwargs.get("-n", True if output_mode == "content" else False)

        # Try ripgrep first, fall back to grep
        for cmd_name in ("rg", "grep"):
            try:
                cmd = [cmd_name]

                if cmd_name == "rg":
                    # Output mode
                    if output_mode == "files_with_matches":
                        cmd.append("-l")
                    elif output_mode == "count":
                        cmd.append("-c")
                    else:
                        # content mode
                        cmd.append("--no-heading")

                    # Context lines
                    if context is not None:
                        cmd.extend(["-C", str(context)])
                    if after is not None:
                        cmd.extend(["-A", str(after)])
                    if before is not None:
                        cmd.extend(["-B", str(before)])

                    # Case insensitive
                    if case_insensitive:
                        cmd.append("-i")

                    # Multiline
                    if multiline:
                        cmd.extend(["-U", "--multiline-dotall"])

                    # File type
                    if file_type:
                        cmd.extend(["--type", file_type])

                    # Line numbers
                    if line_numbers and output_mode == "content":
                        cmd.append("-n")

                    # File glob
                    if file_glob:
                        cmd.extend(["--glob", file_glob])

                else:
                    # Fallback: plain grep (limited feature set)
                    if case_insensitive:
                        cmd.append("-i")
                    if output_mode == "files_with_matches":
                        cmd.append("-rl")
                    elif output_mode == "count":
                        cmd.extend(["-rc"])
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

                # Apply offset and head_limit
                lines = output.splitlines()
                if offset > 0:
                    lines = lines[offset:]
                if head_limit and len(lines) > head_limit:
                    truncated_count = len(lines) - head_limit
                    lines = lines[:head_limit]
                    output = "\n".join(lines) + f"\n... and {truncated_count} more results"
                else:
                    output = "\n".join(lines)

                return output

            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                return "Error: Search timed out"
            except Exception as e:
                return f"Error: {e}"

        return "Error: Neither rg nor grep found on this system"
