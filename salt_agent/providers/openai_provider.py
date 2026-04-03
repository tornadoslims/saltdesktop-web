"""OpenAI provider adapter."""

from __future__ import annotations

import json
import os
from typing import AsyncIterator

from salt_agent.events import AgentEvent, TextChunk, ToolUse, AgentError
from salt_agent.providers.base import ProviderAdapter


class OpenAIAdapter(ProviderAdapter):
    """Adapter for the OpenAI Chat Completions API."""

    DEFAULT_MODEL = "gpt-4o"

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or self.DEFAULT_MODEL

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

        client = openai.OpenAI(api_key=self.api_key)

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

        try:
            stream = client.chat.completions.create(**kwargs)
            tool_calls: dict[int, dict] = {}  # index -> {id, name, arguments}

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
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

        except Exception as e:
            yield AgentError(error=f"OpenAI API error: {e}", recoverable=True)

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
