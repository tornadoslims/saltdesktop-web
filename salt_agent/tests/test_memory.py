"""Tests for the memory system."""

import tempfile
from pathlib import Path

import pytest

from salt_agent.memory import MemorySystem


class TestProjectInstructions:
    def test_find_salt_md_in_working_dir(self, tmp_path):
        """Find SALT.md in the working directory."""
        (tmp_path / "SALT.md").write_text("# Salt Instructions\nDo great things.")
        mem = MemorySystem(working_directory=str(tmp_path))
        instructions = mem.load_project_instructions()
        assert "Salt Instructions" in instructions
        assert "Do great things" in instructions

    def test_find_claude_md_in_working_dir(self, tmp_path):
        """Find CLAUDE.md in the working directory."""
        (tmp_path / "CLAUDE.md").write_text("# Claude Instructions\nBe helpful.")
        mem = MemorySystem(working_directory=str(tmp_path))
        instructions = mem.load_project_instructions()
        assert "Claude Instructions" in instructions

    def test_find_both_salt_and_claude_md(self, tmp_path):
        """Both SALT.md and CLAUDE.md are loaded."""
        (tmp_path / "SALT.md").write_text("Salt rules")
        (tmp_path / "CLAUDE.md").write_text("Claude rules")
        mem = MemorySystem(working_directory=str(tmp_path))
        instructions = mem.load_project_instructions()
        assert "Salt rules" in instructions
        assert "Claude rules" in instructions

    def test_find_in_parent_directory(self, tmp_path):
        """Find CLAUDE.md in a parent directory."""
        (tmp_path / "CLAUDE.md").write_text("Parent instructions")
        child = tmp_path / "src" / "app"
        child.mkdir(parents=True)
        mem = MemorySystem(working_directory=str(child))
        instructions = mem.load_project_instructions()
        assert "Parent instructions" in instructions

    def test_no_instructions_file(self, tmp_path):
        """No instructions file returns empty string."""
        mem = MemorySystem(working_directory=str(tmp_path))
        instructions = mem.load_project_instructions()
        assert instructions == ""

    def test_instructions_truncated_at_5000_chars(self, tmp_path):
        """Instructions are truncated at 5000 characters."""
        (tmp_path / "SALT.md").write_text("x" * 10000)
        mem = MemorySystem(working_directory=str(tmp_path))
        instructions = mem.load_project_instructions()
        # The content portion should be at most 5000 chars (plus the header)
        # Just verify it doesn't contain all 10000
        assert len(instructions) < 6000

    def test_dot_claude_instructions_md(self, tmp_path):
        """Find .claude/instructions.md."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "instructions.md").write_text("Dot claude instructions")
        mem = MemorySystem(working_directory=str(tmp_path))
        instructions = mem.load_project_instructions()
        assert "Dot claude instructions" in instructions


class TestMemoryIndex:
    def test_load_memory_index(self, tmp_path):
        """Load MEMORY.md index."""
        mem = MemorySystem(memory_dir=str(tmp_path))
        (tmp_path / "MEMORY.md").write_text(
            "# Memory\n"
            "- [Session 1](session1.md) -- First session\n"
            "- [Session 2](session2.md) -- Second session\n"
            "Some other text\n"
        )
        entries = mem.load_memory_index()
        assert len(entries) == 2
        assert "Session 1" in entries[0]["line"]
        assert "Session 2" in entries[1]["line"]

    def test_load_memory_index_no_file(self, tmp_path):
        """No MEMORY.md returns empty list."""
        mem = MemorySystem(memory_dir=str(tmp_path))
        entries = mem.load_memory_index()
        assert entries == []

    def test_load_memory_index_empty_file(self, tmp_path):
        """Empty MEMORY.md returns empty list."""
        mem = MemorySystem(memory_dir=str(tmp_path))
        (tmp_path / "MEMORY.md").write_text("")
        entries = mem.load_memory_index()
        assert entries == []


class TestMemoryFiles:
    def test_save_and_load_memory_file(self, tmp_path):
        """Save a memory file and load it back."""
        mem = MemorySystem(memory_dir=str(tmp_path))
        mem.save_memory("test.md", "Some memory content")
        content = mem.load_memory_file("test.md")
        assert content == "Some memory content"

    def test_load_nonexistent_memory_file(self, tmp_path):
        """Loading a nonexistent memory file returns empty string."""
        mem = MemorySystem(memory_dir=str(tmp_path))
        content = mem.load_memory_file("nonexistent.md")
        assert content == ""

    def test_memory_file_truncated_at_3000_chars(self, tmp_path):
        """Memory files are truncated at 3000 characters."""
        mem = MemorySystem(memory_dir=str(tmp_path))
        mem.save_memory("big.md", "x" * 5000)
        content = mem.load_memory_file("big.md")
        assert len(content) == 3000

    def test_save_creates_directory(self, tmp_path):
        """save_memory creates the memory directory if it doesn't exist."""
        mem_dir = tmp_path / "new_memory_dir"
        mem = MemorySystem(memory_dir=str(mem_dir))
        mem.save_memory("test.md", "content")
        assert mem_dir.exists()
        assert (mem_dir / "test.md").read_text() == "content"
