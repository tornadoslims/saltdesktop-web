"""Tests for the file history / rewind system."""

import os
import tempfile
from pathlib import Path

import pytest

from salt_agent.file_history import FileHistory


class TestFileHistorySnapshot:
    def test_snapshot_existing_file(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        target = tmp_path / "hello.txt"
        target.write_text("original content")

        history.snapshot(str(target))

        assert len(history.get_history()) == 1
        assert history.get_history()[0]["path"] == str(target.resolve())

    def test_snapshot_nonexistent_file_tracks_as_created(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        fake_path = str(tmp_path / "new_file.txt")

        history.snapshot(fake_path)

        # Should not be in snapshot history (file didn't exist)
        assert len(history.get_history()) == 0
        # Should be tracked as created
        assert str(Path(fake_path).resolve()) in history._created_files

    def test_snapshot_saves_backup(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        target = tmp_path / "hello.txt"
        target.write_text("backup me")

        history.snapshot(str(target))

        # Check that a .bak file exists in the backup dir
        bak_files = list((tmp_path / "backups" / "test-session").glob("*.bak"))
        assert len(bak_files) == 1
        assert bak_files[0].read_text() == "backup me"

    def test_snapshot_deduplicates_same_content(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        target = tmp_path / "hello.txt"
        target.write_text("same content")

        history.snapshot(str(target))
        history.snapshot(str(target))

        bak_files = list((tmp_path / "backups" / "test-session").glob("*.bak"))
        assert len(bak_files) == 1  # only one backup, same hash
        assert len(history.get_history()) == 2  # two snapshot records

    def test_max_snapshots_limit(self, tmp_path):
        history = FileHistory(
            session_id="test-session",
            backup_dir=str(tmp_path / "backups"),
            max_snapshots=3,
        )

        for i in range(5):
            target = tmp_path / f"file{i}.txt"
            target.write_text(f"content {i}")
            history.snapshot(str(target))

        assert len(history.get_history()) == 3

    def test_snapshot_relative_path_ignored(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))

        history.snapshot("relative/path.txt")

        assert len(history.get_history()) == 0
        assert len(history._created_files) == 0


class TestFileHistoryRewind:
    def test_rewind_restores_modified_file(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        target = tmp_path / "hello.txt"
        target.write_text("original")

        history.snapshot(str(target))

        # Simulate modification
        target.write_text("modified")
        assert target.read_text() == "modified"

        restored = history.rewind()
        assert target.read_text() == "original"
        assert len(restored) == 1
        assert "Restored" in restored[0]

    def test_rewind_deletes_created_files(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        new_file = tmp_path / "created.txt"

        history.snapshot(str(new_file))

        # Simulate creation
        new_file.write_text("I was created")

        restored = history.rewind()
        assert not new_file.exists()
        assert any("Deleted" in r for r in restored)

    def test_rewind_uses_first_snapshot_as_original(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        target = tmp_path / "hello.txt"
        target.write_text("v1")

        history.snapshot(str(target))

        target.write_text("v2")
        history.snapshot(str(target))

        target.write_text("v3")
        history.snapshot(str(target))

        target.write_text("v4")

        restored = history.rewind()
        assert target.read_text() == "v1"

    def test_rewind_empty_history(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        restored = history.rewind()
        assert restored == []

    def test_rewind_created_file_not_existing_is_ok(self, tmp_path):
        """If a created file was already deleted, rewind should not crash."""
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        fake = tmp_path / "ghost.txt"
        history.snapshot(str(fake))

        # Don't create the file
        restored = history.rewind()
        # Should not crash, no entry for ghost since it never existed
        assert restored == []


class TestFileHistoryGetHistory:
    def test_returns_copy(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        target = tmp_path / "hello.txt"
        target.write_text("content")
        history.snapshot(str(target))

        h1 = history.get_history()
        h2 = history.get_history()
        assert h1 == h2
        assert h1 is not h2  # different list objects

    def test_history_has_expected_fields(self, tmp_path):
        history = FileHistory(session_id="test-session", backup_dir=str(tmp_path / "backups"))
        target = tmp_path / "hello.txt"
        target.write_text("content")
        history.snapshot(str(target))

        entry = history.get_history()[0]
        assert "path" in entry
        assert "hash" in entry
        assert "timestamp" in entry
