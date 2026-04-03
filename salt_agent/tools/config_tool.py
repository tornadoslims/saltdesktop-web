"""Config tool -- view or change agent configuration at runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.config import AgentConfig


ALLOWED_KEYS = {"auto_mode", "plan_mode", "max_turns", "temperature", "max_tokens"}


class ConfigTool(Tool):
    """View or change agent configuration at runtime."""

    def __init__(self, agent_config: AgentConfig) -> None:
        self._config = agent_config

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="config",
            description="View or change agent settings. Get: returns current value. Set: changes the value.",
            params=[
                ToolParam("action", "string", "get or set", enum=["get", "set"]),
                ToolParam(
                    "key",
                    "string",
                    "Config key (e.g., auto_mode, plan_mode, max_turns, temperature)",
                ),
                ToolParam("value", "string", "New value (for set action)", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        action = kwargs["action"]
        key = kwargs["key"]

        if key not in ALLOWED_KEYS:
            return f"Cannot access '{key}'. Allowed: {', '.join(sorted(ALLOWED_KEYS))}"

        if action == "get":
            return f"{key} = {getattr(self._config, key, 'unknown')}"
        elif action == "set":
            value = kwargs.get("value", "")
            if key in ("auto_mode", "plan_mode"):
                setattr(self._config, key, value.lower() in ("true", "1", "yes"))
            elif key in ("max_turns", "max_tokens"):
                setattr(self._config, key, int(value))
            elif key == "temperature":
                setattr(self._config, key, float(value))
            return f"{key} set to {getattr(self._config, key)}"
        return f"Unknown action: {action}"
