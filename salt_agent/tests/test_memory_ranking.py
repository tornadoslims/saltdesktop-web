"""Tests for memory types, frontmatter parsing, and LLM-powered relevance ranking."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from salt_agent.memory import MemorySystem, find_relevant_memories, MEMORY_TYPES
from salt_agent.providers.base import ProviderAdapter


# --- Mock provider ---

class MockProvider(ProviderAdapter):
    """Mock provider that returns canned responses for quick_query."""

    def __init__(self, response: str = "NONE"):
        self._response = response

    async def stream_response(self, **kwargs):
        # Not used in these tests
        return
        yield  # make it an async generator

    async def quick_query(self, prompt: str, system: str = "", max_tokens: int = 500) -> str:
        return self._response


# --- Tests for find_relevant_memories ---

class TestFindRelevantMemories:
    def test_empty_index_returns_empty(self):
        provider = MockProvider("NONE")
        result = asyncio.run(
            find_relevant_memories("fix the login bug", [], provider)
        )
        assert result == []

    def test_none_response_returns_empty(self):
        provider = MockProvider("NONE")
        index = [{"filename": "user_prefs.md", "description": "User prefers TS"}]
        result = asyncio.run(
            find_relevant_memories("fix the login bug", index, provider)
        )
        assert result == []

    def test_relevant_memories_returned(self):
        provider = MockProvider("user_prefs.md\nproject_api.md")
        index = [
            {"filename": "user_prefs.md", "description": "User prefers TS"},
            {"filename": "project_api.md", "description": "API patterns"},
            {"filename": "reference_docs.md", "description": "External docs"},
        ]
        result = asyncio.run(
            find_relevant_memories("update the API endpoint", index, provider)
        )
        assert "user_prefs.md" in result
        assert "project_api.md" in result
        assert "reference_docs.md" not in result

    def test_max_5_memories(self):
        # Provider returns more than 5 filenames
        response = "\n".join(f"mem_{i}.md" for i in range(10))
        provider = MockProvider(response)
        index = [
            {"filename": f"mem_{i}.md", "description": f"Memory {i}"}
            for i in range(10)
        ]
        result = asyncio.run(
            find_relevant_memories("some query", index, provider)
        )
        assert len(result) <= 5

    def test_provider_error_returns_empty(self):
        class ErrorProvider(ProviderAdapter):
            async def stream_response(self, **kwargs):
                return
                yield

            async def quick_query(self, prompt, system="", max_tokens=500):
                raise RuntimeError("API down")

        provider = ErrorProvider()
        index = [{"filename": "test.md", "description": "test"}]
        result = asyncio.run(
            find_relevant_memories("query", index, provider)
        )
        assert result == []


# --- Tests for memory file scanning ---

class TestMemoryFileScanning:
    def test_scan_empty_directory(self, tmp_path):
        mem = MemorySystem(memory_dir=str(tmp_path))
        entries = mem.scan_memory_files()
        assert entries == []

    def test_scan_directory_does_not_exist(self, tmp_path):
        mem = MemorySystem(memory_dir=str(tmp_path / "nonexistent"))
        entries = mem.scan_memory_files()
        assert entries == []

    def test_scan_files_with_frontmatter(self, tmp_path):
        (tmp_path / "user_prefs.md").write_text(
            "---\n"
            "name: user_prefs\n"
            "description: User prefers TypeScript\n"
            "type: feedback\n"
            "---\n\n"
            "User said always use TS.\n"
        )
        (tmp_path / "project_api.md").write_text(
            "---\n"
            "name: project_api\n"
            "description: API patterns\n"
            "type: project\n"
            "---\n\n"
            "REST endpoints follow /api/v2/{resource}.\n"
        )
        mem = MemorySystem(memory_dir=str(tmp_path))
        entries = mem.scan_memory_files()
        assert len(entries) == 2
        names = {e["name"] for e in entries}
        assert "user_prefs" in names
        assert "project_api" in names

    def test_scan_skips_memory_md(self, tmp_path):
        (tmp_path / "MEMORY.md").write_text("- [entry](entry.md) -- desc")
        (tmp_path / "entry.md").write_text("---\nname: entry\n---\n\ncontent")
        mem = MemorySystem(memory_dir=str(tmp_path))
        entries = mem.scan_memory_files()
        assert len(entries) == 1
        assert entries[0]["filename"] == "entry.md"

    def test_scan_file_without_frontmatter(self, tmp_path):
        (tmp_path / "plain.md").write_text("Just plain text, no frontmatter.")
        mem = MemorySystem(memory_dir=str(tmp_path))
        entries = mem.scan_memory_files()
        assert len(entries) == 1
        assert entries[0]["name"] == "plain"  # falls back to stem
        assert entries[0]["type"] == "project"  # default


# --- Tests for frontmatter parsing ---

class TestFrontmatterParsing:
    def test_parse_valid_frontmatter(self):
        content = "---\nname: test\ndescription: A test\ntype: user\n---\n\nBody."
        meta = MemorySystem._parse_frontmatter(content)
        assert meta["name"] == "test"
        assert meta["description"] == "A test"
        assert meta["type"] == "user"

    def test_parse_no_frontmatter(self):
        content = "Just plain text."
        meta = MemorySystem._parse_frontmatter(content)
        assert meta == {}

    def test_parse_incomplete_frontmatter(self):
        content = "---\nname: test\nNo closing delimiter"
        meta = MemorySystem._parse_frontmatter(content)
        assert meta == {}

    def test_parse_empty_frontmatter(self):
        content = "---\n---\n\nBody."
        meta = MemorySystem._parse_frontmatter(content)
        assert meta == {}


# --- Tests for save_memory_file ---

class TestSaveMemoryFile:
    def test_save_creates_file_with_frontmatter(self, tmp_path):
        mem = MemorySystem(memory_dir=str(tmp_path))
        mem.save_memory_file(
            name="user_prefers_ts",
            content="Always use TypeScript.",
            memory_type="feedback",
            description="User prefers TypeScript over JS",
        )
        files = list(tmp_path.glob("*.md"))
        # Should have the memory file + MEMORY.md
        filenames = {f.name for f in files}
        assert "user_prefers_ts.md" in filenames
        assert "MEMORY.md" in filenames

        content = (tmp_path / "user_prefers_ts.md").read_text()
        assert "name: user_prefers_ts" in content
        assert "type: feedback" in content
        assert "Always use TypeScript." in content

    def test_save_creates_memory_dir(self, tmp_path):
        mem_dir = tmp_path / "new_mem"
        mem = MemorySystem(memory_dir=str(mem_dir))
        mem.save_memory_file("test", "content", "project", "desc")
        assert mem_dir.exists()

    def test_save_updates_index(self, tmp_path):
        mem = MemorySystem(memory_dir=str(tmp_path))
        mem.save_memory_file("entry_one", "content1", "user", "First entry")
        mem.save_memory_file("entry_two", "content2", "project", "Second entry")

        index_content = (tmp_path / "MEMORY.md").read_text()
        assert "entry_one" in index_content
        assert "entry_two" in index_content

    def test_save_updates_existing_index_entry(self, tmp_path):
        mem = MemorySystem(memory_dir=str(tmp_path))
        mem.save_memory_file("entry", "v1", "user", "Version 1")
        mem.save_memory_file("entry", "v2", "user", "Version 2")

        index_content = (tmp_path / "MEMORY.md").read_text()
        assert "Version 2" in index_content
        # Should not have duplicate entries
        assert index_content.count("entry.md") == 1


# --- Tests for memory types ---

class TestMemoryTypes:
    def test_all_types_defined(self):
        assert "user" in MEMORY_TYPES
        assert "feedback" in MEMORY_TYPES
        assert "project" in MEMORY_TYPES
        assert "reference" in MEMORY_TYPES

    def test_each_type_has_required_fields(self):
        for type_name, type_info in MEMORY_TYPES.items():
            assert "description" in type_info, f"{type_name} missing description"
            assert "when_to_save" in type_info, f"{type_name} missing when_to_save"
            assert "when_to_use" in type_info, f"{type_name} missing when_to_use"
