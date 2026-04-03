"""Anthropic provider adapter."""

from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncIterator

import anthropic

from salt_agent.events import AgentEvent, TextChunk, ToolUse, AgentError
from salt_agent.providers.base import ProviderAdapter

# Retry-eligible error types
_RETRIABLE_ERRORS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)

MAX_RETRIES = 3


class AnthropicAdapter(ProviderAdapter):
    """Adapter for the Anthropic Messages API."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str = "", model: str = "", fallback_model: str = "") -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or self.DEFAULT_MODEL
        self.fallback_model = fallback_model
        self.client = anthropic.Anthropic(api_key=self.api_key)
        # Last usage info from the API (populated after each successful call)
        self.last_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

    async def stream_response(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> AsyncIterator[AgentEvent]:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            # Add cache_control hint to the system prompt for Anthropic prompt caching
            kwargs["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        if tools:
            kwargs["tools"] = tools

        _all_retries_failed = False
        _last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async for event in self._do_stream(kwargs):
                    yield event
                break  # Success — exit retry loop
            except _RETRIABLE_ERRORS as e:
                _last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt  # 1, 2, 4 seconds
                    yield AgentError(
                        error=f"Rate limited, retrying in {wait}s...",
                        recoverable=True,
                    )
                    await asyncio.sleep(wait)
                else:
                    _all_retries_failed = True
            except Exception as e:
                _last_error = e
                _all_retries_failed = True
                break  # Non-retriable errors don't retry

        # Model fallback: if all retries failed and a fallback is configured
        if _all_retries_failed and self.fallback_model:
            yield AgentError(
                error=f"Primary model failed. Falling back to {self.fallback_model}...",
                recoverable=True,
            )
            fallback_kwargs = dict(kwargs)
            fallback_kwargs["model"] = self.fallback_model
            try:
                async for event in self._do_stream(fallback_kwargs):
                    yield event
            except Exception as e2:
                yield AgentError(
                    error=f"Fallback model also failed: {e2}",
                    recoverable=True,
                )
        elif _all_retries_failed:
            yield AgentError(
                error=f"Anthropic API error after {MAX_RETRIES} retries: {_last_error}",
                recoverable=True,
            )

    async def _do_stream(self, kwargs: dict) -> AsyncIterator[AgentEvent]:
        """Internal streaming implementation (separated for retry logic)."""
        with self.client.messages.stream(**kwargs) as stream:
            current_tool_id = ""
            current_tool_name = ""
            current_tool_input_json = ""
            in_tool_use = False

            for event in stream:
                event_type = event.type

                if event_type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        in_tool_use = True
                        current_tool_id = block.id
                        current_tool_name = block.name
                        current_tool_input_json = ""
                    elif block.type == "text":
                        in_tool_use = False

                elif event_type == "content_block_delta":
                    delta = event.delta
                    if hasattr(delta, "text") and delta.text:
                        yield TextChunk(text=delta.text)
                    elif hasattr(delta, "partial_json") and delta.partial_json:
                        current_tool_input_json += delta.partial_json

                elif event_type == "content_block_stop":
                    if in_tool_use:
                        try:
                            tool_input = json.loads(current_tool_input_json) if current_tool_input_json else {}
                        except json.JSONDecodeError:
                            tool_input = {}
                        yield ToolUse(
                            tool_id=current_tool_id,
                            tool_name=current_tool_name,
                            tool_input=tool_input,
                        )
                        in_tool_use = False

            # Extract token usage from the final message
            final_message = stream.get_final_message()
            if final_message and hasattr(final_message, "usage"):
                self.last_usage = {
                    "input_tokens": final_message.usage.input_tokens,
                    "output_tokens": final_message.usage.output_tokens,
                }

    async def quick_query(self, prompt: str, system: str = "", max_tokens: int = 500) -> str:
        """Non-streaming query using the Anthropic messages API directly (faster)."""
        try:
            resp = self.client.messages.create(
                model=self.model,
                system=system or "You are a helpful assistant. Be concise.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            return resp.content[0].text if resp.content else ""
        except Exception:
            return ""
