"""Tests for architecture improvements: microcompact, emergency truncation,
coordinator mode, concurrent session detection, and file mtime tracking."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Feature 1: Microcompaction
# ---------------------------------------------------------------------------

from salt_agent.compaction import microcompact_tool_results


def _make_tool_result_msg(result_text: str) -> dict:
    """Helper: build a user message containing a tool_result block."""
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "test-id",
                "content": result_text,
            }
        ],
    }


class TestMicrocompact:
    def test_truncates_old_tool_results(self):
        """Old tool results exceeding max_result_chars should be truncated."""
        big_result = "x" * 10_000
        messages = [
            _make_tool_result_msg(big_result),  # old (index 0)
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "next"},
            {"role": "assistant", "content": "ok2"},
            {"role": "user", "content": "next2"},
            {"role": "assistant", "content": "ok3"},
            {"role": "user", "content": "final"},  # recent (index 6)
        ]
        result = microcompact_tool_results(messages, max_result_chars=5000, recent_keep=6)
        # The first message (index 0) is before cutoff (len=7, cutoff=1)
        truncated = result[0]["content"][0]["content"]
        assert len(truncated) < len(big_result)
        assert "[...truncated...]" in truncated

    def test_preserves_recent_results(self):
        """Tool results within the recent window should not be truncated."""
        big_result = "y" * 10_000
        messages = [
            {"role": "user", "content": "start"},
            _make_tool_result_msg(big_result),  # index 1, within last 6
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "next"},
            {"role": "assistant", "content": "ok2"},
            {"role": "user", "content": "final"},
        ]
        result = microcompact_tool_results(messages, max_result_chars=5000, recent_keep=6)
        # All messages are within the recent window (len=6, cutoff=0)
        preserved = result[1]["content"][0]["content"]
        assert preserved == big_result

    def test_preserves_small_old_results(self):
        """Old tool results under the threshold should not be truncated."""
        small_result = "z" * 100
        messages = [
            _make_tool_result_msg(small_result),
        ] + [{"role": "user", "content": f"msg-{i}"} for i in range(10)]
        result = microcompact_tool_results(messages, max_result_chars=5000, recent_keep=6)
        assert result[0]["content"][0]["content"] == small_result

    def test_handles_string_content_messages(self):
        """Messages with plain string content should pass through unmodified."""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = microcompact_tool_results(messages)
        assert result == messages


# ---------------------------------------------------------------------------
# Feature 2: Emergency truncation
# ---------------------------------------------------------------------------

from salt_agent.compaction import emergency_truncate, estimate_messages_tokens


class TestEmergencyTruncate:
    def test_drops_old_messages(self):
        """Should drop oldest non-system messages to get under target."""
        messages = [
            {"role": "user", "content": "a" * 4000},
            {"role": "assistant", "content": "b" * 4000},
            {"role": "user", "content": "c" * 4000},
            {"role": "assistant", "content": "d" * 4000},
        ]
        # Estimate: ~16000 chars / 4 = ~4000 tokens
        target = 2000
        result = emergency_truncate(messages, target)
        assert len(result) < 4
        assert estimate_messages_tokens(result) <= target or len(result) <= 2

    def test_keeps_system_messages(self):
        """System messages should never be dropped."""
        messages = [
            {"role": "system", "content": "I am the system"},
            {"role": "user", "content": "a" * 4000},
            {"role": "assistant", "content": "b" * 4000},
        ]
        target = 500
        result = emergency_truncate(messages, target)
        system_msgs = [m for m in result if m.get("role") == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"] == "I am the system"

    def test_stops_at_minimum_two(self):
        """Should keep at least 2 messages."""
        messages = [
            {"role": "user", "content": "a" * 40000},
            {"role": "assistant", "content": "b" * 40000},
        ]
        result = emergency_truncate(messages, target_tokens=1)
        assert len(result) >= 2


# ---------------------------------------------------------------------------
# Feature 3: Coordinator mode
# ---------------------------------------------------------------------------

from salt_agent.coordinator import COORDINATOR_TOOLS, apply_coordinator_mode
from salt_agent.tools.base import Tool, ToolDefinition, ToolParam, ToolRegistry


class _DummyTool(Tool):
    """Minimal tool for testing."""

    def __init__(self, name: str):
        self._name = name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(name=self._name, description="test", params=[])

    def execute(self, **kwargs) -> str:
        return "ok"


class TestCoordinatorMode:
    def test_strips_write_tools(self):
        """Coordinator mode should remove write, edit, bash, agent tools."""
        registry = ToolRegistry()
        for name in ["read", "write", "edit", "bash", "agent", "glob", "grep",
                      "todo_write", "task_create", "task_list"]:
            registry.register(_DummyTool(name))

        apply_coordinator_mode(registry)

        remaining = set(registry.names())
        assert "write" not in remaining
        assert "edit" not in remaining
        assert "bash" not in remaining
        assert "agent" not in remaining

    def test_keeps_delegation_tools(self):
        """Coordinator mode should keep read, search, and task tools."""
        registry = ToolRegistry()
        for name in ["read", "write", "glob", "grep", "todo_write",
                      "task_create", "task_list", "task_get", "skill"]:
            registry.register(_DummyTool(name))

        apply_coordinator_mode(registry)

        remaining = set(registry.names())
        assert "read" in remaining
        assert "glob" in remaining
        assert "grep" in remaining
        assert "todo_write" in remaining
        assert "task_create" in remaining
        assert "task_list" in remaining
        assert "skill" in remaining

    def test_config_flag(self):
        """AgentConfig should accept coordinator_mode."""
        from salt_agent.config import AgentConfig

        config = AgentConfig(coordinator_mode=True)
        assert config.coordinator_mode is True

        config2 = AgentConfig()
        assert config2.coordinator_mode is False


# ---------------------------------------------------------------------------
# Feature 4: Concurrent session detection
# ---------------------------------------------------------------------------

from salt_agent.persistence import SessionPersistence


class TestConcurrentSession:
    def test_detects_live_session(self):
        """Should detect a concurrent session from a live PID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sp = SessionPersistence(sessions_dir=tmpdir)
            # Write a lock with our own PID (which is alive)
            lock_path = Path(tmpdir) / ".lock"
            lock_path.write_text(json.dumps({
                "pid": os.getpid(),
                "started": "2026-01-01T00:00:00",
                "session_id": "other-session",
            }))

            sp2 = SessionPersistence(sessions_dir=tmpdir)
            conflict = sp2.check_concurrent_session()
            assert conflict is not None
            assert conflict["pid"] == os.getpid()

    def test_ignores_stale_lock(self):
        """Should ignore a lock from a dead PID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".lock"
            # Use a PID that's very unlikely to be alive
            lock_path.write_text(json.dumps({
                "pid": 99999999,
                "started": "2026-01-01T00:00:00",
                "session_id": "dead-session",
            }))

            sp = SessionPersistence(sessions_dir=tmpdir)
            conflict = sp.check_concurrent_session()
            assert conflict is None
            # Our lock should have been written
            lock_data = json.loads(lock_path.read_text())
            assert lock_data["pid"] == os.getpid()

    def test_release_lock(self):
        """Should release our own lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sp = SessionPersistence(sessions_dir=tmpdir)
            sp.check_concurrent_session()  # writes lock
            lock_path = Path(tmpdir) / ".lock"
            assert lock_path.exists()

            sp.release_lock()
            assert not lock_path.exists()

    def test_release_does_not_remove_others_lock(self):
        """Should not remove another process's lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".lock"
            lock_path.write_text(json.dumps({
                "pid": os.getpid() + 99999,
                "started": "2026-01-01T00:00:00",
                "session_id": "other",
            }))

            sp = SessionPersistence(sessions_dir=tmpdir)
            sp.release_lock()
            # Lock should still be there since it's not ours
            assert lock_path.exists()


# ---------------------------------------------------------------------------
# Feature 5: File modification tracking
# ---------------------------------------------------------------------------

from salt_agent.tools.read import ReadTool


class TestFileMtimeTracking:
    def test_tracks_mtime_on_read(self):
        """ReadTool should record the mtime when a file is read."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world\n")
            f.flush()
            path = f.name

        try:
            tool = ReadTool(working_directory="/tmp")
            tool.execute(file_path=path)

            resolved = str(Path(path).resolve())
            assert resolved in tool._read_mtimes
            assert tool._read_mtimes[resolved] == Path(path).stat().st_mtime
        finally:
            os.unlink(path)

    def test_detects_modification(self):
        """Should detect when a file is modified after being read."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("original\n")
            f.flush()
            path = f.name

        try:
            tool = ReadTool(working_directory="/tmp")
            tool.execute(file_path=path)

            resolved = str(Path(path).resolve())
            read_mtime = tool._read_mtimes[resolved]

            # Modify the file
            time.sleep(0.05)  # ensure mtime changes
            Path(path).write_text("modified\n")

            current_mtime = Path(path).stat().st_mtime
            assert current_mtime > read_mtime
        finally:
            os.unlink(path)

    def test_unmodified_file(self):
        """Mtime should match when file is not modified."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("unchanged\n")
            f.flush()
            path = f.name

        try:
            tool = ReadTool(working_directory="/tmp")
            tool.execute(file_path=path)

            resolved = str(Path(path).resolve())
            assert tool._read_mtimes[resolved] == Path(path).stat().st_mtime
        finally:
            os.unlink(path)
