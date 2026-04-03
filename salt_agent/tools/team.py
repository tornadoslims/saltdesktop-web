"""Team tools -- create and disband multi-agent teams.

Teams are groups of background tasks that share a purpose.  TeamCreate
spawns a named team and registers it with the task manager.  TeamDelete
stops all running team members and cleans up.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.tasks.manager import TaskManager


# ---------------------------------------------------------------------------
# Team store (session-scoped)
# ---------------------------------------------------------------------------

@dataclass
class TeamMember:
    task_id: str
    role: str


@dataclass
class Team:
    name: str
    description: str
    created_at: str
    members: list[TeamMember] = field(default_factory=list)


class TeamStore:
    """In-memory team registry (session-scoped)."""

    def __init__(self) -> None:
        self._teams: dict[str, Team] = {}

    def create(self, name: str, description: str = "") -> Team:
        team = Team(
            name=name,
            description=description,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._teams[name] = team
        return team

    def get(self, name: str) -> Team | None:
        return self._teams.get(name)

    def delete(self, name: str) -> Team | None:
        return self._teams.pop(name, None)

    def list_all(self) -> list[Team]:
        return list(self._teams.values())


_store = TeamStore()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class TeamCreateTool(Tool):
    """Create a named team of background agents."""

    def __init__(self, task_manager: TaskManager | None = None) -> None:
        self._tasks = task_manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="team_create",
            description=(
                "Create a new team for coordinating multiple background agents. "
                "Each team member becomes a background task. Teams help organize "
                "parallel workstreams under a shared name."
            ),
            params=[
                ToolParam("team_name", "string", "Name for the new team"),
                ToolParam("description", "string", "Team description/purpose", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        name = kwargs.get("team_name", "").strip()
        description = kwargs.get("description", "")

        if not name:
            return "Error: team_name is required."

        if _store.get(name):
            return f"Error: Team '{name}' already exists. Delete it first or choose a different name."

        team = _store.create(name, description)
        return (
            f"Team '{team.name}' created.\n"
            f"Use task_create to add members, then send_message for coordination.\n"
            f"Use team_delete when done."
        )


class TeamDeleteTool(Tool):
    """Disband a team and clean up its resources."""

    def __init__(self, task_manager: TaskManager | None = None) -> None:
        self._tasks = task_manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="team_delete",
            description=(
                "Disband a team and stop all its running members. "
                "This cleans up all associated background tasks."
            ),
            params=[
                ToolParam("team_name", "string", "Name of the team to delete", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        name = kwargs.get("team_name", "").strip()

        if not name:
            teams = _store.list_all()
            if not teams:
                return "No active teams."
            if len(teams) == 1:
                name = teams[0].name
            else:
                names = ", ".join(t.name for t in teams)
                return f"Error: Multiple teams active ({names}). Specify team_name."

        team = _store.delete(name)
        if not team:
            return f"Error: Team '{name}' not found."

        # Stop any running member tasks
        stopped = 0
        if self._tasks and team.members:
            for member in team.members:
                task = self._tasks.get_task(member.task_id)
                if task and task.status.value == "running":
                    self._tasks.stop_task(member.task_id)
                    stopped += 1

        if stopped:
            return f"Team '{name}' deleted. Stopped {stopped} running member(s)."
        return f"Team '{name}' deleted."
