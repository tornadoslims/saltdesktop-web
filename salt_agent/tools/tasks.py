"""Task tools -- create and manage background tasks from within the agent loop.

These tools let the model spawn tasks that run independently in background
threads.  Each task gets its own SaltAgent instance and event loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.tasks.manager import TaskManager


class TaskCreateTool(Tool):
    """Create a background task that runs independently."""

    def __init__(self, manager: TaskManager) -> None:
        self._manager = manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="task_create",
            description=(
                "Create a background task that runs independently while you continue working. "
                "Use for: long-running searches, parallel builds, research, or any work that "
                "can proceed without blocking your main conversation. "
                "Returns the task ID for later reference."
            ),
            params=[
                ToolParam("prompt", "string", "What the background task should do"),
            ],
        )

    def execute(self, **kwargs) -> str:
        prompt = kwargs.get("prompt", "")
        if not prompt:
            return "Error: prompt is required"
        task = self._manager.create_task(prompt)
        return f"Task {task.id} created and running in background.\nPrompt: {prompt[:100]}"


class TaskListTool(Tool):
    """List all tasks and their status."""

    def __init__(self, manager: TaskManager) -> None:
        self._manager = manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="task_list",
            description="List all background tasks and their current status.",
            params=[],
        )

    def execute(self, **kwargs) -> str:
        tasks = self._manager.list_tasks()
        if not tasks:
            return "No tasks."
        lines = []
        for t in tasks:
            elapsed = ""
            if t.started_at and not t.completed_at:
                elapsed = " (running)"
            elif t.completed_at:
                elapsed = f" (done)"
            lines.append(f"[{t.id}] {t.status.value}{elapsed} -- {t.prompt[:80]}")
        return "\n".join(lines)


class TaskGetTool(Tool):
    """Get details about a specific task."""

    def __init__(self, manager: TaskManager) -> None:
        self._manager = manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="task_get",
            description="Get detailed information about a specific background task.",
            params=[
                ToolParam("task_id", "string", "The task ID to look up"),
            ],
        )

    def execute(self, **kwargs) -> str:
        task_id = kwargs.get("task_id", "")
        if not task_id:
            return "Error: task_id is required"
        task = self._manager.get_task(task_id)
        if not task:
            return f"Task {task_id} not found"
        lines = [
            f"Task: {task.id}",
            f"Status: {task.status.value}",
            f"Prompt: {task.prompt}",
            f"Created: {task.created_at}",
        ]
        if task.started_at:
            lines.append(f"Started: {task.started_at}")
        if task.completed_at:
            lines.append(f"Completed: {task.completed_at}")
        if task.events:
            lines.append(f"Events: {len(task.events)}")
        if task.error:
            lines.append(f"Error: {task.error}")
        if task.output:
            lines.append(f"Output preview: {task.output[:500]}")
        return "\n".join(lines)


class TaskOutputTool(Tool):
    """Get the output/result of a completed task."""

    def __init__(self, manager: TaskManager) -> None:
        self._manager = manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="task_output",
            description="Get the full output/result of a background task. Best used after the task completes.",
            params=[
                ToolParam("task_id", "string", "The task ID to get output from"),
            ],
        )

    def execute(self, **kwargs) -> str:
        task_id = kwargs.get("task_id", "")
        if not task_id:
            return "Error: task_id is required"
        return self._manager.get_output(task_id)


class TaskStopTool(Tool):
    """Stop a running task."""

    def __init__(self, manager: TaskManager) -> None:
        self._manager = manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="task_stop",
            description="Stop a running background task. The task will finish its current turn then stop.",
            params=[
                ToolParam("task_id", "string", "The task ID to stop"),
            ],
        )

    def execute(self, **kwargs) -> str:
        task_id = kwargs.get("task_id", "")
        if not task_id:
            return "Error: task_id is required"
        return self._manager.stop_task(task_id)


class TaskUpdateTool(Tool):
    """Update a task's status."""

    def __init__(self, manager: TaskManager) -> None:
        self._manager = manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="task_update",
            description="Update a background task's status. Rarely needed -- tasks manage their own lifecycle.",
            params=[
                ToolParam("task_id", "string", "The task ID to update"),
                ToolParam(
                    "status",
                    "string",
                    "New status for the task",
                    required=False,
                    enum=["pending", "running", "completed", "failed", "stopped"],
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        task_id = kwargs.get("task_id", "")
        if not task_id:
            return "Error: task_id is required"
        status = kwargs.get("status")
        return self._manager.update_task(task_id, status=status)
