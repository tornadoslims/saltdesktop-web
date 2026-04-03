"""Python REPL tool -- execute code in a persistent session."""

from __future__ import annotations

import contextlib
import io

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class ReplTool(Tool):
    """Execute Python code in a persistent REPL session."""

    def __init__(self) -> None:
        self._globals: dict = {}
        self._locals: dict = {}

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="python_repl",
            description=(
                "Execute Python code in a persistent REPL. "
                "Variables persist across calls. Use for quick calculations, "
                "data processing, or testing code snippets."
            ),
            params=[
                ToolParam("code", "string", "Python code to execute"),
            ],
        )

    def execute(self, **kwargs) -> str:
        code = kwargs["code"]
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(code, self._globals, self._locals)  # noqa: S102
            output = stdout.getvalue()
            errors = stderr.getvalue()
            result = output
            if errors:
                result += f"\nStderr: {errors}"
            return result if result.strip() else "OK (no output)"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
