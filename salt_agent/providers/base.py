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

    async def quick_query(self, prompt: str, system: str = "", max_tokens: int = 500) -> str:
        """Non-streaming query for side-queries (memory ranking, extraction, titles).

        Override for provider-specific implementation. Default collects stream.
        Returns empty string on failure (must never crash the caller).
        """
        try:
            text = ""
            async for event in self.stream_response(
                system=system or "You are a helpful assistant. Be concise.",
                messages=[{"role": "user", "content": prompt}],
                tools=[],
                max_tokens=max_tokens,
                temperature=0.0,
            ):
                if hasattr(event, "text"):
                    text += event.text
            return text
        except Exception:
            return ""
