"""Tests for ContextManager — token estimation, truncation, pressure management."""

import json

import pytest

from salt_agent.context import ContextManager


class TestContextManagerTokenEstimation:
    def test_estimate_tokens_known_string(self):
        cm = ContextManager()
        # "hello world" = 11 chars, ~11//4 = 2 tokens
        assert cm.estimate_tokens("hello world") == 11 // 4

    def test_estimate_tokens_empty_string(self):
        cm = ContextManager()
        assert cm.estimate_tokens("") == 0

    def test_estimate_tokens_long_string(self):
        cm = ContextManager()
        text = "a" * 4000
        assert cm.estimate_tokens(text) == 1000

    def test_estimate_messages_tokens(self):
        cm = ContextManager()
        messages = [
            {"role": "user", "content": "x" * 100},
            {"role": "assistant", "content": "y" * 200},
        ]
        tokens = cm.estimate_messages_tokens(messages)
        # Should be > 0 and based on JSON serialization size
        assert tokens > 0


class TestContextManagerTruncation:
    def test_short_result_not_truncated(self):
        cm = ContextManager(max_tool_result_chars=100)
        result = cm.truncate_tool_result("short text")
        assert result == "short text"

    def test_exact_limit_not_truncated(self):
        cm = ContextManager(max_tool_result_chars=10)
        result = cm.truncate_tool_result("1234567890")
        assert result == "1234567890"

    def test_long_result_truncated(self):
        cm = ContextManager(max_tool_result_chars=100)
        long_text = "A" * 500
        result = cm.truncate_tool_result(long_text)
        assert "truncated" in result
        assert len(result) < 500
        # Should keep beginning and end
        assert result.startswith("A")
        assert result.endswith("A")

    def test_truncation_preserves_beginning_and_end(self):
        cm = ContextManager(max_tool_result_chars=100)
        text = "BEGIN" + "x" * 500 + "END"
        result = cm.truncate_tool_result(text)
        assert "BEGIN" in result
        assert "END" in result
        assert "truncated" in result

    def test_truncation_shows_char_count(self):
        cm = ContextManager(max_tool_result_chars=100)
        text = "x" * 600
        result = cm.truncate_tool_result(text)
        assert "500" in result  # 600 - 100 = 500 truncated chars


class TestContextManagerPressure:
    def test_under_limit_no_change(self):
        cm = ContextManager(context_window=200_000)
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        result = cm.manage_pressure(msgs)
        assert result == msgs

    def test_over_limit_messages_unchanged(self):
        """manage_pressure no longer does destructive inline truncation.

        It returns messages unchanged; compaction handles reduction properly.
        """
        cm = ContextManager(context_window=100)  # Very small window
        msgs = [{"role": "user", "content": "original prompt"}]
        for i in range(20):
            msgs.append({"role": "assistant", "content": f"response {i} " * 50})
            msgs.append({"role": "user", "content": f"query {i} " * 50})
        result = cm.manage_pressure(msgs)
        # Messages are returned unchanged -- compaction handles reduction
        assert result == msgs

    def test_pressure_preserves_all_messages(self):
        """manage_pressure returns messages unchanged (delegates to compaction)."""
        cm = ContextManager(context_window=100)
        msgs = [{"role": "user", "content": "FIRST_MESSAGE"}]
        for i in range(20):
            msgs.append({"role": "assistant", "content": f"resp {i} " * 50})
            msgs.append({"role": "user", "content": f"q {i} " * 50})
        result = cm.manage_pressure(msgs)
        assert result[0]["content"] == "FIRST_MESSAGE"
        assert result == msgs

    def test_short_history_unchanged(self):
        """Short messages are returned unchanged."""
        cm = ContextManager(context_window=10)  # Tiny
        msgs = [
            {"role": "user", "content": "x" * 100},
            {"role": "assistant", "content": "y" * 100},
        ]
        result = cm.manage_pressure(msgs)
        assert result == msgs


class TestContextManagerSystemPrompt:
    def test_set_and_get_system_prompt(self):
        cm = ContextManager()
        cm.set_system("You are a helpful agent.")
        assert cm.system_prompt == "You are a helpful agent."

    def test_default_system_prompt_empty(self):
        cm = ContextManager()
        assert cm.system_prompt == ""


class TestContextManagerFileTracking:
    def test_mark_file_read(self):
        cm = ContextManager()
        cm.mark_file_read("/tmp/a.txt")
        assert cm.was_file_read("/tmp/a.txt")
        assert not cm.was_file_read("/tmp/b.txt")

    def test_mark_file_written(self):
        cm = ContextManager()
        cm.mark_file_written("/tmp/out.txt")
        assert "/tmp/out.txt" in cm._files_written

    def test_multiple_files(self):
        cm = ContextManager()
        for i in range(5):
            cm.mark_file_read(f"/tmp/file{i}.txt")
        assert len(cm._files_read) == 5


class TestContextManagerPressureWithToolResults:
    def test_tool_result_blocks_unchanged(self):
        """manage_pressure no longer truncates messages -- returns unchanged."""
        cm = ContextManager(context_window=100)
        msgs = [{"role": "user", "content": "do stuff"}]
        for i in range(10):
            msgs.append({
                "role": "assistant",
                "content": [
                    {"type": "text", "text": f"using tool {i}"},
                    {"type": "tool_use", "id": f"t{i}", "name": "read", "input": {}},
                ],
            })
            msgs.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": f"t{i}", "content": "x" * 200},
                ],
            })
        result = cm.manage_pressure(msgs)
        # Messages returned unchanged -- compaction system handles reduction
        assert result == msgs
