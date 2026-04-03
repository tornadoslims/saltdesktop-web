"""OpenAI provider adapter."""

from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncIterator

from salt_agent.events import AgentEvent, TextChunk, ToolUse, AgentError
from salt_agent.providers.base import ProviderAdapter

MAX_RETRIES = 3


class OpenAIAdapter(ProviderAdapter):
    """Adapter for the OpenAI Chat Completions API."""

    DEFAULT_MODEL = "gpt-4o"

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or self.DEFAULT_MODEL
        self._client = None  # Lazy-init (avoids import error if openai not installed)
        # Last usage info from the API (populated after each successful call)
        self.last_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

    def _get_client(self):
        """Create the OpenAI client once and reuse it."""
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=self.api_key)
        return self._client

    async def stream_response(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> AsyncIterator[AgentEvent]:
        try:
            import openai
        except ImportError:
            yield AgentError(error="openai package not installed", recoverable=False)
            return

        client = self._get_client()

        # OpenAI puts system message in messages array
        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})

        # Convert messages from Anthropic format to OpenAI format
        for msg in messages:
            converted = self._convert_message(msg)
            if isinstance(converted, list):
                oai_messages.extend(converted)
            else:
                oai_messages.append(converted)

        kwargs = {
            "model": self.model,
            "messages": oai_messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        for attempt in range(MAX_RETRIES):
            try:
                async for event in self._do_stream(client, kwargs):
                    yield event
                break  # Success
            except openai.RateLimitError as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    yield AgentError(
                        error=f"Rate limited, retrying in {wait}s...",
                        recoverable=True,
                    )
                    await asyncio.sleep(wait)
                else:
                    yield AgentError(
                        error=f"OpenAI API error after {MAX_RETRIES} retries: {e}",
                        recoverable=True,
                    )
            except openai.APIConnectionError as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    yield AgentError(
                        error=f"Connection error, retrying in {wait}s...",
                        recoverable=True,
                    )
                    await asyncio.sleep(wait)
                else:
                    yield AgentError(
                        error=f"OpenAI connection error after {MAX_RETRIES} retries: {e}",
                        recoverable=True,
                    )
            except Exception as e:
                yield AgentError(error=f"OpenAI API error: {e}", recoverable=True)
                break

    async def _do_stream(self, client, kwargs: dict) -> AsyncIterator[AgentEvent]:
        """Internal streaming implementation (separated for retry logic)."""
        stream = client.chat.completions.create(**kwargs)
        tool_calls: dict[int, dict] = {}  # index -> {id, name, arguments}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                # Check for usage info on the final chunk
                if hasattr(chunk, "usage") and chunk.usage:
                    self.last_usage = {
                        "input_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                        "output_tokens": getattr(chunk.usage, "completion_tokens", 0),
                    }
                continue

            if delta.content:
                yield TextChunk(text=delta.content)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tool_calls[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        tool_calls[idx]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_calls[idx]["arguments"] += tc.function.arguments

            # Check for finish
            finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
            if finish_reason == "tool_calls":
                for idx in sorted(tool_calls.keys()):
                    tc_data = tool_calls[idx]
                    try:
                        tool_input = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                    except json.JSONDecodeError:
                        tool_input = {}
                    yield ToolUse(
                        tool_id=tc_data["id"],
                        tool_name=tc_data["name"],
                        tool_input=tool_input,
                    )

    @staticmethod
    def _convert_message(msg: dict) -> dict:
        """Convert an Anthropic-format message to OpenAI format."""
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            return {"role": role, "content": content}

        if isinstance(content, list):
            # Handle tool results (user role with tool_result blocks)
            if role == "user" and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            ):
                oai_messages = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        oai_messages.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block.get("content", ""),
                        })
                # Return list — caller extends rather than appends
                return oai_messages if len(oai_messages) > 1 else oai_messages[0]

            # Handle assistant messages with tool_use blocks
            if role == "assistant":
                text_parts = []
                tool_calls_out = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block["text"])
                        elif block.get("type") == "tool_use":
                            tool_calls_out.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block.get("input", {})),
                                },
                            })
                result = {"role": "assistant"}
                if text_parts:
                    result["content"] = "\n".join(text_parts)
                if tool_calls_out:
                    result["tool_calls"] = tool_calls_out
                return result

            # Generic: extract text
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block["text"])
                elif isinstance(block, str):
                    texts.append(block)
            return {"role": role, "content": "\n".join(texts)}

        return {"role": role, "content": str(content)}
