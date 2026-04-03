"""Event types for streaming agent output."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    type: str
    data: dict[str, Any] | None = None


@dataclass
class TextChunk(AgentEvent):
    type: str = "text_chunk"
    text: str = ""


@dataclass
class ToolUse(AgentEvent):
    type: str = "tool_use"
    tool_id: str = ""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)


@dataclass
class ToolStart(AgentEvent):
    type: str = "tool_start"
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)


@dataclass
class ToolEnd(AgentEvent):
    type: str = "tool_end"
    tool_name: str = ""
    result: str = ""
    success: bool = True


@dataclass
class AgentComplete(AgentEvent):
    type: str = "complete"
    final_text: str = ""
    turns: int = 0
    tools_used: list[str] = field(default_factory=list)


@dataclass
class AgentError(AgentEvent):
    type: str = "error"
    error: str = ""
    recoverable: bool = True


@dataclass
class ContextCompacted(AgentEvent):
    type: str = "compaction"
    old_tokens: int = 0
    new_tokens: int = 0


@dataclass
class SubagentSpawned(AgentEvent):
    type: str = "subagent_spawned"
    mode: str = ""
    prompt: str = ""


@dataclass
class SubagentComplete(AgentEvent):
    type: str = "subagent_complete"
    mode: str = ""
    result: str = ""


@dataclass
class FileSnapshotted(AgentEvent):
    type: str = "file_snapshotted"
    file_path: str = ""
