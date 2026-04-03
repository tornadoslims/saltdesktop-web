"""Tests for CLI argument parsing and helper functions (no API calls needed)."""

import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

from salt_agent.cli import (
    _build_parser,
    _resolve_api_key,
    _tool_brief,
    _tool_result_brief,
    _abbreviate_path,
    _handle_slash_command,
    TokenTracker,
    __version__,
)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

class TestCLIArgParsing:
    def test_version_flag(self, capsys):
        parser = _build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_help_flag(self, capsys):
        parser = _build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_provider_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["-p", "openai", "hello"])
        assert args.provider == "openai"

    def test_provider_default(self):
        parser = _build_parser()
        args = parser.parse_args(["hello"])
        assert args.provider == "openai"

    def test_model_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["-m", "gpt-4o-mini", "hello"])
        assert args.model == "gpt-4o-mini"

    def test_directory_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["-d", "/tmp/mydir", "hello"])
        assert args.directory == "/tmp/mydir"

    def test_system_prompt_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["-s", "You are a test.", "hello"])
        assert args.system == "You are a test."

    def test_max_turns_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--max-turns", "5", "hello"])
        assert args.max_turns == 5

    def test_api_key_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--api-key", "sk-test", "hello"])
        assert args.api_key == "sk-test"

    def test_verbose_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--verbose", "hello"])
        assert args.verbose is True

    def test_json_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--json", "hello"])
        assert args.json_mode is True

    def test_interactive_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["-i"])
        assert args.interactive is True

    def test_prompt_positional(self):
        parser = _build_parser()
        args = parser.parse_args(["Build a REST API"])
        assert args.prompt == "Build a REST API"

    def test_no_prompt_no_interactive(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.prompt is None
        assert args.interactive is False  # main() would set it to True


# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------

class TestAPIKeyResolution:
    def test_explicit_key_returned(self):
        result = _resolve_api_key("anthropic", explicit_key="sk-explicit")
        assert result == "sk-explicit"

    def test_env_var_anthropic(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env-anthropic"}):
            result = _resolve_api_key("anthropic")
            assert result == "sk-env-anthropic"

    def test_env_var_openai(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-openai"}):
            result = _resolve_api_key("openai")
            assert result == "sk-env-openai"

    def test_no_key_found_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            # Also mock os.path.exists to prevent reading real config files
            with patch("os.path.exists", return_value=False):
                result = _resolve_api_key("anthropic")
                assert result == ""

    def test_explicit_key_overrides_env(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env"}):
            result = _resolve_api_key("anthropic", explicit_key="sk-explicit")
            assert result == "sk-explicit"


# ---------------------------------------------------------------------------
# Tool brief descriptions
# ---------------------------------------------------------------------------

class TestToolBrief:
    def test_bash_tool(self):
        result = _tool_brief("bash", {"command": "echo hello"})
        assert "bash" in result
        assert "echo hello" in result

    def test_bash_long_command_truncated(self):
        long_cmd = "x" * 100
        result = _tool_brief("bash", {"command": long_cmd})
        assert len(result) < 100

    def test_write_tool(self):
        result = _tool_brief("write", {"file_path": "/tmp/test.txt"})
        assert "write" in result

    def test_edit_tool(self):
        result = _tool_brief("edit", {"file_path": "/tmp/test.txt"})
        assert "edit" in result

    def test_read_tool(self):
        result = _tool_brief("read", {"file_path": "/tmp/test.txt"})
        assert "read" in result

    def test_glob_tool(self):
        result = _tool_brief("glob", {"pattern": "*.py"})
        assert "glob" in result
        assert "*.py" in result

    def test_grep_tool(self):
        result = _tool_brief("grep", {"pattern": "TODO"})
        assert "grep" in result
        assert "TODO" in result

    def test_list_files_tool(self):
        result = _tool_brief("list_files", {"path": "/tmp"})
        assert "ls" in result

    def test_unknown_tool(self):
        result = _tool_brief("custom_tool", {"arg": "val"})
        assert result == "custom_tool"


class TestToolResultBrief:
    def test_success_empty_result(self):
        result = _tool_result_brief("bash", "", True)
        assert result == "done"

    def test_edit_success(self):
        result = _tool_result_brief("edit", "Applied successfully", True)
        assert "applied edit" in result

    def test_write_success(self):
        result = _tool_result_brief("write", "Wrote file", True)
        assert "wrote" in result

    def test_bash_single_line(self):
        result = _tool_result_brief("bash", "hello world", True)
        assert result == "hello world"

    def test_bash_multi_line(self):
        result = _tool_result_brief("bash", "line1\nline2\nline3", True)
        assert "3 lines" in result

    def test_failure_result(self):
        result = _tool_result_brief("bash", "Error: command not found\nDetails here", False)
        assert "Error" in result

    def test_failure_long_truncated(self):
        long_error = "Error: " + "x" * 200
        result = _tool_result_brief("bash", long_error, False)
        assert len(result) <= 83  # 80 + "..."


# ---------------------------------------------------------------------------
# Path abbreviation
# ---------------------------------------------------------------------------

class TestAbbreviatePath:
    def test_empty_path(self):
        assert _abbreviate_path("") == ""

    def test_short_path(self):
        result = _abbreviate_path("/tmp/file.txt")
        assert "file.txt" in result

    def test_long_path_abbreviated(self):
        result = _abbreviate_path("/very/long/deeply/nested/path/file.txt")
        assert "..." in result or "file.txt" in result


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

class TestSlashCommands:
    def _make_mock_agent(self):
        agent = MagicMock()
        agent.config = MagicMock()
        agent.config.context_window = 200_000
        agent.config.max_tool_result_chars = 10_000
        agent.config.system_prompt = ""
        agent.tools = MagicMock()
        agent.tools.names.return_value = ["read", "write", "bash"]
        return agent

    def test_help_command(self):
        agent = self._make_mock_agent()
        tracker = TokenTracker()
        result = _handle_slash_command("/help", agent, tracker, False)
        assert result is True

    def test_quit_command(self):
        agent = self._make_mock_agent()
        tracker = TokenTracker()
        result = _handle_slash_command("/quit", agent, tracker, False)
        assert result is None  # None means quit

    def test_exit_command(self):
        agent = self._make_mock_agent()
        tracker = TokenTracker()
        result = _handle_slash_command("/exit", agent, tracker, False)
        assert result is None

    def test_q_command(self):
        agent = self._make_mock_agent()
        tracker = TokenTracker()
        result = _handle_slash_command("/q", agent, tracker, False)
        assert result is None

    def test_tools_command(self):
        agent = self._make_mock_agent()
        tracker = TokenTracker()
        result = _handle_slash_command("/tools", agent, tracker, False)
        assert result is True

    def test_cost_command(self):
        agent = self._make_mock_agent()
        tracker = TokenTracker()
        result = _handle_slash_command("/cost", agent, tracker, False)
        assert result is True

    def test_mode_command(self):
        agent = self._make_mock_agent()
        tracker = TokenTracker()
        result = _handle_slash_command("/mode", agent, tracker, False)
        assert result is True

    def test_unknown_command(self):
        agent = self._make_mock_agent()
        tracker = TokenTracker()
        result = _handle_slash_command("/bogus", agent, tracker, False)
        assert result is False

    def test_clear_resets_context(self):
        agent = self._make_mock_agent()
        tracker = TokenTracker()
        result = _handle_slash_command("/clear", agent, tracker, False)
        assert result is True


# ---------------------------------------------------------------------------
# TokenTracker
# ---------------------------------------------------------------------------

class TestTokenTracker:
    def test_initial_state(self):
        tracker = TokenTracker()
        assert tracker.total_input == 0
        assert tracker.total_output == 0
        assert tracker.total == 0

    def test_add_tokens(self):
        tracker = TokenTracker()
        tracker.add(100, 50)
        assert tracker.total_input == 100
        assert tracker.total_output == 50
        assert tracker.total == 150

    def test_cumulative_tokens(self):
        tracker = TokenTracker()
        tracker.add(100, 50)
        tracker.add(200, 100)
        assert tracker.total_input == 300
        assert tracker.total_output == 150
        assert tracker.total == 450

    def test_estimated_cost(self):
        tracker = TokenTracker(model="gpt-4o")
        tracker.add(1_000_000, 500_000)
        cost = tracker.estimated_cost
        assert cost > 0

    def test_format_empty(self):
        tracker = TokenTracker()
        assert tracker.format() == ""

    def test_format_with_tokens(self):
        tracker = TokenTracker(model="gpt-4o")
        tracker.add(500, 200)
        formatted = tracker.format()
        assert "tokens" in formatted
        assert "$" in formatted

    def test_format_thousands(self):
        tracker = TokenTracker()
        tracker.add(5000, 3000)
        formatted = tracker.format()
        assert "k tokens" in formatted

    def test_unknown_model_uses_default_rates(self):
        tracker = TokenTracker(model="unknown-model-xyz")
        tracker.add(1_000_000, 1_000_000)
        cost = tracker.estimated_cost
        assert cost > 0  # Should use default rates
