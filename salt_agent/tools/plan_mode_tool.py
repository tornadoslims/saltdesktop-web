"""Plan mode tools -- model can enter/exit plan mode via tool calls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from salt_agent.tools.base import Tool, ToolDefinition

if TYPE_CHECKING:
    from salt_agent.config import AgentConfig


class EnterPlanModeTool(Tool):
    """Enter plan mode -- create a plan before executing."""

    def __init__(self, agent_config: AgentConfig) -> None:
        self._config = agent_config

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="enter_plan_mode",
            description="Enter planning mode. You must create a todo_write plan before executing any tools.",
            params=[],
        )

    def execute(self, **kwargs) -> str:
        self._config.plan_mode = True
        return "Plan mode activated. Create your plan with todo_write, then the user will /approve."


class ExitPlanModeTool(Tool):
    """Exit plan mode -- resume normal execution."""

    def __init__(self, agent_config: AgentConfig) -> None:
        self._config = agent_config

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="exit_plan_mode",
            description="Exit planning mode and resume normal execution.",
            params=[],
        )

    def execute(self, **kwargs) -> str:
        self._config.plan_mode = False
        return "Plan mode deactivated. You can now execute tools normally."
