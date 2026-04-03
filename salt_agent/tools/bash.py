"""Bash tool — execute shell commands with configurable sandbox."""

from __future__ import annotations

import fnmatch
import os
import subprocess
from dataclasses import dataclass, field

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


@dataclass
class BashSandbox:
    """Configurable bash execution sandbox."""

    timeout: int = 30
    max_output_chars: int = 30_000
    allowed_commands: set[str] | None = None  # None = all allowed
    blocked_commands: set[str] = field(default_factory=lambda: {
        "rm -rf /", "rm -rf ~", "sudo rm", "mkfs", "dd if=/dev",
        ":(){ :|:& };:", "fork", "> /dev/sda",
    })
    blocked_patterns: list[str] = field(default_factory=lambda: [
        "curl * | bash", "wget * | bash", "curl * | sh", "wget * | sh",
    ])
    allow_network: bool = True
    allow_sudo: bool = False
    allow_background: bool = True
    restricted_paths: list[str] = field(default_factory=lambda: [
        "/etc", "/usr", "/System", "/var",
    ])
    env_whitelist: list[str] | None = None  # None = inherit all
    env_blacklist: list[str] = field(default_factory=lambda: [
        "AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    ])

    def validate(self, command: str) -> tuple[bool, str]:
        """Check if command is allowed. Returns (allowed, reason)."""
        # Check blocked commands
        for blocked in self.blocked_commands:
            if blocked in command:
                return False, f"Blocked: contains '{blocked}'"

        # Check blocked patterns
        for pattern in self.blocked_patterns:
            if fnmatch.fnmatch(command, pattern):
                return False, f"Blocked: matches pattern '{pattern}'"

        # Check sudo
        if not self.allow_sudo and command.strip().startswith("sudo"):
            return False, "sudo is not allowed"

        # Check background processes
        if not self.allow_background and command.rstrip().endswith("&"):
            return False, "Background processes are not allowed"

        # Check network commands
        if not self.allow_network:
            network_cmds = ["curl", "wget", "ssh", "scp", "rsync", "nc", "ncat"]
            first_word = command.strip().split()[0] if command.strip() else ""
            if first_word in network_cmds:
                return False, f"Network command '{first_word}' is not allowed"

        # Check restricted paths
        for path in self.restricted_paths:
            # Only block write-like operations to restricted paths
            write_ops = ["rm ", "mv ", "cp ", "> ", ">> ", "chmod ", "chown ", "truncate "]
            for op in write_ops:
                if op in command and path in command:
                    return False, f"Write operation to restricted path '{path}'"

        # Check allowed commands whitelist
        if self.allowed_commands is not None:
            first_word = command.strip().split()[0] if command.strip() else ""
            if first_word not in self.allowed_commands:
                return False, f"Command '{first_word}' not in allowed list"

        return True, ""

    def get_env(self) -> dict:
        """Get environment variables for the sandbox."""
        env = dict(os.environ)
        for key in self.env_blacklist:
            env.pop(key, None)
        if self.env_whitelist is not None:
            env = {k: v for k, v in env.items() if k in self.env_whitelist}
        return env


class BashTool(Tool):
    """Execute a shell command and return stdout + stderr."""

    def __init__(
        self,
        timeout: int = 30,
        max_output: int = 30_000,
        working_directory: str = ".",
        sandbox: BashSandbox | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_output = max_output
        self.working_directory = working_directory
        self.sandbox = sandbox

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

        # Sandbox validation
        if self.sandbox:
            allowed, reason = self.sandbox.validate(command)
            if not allowed:
                return f"Error: {reason}"
            timeout = min(timeout, self.sandbox.timeout)

        env = self.sandbox.get_env() if self.sandbox else None
        max_output = self.sandbox.max_output_chars if self.sandbox else self.max_output

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_directory,
                env=env,
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
            if len(output) > max_output:
                keep = max_output // 2
                output = (
                    output[:keep]
                    + f"\n\n... [truncated {len(output) - max_output} chars] ...\n\n"
                    + output[-keep:]
                )

            if result.returncode != 0:
                output = f"Exit code: {result.returncode}\n{output}"

            return output

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Error executing command: {e}"
