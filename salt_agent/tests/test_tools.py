"""Tests for built-in tools."""

import os
import tempfile
from pathlib import Path

import pytest

from salt_agent.tools.base import ToolRegistry, ToolDefinition, ToolParam
from salt_agent.tools.read import ReadTool
from salt_agent.tools.write import WriteTool
from salt_agent.tools.edit import EditTool
from salt_agent.tools.bash import BashTool
from salt_agent.tools.glob_tool import GlobTool
from salt_agent.tools.grep import GrepTool
from salt_agent.tools.list_files import ListFilesTool


# --- ToolRegistry ---

class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = ReadTool()
        reg.register(tool)
        assert reg.get("read") is tool

    def test_get_missing(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_list_definitions(self):
        reg = ToolRegistry()
        reg.register(ReadTool())
        reg.register(BashTool())
        defs = reg.list_definitions()
        assert len(defs) == 2
        names = [d.name for d in defs]
        assert "read" in names
        assert "bash" in names

    def test_names(self):
        reg = ToolRegistry()
        reg.register(ReadTool())
        reg.register(BashTool())
        assert set(reg.names()) == {"read", "bash"}

    def test_to_anthropic_tools(self):
        reg = ToolRegistry()
        reg.register(ReadTool())
        tools = reg.to_anthropic_tools()
        assert len(tools) == 1
        t = tools[0]
        assert t["name"] == "read"
        assert "input_schema" in t
        assert t["input_schema"]["type"] == "object"
        assert "file_path" in t["input_schema"]["properties"]
        assert "file_path" in t["input_schema"]["required"]

    def test_to_openai_tools(self):
        reg = ToolRegistry()
        reg.register(ReadTool())
        tools = reg.to_openai_tools()
        assert len(tools) == 1
        t = tools[0]
        assert t["type"] == "function"
        assert t["function"]["name"] == "read"
        assert "parameters" in t["function"]
        assert "file_path" in t["function"]["parameters"]["properties"]

    def test_optional_params_not_required(self):
        reg = ToolRegistry()
        reg.register(ReadTool())
        tools = reg.to_anthropic_tools()
        required = tools[0]["input_schema"]["required"]
        assert "offset" not in required
        assert "limit" not in required


# --- ReadTool ---

class TestReadTool:
    def test_read_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = ReadTool()
        result = tool.execute(file_path=str(f))
        assert "line1" in result
        assert "line2" in result
        assert "3 lines total" in result
        assert str(f.resolve()) in tool.files_read

    def test_read_with_offset(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("a\nb\nc\nd\ne\n")
        tool = ReadTool()
        result = tool.execute(file_path=str(f), offset=2, limit=2)
        assert "c" in result
        assert "d" in result

    def test_read_nonexistent(self):
        tool = ReadTool()
        result = tool.execute(file_path="/nonexistent/file.txt")
        assert "Error" in result

    def test_read_directory(self, tmp_path):
        tool = ReadTool()
        result = tool.execute(file_path=str(tmp_path))
        assert "Error" in result

    def test_read_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        tool = ReadTool()
        result = tool.execute(file_path=str(f))
        assert "empty" in result.lower()

    def test_tracks_files_read(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("hello")
        tool = ReadTool()
        tool.execute(file_path=str(f))
        assert str(f.resolve()) in tool.files_read


# --- WriteTool ---

class TestWriteTool:
    def test_write_new_file(self, tmp_path):
        f = tmp_path / "new.txt"
        tool = WriteTool()
        result = tool.execute(file_path=str(f), content="hello world\n")
        assert "Successfully" in result
        assert f.read_text() == "hello world\n"

    def test_write_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "a" / "b" / "c.txt"
        tool = WriteTool()
        result = tool.execute(file_path=str(f), content="deep\n")
        assert "Successfully" in result
        assert f.read_text() == "deep\n"

    def test_write_existing_requires_read(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("old")
        read_tool = ReadTool()
        write_tool = WriteTool(read_tool=read_tool)
        result = write_tool.execute(file_path=str(f), content="new")
        assert "Error" in result
        assert "not been read" in result

    def test_write_existing_after_read(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("old")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        write_tool = WriteTool(read_tool=read_tool)
        result = write_tool.execute(file_path=str(f), content="new")
        assert "Successfully" in result
        assert f.read_text() == "new"

    def test_write_tracks_files(self, tmp_path):
        f = tmp_path / "track.txt"
        tool = WriteTool()
        tool.execute(file_path=str(f), content="x")
        assert str(f.resolve()) in tool.files_written


# --- EditTool ---

class TestEditTool:
    def test_edit_basic(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("hello world")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="hello", new_string="goodbye")
        assert "Successfully" in result
        assert f.read_text() == "goodbye world"

    def test_edit_requires_read(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("hello")
        read_tool = ReadTool()
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="hello", new_string="bye")
        assert "Error" in result
        assert "not been read" in result

    def test_edit_nonexistent(self):
        edit_tool = EditTool()
        result = edit_tool.execute(file_path="/nonexistent", old_string="a", new_string="b")
        assert "Error" in result

    def test_edit_not_found(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("hello")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="xyz", new_string="abc")
        assert "not found" in result

    def test_edit_ambiguous(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("aaa bbb aaa")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="aaa", new_string="ccc")
        assert "appears 2 times" in result

    def test_edit_replace_all(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("aaa bbb aaa")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="aaa", new_string="ccc", replace_all=True)
        assert "2 occurrence" in result
        assert f.read_text() == "ccc bbb ccc"

    def test_edit_identical_strings(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("hello")
        read_tool = ReadTool()
        read_tool.execute(file_path=str(f))
        edit_tool = EditTool(read_tool=read_tool)
        result = edit_tool.execute(file_path=str(f), old_string="hello", new_string="hello")
        assert "identical" in result


# --- BashTool ---

class TestBashTool:
    def test_simple_command(self):
        tool = BashTool()
        result = tool.execute(command="echo hello")
        assert "hello" in result

    def test_command_failure(self):
        tool = BashTool()
        result = tool.execute(command="ls /nonexistent_dir_12345")
        assert "Exit code" in result or "Error" in result or "No such file" in result

    def test_timeout(self):
        tool = BashTool(timeout=1)
        result = tool.execute(command="sleep 10")
        assert "timed out" in result

    def test_custom_timeout_param(self):
        tool = BashTool()
        result = tool.execute(command="sleep 10", timeout=1)
        assert "timed out" in result

    def test_output_truncation(self):
        tool = BashTool(max_output=100)
        result = tool.execute(command="python3 -c \"print('x' * 500)\"")
        assert "truncated" in result

    def test_working_directory(self, tmp_path):
        tool = BashTool(working_directory=str(tmp_path))
        result = tool.execute(command="pwd")
        assert str(tmp_path) in result

    def test_stderr_captured(self):
        tool = BashTool()
        result = tool.execute(command="echo err >&2")
        assert "err" in result


# --- GlobTool ---

class TestGlobTool:
    def test_glob_basic(self, tmp_path):
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("y")
        (tmp_path / "c.txt").write_text("z")
        tool = GlobTool(working_directory=str(tmp_path))
        result = tool.execute(pattern="*.py", path=str(tmp_path))
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    def test_glob_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("x")
        tool = GlobTool()
        result = tool.execute(pattern="**/*.py", path=str(tmp_path))
        assert "deep.py" in result

    def test_glob_no_matches(self, tmp_path):
        tool = GlobTool()
        result = tool.execute(pattern="*.xyz", path=str(tmp_path))
        assert "No files matched" in result

    def test_glob_nonexistent_dir(self):
        tool = GlobTool()
        result = tool.execute(pattern="*", path="/nonexistent_12345")
        assert "Error" in result


# --- GrepTool ---

class TestGrepTool:
    def test_grep_basic(self, tmp_path):
        (tmp_path / "test.txt").write_text("hello world\nfoo bar\nhello again\n")
        tool = GrepTool(working_directory=str(tmp_path))
        result = tool.execute(pattern="hello", path=str(tmp_path))
        assert "hello" in result

    def test_grep_no_match(self, tmp_path):
        (tmp_path / "test.txt").write_text("hello world\n")
        tool = GrepTool(working_directory=str(tmp_path))
        result = tool.execute(pattern="zzzzz", path=str(tmp_path))
        assert "No matches" in result


# --- ListFilesTool ---

class TestListFilesTool:
    def test_list_basic(self, tmp_path):
        (tmp_path / "file.txt").write_text("hello")
        sub = tmp_path / "subdir"
        sub.mkdir()
        tool = ListFilesTool()
        result = tool.execute(path=str(tmp_path))
        assert "file.txt" in result
        assert "subdir/" in result

    def test_list_nonexistent(self):
        tool = ListFilesTool()
        result = tool.execute(path="/nonexistent_12345")
        assert "Error" in result

    def test_list_hides_dotfiles(self, tmp_path):
        (tmp_path / ".hidden").write_text("x")
        (tmp_path / "visible.txt").write_text("y")
        tool = ListFilesTool()
        result = tool.execute(path=str(tmp_path))
        assert ".hidden" not in result
        assert "visible.txt" in result
