"""Tool ABC and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class ToolParam:
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    enum: list[str] | None = None
    default: Any = None
    items: dict[str, Any] | None = None  # For array types: {"type": "object", "properties": {...}}


@dataclass
class ToolDefinition:
    name: str
    description: str
    params: list[ToolParam]


class Tool(ABC):
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool's schema for the LLM."""
        ...

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the tool and return the result as a string."""
        ...

    def is_async(self) -> bool:
        """Override to True for tools that yield events (like the agent tool).

        Async tools implement async_execute() which yields dicts with
        ``{"type": "event", "event": <AgentEvent>}`` for intermediate events
        and ``{"type": "result", "content": <str>}`` for the final tool result.
        """
        return False

    async def async_execute(self, **kwargs) -> AsyncIterator[dict]:
        """Async execution that can yield events. Override for streaming tools.

        Default implementation wraps the sync execute() call.
        """
        yield {"type": "result", "content": self.execute(**kwargs)}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        defn = tool.definition()
        self._tools[defn.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_definitions(self) -> list[ToolDefinition]:
        return [t.definition() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    # -- Provider format converters --

    @staticmethod
    def _params_to_json_schema(params: list[ToolParam]) -> tuple[dict, list[str]]:
        props: dict[str, dict] = {}
        required: list[str] = []
        for p in params:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.type == "array" and p.items:
                prop["items"] = p.items
            elif p.type == "array" and not p.items:
                # Default items schema for arrays
                prop["items"] = {"type": "string"}
            props[p.name] = prop
            if p.required:
                required.append(p.name)
        return props, required

    def to_anthropic_tools(self) -> list[dict]:
        tools = []
        for defn in self.list_definitions():
            props, required = self._params_to_json_schema(defn.params)
            tools.append({
                "name": defn.name,
                "description": defn.description,
                "input_schema": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            })
        return tools

    def to_openai_tools(self) -> list[dict]:
        tools = []
        for defn in self.list_definitions():
            props, required = self._params_to_json_schema(defn.params)
            tools.append({
                "type": "function",
                "function": {
                    "name": defn.name,
                    "description": defn.description,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    },
                },
            })
        return tools
