"""Anthropic provider adapter."""

from __future__ import annotations

import json
import os
from typing import AsyncIterator

import anthropic

from salt_agent.events import AgentEvent, TextChunk, ToolUse, AgentError
from salt_agent.providers.base import ProviderAdapter


class AnthropicAdapter(ProviderAdapter):
    """Adapter for the Anthropic Messages API."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or self.DEFAULT_MODEL

    async def stream_response(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> AsyncIterator[AgentEvent]:
        client = anthropic.Anthropic(api_key=self.api_key)

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            with client.messages.stream(**kwargs) as stream:
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

        except Exception as e:
            yield AgentError(error=f"Anthropic API error: {e}", recoverable=True)
