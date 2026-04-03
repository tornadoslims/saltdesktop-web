"""Sleep tool -- wait for a duration or until a background task completes."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.tasks.manager import TaskManager


class SleepTool(Tool):
    """Wait for a specified duration or until a background task completes."""

    def __init__(self, task_manager: TaskManager | None = None) -> None:
        self._tasks = task_manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="sleep",
            description="Wait for a duration (seconds) or until a background task completes.",
            params=[
                ToolParam("seconds", "integer", "Seconds to wait (max 30)", required=False),
                ToolParam("task_id", "string", "Wait for this task to complete", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        seconds = min(kwargs.get("seconds", 0) or 0, 30)
        task_id = kwargs.get("task_id")

        if task_id and self._tasks:
            # Wait for task completion (poll every 0.5s, max 30s)
            for _ in range(60):
                task = self._tasks.get_task(task_id)
                if task and task.status.value in ("completed", "failed", "stopped"):
                    return f"Task {task_id} is {task.status.value}."
                time.sleep(0.5)
            return f"Timeout waiting for task {task_id}."
        elif seconds > 0:
            time.sleep(seconds)
            return f"Waited {seconds} seconds."
        return "Nothing to wait for."
