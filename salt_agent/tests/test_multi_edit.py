"""Tests for the multi-edit tool."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from salt_agent.tools.multi_edit import MultiEditTool
from salt_agent.tools.read import ReadTool


class TestMultiEditTool:
    def test_definition(self):
        tool = MultiEditTool()
        defn = tool.definition()
        assert defn.name == "multi_edit"
        assert len(defn.params) == 2

    def test_multiple_edits(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("foo = 1\nbar = 2\nbaz = 3\n")

        read_tool = ReadTool(working_directory=str(tmp_path))
        read_tool.files_read.add(str(target.resolve()))

        tool = MultiEditTool(read_tool=read_tool, working_directory=str(tmp_path))
        result = tool.execute(
            file_path=str(target),
            edits=[
                {"old_string": "foo = 1", "new_string": "foo = 10"},
                {"old_string": "baz = 3", "new_string": "baz = 30"},
            ],
        )

        assert "Applied 2/2" in result
        content = target.read_text()
        assert "foo = 10" in content
        assert "bar = 2" in content
        assert "baz = 30" in content

    def test_requires_read_first(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("hello")

        read_tool = ReadTool(working_directory=str(tmp_path))
        tool = MultiEditTool(read_tool=read_tool, working_directory=str(tmp_path))

        result = tool.execute(
            file_path=str(target),
            edits=[{"old_string": "hello", "new_string": "world"}],
        )
        assert "not been read first" in result

    def test_old_string_not_found(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("hello world")

        read_tool = ReadTool(working_directory=str(tmp_path))
        read_tool.files_read.add(str(target.resolve()))

        tool = MultiEditTool(read_tool=read_tool, working_directory=str(tmp_path))
        result = tool.execute(
            file_path=str(target),
            edits=[{"old_string": "nonexistent", "new_string": "replacement"}],
        )

        assert "Applied 0/1" in result
        assert "not found" in result

    def test_non_unique_old_string(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("aaa\naaa\nbbb\n")

        read_tool = ReadTool(working_directory=str(tmp_path))
        read_tool.files_read.add(str(target.resolve()))

        tool = MultiEditTool(read_tool=read_tool, working_directory=str(tmp_path))
        result = tool.execute(
            file_path=str(target),
            edits=[{"old_string": "aaa", "new_string": "ccc"}],
        )

        assert "Applied 0/1" in result
        assert "not unique" in result

    def test_file_not_found(self, tmp_path):
        tool = MultiEditTool(working_directory=str(tmp_path))
        result = tool.execute(
            file_path=str(tmp_path / "nonexistent.py"),
            edits=[{"old_string": "a", "new_string": "b"}],
        )
        assert "not found" in result

    def test_mixed_success_and_failure(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("alpha\nbeta\ngamma\n")

        read_tool = ReadTool(working_directory=str(tmp_path))
        read_tool.files_read.add(str(target.resolve()))

        tool = MultiEditTool(read_tool=read_tool, working_directory=str(tmp_path))
        result = tool.execute(
            file_path=str(target),
            edits=[
                {"old_string": "alpha", "new_string": "ALPHA"},
                {"old_string": "missing", "new_string": "MISSING"},
                {"old_string": "gamma", "new_string": "GAMMA"},
            ],
        )

        assert "Applied 2/3" in result
        content = target.read_text()
        assert "ALPHA" in content
        assert "beta" in content
        assert "GAMMA" in content

    def test_empty_edits(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("content")

        read_tool = ReadTool(working_directory=str(tmp_path))
        read_tool.files_read.add(str(target.resolve()))

        tool = MultiEditTool(read_tool=read_tool, working_directory=str(tmp_path))
        result = tool.execute(file_path=str(target), edits=[])

        assert "Applied 0/0" in result

    def test_no_read_tool_skips_check(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("hello")

        tool = MultiEditTool(read_tool=None, working_directory=str(tmp_path))
        result = tool.execute(
            file_path=str(target),
            edits=[{"old_string": "hello", "new_string": "world"}],
        )
        assert "Applied 1/1" in result
        assert target.read_text() == "world"

    def test_relative_path_resolved(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("hello")

        read_tool = ReadTool(working_directory=str(tmp_path))
        read_tool.files_read.add(str(target.resolve()))

        tool = MultiEditTool(read_tool=read_tool, working_directory=str(tmp_path))
        result = tool.execute(
            file_path="test.py",
            edits=[{"old_string": "hello", "new_string": "world"}],
        )
        assert "Applied 1/1" in result
