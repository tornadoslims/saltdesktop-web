"""TodoWrite tool — agent self-tracking task list with replace-all semantics."""

from __future__ import annotations

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class TodoWriteTool(Tool):
    """Agent self-tracking task list. Replace-all semantics -- agent writes the ENTIRE list each time."""

    def __init__(self) -> None:
        self.tasks: list[dict] = []

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="todo_write",
            description=(
                "Write your task plan. Use this to track what you need to do and your progress. "
                "Pass the COMPLETE list of tasks each time (replace-all, not append). "
                "Status: pending, in_progress, completed."
            ),
            params=[
                ToolParam(
                    "tasks",
                    "array",
                    "Complete list of tasks with content and status",
                    required=True,
                    items={
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "Task description"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"], "description": "Task status"},
                        },
                        "required": ["content", "status"],
                    },
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        tasks = kwargs.get("tasks", [])
        self.tasks = []
        for t in tasks:
            self.tasks.append({
                "content": t.get("content", ""),
                "status": t.get("status", "pending"),
            })

        pending = sum(1 for t in self.tasks if t["status"] == "pending")
        in_progress = sum(1 for t in self.tasks if t["status"] == "in_progress")
        completed = sum(1 for t in self.tasks if t["status"] == "completed")
        return f"Task list updated: {completed} done, {in_progress} in progress, {pending} pending"

    def get_context_injection(self) -> str:
        """Return the current task list for injection into context."""
        if not self.tasks:
            return ""
        lines = ["## Current Tasks"]
        for t in self.tasks:
            icon = {"pending": "\u25cb", "in_progress": "\u25d0", "completed": "\u2713"}.get(
                t["status"], "?"
            )
            lines.append(f"  {icon} {t['content']}")
        return "\n".join(lines)
