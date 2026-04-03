"""Tests for new tools: brief, python_repl, clipboard, open."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from salt_agent.tools.brief import BriefTool
from salt_agent.tools.clipboard import ClipboardTool
from salt_agent.tools.open_tool import OpenTool
from salt_agent.tools.repl import ReplTool


# ---------------------------------------------------------------------------
# BriefTool
# ---------------------------------------------------------------------------


class TestBriefTool:
    def test_definition(self):
        tool = BriefTool()
        defn = tool.definition()
        assert defn.name == "brief"
        param_names = [p.name for p in defn.params]
        assert "message" in param_names

    def test_execute_returns_message(self):
        tool = BriefTool()
        result = tool.execute(message="Done")
        assert result == "Done"

    def test_execute_returns_long_message(self):
        tool = BriefTool()
        msg = "Working on refactoring the module..."
        assert tool.execute(message=msg) == msg


# ---------------------------------------------------------------------------
# ReplTool
# ---------------------------------------------------------------------------


class TestReplTool:
    def test_definition(self):
        tool = ReplTool()
        defn = tool.definition()
        assert defn.name == "python_repl"
        param_names = [p.name for p in defn.params]
        assert "code" in param_names

    def test_simple_print(self):
        tool = ReplTool()
        result = tool.execute(code='print("hello")')
        assert "hello" in result

    def test_no_output(self):
        tool = ReplTool()
        result = tool.execute(code="x = 42")
        assert result == "OK (no output)"

    def test_state_persists(self):
        tool = ReplTool()
        tool.execute(code="counter = 10")
        result = tool.execute(code="print(counter + 5)")
        assert "15" in result

    def test_syntax_error(self):
        tool = ReplTool()
        result = tool.execute(code="def")
        assert "Error:" in result
        assert "SyntaxError" in result

    def test_runtime_error(self):
        tool = ReplTool()
        result = tool.execute(code="1/0")
        assert "Error:" in result
        assert "ZeroDivisionError" in result

    def test_stderr_captured(self):
        tool = ReplTool()
        result = tool.execute(code='import sys; sys.stderr.write("warn\\n")')
        assert "Stderr:" in result
        assert "warn" in result

    def test_multiline_code(self):
        tool = ReplTool()
        code = "for i in range(3):\n    print(i)"
        result = tool.execute(code=code)
        assert "0" in result
        assert "1" in result
        assert "2" in result


# ---------------------------------------------------------------------------
# ClipboardTool
# ---------------------------------------------------------------------------


class TestClipboardTool:
    def test_definition(self):
        tool = ClipboardTool()
        defn = tool.definition()
        assert defn.name == "clipboard"
        param_names = [p.name for p in defn.params]
        assert "action" in param_names
        assert "content" in param_names
        # content should be optional
        content_param = next(p for p in defn.params if p.name == "content")
        assert content_param.required is False

    def test_write(self):
        tool = ClipboardTool()
        with patch("salt_agent.tools.clipboard.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            result = tool.execute(action="write", content="hello world")
        assert "11 chars" in result
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["pbcopy"]
        assert call_args[1]["input"] == b"hello world"

    def test_write_empty(self):
        tool = ClipboardTool()
        with patch("salt_agent.tools.clipboard.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            result = tool.execute(action="write")
        assert "0 chars" in result

    def test_read(self):
        tool = ClipboardTool()
        mock_proc = MagicMock()
        mock_proc.stdout = "clipboard content"
        with patch("salt_agent.tools.clipboard.subprocess.run", return_value=mock_proc):
            result = tool.execute(action="read")
        assert result == "clipboard content"

    def test_read_empty(self):
        tool = ClipboardTool()
        mock_proc = MagicMock()
        mock_proc.stdout = ""
        with patch("salt_agent.tools.clipboard.subprocess.run", return_value=mock_proc):
            result = tool.execute(action="read")
        assert result == "(clipboard is empty)"


# ---------------------------------------------------------------------------
# OpenTool
# ---------------------------------------------------------------------------


class TestOpenTool:
    def test_definition(self):
        tool = OpenTool()
        defn = tool.definition()
        assert defn.name == "open"
        param_names = [p.name for p in defn.params]
        assert "target" in param_names

    def test_open_file_darwin(self):
        tool = OpenTool()
        with patch("salt_agent.tools.open_tool.sys") as mock_sys, \
             patch("salt_agent.tools.open_tool.subprocess.Popen") as mock_popen:
            mock_sys.platform = "darwin"
            result = tool.execute(target="/tmp/test.txt")
        assert "Opened /tmp/test.txt" in result
        mock_popen.assert_called_once_with(["open", "/tmp/test.txt"])

    def test_open_url_darwin(self):
        tool = OpenTool()
        with patch("salt_agent.tools.open_tool.sys") as mock_sys, \
             patch("salt_agent.tools.open_tool.subprocess.Popen") as mock_popen:
            mock_sys.platform = "darwin"
            result = tool.execute(target="https://example.com")
        assert "Opened https://example.com" in result
        mock_popen.assert_called_once_with(["open", "https://example.com"])

    def test_open_linux(self):
        tool = OpenTool()
        with patch("salt_agent.tools.open_tool.sys") as mock_sys, \
             patch("salt_agent.tools.open_tool.subprocess.Popen") as mock_popen:
            mock_sys.platform = "linux"
            result = tool.execute(target="/tmp/test.txt")
        assert "Opened" in result
        mock_popen.assert_called_once_with(["xdg-open", "/tmp/test.txt"])

    def test_open_windows(self):
        tool = OpenTool()
        with patch("salt_agent.tools.open_tool.sys") as mock_sys, \
             patch("salt_agent.tools.open_tool.subprocess.Popen") as mock_popen:
            mock_sys.platform = "win32"
            result = tool.execute(target="C:\\test.txt")
        assert "Opened" in result
        mock_popen.assert_called_once_with(["start", "C:\\test.txt"], shell=True)
