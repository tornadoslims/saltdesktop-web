"""Bash tool — execute shell commands."""

from __future__ import annotations

import subprocess

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class BashTool(Tool):
    """Execute a shell command and return stdout + stderr."""

    def __init__(self, timeout: int = 30, max_output: int = 30_000, working_directory: str = ".") -> None:
        self.timeout = timeout
        self.max_output = max_output
        self.working_directory = working_directory

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="bash",
            description="Execute a shell command. Returns stdout and stderr.",
            params=[
                ToolParam("command", "string", "The shell command to execute."),
                ToolParam("timeout", "integer", "Timeout in seconds (default 30).", required=False),
                ToolParam("description", "string", "Brief description of what this command does.", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        command: str = kwargs["command"]
        timeout: int = kwargs.get("timeout") or self.timeout

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_directory,
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                if output:
                    output += "\n"
                output += result.stderr

            if not output:
                output = "(no output)"

            # Truncate if too long — keep first and last portions
            if len(output) > self.max_output:
                keep = self.max_output // 2
                output = (
                    output[:keep]
                    + f"\n\n... [truncated {len(output) - self.max_output} chars] ...\n\n"
                    + output[-keep:]
                )

            if result.returncode != 0:
                output = f"Exit code: {result.returncode}\n{output}"

            return output

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Error executing command: {e}"
