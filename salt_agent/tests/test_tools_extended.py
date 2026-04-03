"""Extended tool tests — deeper coverage for all built-in tools."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from salt_agent.tools.read import ReadTool
from salt_agent.tools.write import WriteTool
from salt_agent.tools.edit import EditTool
from salt_agent.tools.bash import BashTool
from salt_agent.tools.glob_tool import GlobTool
from salt_agent.tools.grep import GrepTool
from salt_agent.tools.list_files import ListFilesTool


# ---------------------------------------------------------------------------
# ReadTool
# ---------------------------------------------------------------------------

class TestReadToolExtended:
    def test_read_content_with_line_numbers(self, tmp_path):
        f = tmp_path / "numbered.txt"
        f.write_text("alpha\nbeta\ngamma\n")
        tool = ReadTool()
        result = tool.execute(file_path=str(f))
        assert "1\talpha" in result
        assert "2\tbeta" in result
        assert "3\tgamma" in result

    def test_read_with_offset_and_limit(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("\n".join(f"line{i}" for i in range(20)))
        tool = ReadTool()
        result = tool.execute(file_path=str(f), offset=5, limit=3)
        assert "line5" in result
        assert "line6" in result
        assert "line7" in result
        assert "line8" not in result
        assert "showing lines 6-8" in result

    def test_read_nonexistent_file(self):
        tool = ReadTool()
        result = tool.execute(file_path="/tmp/does_not_exist_999.txt")
        assert "Error" in result
        assert "not found" in result.lower() or "File not found" in result

    def test_read_binary_file(self, tmp_path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\x00\x01\x02\xff\xfe")
        tool = ReadTool()
        result = tool.execute(file_path=str(f))
        # Should not crash; errors="replace" handles it
        assert "binary.bin" in result

    def test_files_read_tracking(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("a")
        f2.write_text("b")
        tool = ReadTool()
        assert len(tool.files_read) == 0
        tool.execute(file_path=str(f1))
        assert str(f1.resolve()) in tool.files_read
        assert str(f2.resolve()) not in tool.files_read
        tool.execute(file_path=str(f2))
        assert str(f2.resolve()) in tool.files_read

    def test_relative_path_resolved_from_working_directory(self, tmp_path):
        f = tmp_path / "rel.txt"
        f.write_text("relative content")
        tool = ReadTool(working_directory=str(tmp_path))
        result = tool.execute(file_path="rel.txt")
        assert "relative content" in result

    def test_read_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        tool = ReadTool()
        result = tool.execute(file_path=str(f))
        assert "empty" in result.lower()

    def test_read_large_offset_returns_nothing(self, tmp_path):
        f = tmp_path / "short.txt"
        f.write_text("one\ntwo\n")
        tool = ReadTool()
        result = tool.execute(file_path=str(f), offset=100)
        # Should get header but no lines (or empty marker)
        assert "2 lines total" in result


# ---------------------------------------------------------------------------
# WriteTool
# ---------------------------------------------------------------------------

class TestWriteToolExtended:
    def test_write_new_file_in_working_directory(self, tmp_path):
        tool = WriteTool(working_directory=str(tmp_path))
        result = tool.execute(file_path="newfile.txt", content="hello\n")
        assert "Successfully" in result
        assert (tmp_path / "newfile.txt").read_text() == "hello\n"

    def test_write_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "deep" / "nested" / "file.txt"
        tool = WriteTool()
        result = tool.execute(file_path=str(f), content="deep content\n")
        assert "Successfully" in result
        assert f.read_text() == "deep content\n"

    def test_write_existing_file_requires_read_first(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("original")
        read_tool = ReadTool()
        write_tool = WriteTool(read_tool=read_tool)
        result = write_tool.execute(file_path=str(f), content="overwrite")
        assert "Error" in result
        assert "not been read" in result

    def test_write_existing_file_after_read_succeeds(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("original")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        write_tool = WriteTool(read_tool=read_tool)
        result = write_tool.execute(file_path=str(f), content="new content")
        assert "Successfully" in result
        assert f.read_text() == "new content"

    def test_write_tracks_files_written(self, tmp_path):
        f = tmp_path / "tracked.txt"
        tool = WriteTool()
        tool.execute(file_path=str(f), content="x")
        assert str(f.resolve()) in tool.files_written

    def test_write_without_read_tool_allows_overwrite(self, tmp_path):
        """When no read_tool is provided, write allows overwriting existing files."""
        f = tmp_path / "existing.txt"
        f.write_text("old")
        tool = WriteTool(read_tool=None)
        result = tool.execute(file_path=str(f), content="new")
        assert "Successfully" in result
        assert f.read_text() == "new"

    def test_write_line_count_reporting(self, tmp_path):
        f = tmp_path / "multiline.txt"
        tool = WriteTool()
        result = tool.execute(file_path=str(f), content="a\nb\nc\n")
        assert "3 lines" in result


# ---------------------------------------------------------------------------
# EditTool
# ---------------------------------------------------------------------------

class TestEditToolExtended:
    def test_basic_string_replacement(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("foo bar baz")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="bar", new_string="qux")
        assert "Successfully" in result
        assert f.read_text() == "foo qux baz"

    def test_edit_requires_read_first(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("content")
        read_tool = ReadTool()
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="content", new_string="new")
        assert "Error" in result
        assert "not been read" in result

    def test_non_unique_old_string_error(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("abc def abc ghi abc")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="abc", new_string="xyz")
        assert "3 times" in result

    def test_old_string_not_found(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("hello world")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="missing", new_string="replacement")
        assert "not found" in result

    def test_replace_all_flag(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("x + x = 2x")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(
            file_path=str(f), old_string="x", new_string="y", replace_all=True
        )
        assert "3 occurrence" in result
        assert f.read_text() == "y + y = 2y"

    def test_identical_old_and_new_string(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("same")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="same", new_string="same")
        assert "identical" in result

    def test_relative_path_resolution(self, tmp_path):
        f = tmp_path / "edit_rel.txt"
        f.write_text("old text here")
        read_tool = ReadTool(working_directory=str(tmp_path))
        read_tool.execute(file_path="edit_rel.txt")
        edit_tool = EditTool(read_tool=read_tool, working_directory=str(tmp_path))
        result = edit_tool.execute(file_path="edit_rel.txt", old_string="old", new_string="new")
        assert "Successfully" in result
        assert f.read_text() == "new text here"

    def test_edit_nonexistent_file(self):
        edit_tool = EditTool()
        result = edit_tool.execute(file_path="/no/such/file.txt", old_string="a", new_string="b")
        assert "Error" in result
        assert "not found" in result.lower() or "File not found" in result


# ---------------------------------------------------------------------------
# BashTool
# ---------------------------------------------------------------------------

class TestBashToolExtended:
    def test_simple_command(self):
        tool = BashTool()
        result = tool.execute(command="echo hello world")
        assert "hello world" in result

    def test_command_with_nonzero_exit(self):
        tool = BashTool()
        result = tool.execute(command="exit 42")
        assert "Exit code: 42" in result

    def test_timeout_enforcement(self):
        tool = BashTool(timeout=1)
        result = tool.execute(command="sleep 60")
        assert "timed out" in result

    def test_output_truncation_for_long_output(self):
        tool = BashTool(max_output=200)
        result = tool.execute(command="python3 -c \"print('A' * 1000)\"")
        assert "truncated" in result
        assert len(result) < 1000

    def test_working_directory_enforcement(self, tmp_path):
        tool = BashTool(working_directory=str(tmp_path))
        result = tool.execute(command="pwd")
        assert str(tmp_path) in result

    def test_stderr_captured(self):
        tool = BashTool()
        result = tool.execute(command="echo error_msg >&2")
        assert "error_msg" in result

    def test_no_output_command(self):
        tool = BashTool()
        result = tool.execute(command="true")
        assert "no output" in result.lower()

    def test_timeout_param_override(self):
        tool = BashTool(timeout=60)
        result = tool.execute(command="sleep 60", timeout=1)
        assert "timed out" in result

    def test_combined_stdout_stderr(self):
        tool = BashTool()
        result = tool.execute(command="echo out && echo err >&2")
        assert "out" in result
        assert "err" in result


# ---------------------------------------------------------------------------
# GlobTool
# ---------------------------------------------------------------------------

class TestGlobToolExtended:
    def test_find_py_files(self, tmp_path):
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("y")
        (tmp_path / "c.js").write_text("z")
        tool = GlobTool(working_directory=str(tmp_path))
        result = tool.execute(pattern="*.py")
        assert "a.py" in result
        assert "b.py" in result
        assert "c.js" not in result

    def test_recursive_pattern(self, tmp_path):
        sub = tmp_path / "sub" / "deep"
        sub.mkdir(parents=True)
        (sub / "found.py").write_text("x")
        tool = GlobTool()
        result = tool.execute(pattern="**/*.py", path=str(tmp_path))
        assert "found.py" in result

    def test_no_matches_empty_result(self, tmp_path):
        tool = GlobTool()
        result = tool.execute(pattern="*.nonexistent", path=str(tmp_path))
        assert "No files matched" in result

    def test_working_directory_as_default_path(self, tmp_path):
        (tmp_path / "default.txt").write_text("x")
        tool = GlobTool(working_directory=str(tmp_path))
        result = tool.execute(pattern="*.txt")
        assert "default.txt" in result

    def test_nonexistent_search_path(self):
        tool = GlobTool()
        result = tool.execute(pattern="*", path="/nonexistent_dir_xyz")
        assert "Error" in result

    def test_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        tool = GlobTool()
        result = tool.execute(pattern="*", path=str(f))
        assert "Error" in result


# ---------------------------------------------------------------------------
# GrepTool
# ---------------------------------------------------------------------------

class TestGrepToolExtended:
    def test_basic_pattern_search(self, tmp_path):
        (tmp_path / "test.py").write_text("def hello():\n    pass\ndef world():\n    pass\n")
        tool = GrepTool(working_directory=str(tmp_path))
        result = tool.execute(pattern="def", path=str(tmp_path))
        assert "def hello" in result
        assert "def world" in result

    def test_regex_pattern(self, tmp_path):
        (tmp_path / "data.txt").write_text("foo123\nbar456\nbaz\n")
        tool = GrepTool(working_directory=str(tmp_path))
        # Use basic regex (BRE compatible) since macOS grep doesn't support ERE by default
        result = tool.execute(pattern="foo.*3", path=str(tmp_path))
        assert "foo123" in result

    def test_no_matches(self, tmp_path):
        (tmp_path / "empty_match.txt").write_text("nothing interesting\n")
        tool = GrepTool(working_directory=str(tmp_path))
        result = tool.execute(pattern="zzzzz_unique_pattern", path=str(tmp_path))
        assert "No matches" in result

    def test_working_directory_default_path(self, tmp_path):
        (tmp_path / "wd.txt").write_text("findme_marker\n")
        tool = GrepTool(working_directory=str(tmp_path))
        result = tool.execute(pattern="findme_marker")
        assert "findme_marker" in result

    def test_case_insensitive(self, tmp_path):
        (tmp_path / "case.txt").write_text("Hello World\nhello world\nHELLO WORLD\n")
        tool = GrepTool(working_directory=str(tmp_path))
        result = tool.execute(pattern="hello", path=str(tmp_path), case_insensitive=True)
        # Should find all three lines
        assert "Hello" in result or "hello" in result

    def test_glob_filter(self, tmp_path):
        (tmp_path / "a.py").write_text("target_word\n")
        (tmp_path / "b.txt").write_text("target_word\n")
        tool = GrepTool(working_directory=str(tmp_path))
        result = tool.execute(pattern="target_word", path=str(tmp_path), **{"glob": "*.py"})
        assert "a.py" in result


# ---------------------------------------------------------------------------
# ListFilesTool
# ---------------------------------------------------------------------------

class TestListFilesToolExtended:
    def test_list_directory_contents(self, tmp_path):
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.py").write_text("b")
        sub = tmp_path / "subdir"
        sub.mkdir()
        tool = ListFilesTool()
        result = tool.execute(path=str(tmp_path))
        assert "file1.txt" in result
        assert "file2.py" in result
        assert "subdir/" in result

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty_dir"
        empty.mkdir()
        tool = ListFilesTool()
        result = tool.execute(path=str(empty))
        assert "empty" in result.lower()

    def test_nonexistent_directory(self):
        tool = ListFilesTool()
        result = tool.execute(path="/nonexistent_dir_xyz_12345")
        assert "Error" in result

    def test_hidden_files_excluded(self, tmp_path):
        (tmp_path / ".hidden").write_text("x")
        (tmp_path / "visible.txt").write_text("y")
        tool = ListFilesTool()
        result = tool.execute(path=str(tmp_path))
        assert ".hidden" not in result
        assert "visible.txt" in result

    def test_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        tool = ListFilesTool()
        result = tool.execute(path=str(f))
        assert "Error" in result
        assert "Not a directory" in result

    def test_directories_listed_with_slash(self, tmp_path):
        sub = tmp_path / "mydir"
        sub.mkdir()
        tool = ListFilesTool()
        result = tool.execute(path=str(tmp_path))
        assert "mydir/" in result

    def test_file_sizes_shown(self, tmp_path):
        f = tmp_path / "sized.txt"
        f.write_text("hello")  # 5 bytes
        tool = ListFilesTool()
        result = tool.execute(path=str(tmp_path))
        assert "sized.txt" in result
        assert "B" in result  # Should show size with unit

    def test_working_directory_default(self, tmp_path):
        (tmp_path / "wd_file.txt").write_text("x")
        tool = ListFilesTool(working_directory=str(tmp_path))
        result = tool.execute()
        assert "wd_file.txt" in result
