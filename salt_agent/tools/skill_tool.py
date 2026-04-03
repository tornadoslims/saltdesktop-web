"""Skill invocation tool -- loads skill content into the agent's context."""

from __future__ import annotations

from typing import TYPE_CHECKING

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.skills.manager import SkillManager


class SkillTool(Tool):
    """Invoke a skill by name. Loads the skill's SKILL.md content for the agent to follow."""

    def __init__(self, skill_manager: SkillManager) -> None:
        self._manager = skill_manager

    def definition(self) -> ToolDefinition:
        # Build a description that includes available skill names
        skills = self._manager.list_skills()
        if skills:
            names = ", ".join(sorted(s.name for s in skills))
            extra = f" Available skills: {names}"
        else:
            extra = ""
        return ToolDefinition(
            name="skill",
            description=(
                "Invoke a skill by name. Skills are markdown-based instructions "
                "that teach you how to perform specific tasks. Use this to load "
                "a skill's instructions and then follow them." + extra
            ),
            params=[
                ToolParam("name", "string", "The skill name to invoke"),
            ],
        )

    def execute(self, **kwargs) -> str:
        name = kwargs.get("name", "")
        if not name:
            skills = self._manager.list_skills()
            if skills:
                lines = [f"- {s.name}: {s.description}" for s in skills]
                return "Available skills:\n" + "\n".join(lines)
            return "No skills available."
        return self._manager.invoke(name)
