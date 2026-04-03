"""Brief tool -- send a short status message to the user."""

from __future__ import annotations

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam


class BriefTool(Tool):
    """Send a brief message to the user. Use for quick status updates without a full response."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="brief",
            description="Send a brief status message to the user. Use for quick updates like 'Done' or 'Working on it...'",
            params=[
                ToolParam("message", "string", "The brief message"),
            ],
        )

    def execute(self, **kwargs) -> str:
        return kwargs["message"]
