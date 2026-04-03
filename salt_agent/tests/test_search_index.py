"""Tests for the session search index."""

import json
import time
from pathlib import Path

import pytest

from salt_agent.search_index import SearchResult, SessionSearchIndex


def _write_session(sessions_dir: Path, session_id: str, entries: list[dict]) -> Path:
    """Helper: write a JSONL session file."""
    path = sessions_dir / f"{session_id}.jsonl"
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


class TestSessionSearchIndex:
    def test_build_empty_dir(self, tmp_path):
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()
        assert idx._built is True
        assert idx.search("anything") == []

    def test_build_nonexistent_dir(self, tmp_path):
        idx = SessionSearchIndex(str(tmp_path / "nope"))
        idx.build()
        # Should not crash, just no results
        assert idx.search("test") == []

    def test_index_checkpoint_messages(self, tmp_path):
        _write_session(tmp_path, "sess-1", [
            {
                "type": "checkpoint",
                "messages": [
                    {"role": "user", "content": "build a web scraper for python"},
                    {"role": "assistant", "content": "I will create the scraper now"},
                ],
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()

        results = idx.search("scraper")
        assert len(results) >= 1
        assert results[0].session_id == "sess-1"
        assert results[0].line_number == 0

    def test_search_multiple_words_score(self, tmp_path):
        _write_session(tmp_path, "sess-a", [
            {
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "python web scraper"}],
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        _write_session(tmp_path, "sess-b", [
            {
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "python data analysis"}],
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()

        # "python scraper" should rank sess-a higher (2 word matches) vs sess-b (1 match)
        results = idx.search("python scraper")
        assert len(results) >= 2
        assert results[0].session_id == "sess-a"
        assert results[0].score > results[1].score

    def test_search_auto_builds(self, tmp_path):
        """Search triggers build if not yet built."""
        _write_session(tmp_path, "sess-auto", [
            {
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "automatic indexing test"}],
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        assert idx._built is False
        results = idx.search("automatic")
        assert idx._built is True
        assert len(results) >= 1

    def test_max_results(self, tmp_path):
        # Create many sessions
        for i in range(20):
            _write_session(tmp_path, f"sess-{i}", [
                {
                    "type": "checkpoint",
                    "messages": [{"role": "user", "content": f"common keyword entry {i}"}],
                    "timestamp": "2026-03-30T10:00:00Z",
                },
            ])
        idx = SessionSearchIndex(str(tmp_path))
        results = idx.search("common keyword", max_results=5)
        assert len(results) == 5

    def test_incremental_rebuild(self, tmp_path):
        _write_session(tmp_path, "sess-1", [
            {
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "original content"}],
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()
        assert len(idx.search("original")) >= 1
        assert len(idx.search("updated")) == 0

        # Overwrite session with new content
        time.sleep(0.05)  # ensure mtime changes
        _write_session(tmp_path, "sess-1", [
            {
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "updated content"}],
                "timestamp": "2026-03-30T11:00:00Z",
            },
        ])
        idx.build()  # should re-index changed file
        assert len(idx.search("updated")) >= 1

    def test_unchanged_session_skipped(self, tmp_path):
        _write_session(tmp_path, "sess-skip", [
            {
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "stable content"}],
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()
        # Build again without changes -- should skip (no error)
        idx.build()
        assert len(idx.search("stable")) >= 1

    def test_index_event_data(self, tmp_path):
        _write_session(tmp_path, "sess-evt", [
            {
                "type": "tool_use",
                "data": {"tool": "bash", "command": "deploy_service"},
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()
        results = idx.search("deploy_service")
        assert len(results) >= 1
        assert results[0].session_id == "sess-evt"

    def test_short_words_ignored(self, tmp_path):
        """Words shorter than 3 chars are not indexed."""
        _write_session(tmp_path, "sess-short", [
            {
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "an if do so"}],
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()
        # Query with only short words -> no results
        assert idx.search("an if") == []

    def test_invalidate_session(self, tmp_path):
        _write_session(tmp_path, "sess-inv", [
            {
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "invalidation test"}],
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()
        idx.invalidate("sess-inv")
        # Mtime cleared, so next build will re-index
        assert "sess-inv" not in idx._session_mtimes

    def test_invalidate_all(self, tmp_path):
        _write_session(tmp_path, "sess-x", [
            {
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "test"}],
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()
        idx.invalidate()
        assert idx._built is False
        assert len(idx._session_mtimes) == 0

    def test_preview_content(self, tmp_path):
        _write_session(tmp_path, "sess-prev", [
            {
                "type": "tool_use",
                "data": {"tool": "read", "path": "/foo/bar.py"},
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        results = idx.search("read")
        assert len(results) >= 1
        assert results[0].preview  # not empty

    def test_malformed_json_lines_skipped(self, tmp_path):
        """Malformed lines don't break indexing."""
        path = tmp_path / "sess-bad.jsonl"
        with open(path, "w") as f:
            f.write("not valid json\n")
            f.write(json.dumps({
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "good line"}],
                "timestamp": "2026-03-30T10:00:00Z",
            }) + "\n")
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()
        results = idx.search("good")
        assert len(results) >= 1

    def test_force_rebuild(self, tmp_path):
        _write_session(tmp_path, "sess-force", [
            {
                "type": "checkpoint",
                "messages": [{"role": "user", "content": "force rebuild test"}],
                "timestamp": "2026-03-30T10:00:00Z",
            },
        ])
        idx = SessionSearchIndex(str(tmp_path))
        idx.build()
        # Force should re-index even without mtime change
        idx.build(force=True)
        results = idx.search("rebuild")
        assert len(results) >= 1


class TestPersistenceSearchIntegration:
    """Test that persistence.search_sessions uses the index."""

    def test_search_via_persistence(self, tmp_path):
        from salt_agent.persistence import SessionPersistence

        sp = SessionPersistence(session_id="int-test", sessions_dir=str(tmp_path))
        sp.save_checkpoint(
            [{"role": "user", "content": "build a python web scraper"}],
            system="You are helpful.",
        )
        sp.save_event("tool_use", {"tool": "bash", "command": "pip install requests"})

        results = sp.search_sessions("scraper")
        assert len(results) >= 1
        assert results[0]["session_id"] == "int-test"
        assert "score" in results[0]

    def test_search_returns_compatible_dicts(self, tmp_path):
        from salt_agent.persistence import SessionPersistence

        sp = SessionPersistence(session_id="compat-test", sessions_dir=str(tmp_path))
        sp.save_checkpoint(
            [{"role": "user", "content": "hello world program"}],
        )
        results = sp.search_sessions("hello")
        assert len(results) >= 1
        r = results[0]
        # Check backward-compatible keys
        assert "session_id" in r
        assert "line" in r
        assert "type" in r
        assert "preview" in r
        assert "timestamp" in r
