"""Centralized reactive state for the agent.

Tracks all dynamic state in one place. Consumers subscribe to changes.
Inspired by Claude Code's AppStateStore pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable


@dataclass
class AgentState:
    """The complete agent state, observable by the UI/hooks/plugins."""

    # Session
    session_id: str = ""
    session_title: str = ""
    turn_count: int = 0

    # Conversation
    message_count: int = 0
    estimated_tokens: int = 0

    # Agent status
    status: str = "idle"  # idle, thinking, executing_tool, compacting, error
    current_tool: str = ""
    current_tool_input: dict = field(default_factory=dict)

    # Budget
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    budget_remaining: float = 0.0

    # Active subagents/tasks
    active_tasks: list[str] = field(default_factory=list)
    active_subagents: int = 0

    # Mode
    auto_mode: bool = False
    plan_mode: bool = False
    coordinator_mode: bool = False

    # Files
    files_read: list[str] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    files_modified_externally: list[str] = field(default_factory=list)

    # Memory
    memory_files_count: int = 0
    memories_surfaced_this_turn: int = 0

    # MCP
    mcp_servers: list[str] = field(default_factory=list)
    mcp_tools_count: int = 0


class StateStore:
    """Observable state container. Notify subscribers on changes."""

    def __init__(self) -> None:
        self.state = AgentState()
        self._subscribers: list[Callable[[str, Any], None]] = []

    def subscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Subscribe to state changes. Callback receives (field_name, new_value)."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Remove a subscriber."""
        self._subscribers = [cb for cb in self._subscribers if cb != callback]

    def update(self, **kwargs: Any) -> None:
        """Update one or more state fields. Notifies subscribers for changed fields."""
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                old = getattr(self.state, key)
                if old != value:
                    setattr(self.state, key, value)
                    self._notify(key, value)

    def get(self, field_name: str) -> Any:
        """Get a single state field value."""
        return getattr(self.state, field_name, None)

    def _notify(self, field_name: str, value: Any) -> None:
        for cb in self._subscribers:
            try:
                cb(field_name, value)
            except Exception:
                pass  # Subscribers must never crash the agent

    def snapshot(self) -> dict:
        """Return current state as a dict."""
        return asdict(self.state)
