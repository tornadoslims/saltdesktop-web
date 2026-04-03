"""Tests for session persistence."""

import json
import tempfile
from pathlib import Path

import pytest

from salt_agent.persistence import SessionPersistence


class TestSessionPersistence:
    def test_save_and_load_checkpoint(self, tmp_path):
        """Save a checkpoint, load it back."""
        sp = SessionPersistence(session_id="test-1", sessions_dir=str(tmp_path))
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        sp.save_checkpoint(messages, system="You are helpful.")

        loaded = sp.load_last_checkpoint()
        assert loaded is not None
        assert loaded["type"] == "checkpoint"
        assert loaded["messages"] == messages
        assert loaded["system"] == "You are helpful."
        assert "timestamp" in loaded

    def test_multiple_checkpoints_returns_last(self, tmp_path):
        """Multiple checkpoints -- load_last returns the most recent."""
        sp = SessionPersistence(session_id="test-2", sessions_dir=str(tmp_path))

        sp.save_checkpoint([{"role": "user", "content": "first"}], system="sys1")
        sp.save_checkpoint([{"role": "user", "content": "second"}], system="sys2")
        sp.save_checkpoint([{"role": "user", "content": "third"}], system="sys3")

        loaded = sp.load_last_checkpoint()
        assert loaded is not None
        assert loaded["messages"] == [{"role": "user", "content": "third"}]
        assert loaded["system"] == "sys3"

    def test_save_event(self, tmp_path):
        """Save an event and verify it's in the file."""
        sp = SessionPersistence(session_id="test-3", sessions_dir=str(tmp_path))
        sp.save_event("tool_use", {"tool": "bash", "command": "ls"})

        events = sp.load_all_events()
        assert len(events) == 1
        assert events[0]["type"] == "tool_use"
        assert events[0]["data"]["tool"] == "bash"
        assert "timestamp" in events[0]

    def test_list_sessions(self, tmp_path):
        """List sessions returns all session files."""
        # Create two sessions
        sp1 = SessionPersistence(session_id="session-a", sessions_dir=str(tmp_path))
        sp1.save_checkpoint([{"role": "user", "content": "a"}])

        sp2 = SessionPersistence(session_id="session-b", sessions_dir=str(tmp_path))
        sp2.save_checkpoint([{"role": "user", "content": "b"}])

        sessions = sp1.list_sessions()
        assert len(sessions) == 2
        session_ids = {s["session_id"] for s in sessions}
        assert "session-a" in session_ids
        assert "session-b" in session_ids
        # Each session has a path, size, and modified time
        for s in sessions:
            assert "path" in s
            assert s["size"] > 0
            assert "modified" in s

    def test_load_last_checkpoint_no_file(self, tmp_path):
        """No session file returns None."""
        sp = SessionPersistence(session_id="nonexistent", sessions_dir=str(tmp_path))
        assert sp.load_last_checkpoint() is None

    def test_auto_generated_session_id(self, tmp_path):
        """Session ID is auto-generated if not provided."""
        sp = SessionPersistence(sessions_dir=str(tmp_path))
        assert sp.session_id  # not empty
        assert len(sp.session_id) == 36  # UUID format

    def test_checkpoint_with_metadata(self, tmp_path):
        """Metadata is preserved in checkpoints."""
        sp = SessionPersistence(session_id="test-meta", sessions_dir=str(tmp_path))
        sp.save_checkpoint(
            [{"role": "user", "content": "hi"}],
            metadata={"model": "claude-3", "turn": 5},
        )
        loaded = sp.load_last_checkpoint()
        assert loaded["metadata"]["model"] == "claude-3"
        assert loaded["metadata"]["turn"] == 5

    def test_mixed_checkpoints_and_events(self, tmp_path):
        """Events don't interfere with checkpoint loading."""
        sp = SessionPersistence(session_id="test-mixed", sessions_dir=str(tmp_path))
        sp.save_checkpoint([{"role": "user", "content": "q1"}])
        sp.save_event("tool_use", {"tool": "read"})
        sp.save_event("tool_use", {"tool": "write"})
        sp.save_checkpoint([{"role": "user", "content": "q2"}])
        sp.save_event("completion", {"text": "done"})

        loaded = sp.load_last_checkpoint()
        assert loaded["messages"] == [{"role": "user", "content": "q2"}]

        all_events = sp.load_all_events()
        assert len(all_events) == 5

    def test_resume_hydrates_messages(self, tmp_path):
        """SessionPersistence can hydrate messages for resume."""
        sp = SessionPersistence(session_id="resume-test", sessions_dir=str(tmp_path))
        messages = [
            {"role": "user", "content": "Build a web app"},
            {"role": "assistant", "content": "I'll start by..."},
            {"role": "user", "content": [{"type": "tool_result", "content": "OK"}]},
        ]
        sp.save_checkpoint(messages, system="You are a coding assistant.")

        # Simulate resume
        loaded = sp.load_last_checkpoint()
        assert len(loaded["messages"]) == 3
        assert loaded["messages"][0]["content"] == "Build a web app"
        assert loaded["system"] == "You are a coding assistant."
