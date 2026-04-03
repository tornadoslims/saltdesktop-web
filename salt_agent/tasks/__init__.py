"""Background task management system.

Tasks are independent agent runs that execute in the background.
The main agent can create, monitor, and collect results from tasks.
"""

from salt_agent.tasks.manager import Task, TaskManager, TaskStatus

__all__ = ["Task", "TaskManager", "TaskStatus"]
