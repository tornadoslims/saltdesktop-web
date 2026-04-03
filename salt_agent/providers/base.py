"""Abstract provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from salt_agent.events import AgentEvent


class ProviderAdapter(ABC):
    @abstractmethod
    async def stream_response(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> AsyncIterator[AgentEvent]:
        """Stream a response from the LLM, yielding events."""
        ...
