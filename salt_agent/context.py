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
        """Check if context pressure is high and signal that compaction is needed.

        This method no longer does destructive inline message truncation.
        Instead, it simply returns the messages unchanged -- the compaction
        system (compact_context) handles proper LLM-based summarization when
        needs_compaction() returns True.

        Tool result truncation is handled separately by truncate_tool_result()
        at the point of insertion, which is fine (individual results, not whole messages).
        """
        # No destructive inline summarization -- let compaction handle it properly
        return messages
