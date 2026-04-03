"""Send message tool -- inter-task communication."""

from __future__ import annotations

from typing import TYPE_CHECKING

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.tasks.manager import TaskManager


class SendMessageTool(Tool):
    """Send a message to another agent or task."""

    def __init__(self, task_manager: TaskManager | None = None) -> None:
        self._tasks = task_manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="send_message",
            description="Send a message to a running background task.",
            params=[
                ToolParam("task_id", "string", "The task to message"),
                ToolParam("message", "string", "The message to send"),
            ],
        )

    def execute(self, **kwargs) -> str:
        task_id = kwargs["task_id"]
        message = kwargs["message"]
        if self._tasks:
            task = self._tasks.get_task(task_id)
            if task:
                task.events.append({"type": "message", "content": message})
                return f"Message sent to task {task_id}."
            return f"Task {task_id} not found."
        return "No task manager available."
