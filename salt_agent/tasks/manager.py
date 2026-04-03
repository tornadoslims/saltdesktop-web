"""Task manager -- background agent execution in separate threads.

Each task spawns a fresh SaltAgent in a daemon thread with its own
event loop.  The main agent continues while tasks run in parallel.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from salt_agent.agent import SaltAgent


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class Task:
    id: str
    prompt: str
    status: TaskStatus = TaskStatus.PENDING
    output: str = ""
    error: str = ""
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    events: list[dict] = field(default_factory=list)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _cancel: bool = field(default=False, repr=False)


class TaskManager:
    """Manages background tasks (agent runs in separate threads)."""

    def __init__(self, parent_agent: SaltAgent) -> None:
        self.parent = parent_agent
        self._tasks: dict[str, Task] = {}
        self._callbacks: list = []  # completion callbacks

    def on_complete(self, callback) -> None:
        """Register a callback that fires when any task completes.

        Callback signature: ``callback(task: Task) -> None``
        """
        self._callbacks.append(callback)

    def create_task(self, prompt: str) -> Task:
        """Create and start a background task."""
        task = Task(
            id=str(uuid.uuid4())[:8],
            prompt=prompt,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._tasks[task.id] = task

        # Fire task_created hook
        if hasattr(self.parent, "hooks"):
            self.parent.hooks.fire("task_created", {
                "task_id": task.id,
                "prompt": task.prompt[:200],
            })

        thread = threading.Thread(
            target=self._run_task,
            args=(task,),
            daemon=True,
            name=f"salt-task-{task.id}",
        )
        task._thread = thread
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc).isoformat()
        thread.start()

        return task

    def _run_task(self, task: Task) -> None:
        """Run a task in a background thread with its own event loop."""
        try:
            from salt_agent.subagent import _get_create_agent

            factory = _get_create_agent()

            # Create a fresh agent for this task
            child = factory(
                provider=self.parent.config.provider,
                model=self.parent.config.model,
                api_key=self.parent.config.api_key,
                working_directory=self.parent.config.working_directory,
                max_turns=15,
                persist=False,
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                async def _execute():
                    from salt_agent.events import AgentComplete, TextChunk

                    result_text = ""
                    async for event in child.run(task.prompt):
                        if task._cancel:
                            break
                        task.events.append({
                            "type": event.type,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        if isinstance(event, AgentComplete) and event.final_text:
                            result_text = event.final_text
                        elif isinstance(event, TextChunk):
                            result_text += event.text
                    return result_text

                result = loop.run_until_complete(_execute())

                if task._cancel:
                    task.status = TaskStatus.STOPPED
                    task.output = result or "Task was stopped"
                else:
                    task.status = TaskStatus.COMPLETED
                    task.output = result
            finally:
                loop.close()

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)

        task.completed_at = datetime.now(timezone.utc).isoformat()

        # Fire task hooks
        if hasattr(self.parent, "hooks"):
            if task.status == TaskStatus.COMPLETED:
                self.parent.hooks.fire("task_completed", {
                    "task_id": task.id,
                    "output_length": len(task.output),
                })
            elif task.status == TaskStatus.FAILED:
                self.parent.hooks.fire("task_failed", {
                    "task_id": task.id,
                    "error": task.error,
                })

        # Fire completion callbacks
        for cb in self._callbacks:
            try:
                cb(task)
            except Exception:
                pass

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def get_output(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"
        if task.status == TaskStatus.RUNNING:
            return f"Task {task_id} is still running ({len(task.events)} events so far)"
        if task.status == TaskStatus.FAILED:
            return f"Task {task_id} failed: {task.error}"
        return task.output or task.error or "No output"

    def stop_task(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"
        if task.status != TaskStatus.RUNNING:
            return f"Task {task_id} is not running (status: {task.status.value})"
        task._cancel = True
        return f"Stopping task {task_id}..."

    def update_task(self, task_id: str, status: str | None = None) -> str:
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"
        if status:
            try:
                task.status = TaskStatus(status)
            except ValueError:
                return f"Invalid status: {status}. Valid: {', '.join(s.value for s in TaskStatus)}"
        return f"Task {task_id} updated (status: {task.status.value})"
