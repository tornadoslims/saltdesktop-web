"""Context assembly and pressure management."""

from __future__ import annotations

import json


class ContextManager:
    """Manages context window pressure for the agent loop."""

    def __init__(self, context_window: int = 200_000, max_tool_result_chars: int = 10_000):
        self.context_window = context_window
        self.max_tool_result_chars = max_tool_result_chars
        self.system_prompt: str = ""
        self._files_read: set[str] = set()
        self._files_written: set[str] = set()

    def set_system(self, prompt: str) -> None:
        self.system_prompt = prompt

    def mark_file_read(self, path: str) -> None:
        self._files_read.add(path)

    def mark_file_written(self, path: str) -> None:
        self._files_written.add(path)

    def was_file_read(self, path: str) -> bool:
        return path in self._files_read

    def estimate_tokens(self, text: str) -> int:
        """Approximate token count: ~4 chars per token."""
        return len(text) // 4

    def estimate_messages_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens in message history."""
        return self.estimate_tokens(json.dumps(messages, default=str))

    def truncate_tool_result(self, result: str) -> str:
        """Truncate a tool result if it exceeds the max size.

        Keeps the first and last portions so the model sees both the
        beginning and end of long outputs.
        """
        if len(result) <= self.max_tool_result_chars:
            return result
        keep = self.max_tool_result_chars // 2
        return (
            result[:keep]
            + f"\n\n... [truncated {len(result) - self.max_tool_result_chars} chars] ...\n\n"
            + result[-keep:]
        )

    def manage_pressure(self, messages: list[dict]) -> list[dict]:
        """Reduce message history if approaching context limit.

        Strategy: if estimated tokens exceed 75% of the window, summarize
        older turns by replacing their content with a placeholder.
        """
        threshold = int(self.context_window * 0.75)
        tokens = self.estimate_messages_tokens(messages)

        if tokens <= threshold:
            return messages

        # Keep the first message (original prompt) and last 6 messages
        if len(messages) <= 8:
            return messages

        keep_start = 1
        keep_end = 6
        middle = messages[keep_start:-keep_end]

        # Summarize middle messages
        summary_parts = []
        for msg in middle:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block["text"][:100])
                        elif block.get("type") == "tool_use":
                            text_parts.append(f"[tool: {block.get('name', '?')}]")
                        elif block.get("type") == "tool_result":
                            text_parts.append("[tool result]")
                content_str = " | ".join(text_parts)
            else:
                content_str = str(content)[:200]
            summary_parts.append(f"{role}: {content_str}")

        summary = "[Earlier conversation summarized]\n" + "\n".join(summary_parts)
        summary_msg = {"role": "user", "content": summary}

        return messages[:keep_start] + [summary_msg] + messages[-keep_end:]
