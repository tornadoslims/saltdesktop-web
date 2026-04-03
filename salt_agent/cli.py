#!/usr/bin/env python3
"""
SaltAgent CLI — a polished terminal interface for SaltAgent.

Usage:
    salt-agent "Create a hello world script"
    salt-agent -p openai -m gpt-4o-mini "Build a web scraper"
    salt-agent -i  # interactive mode
    salt-agent --help
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import glob as _glob_module
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import readline as _readline
except ImportError:
    _readline = None  # type: ignore[assignment]

from salt_agent.config import AgentConfig
from salt_agent.events import (
    AgentComplete,
    AgentError,
    SubagentComplete,
    SubagentSpawned,
    TextChunk,
    ToolEnd,
    ToolStart,
    ToolUse,
)

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# ANSI escape codes
# ---------------------------------------------------------------------------
_BLUE = "\033[34m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"
_CLEAR_LINE = "\033[2K\r"

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    """Wrap text in ANSI escape codes if color is enabled."""
    if not _USE_COLOR:
        return text
    return f"{code}{text}{_RESET}"


def _write(text: str) -> None:
    """Write to stdout and flush."""
    sys.stdout.write(text)
    sys.stdout.flush()


def _term_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


# ---------------------------------------------------------------------------
# Spinner
# ---------------------------------------------------------------------------
_SPINNER_FRAMES = "\\u280b\\u2819\\u2839\\u2838\\u283c\\u2834\\u2826\\u2827\\u2807\\u280f"
# Actual unicode braille spinner
_SPINNER = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]


_HEARTBEAT_MESSAGES = [
    "Thinking...",
    "Still thinking...",
    "Deep in thought...",
    "Working on it...",
]


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as (Xs) or (Xm Ys)."""
    s = int(seconds)
    if s < 60:
        return f"({s}s)"
    m, s = divmod(s, 60)
    return f"({m}m {s}s)"


class StatusBar:
    """Persistent status bar at the bottom of the terminal."""

    def __init__(self, agent):
        self.agent = agent
        self._visible = True

    def render(self) -> str:
        """Build the status bar text."""
        parts: list[str] = []

        # Permission mode
        if getattr(self.agent.config, "auto_mode", False):
            parts.append(f"{_RED}\u25b8\u25b8 auto mode{_RESET}")

        # Active tasks
        if hasattr(self.agent, "task_manager"):
            running = sum(
                1
                for t in self.agent.task_manager.list_tasks()
                if t.status.value == "running"
            )
            if running:
                word = "task" if running == 1 else "tasks"
                parts.append(f"{_CYAN}{running} background {word}{_RESET}")

        # Model
        model = self.agent.config.model
        provider = self.agent.config.provider
        if not model:
            model = _resolve_default_model(provider)
        parts.append(f"{_DIM}{_capitalize_provider(provider)}/{model}{_RESET}")

        # Hints
        parts.append(f"{_DIM}ctrl-c to interrupt \u00b7 /help for commands{_RESET}")

        return " \u00b7 ".join(parts)

    def draw(self) -> None:
        """Draw the status bar at the bottom of the terminal."""
        if not _USE_COLOR or not self._visible:
            return

        rows, cols = shutil.get_terminal_size()
        bar_text = self.render()

        # Save cursor, move to last line, clear it, write, restore cursor
        _write(f"\033[s\033[{rows};1H\033[2K  {bar_text}\033[u")

    def clear(self) -> None:
        """Remove the status bar."""
        if not _USE_COLOR:
            return
        rows, _ = shutil.get_terminal_size()
        _write(f"\033[s\033[{rows};1H\033[2K\033[u")


def _resolve_default_model(provider: str) -> str:
    """Resolve the default model name for a given provider."""
    try:
        if provider == "anthropic":
            from salt_agent.providers.anthropic import AnthropicAdapter
            return AnthropicAdapter.DEFAULT_MODEL
        elif provider == "openai":
            from salt_agent.providers.openai_provider import OpenAIAdapter
            return OpenAIAdapter.DEFAULT_MODEL
    except ImportError:
        pass
    return "(unknown)"


class Spinner:
    """Animated thinking spinner that runs in a background thread."""

    def __init__(self, message: str = "Thinking..."):
        self._message = message
        self._running = False
        self._thread: threading.Thread | None = None
        self._start_time: float = 0.0
        self._last_event_time: float = 0.0
        self._phase: str = "thinking"  # "thinking" or "tool"

    def start(self) -> None:
        if not _USE_COLOR:
            return
        if self._thread and self._running:
            return  # Already running
        self._running = True
        now = time.monotonic()
        if self._start_time == 0:
            self._start_time = now
        self._last_event_time = now
        self._phase = "thinking"
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running and self._thread is None:
            return  # Already stopped — don't write CLEAR_LINE again
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
            # Only clear the spinner line on the FIRST stop
            if _USE_COLOR:
                _write(_CLEAR_LINE)
            # Tiny settle so the terminal flushes the clear before the next
            # write (prevents flicker / partial line remnants).
            time.sleep(0.02)

    def note_event(self) -> None:
        """Record that an event was received (resets heartbeat timer)."""
        self._last_event_time = time.monotonic()

    @property
    def elapsed(self) -> float:
        """Seconds since the spinner was started."""
        if self._start_time == 0:
            return 0.0
        return time.monotonic() - self._start_time

    def _pick_message(self) -> str:
        """Pick a heartbeat message based on time since last event."""
        if self._phase != "thinking":
            return self._message
        silence = time.monotonic() - self._last_event_time
        idx = min(int(silence // 5), len(_HEARTBEAT_MESSAGES) - 1)
        return _HEARTBEAT_MESSAGES[idx]

    def _animate(self) -> None:
        idx = 0
        while self._running:
            frame = _SPINNER[idx % len(_SPINNER)]
            msg = self._pick_message()
            elapsed_str = _format_elapsed(self.elapsed)
            _write(f"{_CLEAR_LINE}  {_c(_DIM, f'{frame} {msg} {elapsed_str}')}")
            idx += 1
            time.sleep(0.08)


# ---------------------------------------------------------------------------
# Markdown renderer (ANSI, no dependencies)
# ---------------------------------------------------------------------------

def _highlight_python(code: str) -> str:
    """Basic Python syntax highlighting with ANSI."""
    # Keywords
    keywords = r'\b(def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|in|not|and|or|is|True|False|None|async|await|yield|raise|pass|break|continue|lambda)\b'
    code = re.sub(keywords, rf'{_BOLD}{_BLUE}\1{_RESET}', code)
    # Strings (simple -- single and double quotes, not multiline)
    code = re.sub(r'(\"[^\"]*\"|\'[^\']*\')', rf'{_GREEN}\1{_RESET}', code)
    # Comments
    code = re.sub(r'(#.*)$', rf'{_DIM}\1{_RESET}', code, flags=re.MULTILINE)
    # Numbers
    code = re.sub(r'\b(\d+\.?\d*)\b', rf'{_CYAN}\1{_RESET}', code)
    # Decorators
    code = re.sub(r'^(\s*@\w+)', rf'{_YELLOW}\1{_RESET}', code, flags=re.MULTILINE)
    return code


def _is_python_code(lang: str, code: str) -> bool:
    """Detect if a code block is Python."""
    if lang in ("python", "py", "python3"):
        return True
    if not lang and ("def " in code or "import " in code):
        return True
    return False


def render_markdown(text: str) -> str:
    """Convert markdown to ANSI-formatted terminal text."""
    if not _USE_COLOR:
        return text

    lines = text.split("\n")
    result: list[str] = []
    in_code_block = False
    code_lang = ""
    code_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Code block toggle
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_lang = line.strip()[3:].strip().lower()
                code_lines = []
                result.append("")  # blank line before code block
            else:
                # Closing fence -- render collected code block
                in_code_block = False
                raw_code = "\n".join(code_lines)
                if _is_python_code(code_lang, raw_code):
                    highlighted = _highlight_python(raw_code)
                    for hl in highlighted.split("\n"):
                        result.append(f"  {_DIM}\u2502{_RESET} {hl}")
                else:
                    for cl in code_lines:
                        result.append(f"  {_DIM}\u2502{_RESET} {_DIM}{cl}{_RESET}")
                code_lang = ""
                code_lines = []
                result.append("")  # blank line after code block
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # Headers
        header_match = re.match(r"^(#{1,3})\s+(.*)", line)
        if header_match:
            result.append(f"{_BOLD}{header_match.group(2)}{_RESET}")
            i += 1
            continue

        # Inline formatting
        line = _render_inline(line)
        result.append(line)
        i += 1

    return "\n".join(result)


def _render_inline(text: str) -> str:
    """Apply inline markdown formatting: bold, code spans."""
    if not _USE_COLOR:
        return text
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", rf"{_BOLD}\1{_RESET}", text)
    text = re.sub(r"__(.+?)__", rf"{_BOLD}\1{_RESET}", text)
    # Inline code: `text`
    text = re.sub(r"`([^`]+)`", rf"{_CYAN}\1{_RESET}", text)
    return text


# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------

def _resolve_api_key(provider: str, explicit_key: str = "") -> str:
    if explicit_key:
        return explicit_key

    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    env_var = env_map.get(provider, "")
    if env_var:
        key = os.environ.get(env_var, "")
        if key:
            return key

    for path in ["~/.openclaw/secrets.json", "~/.salt-agent/config.json"]:
        expanded = os.path.expanduser(path)
        if os.path.exists(expanded):
            try:
                with open(expanded) as f:
                    data = json.load(f)
                for key_name in [f"{provider}_key", f"{provider}_token", f"{provider}_api_key"]:
                    if key_name in data:
                        return data[key_name]
            except (json.JSONDecodeError, OSError):
                continue

    return ""


# ---------------------------------------------------------------------------
# Tool description helpers
# ---------------------------------------------------------------------------

def _tool_brief(name: str, tool_input: dict) -> str:
    """Return a short human-readable description of a tool call (Claude Code style)."""
    name_lower = name.lower()
    if name_lower == "bash":
        cmd = tool_input.get("command", "")
        if len(cmd) > 60:
            cmd = cmd[:57] + "..."
        return f"Bash {cmd}"
    if name_lower == "write":
        fp = tool_input.get("file_path", "")
        return f"Write {Path(fp).name}" if fp else "Write"
    if name_lower == "edit":
        fp = tool_input.get("file_path", "")
        return f"Edit {Path(fp).name}" if fp else "Edit"
    if name_lower == "read":
        fp = tool_input.get("file_path", "")
        return f"Read {Path(fp).name}" if fp else "Read"
    if name_lower == "glob":
        pat = tool_input.get("pattern", "")
        return f"Glob {pat}"
    if name_lower == "grep":
        pat = tool_input.get("pattern", "")
        if len(pat) > 40:
            pat = pat[:37] + "..."
        return f"Grep {pat}"
    if name_lower == "web_search":
        query = tool_input.get("query", "")
        if len(query) > 40:
            query = query[:37] + "..."
        return f"Search \"{query}\""
    if name_lower == "web_fetch":
        url = tool_input.get("url", "")
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            return f"Fetch {domain}"
        except Exception:
            return f"Fetch {url[:40]}"
    if name_lower == "todo_write":
        return "Update tasks"
    if name_lower == "agent":
        mode = tool_input.get("mode", "general")
        return f"Spawn {mode} agent"
    if name_lower in ("list_files", "listfiles"):
        p = tool_input.get("path", ".")
        return f"List {p}"
    if name_lower.startswith("task_"):
        action = name_lower.replace("task_", "")
        return f"Task {action}"
    # Default: capitalize and clean up underscores
    return name.replace("_", " ").title()


def _abbreviate_path(fp: str) -> str:
    """Abbreviate a file path: use basename if short, else abbreviate."""
    if not fp:
        return ""
    p = Path(fp)
    home = Path.home()
    try:
        rel = p.relative_to(home)
        return f"~/{rel}"
    except ValueError:
        pass
    # Just use the last 2 path components
    parts = p.parts
    if len(parts) <= 3:
        return str(p)
    return f".../{'/'.join(parts[-2:])}"


def _extract_first_def(text: str) -> str:
    """Extract the first function/class/import definition from text."""
    for line in text.split("\n"):
        stripped = line.strip()
        for prefix in ("def ", "class ", "import ", "from "):
            if stripped.startswith(prefix):
                snippet = stripped[:60]
                if len(stripped) > 60:
                    snippet += "..."
                return snippet
    # Fallback: first non-empty line
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            snippet = stripped[:60]
            if len(stripped) > 60:
                snippet += "..."
            return snippet
    return ""


def _parse_pytest_output(text: str) -> str | None:
    """Try to extract pytest summary from output."""
    # Look for "X passed" pattern
    m = re.search(r"(\d+) passed", text)
    if m:
        passed = m.group(1)
        failed_m = re.search(r"(\d+) failed", text)
        failed = failed_m.group(1) if failed_m else "0"
        # Look for timing
        time_m = re.search(r"in ([\d.]+)s", text)
        time_str = f" ({time_m.group(1)}s)" if time_m else ""
        return f"{passed} passed, {failed} failed{time_str}"
    return None


def _tool_result_brief(name: str, result: str, success: bool) -> str:
    """Return a brief one-line summary of a tool result (Claude Code style)."""
    if not success:
        # Show just the first line of the error
        first_line = result.strip().split("\n")[0][:80]
        if len(result.strip().split("\n")[0]) > 80:
            first_line = first_line[:77] + "..."
        return first_line

    result_stripped = result.strip()
    if not result_stripped:
        return "Done"

    name_lower = name.lower()

    if name_lower == "write":
        # Extract line count
        m = re.search(r"(\d+) lines?", result_stripped)
        if m:
            count = m.group(1)
        else:
            count = str(result_stripped.count("\n") + 1) if result_stripped else "?"
        word = "line" if count == "1" else "lines"
        return f"Wrote {count} {word}"

    if name_lower == "bash":
        # Show first meaningful line of output
        lines = [ln for ln in result_stripped.splitlines() if ln.strip()]
        if not lines:
            return "Done"
        # Check for pytest
        for ln in lines:
            if "passed" in ln or "failed" in ln:
                return ln.strip()[:80]
        if len(lines) == 1 and len(lines[0]) < 80:
            return lines[0]
        return f"{len(lines)} lines of output"

    if name_lower == "read":
        lines = result_stripped.count("\n") + 1
        word = "line" if lines == 1 else "lines"
        return f"{lines} {word}"

    if name_lower == "edit":
        return "Applied"

    if name_lower == "web_search":
        count = result_stripped.count("\n\n") + 1
        return f"{count} results"

    if name_lower == "web_fetch":
        chars = len(result_stripped)
        if chars > 1000:
            return f"{chars // 1000}K chars"
        return f"{chars} chars"

    if name_lower == "glob":
        count = len([ln for ln in result_stripped.splitlines() if ln.strip()])
        return f"{count} files"

    if name_lower == "grep":
        count = len([ln for ln in result_stripped.splitlines() if ln.strip()])
        return f"{count} matches"

    if name_lower in ("list_files", "listfiles"):
        count = len([ln for ln in result_stripped.splitlines() if ln.strip()])
        return f"{count} items"

    if name_lower == "todo_write":
        return result_stripped[:60]

    # Generic: first line, max 60 chars
    first = result_stripped.split("\n")[0][:60]
    if len(result_stripped.split("\n")[0]) > 60:
        first = first[:57] + "..."
    return first


# ---------------------------------------------------------------------------
# Token / cost tracking
# ---------------------------------------------------------------------------

class TokenTracker:
    """Track cumulative token usage and estimate cost."""

    # Rough cost per 1M tokens (input/output) for common models
    _COST_TABLE = {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-4.1-nano": (0.10, 0.40),
        "claude-sonnet-4-20250514": (3.00, 15.00),
        "claude-3-5-sonnet-20241022": (3.00, 15.00),
        "claude-3-haiku-20240307": (0.25, 1.25),
    }

    def __init__(self, model: str = ""):
        self.model = model
        self.total_input = 0
        self.total_output = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input += input_tokens
        self.total_output += output_tokens

    @property
    def total(self) -> int:
        return self.total_input + self.total_output

    @property
    def estimated_cost(self) -> float:
        rates = self._COST_TABLE.get(self.model, (2.50, 10.00))
        cost = (self.total_input / 1_000_000 * rates[0]) + (
            self.total_output / 1_000_000 * rates[1]
        )
        return cost

    def format(self) -> str:
        total = self.total
        if total == 0:
            return ""
        if total < 1000:
            tok_str = f"{total} tokens"
        else:
            tok_str = f"{total / 1000:.1f}k tokens"
        cost = self.estimated_cost
        return f"{tok_str} \u00b7 ${cost:.4f}"


# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------

def _format_time_ago(seconds: float) -> str:
    """Format seconds as a human-readable 'X ago' string."""
    if seconds < 60:
        return "just now"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _capitalize_provider(name: str) -> str:
    """Properly capitalize provider names: 'openai' -> 'OpenAI', 'anthropic' -> 'Anthropic'."""
    special = {"openai": "OpenAI", "anthropic": "Anthropic"}
    return special.get(name.lower(), name.capitalize())


def _print_banner(
    config: AgentConfig,
    tool_names: list[str],
    session_info: dict | None = None,
    mcp_servers: list[str] | None = None,
    skill_count: int = 0,
) -> None:
    """Print a compact startup banner box (~50 chars wide)."""
    home = os.path.expanduser("~")
    wd = os.path.abspath(config.working_directory)
    display_dir = wd.replace(home, "~") if wd.startswith(home) else wd

    # Add git branch if in a repo
    branch = _get_git_branch(config.working_directory)
    if branch:
        display_dir = f"{display_dir} ({branch})"

    model = config.model or _resolve_default_model(config.provider)
    provider_name = _capitalize_provider(config.provider)
    provider_display = f"{provider_name} \u00b7 {model}"

    tool_count = len(tool_names)

    # Build summary line: "31 tools · 2 skills · /help for commands"
    summary_parts = [f"{tool_count} tools"]
    if skill_count > 0:
        summary_parts.append(f"{skill_count} skills")
    summary_parts.append("/help for commands")
    summary_line = " \u00b7 ".join(summary_parts)

    # Fixed-width box (~48 inner width)
    BOX_WIDTH = 48

    # Content lines as (display_text, visual_width) tuples
    title = f"\U0001f9c2 SaltAgent v{__version__}"
    content_lines: list[tuple[str, int]] = [
        (title, len(title) + 1),  # +1 for emoji extra column width
        ("", 0),
        (f"Provider: {provider_display}", len(f"Provider: {provider_display}")),
        (f"Directory: {display_dir}", len(f"Directory: {display_dir}")),
        ("", 0),
        (summary_line, len(summary_line)),
    ]

    # Session resume indicator
    if session_info:
        turns = session_info.get("turns", 0)
        time_ago = session_info.get("time_ago", "")
        resume_text = f"\u21bb Resuming session ({turns} turns, {time_ago})"
        content_lines.append((resume_text, len(resume_text)))

    content_lines.append(("", 0))

    _write("\n")
    _write(f"{_c(_DIM, '\u256d' + '\u2500' * BOX_WIDTH + '\u256e')}\n")
    _write(f"{_c(_DIM, '\u2502')}{' ' * BOX_WIDTH}{_c(_DIM, '\u2502')}\n")

    for text, vis_width in content_lines:
        if not text:
            _write(f"{_c(_DIM, '\u2502')}{' ' * BOX_WIDTH}{_c(_DIM, '\u2502')}\n")
        else:
            padding = max(BOX_WIDTH - vis_width - 2, 0)
            display = text
            if text.startswith("\U0001f9c2"):
                display = _c(_BOLD, text)
            _write(f"{_c(_DIM, '\u2502')}  {display}{' ' * padding}{_c(_DIM, '\u2502')}\n")

    _write(f"{_c(_DIM, '\u2502')}{' ' * BOX_WIDTH}{_c(_DIM, '\u2502')}\n")
    _write(f"{_c(_DIM, '\u2570' + '\u2500' * BOX_WIDTH + '\u256f')}\n")
    _write("\n")


# ---------------------------------------------------------------------------
# Slash command handlers
# ---------------------------------------------------------------------------

_SLASH_COMMANDS = {
    # Session
    "/sessions": "List recent sessions with titles and dates",
    "/resume": "Resume a previous session: /resume [id]",
    "/history": "Show conversation summary",
    "/clear": "Clear conversation history",
    "/search": "Search past sessions: /search <query>",
    # Code
    "/commit": "Invoke the commit skill",
    "/review": "Invoke the review skill",
    "/diff": "Show git diff output",
    "/status": "Show git status output",
    "/branch": "Show current git branch",
    "/log": "Show last n git commits: /log [n]",
    "/stash": "Run git stash",
    "/undo": "Rewind file changes (uses file_history)",
    # Agent
    "/tasks": "List background tasks and their status",
    "/model": "Show/change current model: /model [name]",
    "/provider": "Show/change current provider: /provider [name]",
    "/tokens": "Show token usage stats",
    "/budget": "Show budget tracker stats",
    "/compact": "Force context compaction now",
    "/cost": "Show token usage this session",
    # Memory
    "/memory": "List memory files",
    "/memories": "List memory files",
    "/forget": "Delete a memory file: /forget <file>",
    # Mode
    "/auto": "Toggle auto mode (skip all permission prompts)",
    "/plan": "Enable plan mode (agent must plan before acting)",
    "/approve": "Approve plan and let agent proceed",
    "/verify": "Spawn verification specialist to review code",
    "/mode": "Show/change agent mode",
    "/coordinator": "Enter coordinator mode",
    # Utility
    "/doctor": "Run health checks",
    "/version": "Show version",
    "/config": "Get/set config: /config [key] [value]",
    "/export": "Export conversation as markdown",
    "/tools": "List available tools",
    "/skills": "List available skills",
    "/help": "Show available commands",
    "/quit": "Exit",
    # Development
    "/init": "Initialize SaltAgent in current directory",
    "/scaffold": "Create basic project structure (README, tests/, src/)",
    # Navigation
    "/cd": "Change working directory: /cd <path>",
    "/ls": "Quick directory listing: /ls [path]",
    "/cat": "Quick file view: /cat <file>",
    "/find": "Quick glob search: /find <pattern>",
    # Git (additional)
    "/pr": "Create a pull request via gh",
    "/merge": "Merge current branch into main",
    "/rebase": "Rebase current branch on main",
    "/amend": "Amend last commit with staged changes",
    # Agent control
    "/stop": "Stop all background tasks",
    "/retry": "Retry the last failed turn",
    "/continue": "Continue from where the agent stopped",
    "/redo": "Redo the last prompt",
    # Information
    "/context": "Show context window usage",
    "/state": "Show full agent state",
    "/debug": "Toggle verbose/debug mode",
    "/env": "Show relevant environment variables",
    # File management
    "/recent": "Show recently modified files",
    "/changed": "Show files changed in this session",
}


# ---------------------------------------------------------------------------
# Tab completion and persistent history
# ---------------------------------------------------------------------------

HISTORY_FILE = Path.home() / ".salt-agent" / "history"


class SlashCompleter:
    """Tab completion for slash commands and file paths."""

    def __init__(self, commands: list[str], agent=None):
        self.commands = sorted(commands)
        self.agent = agent
        self._matches: list[str] = []

    def complete(self, text: str, state: int) -> str | None:
        if state == 0:
            if text.startswith("/"):
                # Complete slash commands
                self._matches = [c for c in self.commands if c.startswith(text)]
                # Also check skill names if agent has a skill_manager
                if self.agent and hasattr(self.agent, "skill_manager"):
                    try:
                        skills = self.agent.skill_manager.list_user_invocable()
                        skill_cmds = ["/" + s.name for s in skills]
                        self._matches.extend(
                            c for c in skill_cmds
                            if c.startswith(text) and c not in self._matches
                        )
                    except Exception:
                        pass
                self._matches.sort()
            elif "/" in text or "." in text:
                # Complete file paths
                self._matches = self._path_complete(text)
            else:
                self._matches = []

        if state < len(self._matches):
            return self._matches[state]
        return None

    def _path_complete(self, text: str) -> list[str]:
        """Complete file paths."""
        results = _glob_module.glob(text + "*")
        # Append / for directories so the user can keep tabbing
        out: list[str] = []
        for r in results[:20]:
            if os.path.isdir(r):
                out.append(r + "/")
            else:
                out.append(r)
        return out


def _setup_readline(agent=None) -> None:
    """Configure readline: tab completion, persistent history, keybindings."""
    if _readline is None:
        return

    # --- Tab completion ---
    all_commands = list(_SLASH_COMMANDS.keys())
    completer = SlashCompleter(all_commands, agent)
    _readline.set_completer(completer.complete)
    _readline.set_completer_delims(" \t\n")

    # libedit (macOS) vs GNU readline use different bind syntax
    if "libedit" in (_readline.__doc__ or ""):
        _readline.parse_and_bind("bind ^I rl_complete")
    else:
        _readline.parse_and_bind("tab: complete")
        # GNU readline: up/down search history by prefix
        _readline.parse_and_bind('"\\e[A": history-search-backward')
        _readline.parse_and_bind('"\\e[B": history-search-forward')

    # --- Persistent history ---
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        _readline.read_history_file(str(HISTORY_FILE))
    except (FileNotFoundError, OSError):
        pass
    _readline.set_history_length(1000)
    atexit.register(_readline.write_history_file, str(HISTORY_FILE))


def _is_multiline_start(line: str) -> bool:
    """Return True if the line signals the start of a triple-backtick block."""
    return line.strip() == "```" or line.strip().startswith("```")


def _read_multiline_backtick() -> str:
    """Read lines until a closing ``` is encountered. Returns the content between fences."""
    lines: list[str] = []
    while True:
        try:
            cont_prompt = f"{_c(_DIM, '... ')}" if _USE_COLOR else "... "
            continuation = input(cont_prompt)
        except EOFError:
            break
        except KeyboardInterrupt:
            return ""
        if continuation.strip() == "```":
            break
        lines.append(continuation)
    return "\n".join(lines)


def _needs_continuation(line: str) -> bool:
    """Check if a line needs continuation (unbalanced quotes, trailing : { ()."""
    stripped = line.rstrip()
    if not stripped:
        return False
    # Trailing backslash (existing behavior)
    if stripped.endswith("\\"):
        return True
    # Unbalanced quotes
    single_count = stripped.count("'") - stripped.count("\\'")
    double_count = stripped.count('"') - stripped.count('\\"')
    if single_count % 2 != 0 or double_count % 2 != 0:
        return True
    return False


def _handle_slash_command(
    cmd: str,
    agent,
    tracker: TokenTracker,
    verbose: bool,
) -> bool | None:
    """Handle a slash command. Returns True if handled, None to quit, False if not a command."""
    parts = cmd.strip().split(None, 1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    # --- Quit ---
    if command in ("/quit", "/exit", "/q"):
        return None

    # --- Help (grouped by category) ---
    if command == "/help":
        _write("\n")
        _write(f"  {_c(_BOLD, 'Commands')}\n\n")
        categories = {
            "Session":  ["/sessions", "/resume", "/history", "/clear", "/search"],
            "Code":     ["/commit", "/review", "/diff", "/status", "/branch", "/log", "/stash", "/undo"],
            "Git":      ["/pr", "/merge", "/rebase", "/amend"],
            "Agent":    ["/tasks", "/model", "/provider", "/tokens", "/budget", "/compact", "/cost"],
            "Control":  ["/stop", "/retry", "/continue", "/redo"],
            "Navigate": ["/cd", "/ls", "/cat", "/find"],
            "Develop":  ["/init", "/scaffold"],
            "Info":     ["/context", "/state", "/debug", "/env", "/recent", "/changed"],
            "Memory":   ["/memory", "/forget", "/memories"],
            "Mode":     ["/auto", "/plan", "/approve", "/verify", "/coordinator", "/mode"],
            "Utility":  ["/doctor", "/version", "/config", "/export", "/skills", "/tools", "/help", "/quit"],
        }
        for cat, cmds in categories.items():
            _write(f"  {_c(_BOLD, cat):12s} {_c(_DIM, ' '.join(cmds))}\n")
        _write("\n")
        return True

    # --- Session commands ---
    if command == "/sessions":
        if agent.persistence:
            sessions = agent.persistence.list_sessions()
            if sessions:
                _write(f"\n  {_c(_BOLD, 'Recent Sessions')}\n\n")
                for s in sessions[:20]:
                    sid = s["session_id"][:12]
                    from datetime import datetime
                    try:
                        mtime = datetime.fromtimestamp(s["modified"])
                        ts = mtime.strftime("%Y-%m-%d %H:%M")
                    except (KeyError, TypeError, OSError):
                        ts = "unknown"
                    size_kb = s.get("size", 0) / 1024
                    _write(f"  {_c(_CYAN, sid)}  {_c(_DIM, ts)}  {_c(_DIM, f'{size_kb:.0f}KB')}\n")
            else:
                _write(f"\n  {_c(_DIM, 'No sessions found.')}\n")
            _write("\n")
        else:
            _write(f"\n  {_c(_DIM, 'Session persistence not enabled.')}\n\n")
        return True

    if command == "/resume":
        if agent.persistence:
            if arg:
                sessions = agent.persistence.list_sessions()
                match = None
                for s in sessions:
                    if s["session_id"].startswith(arg):
                        match = s
                        break
                if match:
                    import json as _json
                    try:
                        last_checkpoint = None
                        with open(match["path"]) as f:
                            for line in f:
                                entry = _json.loads(line.strip())
                                if entry.get("type") == "checkpoint":
                                    last_checkpoint = entry
                        if last_checkpoint and "messages" in last_checkpoint:
                            agent._conversation_messages = list(last_checkpoint["messages"])
                            sid = match["session_id"][:12]
                            _write(f"\n  {_c(_GREEN, f'Resumed session {sid}')}\n\n")
                        else:
                            _write(f"\n  {_c(_RED, 'No checkpoint found in that session.')}\n\n")
                    except Exception as e:
                        _write(f"\n  {_c(_RED, f'Failed to resume: {e}')}\n\n")
                else:
                    _write(f"\n  {_c(_RED, f'No session matching \"{arg}\"')}\n\n")
            else:
                checkpoint = agent.persistence.load_last_checkpoint()
                if checkpoint and "messages" in checkpoint:
                    agent._conversation_messages = list(checkpoint["messages"])
                    turns = len([m for m in checkpoint["messages"] if m.get("role") == "user"])
                    _write(f"\n  {_c(_GREEN, f'Resumed last session ({turns} turns)')}\n\n")
                else:
                    _write(f"\n  {_c(_DIM, 'No previous session to resume.')}\n\n")
        else:
            _write(f"\n  {_c(_DIM, 'Session persistence not enabled.')}\n\n")
        return True

    if command == "/history":
        msgs = getattr(agent, "_conversation_messages", [])
        if not msgs:
            _write(f"\n  {_c(_DIM, 'No conversation history.')}\n\n")
        else:
            _write(f"\n  {_c(_BOLD, 'Conversation Summary')}\n\n")
            user_count = 0
            assistant_count = 0
            tool_uses = 0
            for m in msgs:
                role = m.get("role", "")
                if role == "user":
                    user_count += 1
                elif role == "assistant":
                    assistant_count += 1
                content = m.get("content", "")
                if isinstance(content, list):
                    tool_uses += sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use")
            _write(f"  Messages: {len(msgs)} ({user_count} user, {assistant_count} assistant)\n")
            _write(f"  Tool uses: {tool_uses}\n")
            user_msgs = [m for m in msgs if m.get("role") == "user"]
            if user_msgs:
                _write(f"\n  {_c(_DIM, 'Recent prompts:')}\n")
                for m in user_msgs[-5:]:
                    content = m.get("content", "")
                    if isinstance(content, str):
                        preview = content[:80]
                        if len(content) > 80:
                            preview += "..."
                        _write(f"    {_c(_DIM, '>')} {preview}\n")
            _write("\n")
        return True

    if command == "/clear":
        from salt_agent.context import ContextManager
        agent.context = ContextManager(
            context_window=agent.config.context_window,
            max_tool_result_chars=agent.config.max_tool_result_chars,
        )
        if agent.config.system_prompt:
            agent.context.set_system(agent.config.system_prompt)
        agent.clear_conversation()
        _write(f"\n  {_c(_DIM, 'Context cleared.')}\n\n")
        return True

    if command == "/search":
        query = arg
        if not query:
            _write(f"\n  {_c(_DIM, 'Usage: /search <query>')}\n\n")
            return True
        if agent.persistence:
            results = agent.persistence.search_sessions(query)
            if results:
                _write(f"\n  {_c(_BOLD, f'Search results for \"{query}\"')}\n\n")
                for r in results:
                    ts = r.get("timestamp", "")[:19]
                    sid = r["session_id"][:12]
                    _write(f"  {_c(_CYAN, sid)} {_c(_DIM, ts)} [{r['type']}]\n")
                    preview = r["preview"][:120]
                    if len(r["preview"]) > 120:
                        preview += "..."
                    _write(f"    {_c(_DIM, preview)}\n")
            else:
                _write(f"\n  {_c(_DIM, f'No results for \"{query}\"')}\n")
            _write("\n")
        else:
            _write(f"\n  {_c(_DIM, 'Session persistence not enabled.')}\n\n")
        return True

    # --- Code commands (git) ---
    if command == "/diff":
        result = subprocess.run(
            ["git", "diff"], cwd=getattr(agent.config, "working_directory", "."),
            capture_output=True, text=True,
        )
        output = result.stdout or "No changes."
        _write(f"\n{output}\n\n")
        return True

    if command == "/status":
        result = subprocess.run(
            ["git", "status", "--short"], cwd=getattr(agent.config, "working_directory", "."),
            capture_output=True, text=True,
        )
        output = result.stdout or "Working tree clean."
        _write(f"\n{output}\n")
        return True

    if command == "/branch":
        result = subprocess.run(
            ["git", "branch", "--show-current"], cwd=getattr(agent.config, "working_directory", "."),
            capture_output=True, text=True,
        )
        branch = result.stdout.strip() or "unknown"
        _write(f"\n  Branch: {_c(_CYAN, branch)}\n\n")
        return True

    if command == "/log":
        n = "5"
        if arg and arg.strip().isdigit():
            n = arg.strip()
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            cwd=getattr(agent.config, "working_directory", "."),
            capture_output=True, text=True,
        )
        output = result.stdout or "No commits."
        _write(f"\n{output}\n")
        return True

    if command == "/stash":
        result = subprocess.run(
            ["git", "stash"], cwd=getattr(agent.config, "working_directory", "."),
            capture_output=True, text=True,
        )
        output = result.stdout.strip() or result.stderr.strip() or "Done."
        _write(f"\n  {output}\n\n")
        return True

    if command == "/undo":
        file_history = getattr(agent, "file_history", None)
        if file_history and hasattr(file_history, "undo_last"):
            try:
                undone = file_history.undo_last()
                if undone:
                    _write(f"\n  {_c(_GREEN, f'Undone: {undone}')}\n\n")
                else:
                    _write(f"\n  {_c(_DIM, 'Nothing to undo.')}\n\n")
            except Exception as e:
                _write(f"\n  {_c(_RED, f'Undo failed: {e}')}\n\n")
        else:
            _write(f"\n  {_c(_DIM, 'File history not available.')}\n\n")
        return True

    if command == "/commit":
        if hasattr(agent, "skill_manager"):
            try:
                content = agent.skill_manager.invoke("commit")
                if content:
                    _write(f"\n  {_c(_CYAN, 'Invoking commit skill...')}\n")
                    asyncio.run(_run_agent(agent, f"Follow these instructions:\n\n{content}", tracker=tracker))
                else:
                    _write(f"\n  {_c(_DIM, 'Commit skill not available.')}\n\n")
            except Exception as e:
                _write(f"\n  {_c(_RED, f'Commit failed: {e}')}\n\n")
        else:
            _write(f"\n  {_c(_DIM, 'Skill system not available.')}\n\n")
        return True

    if command == "/review":
        if hasattr(agent, "skill_manager"):
            try:
                content = agent.skill_manager.invoke("review")
                if content:
                    _write(f"\n  {_c(_CYAN, 'Invoking review skill...')}\n")
                    asyncio.run(_run_agent(agent, f"Follow these instructions:\n\n{content}", tracker=tracker))
                else:
                    _write(f"\n  {_c(_DIM, 'Review skill not available.')}\n\n")
            except Exception as e:
                _write(f"\n  {_c(_RED, f'Review failed: {e}')}\n\n")
        else:
            _write(f"\n  {_c(_DIM, 'Skill system not available.')}\n\n")
        return True

    # --- Agent commands ---
    if command == "/tasks":
        if hasattr(agent, "task_manager"):
            tasks = agent.task_manager.list_tasks()
            if not tasks:
                _write(f"\n  {_c(_DIM, 'No background tasks.')}\n\n")
            else:
                _write(f"\n  {_c(_BOLD, 'Background Tasks')}\n\n")
                for t in tasks:
                    status_color = {
                        "running": _CYAN,
                        "completed": _GREEN,
                        "failed": _RED,
                        "stopped": _YELLOW,
                        "pending": _DIM,
                    }.get(t.status.value, _DIM)
                    _write(f"  [{_c(_CYAN, t.id)}] {_c(status_color, t.status.value):20s}  {t.prompt[:60]}\n")
                _write("\n")
        else:
            _write(f"\n  {_c(_DIM, 'Task system not available.')}\n\n")
        return True

    if command == "/model":
        if arg:
            old_model = agent.config.model or _resolve_default_model(agent.config.provider)
            agent.config.model = arg
            # Recreate the provider with the new model
            try:
                agent.provider = agent._create_provider()
                _write(f"\n  Model changed: {_c(_DIM, old_model)} -> {_c(_CYAN, arg)}\n\n")
            except Exception as e:
                agent.config.model = old_model
                _write(f"\n  {_c(_RED, f'Failed to switch model: {e}')}\n\n")
        else:
            model = agent.config.model or _resolve_default_model(agent.config.provider)
            provider_name = _capitalize_provider(agent.config.provider)
            _write(f"\n  Provider: {_c(_CYAN, provider_name)}\n  Model: {_c(_CYAN, model)}\n\n")
        return True

    if command == "/provider":
        if arg:
            old_provider = agent.config.provider
            agent.config.provider = arg
            try:
                agent.provider = agent._create_provider()
                _write(f"\n  Provider changed: {_c(_DIM, _capitalize_provider(old_provider))} -> {_c(_CYAN, _capitalize_provider(arg))}\n\n")
            except Exception as e:
                agent.config.provider = old_provider
                _write(f"\n  {_c(_RED, f'Failed to switch provider: {e}')}\n\n")
        else:
            _write(f"\n  Provider: {_c(_CYAN, _capitalize_provider(agent.config.provider))}\n\n")
        return True

    if command == "/tokens":
        _write("\n")
        _write(f"  {_c(_BOLD, 'Token Usage')}\n\n")
        _write(f"  Input:  {tracker.total_input:,}\n")
        _write(f"  Output: {tracker.total_output:,}\n")
        _write(f"  Total:  {tracker.total:,}\n")
        cost = tracker.estimated_cost
        _write(f"  Est. cost: ${cost:.4f}\n")
        _write("\n")
        return True

    if command == "/budget":
        _write("\n")
        budget = getattr(agent, "budget", None)
        if budget and hasattr(budget, "total_tokens"):
            _write(f"  {_c(_BOLD, 'Budget Tracker')}\n\n")
            _write(f"  Total tokens: {budget.total_tokens:,}\n")
            if hasattr(budget, "total_input"):
                _write(f"  Input:  {budget.total_input:,}\n")
            if hasattr(budget, "total_output"):
                _write(f"  Output: {budget.total_output:,}\n")
            if hasattr(budget, "format"):
                _write(f"  {budget.format()}\n")
        else:
            _write(f"  {_c(_DIM, 'No budget data available.')}\n")
        _write("\n")
        return True

    if command == "/compact":
        try:
            from salt_agent.compaction import compact_context
            msgs = getattr(agent, "_conversation_messages", [])
            old_count = len(msgs)
            if old_count < 4:
                _write(f"\n  {_c(_DIM, 'Too few messages to compact.')}\n\n")
                return True
            system_prompt = getattr(agent.context, "system_prompt", "") or ""
            agent._conversation_messages = asyncio.run(compact_context(
                agent._conversation_messages, system_prompt,
                agent.config, agent.provider,
            ))
            new_count = len(agent._conversation_messages)
            _write(f"\n  Compacted: {old_count} messages -> {new_count} messages\n\n")
        except Exception as e:
            _write(f"\n  {_c(_RED, f'Compaction failed: {e}')}\n\n")
        return True

    if command == "/cost":
        _write("\n")
        _budget_shown = False
        try:
            budget = getattr(agent, "budget", None)
            if budget and hasattr(budget, "total_tokens") and budget.total_tokens > 0:
                info = budget.format()
                stats = budget.get_stats()
                _write(f"  {_c(_BOLD, 'Token Usage')}\n\n")
                _write(f"  {_c(_DIM, info)}\n")
                turn_count = stats["turns"]
                _write(f"  {_c(_DIM, f'Turns: {turn_count}')}\n")
                _budget_shown = True
        except (TypeError, AttributeError):
            pass
        if not _budget_shown:
            info = tracker.format()
            if info:
                _write(f"  {_c(_DIM, info)}\n")
            else:
                _write(f"  {_c(_DIM, 'No tokens used yet.')}\n")
        _write("\n")
        return True

    # --- Memory commands ---
    if command in ("/memory", "/memories"):
        memory = getattr(agent, "memory", None)
        if memory and hasattr(memory, "scan_memory_files"):
            files = memory.scan_memory_files()
            if files:
                _write(f"\n  {_c(_BOLD, 'Memory Files')}\n\n")
                for f in files:
                    name = f.get("filename", f.get("name", "unknown"))
                    mtype = f.get("type", "")
                    _write(f"  {_c(_CYAN, name)}")
                    if mtype:
                        _write(f"  {_c(_DIM, f'({mtype})')}")
                    _write("\n")
            else:
                _write(f"\n  {_c(_DIM, 'No memory files.')}\n")
            _write("\n")
        else:
            _write(f"\n  {_c(_DIM, 'Memory system not available.')}\n\n")
        return True

    if command == "/forget":
        if not arg:
            _write(f"\n  {_c(_DIM, 'Usage: /forget <filename>')}\n\n")
            return True
        memory = getattr(agent, "memory", None)
        if memory and hasattr(memory, "memory_dir"):
            target = memory.memory_dir / arg
            if target.exists():
                target.unlink()
                _write(f"\n  {_c(_GREEN, f'Deleted: {arg}')}\n\n")
            else:
                _write(f"\n  {_c(_RED, f'File not found: {arg}')}\n\n")
        else:
            _write(f"\n  {_c(_DIM, 'Memory system not available.')}\n\n")
        return True

    # --- Mode commands ---
    if command == "/auto":
        agent.config.auto_mode = not agent.config.auto_mode
        agent.permissions.auto_mode = agent.config.auto_mode
        status = "ON" if agent.config.auto_mode else "OFF"
        color = _GREEN if agent.config.auto_mode else _RED
        _write(f"\n  Auto mode: {_c(color, status)}\n\n")
        return True

    if command == "/plan":
        agent.config.plan_mode = True
        agent.permissions.plan_mode = True
        _write(f"\n  {_c(_YELLOW, 'Plan mode enabled.')} Agent must use todo_write to plan.\n")
        _write(f"  {_c(_DIM, 'Use /approve when ready to execute.')}\n\n")
        return True

    if command == "/approve":
        agent.config.plan_mode = False
        agent.permissions.plan_mode = False
        _write(f"\n  {_c(_GREEN, 'Plan approved.')} Agent can now execute tools.\n\n")
        return True

    if command == "/verify":
        _write(f"\n  {_c(_CYAN, 'Spawning verification specialist...')}\n")
        try:
            result = asyncio.run(
                agent.subagent_manager.spawn_fresh(
                    "Review all recent code changes. Run all tests. Report any issues, "
                    "bugs, or missing test coverage.",
                    mode="verify",
                    max_turns=15,
                )
            )
            output = result.get("result", "No findings.")
            _write(f"\n{render_markdown(output)}\n\n")
        except Exception as e:
            _write(f"\n  {_c(_RED, f'Verification failed: {e}')}\n\n")
        return True

    if command == "/mode":
        auto = getattr(agent.config, "auto_mode", False)
        plan = getattr(agent.config, "plan_mode", False)
        if plan:
            _write(f"\n  Mode: {_c(_YELLOW, 'plan')}\n\n")
        elif auto:
            _write(f"\n  Mode: {_c(_GREEN, 'auto')}\n\n")
        else:
            _write(f"\n  Mode: {_c(_DIM, 'default')}\n\n")
        return True

    if command == "/coordinator":
        agent.config.plan_mode = False
        if hasattr(agent.config, "coordinator_mode"):
            agent.config.coordinator_mode = True
        _write(f"\n  {_c(_CYAN, 'Coordinator mode enabled.')} Agent will orchestrate subagents.\n\n")
        return True

    # --- Utility commands ---
    if command == "/doctor":
        _write(f"\n  {_c(_BOLD, 'Health Check')}\n\n")
        _model = agent.config.model or _resolve_default_model(agent.config.provider)
        _write(f"  Provider: {_capitalize_provider(agent.config.provider)} ({_model})\n")
        _write(f"  Tools: {len(agent.tools.names())} registered\n")
        memory = getattr(agent, "memory", None)
        if memory and hasattr(memory, "scan_memory_files"):
            _write(f"  Memory: {len(memory.scan_memory_files())} files\n")
        else:
            _write(f"  Memory: not available\n")
        if agent.persistence:
            _write(f"  Sessions: {len(agent.persistence.list_sessions())}\n")
        else:
            _write(f"  Sessions: disabled\n")
        _write(f"  Working dir: {agent.config.working_directory}\n")
        _write("\n")
        return True

    if command == "/version":
        _write(f"\n  SaltAgent v{__version__}\n\n")
        return True

    if command == "/config":
        config_parts = arg.split(None, 1) if arg else []
        if len(config_parts) == 0:
            _write(f"\n  {_c(_BOLD, 'Configuration')}\n\n")
            for key in sorted(vars(agent.config)):
                if key.startswith("_") or key == "api_key":
                    continue
                val = getattr(agent.config, key)
                _write(f"  {_c(_CYAN, key)}: {val}\n")
            _write("\n")
        elif len(config_parts) == 1:
            key = config_parts[0]
            val = getattr(agent.config, key, None)
            if val is not None:
                _write(f"\n  {key} = {val}\n\n")
            else:
                _write(f"\n  {_c(_RED, f'Unknown config key: {key}')}\n\n")
        else:
            key, value = config_parts
            if hasattr(agent.config, key) and not key.startswith("_") and key != "api_key":
                old = getattr(agent.config, key)
                if isinstance(old, bool):
                    setattr(agent.config, key, value.lower() in ("true", "1", "yes"))
                elif isinstance(old, int):
                    setattr(agent.config, key, int(value))
                else:
                    setattr(agent.config, key, value)
                _write(f"\n  {key} = {getattr(agent.config, key)}\n\n")
            else:
                _write(f"\n  {_c(_RED, f'Cannot set: {key}')}\n\n")
        return True

    if command == "/export":
        msgs = getattr(agent, "_conversation_messages", [])
        if not msgs:
            _write(f"\n  {_c(_DIM, 'No conversation to export.')}\n\n")
            return True
        lines = []
        lines.append("# SaltAgent Conversation Export\n")
        for m in msgs:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, str):
                lines.append(f"## {role.title()}\n\n{content}\n")
            elif isinstance(content, list):
                text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                if text_parts:
                    lines.append(f"## {role.title()}\n\n{''.join(text_parts)}\n")
        export_text = "\n".join(lines)
        export_path = Path(agent.config.working_directory) / "conversation_export.md"
        export_path.write_text(export_text)
        _write(f"\n  Exported to: {_c(_CYAN, str(export_path))}\n\n")
        return True

    if command == "/tools":
        _write("\n")
        _write(f"  {_c(_BOLD, 'Available Tools')}\n\n")
        for name in sorted(agent.tools.names()):
            _write(f"  {_c(_CYAN, name)}\n")
        _write("\n")
        return True

    if command == "/skills":
        _write("\n")
        if hasattr(agent, "skill_manager"):
            skills = agent.skill_manager.list_user_invocable()
            if skills:
                _write(f"  {_c(_BOLD, 'Available Skills')}\n\n")
                for s in sorted(skills, key=lambda s: s.name):
                    desc = f" -- {s.description}" if s.description else ""
                    _write(f"  {_c(_CYAN, '/' + s.name):20s}  {_c(_DIM, desc)}\n")
            else:
                _write(f"  {_c(_DIM, 'No skills installed.')}\n")
        else:
            _write(f"  {_c(_DIM, 'Skill system not available.')}\n")
        _write("\n")
        return True

    # --- Development commands ---
    if command == "/init":
        init_dir = Path(agent.config.working_directory) / ".salt-agent"
        if init_dir.exists():
            _write(f"\n  {_c(_DIM, 'Already initialized (.salt-agent/ exists).')}\n\n")
        else:
            init_dir.mkdir(parents=True)
            (init_dir / "config.json").write_text("{}\n")
            _write(f"\n  {_c(_GREEN, 'Initialized .salt-agent/ in current directory.')}\n\n")
        return True

    if command == "/scaffold":
        wd = Path(agent.config.working_directory)
        created: list[str] = []
        for d in ["src", "tests"]:
            p = wd / d
            if not p.exists():
                p.mkdir(parents=True)
                (p / "__init__.py").write_text("")
                created.append(d + "/")
        readme = wd / "README.md"
        if not readme.exists():
            readme.write_text(f"# {wd.name}\n")
            created.append("README.md")
        if created:
            _write(f"\n  {_c(_GREEN, 'Created:')} {', '.join(created)}\n\n")
        else:
            _write(f"\n  {_c(_DIM, 'Project structure already exists.')}\n\n")
        return True

    # --- Navigation commands ---
    if command == "/cd":
        if not arg:
            _write(f"\n  {_c(_DIM, f'CWD: {agent.config.working_directory}')}\n\n")
            return True
        target = Path(arg).expanduser()
        if not target.is_absolute():
            target = Path(agent.config.working_directory) / target
        target = target.resolve()
        if target.is_dir():
            agent.config.working_directory = str(target)
            os.chdir(target)
            _write(f"\n  {_c(_GREEN, str(target))}\n\n")
        else:
            _write(f"\n  {_c(_RED, f'Not a directory: {target}')}\n\n")
        return True

    if command == "/ls":
        target = arg or agent.config.working_directory
        result = subprocess.run(
            ["ls", "-la", target],
            capture_output=True, text=True,
        )
        output = result.stdout or result.stderr or "Empty."
        _write(f"\n{output}\n")
        return True

    if command == "/cat":
        if not arg:
            _write(f"\n  {_c(_DIM, 'Usage: /cat <file>')}\n\n")
            return True
        target = Path(arg)
        if not target.is_absolute():
            target = Path(agent.config.working_directory) / target
        try:
            content = target.read_text()
            _write(f"\n{content}\n")
        except Exception as e:
            _write(f"\n  {_c(_RED, str(e))}\n\n")
        return True

    if command == "/find":
        if not arg:
            _write(f"\n  {_c(_DIM, 'Usage: /find <pattern>')}\n\n")
            return True
        matches = sorted(_glob_module.glob(
            os.path.join(agent.config.working_directory, "**", arg),
            recursive=True,
        ))[:30]
        if matches:
            wd = agent.config.working_directory
            for m in matches:
                rel = os.path.relpath(m, wd)
                _write(f"  {_c(_CYAN, rel)}\n")
        else:
            _write(f"\n  {_c(_DIM, 'No matches.')}\n")
        _write("\n")
        return True

    # --- Git additional commands ---
    if command == "/pr":
        wd = getattr(agent.config, "working_directory", ".")
        _write(f"\n  {_c(_CYAN, 'Creating pull request...')}\n")
        result = subprocess.run(
            ["gh", "pr", "create", "--fill"],
            cwd=wd, capture_output=True, text=True,
        )
        output = result.stdout.strip() or result.stderr.strip() or "Done."
        _write(f"  {output}\n\n")
        return True

    if command == "/merge":
        wd = getattr(agent.config, "working_directory", ".")
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"], cwd=wd,
            capture_output=True, text=True,
        )
        branch = branch_result.stdout.strip()
        if branch in ("main", "master"):
            _write(f"\n  {_c(_RED, 'Already on main branch.')}\n\n")
        else:
            result = subprocess.run(
                ["git", "merge", "main"], cwd=wd,
                capture_output=True, text=True,
            )
            output = result.stdout.strip() or result.stderr.strip() or "Done."
            _write(f"\n  {output}\n\n")
        return True

    if command == "/rebase":
        wd = getattr(agent.config, "working_directory", ".")
        result = subprocess.run(
            ["git", "rebase", "main"], cwd=wd,
            capture_output=True, text=True,
        )
        output = result.stdout.strip() or result.stderr.strip() or "Done."
        _write(f"\n  {output}\n\n")
        return True

    if command == "/amend":
        wd = getattr(agent.config, "working_directory", ".")
        result = subprocess.run(
            ["git", "commit", "--amend", "--no-edit"], cwd=wd,
            capture_output=True, text=True,
        )
        output = result.stdout.strip() or result.stderr.strip() or "Done."
        _write(f"\n  {output}\n\n")
        return True

    # --- Agent control commands ---
    if command == "/stop":
        if hasattr(agent, "task_manager"):
            stopped = 0
            for t in agent.task_manager.list_tasks():
                if t.status.value == "running":
                    agent.task_manager.cancel_task(t.id)
                    stopped += 1
            _write(f"\n  {_c(_YELLOW, f'Stopped {stopped} task(s).')}\n\n")
        else:
            _write(f"\n  {_c(_DIM, 'No task manager available.')}\n\n")
        return True

    if command == "/retry":
        msgs = getattr(agent, "_conversation_messages", [])
        last_user = None
        for m in reversed(msgs):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, str) and content.strip():
                    last_user = content
                    break
        if last_user:
            _write(f"\n  {_c(_CYAN, 'Retrying last prompt...')}\n")
            asyncio.run(_run_agent(agent, last_user, tracker=tracker))
        else:
            _write(f"\n  {_c(_DIM, 'No previous prompt to retry.')}\n\n")
        return True

    if command == "/continue":
        _write(f"\n  {_c(_CYAN, 'Continuing...')}\n")
        asyncio.run(_run_agent(agent, "Continue from where you left off.", tracker=tracker))
        return True

    if command == "/redo":
        msgs = getattr(agent, "_conversation_messages", [])
        last_user = None
        for m in reversed(msgs):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, str) and content.strip():
                    last_user = content
                    break
        if last_user:
            # Remove the last assistant+user exchange to truly redo
            while msgs and msgs[-1].get("role") != "user":
                msgs.pop()
            if msgs:
                msgs.pop()  # remove the user message itself
            _write(f"\n  {_c(_CYAN, 'Redoing last prompt...')}\n")
            asyncio.run(_run_agent(agent, last_user, tracker=tracker))
        else:
            _write(f"\n  {_c(_DIM, 'No previous prompt to redo.')}\n\n")
        return True

    # --- Information commands ---
    if command == "/context":
        msgs = getattr(agent, "_conversation_messages", [])
        # Rough estimate: ~4 chars per token
        total_chars = sum(
            len(json.dumps(m.get("content", ""))) for m in msgs
        )
        est_tokens = total_chars // 4
        window = getattr(agent.context, "context_window", 200_000)
        pct = (est_tokens / window * 100) if window else 0
        _write(f"\n  {_c(_BOLD, 'Context Window')}\n\n")
        _write(f"  Messages:  {len(msgs)}\n")
        _write(f"  Est. tokens: {est_tokens:,} / {window:,}\n")
        bar_len = 30
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        color = _GREEN if pct < 50 else (_YELLOW if pct < 80 else _RED)
        _write(f"  Usage: {_c(color, f'{bar} {pct:.1f}%')}\n")
        _write("\n")
        return True

    if command == "/state":
        state = getattr(agent, "state", None)
        if state and hasattr(state, "state"):
            from dataclasses import asdict
            d = asdict(state.state)
            _write(f"\n  {_c(_BOLD, 'Agent State')}\n\n")
            for k, v in sorted(d.items()):
                if isinstance(v, list) and len(v) > 5:
                    v = f"[{len(v)} items]"
                _write(f"  {_c(_CYAN, k):30s}: {v}\n")
            _write("\n")
        else:
            _write(f"\n  {_c(_DIM, 'State store not available.')}\n\n")
        return True

    if command == "/debug":
        # Toggle verbose on the agent config
        current = getattr(agent.config, "verbose", False)
        agent.config.verbose = not current
        status = "ON" if agent.config.verbose else "OFF"
        color = _GREEN if agent.config.verbose else _RED
        _write(f"\n  Debug mode: {_c(color, status)}\n\n")
        return True

    if command == "/env":
        _write(f"\n  {_c(_BOLD, 'Environment')}\n\n")
        env_keys = [
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "SALT_AGENT_MODEL",
            "SALT_AGENT_PROVIDER", "SALT_AGENT_HOME", "SHELL", "EDITOR",
            "HOME", "PATH", "VIRTUAL_ENV", "NO_COLOR",
        ]
        for key in env_keys:
            val = os.environ.get(key)
            if val:
                # Mask API keys
                if "API_KEY" in key or "SECRET" in key:
                    display = val[:8] + "..." + val[-4:] if len(val) > 16 else "***"
                elif key == "PATH":
                    display = val[:80] + "..." if len(val) > 80 else val
                else:
                    display = val
                _write(f"  {_c(_CYAN, key):30s}: {display}\n")
        _write("\n")
        return True

    # --- File management commands ---
    if command == "/recent":
        wd = agent.config.working_directory
        result = subprocess.run(
            ["find", wd, "-maxdepth", "3", "-type", "f",
             "-not", "-path", "*/.git/*", "-not", "-path", "*/__pycache__/*",
             "-not", "-path", "*/.venv/*", "-not", "-path", "*/node_modules/*"],
            capture_output=True, text=True,
        )
        if result.stdout:
            files = result.stdout.strip().split("\n")
            # Sort by mtime
            timed = []
            for f in files:
                try:
                    timed.append((os.path.getmtime(f), f))
                except OSError:
                    pass
            timed.sort(reverse=True)
            _write(f"\n  {_c(_BOLD, 'Recently Modified')}\n\n")
            for mtime, fpath in timed[:15]:
                from datetime import datetime
                ts = datetime.fromtimestamp(mtime).strftime("%H:%M:%S")
                rel = os.path.relpath(fpath, wd)
                _write(f"  {_c(_DIM, ts)}  {rel}\n")
        else:
            _write(f"\n  {_c(_DIM, 'No files found.')}\n")
        _write("\n")
        return True

    if command == "/changed":
        state = getattr(agent, "state", None)
        written: list[str] = []
        if state and hasattr(state, "state"):
            written = list(state.state.files_written or [])
        fh = getattr(agent, "file_history", None)
        if fh and hasattr(fh, "tracked_files"):
            written = list(set(written) | set(fh.tracked_files()))
        if written:
            _write(f"\n  {_c(_BOLD, 'Files Changed This Session')}\n\n")
            for f in sorted(written):
                _write(f"  {_c(_CYAN, f)}\n")
        else:
            _write(f"\n  {_c(_DIM, 'No files changed this session.')}\n")
        _write("\n")
        return True

    return False


# ---------------------------------------------------------------------------
# Event rendering
# ---------------------------------------------------------------------------

def _format_file_tree(file_list: list[str]) -> list[str]:
    """Format a list of file paths as a tree with box-drawing characters."""
    lines = []
    for i, f in enumerate(file_list):
        is_last = i == len(file_list) - 1
        prefix = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
        lines.append(f"      {prefix}{f}")
    return lines


def _edit_colored_summary(tool_input: dict, result: str) -> str | None:
    """Return a colored old/new summary for edit tool results."""
    result_stripped = result.strip()
    occ_m = re.search(r"replaced (\d+) occurrence", result_stripped)
    if not occ_m:
        return None
    count = occ_m.group(1)
    old_str = tool_input.get("old_string", "")
    new_str = tool_input.get("new_string", "")
    if not old_str or not new_str:
        return None
    # Truncate for display
    old_preview = old_str.split("\n")[0][:30]
    new_preview = new_str.split("\n")[0][:30]
    if len(old_str.split("\n")[0]) > 30:
        old_preview += "..."
    if len(new_str.split("\n")[0]) > 30:
        new_preview += "..."
    return f'{count} edit — {_RED}\u207b{old_preview}{_RESET} {_GREEN}\u207a{new_preview}{_RESET}'


def _render_event(
    event,
    *,
    verbose: bool = False,
    spinner: Spinner | None = None,
    tracker: TokenTracker | None = None,
    text_started: list[bool] | None = None,
    tool_count: list[int] | None = None,
    last_tool_input: dict | None = None,
    indent: str = "",
) -> None:
    """Render a single agent event to the terminal.

    *indent* is prepended to every output line -- used to visually nest
    subagent events under the parent's tool call.
    """

    # Notify spinner of activity (resets heartbeat timer)
    if spinner:
        spinner.note_event()

    if isinstance(event, TextChunk):
        if spinner:
            spinner.stop()
        if text_started is not None and not text_started[0]:
            _write("\n")
            text_started[0] = True
        # Render markdown inline - accumulate would be better but chunk-by-chunk
        # works for streaming. We apply inline formatting to each chunk.
        rendered = _render_inline(event.text)
        if indent:
            # For subagent text, only indent at the very start or after newlines
            rendered = rendered.replace("\n", f"\n{indent}")
            # Only write prefix if this is a fresh line
        _write(rendered)

    elif isinstance(event, ToolStart):
        if spinner:
            spinner.stop()
        if tool_count is not None:
            tool_count[0] += 1
        # Stash tool_input for use in ToolEnd
        if last_tool_input is not None:
            last_tool_input.clear()
            last_tool_input.update({"_name": event.tool_name, **event.tool_input})
        brief = _tool_brief(event.tool_name, event.tool_input)
        _write(f"\n{indent}  {_c(_CYAN, f'\u26a1 {brief}')}\n")
        if verbose:
            for k, v in event.tool_input.items():
                val = str(v)
                if len(val) > 120:
                    val = val[:117] + "..."
                _write(f"{indent}    {_c(_DIM, f'{k}: {val}')}\n")

    elif isinstance(event, ToolEnd):
        name_lower = event.tool_name.lower()

        # Colored edit summary
        if name_lower in ("edit", "multi_edit") and event.success and last_tool_input:
            colored = _edit_colored_summary(last_tool_input, event.result)
            if colored:
                _write(f"{indent}    {_c(_DIM, '\u2713')} {colored}\n")
            else:
                summary = _tool_result_brief(event.tool_name, event.result, event.success)
                _write(f"{indent}    {_c(_DIM + _GREEN, f'\u2713 {summary}')}\n")
        elif event.success:
            summary = _tool_result_brief(event.tool_name, event.result, event.success)
            _write(f"{indent}    {_c(_DIM + _GREEN, f'\u2713 {summary}')}\n")
        else:
            summary = _tool_result_brief(event.tool_name, event.result, event.success)
            _write(f"{indent}    {_c(_RED, f'\u2717 {summary}')}\n")

        # Verbose: show file tree for list_files, or raw output for others
        if verbose and event.result.strip():
            if name_lower in ("list_files", "listfiles") and event.success:
                file_list = [l for l in event.result.strip().split("\n") if l.strip()]
                tree = _format_file_tree(file_list)
                for tl in tree:
                    _write(f"{indent}    {_c(_DIM, tl)}\n")
            else:
                for line in event.result.strip().splitlines()[:10]:
                    _write(f"{indent}    {_c(_DIM, f'  {line}')}\n")
                if len(event.result.strip().splitlines()) > 10:
                    _write(f"{indent}    {_c(_DIM, f'  ... ({len(event.result.strip().splitlines())} lines)')}\n")
        # Don't restart spinner — it erases streaming text
        # The spinner only runs while waiting for the first response

    elif isinstance(event, AgentError):
        if spinner:
            spinner.stop()
        if event.recoverable:
            _write(f"\n{indent}  {_c(_YELLOW, f'\u274c {event.error}')}\n")
        else:
            _write(f"\n{indent}  {_c(_RED, f'\u274c {event.error}')}\n")

    elif isinstance(event, SubagentSpawned):
        if spinner:
            spinner.stop()
        _write(f"\n{indent}    {_c(_DIM, f'-> Spawning {event.mode} subagent...')}\n")

    elif isinstance(event, SubagentComplete):
        _write(f"{indent}    {_c(_DIM, f'-> Subagent complete')}\n")

    elif isinstance(event, AgentComplete):
        if tracker:
            # Estimate tokens from text length (rough heuristic when not provided by API)
            text_len = len(event.final_text) if event.final_text else 0
            # Very rough: ~4 chars per token
            estimated_output = max(text_len // 4, 50)
            estimated_input = estimated_output * 3  # input usually larger
            tracker.add(estimated_input, estimated_output)


def _print_event_json(event) -> None:
    """Print event as JSON line."""
    obj = {"type": event.type}
    if isinstance(event, TextChunk):
        obj["text"] = event.text
    elif isinstance(event, ToolStart):
        obj["tool_name"] = event.tool_name
        obj["tool_input"] = event.tool_input
    elif isinstance(event, ToolEnd):
        obj["tool_name"] = event.tool_name
        obj["result"] = event.result
        obj["success"] = event.success
    elif isinstance(event, AgentComplete):
        obj["final_text"] = event.final_text
        obj["turns"] = event.turns
        obj["tools_used"] = event.tools_used
    elif isinstance(event, AgentError):
        obj["error"] = event.error
        obj["recoverable"] = event.recoverable
    print(json.dumps(obj), flush=True)


# ---------------------------------------------------------------------------
# Cost display
# ---------------------------------------------------------------------------

def _print_cost_line(tracker: TokenTracker) -> None:
    """Print right-aligned cost/token summary."""
    info = tracker.format()
    if not info:
        return
    width = _term_width()
    padding = max(width - len(info) - 2, 0)
    _write(f"{' ' * padding}{_c(_DIM, info)}\n")


def _print_completion_summary(
    elapsed: float,
    tool_calls: int,
    tracker: TokenTracker | None,
) -> None:
    """Print a compact dim completion summary line (left-aligned, concise)."""
    parts: list[str] = []

    # Elapsed time
    secs = int(elapsed)
    if secs < 60:
        parts.append(f"{secs}s")
    else:
        m, s = divmod(secs, 60)
        parts.append(f"{m}m {s}s")

    # Tool calls
    if tool_calls > 0:
        parts.append(f"{tool_calls} tool{'s' if tool_calls != 1 else ''}")

    # Tokens (no cost if negligible)
    if tracker and tracker.total > 0:
        if tracker.total < 1000:
            parts.append(f"{tracker.total} tokens")
        else:
            parts.append(f"{tracker.total / 1000:.1f}k tokens")
        cost = tracker.estimated_cost
        if cost >= 0.01:
            parts.append(f"${cost:.3f}")

    summary = " \u00b7 ".join(parts)
    _write(f"\n  {_c(_DIM, summary)}\n")


# ---------------------------------------------------------------------------
# Run agent (one-shot or single turn)
# ---------------------------------------------------------------------------

async def _run_agent(
    agent,
    prompt: str,
    *,
    verbose: bool = False,
    json_mode: bool = False,
    tracker: TokenTracker | None = None,
    show_spinner: bool = True,
) -> None:
    if json_mode:
        async for event in agent.run(prompt):
            _print_event_json(event)
        return

    spinner = Spinner("Thinking...") if show_spinner and _USE_COLOR else None
    text_started = [False]
    tool_count = [0]
    last_tool_input: dict = {}
    run_start = time.monotonic()

    if spinner:
        spinner.start()

    try:
        async for event in agent.run(prompt):
            _render_event(
                event,
                verbose=verbose,
                spinner=spinner,
                tracker=tracker,
                text_started=text_started,
                tool_count=tool_count,
                last_tool_input=last_tool_input,
            )
    finally:
        if spinner:
            spinner.stop()

    # End with newline if text was streamed
    if text_started[0]:
        _write("\n")

    # Sync real token data from the agent's budget tracker to the CLI tracker
    try:
        budget = getattr(agent, "budget", None)
        if tracker and budget and hasattr(budget, "total_tokens") and budget.total_tokens > 0:
            tracker.total_input = budget.total_input
            tracker.total_output = budget.total_output
    except (TypeError, AttributeError):
        pass

    # Show completion summary line (skip for empty responses)
    elapsed = time.monotonic() - run_start
    if text_started[0] or tool_count[0] > 0:
        _print_completion_summary(elapsed, tool_count[0], tracker)


def _get_git_branch(cwd: str) -> str:
    """Return the current git branch name, or empty string if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd, capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

async def _interactive(
    agent,
    *,
    verbose: bool = False,
    json_mode: bool = False,
) -> None:
    # Check for persisted session
    session_info = None
    if agent.persistence:
        try:
            checkpoint = agent.persistence.load_last_checkpoint()
            if checkpoint:
                messages = checkpoint.get("messages", [])
                turns = len([m for m in messages if m.get("role") == "user"])
                ts = checkpoint.get("timestamp", "")
                if ts:
                    from datetime import datetime, timezone
                    try:
                        saved_at = datetime.fromisoformat(ts)
                        now = datetime.now(timezone.utc)
                        if saved_at.tzinfo is None:
                            saved_at = saved_at.replace(tzinfo=timezone.utc)
                        elapsed = (now - saved_at).total_seconds()
                        time_ago = _format_time_ago(elapsed)
                    except (ValueError, TypeError):
                        time_ago = ""
                else:
                    time_ago = ""
                if turns > 0:
                    session_info = {"turns": turns, "time_ago": time_ago}
        except Exception:
            pass  # Don't let persistence errors break startup

    # Register diff preview hook for edit tools
    def _diff_preview_hook(data: dict):
        """Show a diff preview before edit/multi_edit and ask for confirmation."""
        from salt_agent.hooks import HookResult
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})
        if tool_name in ("edit", "multi_edit") and not agent.config.auto_mode:
            old = tool_input.get("old_string", "")
            new = tool_input.get("new_string", "")
            fp = tool_input.get("file_path", "")
            if old and new:
                _write(f"\n  {_c(_BOLD, f'Diff preview: {_abbreviate_path(fp)}')}\n")
                for line in old.splitlines()[:5]:
                    preview = line[:100]
                    _write(f"  {_c(_RED, f'- {preview}')}\n")
                if len(old.splitlines()) > 5:
                    _write(f"  {_c(_RED, f'  ... ({len(old.splitlines())} lines)')}\n")
                for line in new.splitlines()[:5]:
                    preview = line[:100]
                    _write(f"  {_c(_GREEN, f'+ {preview}')}\n")
                if len(new.splitlines()) > 5:
                    _write(f"  {_c(_GREEN, f'  ... ({len(new.splitlines())} lines)')}\n")
                try:
                    response = input("  Apply? [Y/n] ")
                    if response.strip().lower() == "n":
                        return HookResult(action="block", reason="User rejected edit")
                except (EOFError, KeyboardInterrupt):
                    return HookResult(action="block", reason="User cancelled")
        return None

    agent.hooks.on("pre_tool_use", _diff_preview_hook)

    # Print banner
    tool_names = sorted(agent.tools.names())
    mcp_servers = agent.mcp_manager.server_names if agent.mcp_manager and agent.mcp_manager.is_started else None
    skill_count = len(agent.skill_manager.list_user_invocable()) if hasattr(agent, 'skill_manager') and agent.skill_manager else 0
    _print_banner(agent.config, tool_names, session_info=session_info, mcp_servers=mcp_servers, skill_count=skill_count)

    tracker = TokenTracker(model=agent.config.model)

    # Persistent status bar
    status_bar = StatusBar(agent)

    # Enable readline: tab completion, persistent history, keybindings
    _setup_readline(agent)

    # Build prompt prefix
    home = os.path.expanduser("~")
    wd = os.path.abspath(agent.config.working_directory)
    display_dir = wd.replace(home, "~") if wd.startswith(home) else wd

    # Session title (updated after first turn if persistence provides it)
    _session_title: list[str | None] = [None]

    _last_interrupt: float = 0.0

    # Task completion notification queue
    _completed_tasks: list = []

    def _task_completed_callback(task):
        _completed_tasks.append(task)

    if hasattr(agent, "task_manager"):
        agent.task_manager.on_complete(_task_completed_callback)

    while True:
        # Show any task completion notifications
        while _completed_tasks:
            t = _completed_tasks.pop(0)
            status_color = _GREEN if t.status.value == "completed" else _RED
            _write(f"\n  {_c(_DIM, 'Task')} {_c(_CYAN, t.id)} {_c(status_color, t.status.value)} -- \"{t.prompt[:60]}\"\n")

        # Draw status bar before prompt
        status_bar.draw()

        try:
            auto_indicator = f" {_c(_YELLOW, 'AUTO')}" if agent.config.auto_mode else ""
            branch = _get_git_branch(agent.config.working_directory)
            branch_str = f" {_c(_DIM, f'({branch})')}" if branch else ""
            # Session title in prompt (Feature 5)
            title_str = ""
            if _session_title[0]:
                short_title = _session_title[0][:30]
                if len(_session_title[0]) > 30:
                    short_title += "..."
                title_str = f" {_c(_DIM, chr(0xB7))} {_c(_DIM, short_title)}" if _USE_COLOR else f" - {short_title}"
            prompt_str = f"{_c(_CYAN, display_dir)}{branch_str}{title_str}{auto_indicator} {_c(_DIM, '>')} " if _USE_COLOR else f"{display_dir}{f' ({branch})' if branch else ''}{title_str}{' AUTO' if agent.config.auto_mode else ''} > "
            line = input(prompt_str)
        except EOFError:
            _write(f"\n{_c(_DIM, 'Goodbye!')}\n")
            return
        except KeyboardInterrupt:
            _write("\n")  # Clear the ^C, show fresh prompt (like Claude Code)
            continue

        # Multi-line support: triple-backtick block
        if line.strip() == "```":
            line = _read_multiline_backtick()
            if not line:
                continue
        else:
            # Legacy: lines ending with backslash, or unbalanced quotes
            while _needs_continuation(line):
                if line.endswith("\\"):
                    line = line[:-1]
                try:
                    cont_prompt = f"{_c(_DIM, '... >')} " if _USE_COLOR else "... > "
                    continuation = input(cont_prompt)
                    line = line + "\n" + continuation
                except EOFError:
                    break
                except KeyboardInterrupt:
                    _write("\n")
                    line = ""
                    break

        line = line.strip()
        if not line:
            continue

        # Input classification (Claude Code pattern: classify before processing)
        # Only treat as slash command if the first word is a registered command
        # File paths like /Users/... are treated as regular prompts
        if line.startswith("/"):
            first_word = line.split()[0] if line.split() else line
            known_commands = set(_SLASH_COMMANDS.keys()) | {"/q", "/exit"}
            # Some commands take arguments -- match by prefix
            if first_word in known_commands:
                result = _handle_slash_command(line, agent, tracker, verbose)
                if result is None:
                    _write(f"{_c(_DIM, 'Goodbye!')}\n")
                    return
                if result:
                    continue

            # Check if it's a skill invocation (e.g., /commit, /review)
            skill_name = first_word[1:]  # strip leading /
            if hasattr(agent, "skill_manager"):
                skill = agent.skill_manager.get(skill_name)
                if skill and skill.user_invocable:
                    # Inject skill content as user prompt
                    skill_content = agent.skill_manager.invoke(skill_name)
                    _write(f"\n  {_c(_CYAN, f'Invoking skill: {skill_name}')}\n")
                    line = f"<skill-invocation name=\"{skill_name}\">\n{skill_content}\n</skill-invocation>"
                    # Fall through to run the agent with this as the prompt

            # Not a known command or skill — treat as regular prompt (e.g., file path)

        # Clear status bar before running agent (avoid overlap with output)
        status_bar.clear()

        # Run agent
        try:
            await _run_agent(
                agent,
                line,
                verbose=verbose,
                json_mode=json_mode,
                tracker=tracker,
            )
        except KeyboardInterrupt:
            _write(f"\n  {_c(_YELLOW, 'Cancelled.')}\n\n")
            continue
        except asyncio.CancelledError:
            _write(f"\n  {_c(_YELLOW, 'Cancelled.')}\n\n")
            continue
        except Exception as e:
            err_msg = str(e)
            width = _term_width() - 6  # indent + margin
            if width > 20 and len(err_msg) > width:
                import textwrap
                wrapped = textwrap.fill(err_msg, width=width)
                _write(f"\n  {_c(_RED, f'\u274c {wrapped}')}\n\n")
            else:
                _write(f"\n  {_c(_RED, f'\u274c {err_msg}')}\n\n")
            continue

        # Update session title from persistence (Feature 5)
        if _session_title[0] is None and agent.persistence:
            try:
                title = getattr(agent.persistence, "session_title", None)
                if callable(title):
                    title = title()
                if title:
                    _session_title[0] = title
            except Exception:
                pass

        # Show follow-up suggestions only if enabled in config
        if getattr(agent.config, 'show_suggestions', False):
            if hasattr(agent, 'stop_hooks') and hasattr(agent.stop_hooks, 'last_suggestions'):
                suggestions = agent.stop_hooks.last_suggestions
                if suggestions:
                    _write(f"\n  {_c(_DIM, 'Suggestions:')}\n")
                    for s in suggestions:
                        _write(f"    {_c(_DIM, f'→ {s}')}\n")
                    _write("\n")

        _write("\n")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="salt-agent",
        description="SaltAgent -- a general-purpose AI agent for the terminal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  salt-agent "Create a hello world script"
  salt-agent -p openai -m gpt-4o-mini "Build a REST API"
  salt-agent -i                            # interactive mode
  salt-agent -i -d ~/projects/myapp        # interactive in a specific directory
""",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="The prompt to run (one-shot mode)",
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Interactive REPL mode",
    )
    parser.add_argument(
        "-p", "--provider",
        default="openai",
        help="LLM provider: anthropic, openai (default: openai)",
    )
    parser.add_argument(
        "-m", "--model",
        default="",
        help="Model name (default: provider's best)",
    )
    parser.add_argument(
        "-d", "--directory",
        default=".",
        help="Working directory (default: current dir)",
    )
    parser.add_argument(
        "-s", "--system",
        default="",
        help="System prompt",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=30,
        help="Max agent turns (default: 30)",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key (default: read from env/config)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed tool inputs/outputs",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_mode",
        help="Output events as JSON lines (for piping)",
    )
    parser.add_argument(
        "--web-extractor",
        default="trafilatura",
        choices=["trafilatura", "readability", "regex"],
        help="HTML content extraction method (default: trafilatura)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Start in auto mode (skip all permission prompts)",
    )
    parser.add_argument(
        "--fallback-model",
        default="",
        help="Fallback model when primary model fails (e.g., gpt-4o-mini)",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Disable MCP server auto-discovery from .mcp.json",
    )
    parser.add_argument(
        "--coordinator",
        action="store_true",
        help="Coordinator mode: delegate only, no direct file writes or command execution",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "--max-budget-usd",
        type=float,
        help="Maximum dollar amount to spend on API calls",
    )
    parser.add_argument(
        "--no-session-persistence",
        action="store_true",
        help="Disable session persistence",
    )
    parser.add_argument(
        "--suggestions",
        action="store_true",
        help="Show follow-up suggestions after each turn",
    )
    parser.add_argument(
        "--append-system-prompt",
        help="Append to the default system prompt",
    )
    parser.add_argument(
        "--resume",
        metavar="SESSION_ID",
        help="Resume a previous session",
    )
    parser.add_argument(
        "--bare",
        action="store_true",
        help="Minimal mode: skip hooks, memory, plugins",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"salt-agent {__version__}",
    )
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --no-color: disable colored output before any output
    if args.no_color or os.environ.get("NO_COLOR"):
        global _USE_COLOR
        _USE_COLOR = False

    # If no prompt and not interactive, default to interactive
    if not args.interactive and args.prompt is None:
        args.interactive = True

    api_key = _resolve_api_key(args.provider, args.api_key)
    if not api_key:
        env_var = "ANTHROPIC_API_KEY" if args.provider == "anthropic" else "OPENAI_API_KEY"
        _write(
            f"\n  {_c(_RED, 'Error:')} No API key found for provider '{args.provider}'.\n"
            f"  Set {env_var}, pass --api-key, or add {args.provider}_key to "
            f"~/.openclaw/secrets.json\n\n"
        )
        sys.exit(1)

    config = AgentConfig(
        provider=args.provider,
        model=args.model,
        api_key=api_key,
        max_turns=args.max_turns,
        working_directory=os.path.abspath(args.directory),
        system_prompt=args.system,
        web_extractor=args.web_extractor,
        auto_mode=args.auto,
        fallback_model=args.fallback_model,
        enable_mcp=not args.no_mcp,
        coordinator_mode=args.coordinator,
    )

    # --suggestions: enable follow-up suggestions
    if args.suggestions:
        config.show_suggestions = True

    # --max-budget-usd: set budget limit
    if args.max_budget_usd is not None:
        config.max_budget_usd = args.max_budget_usd

    # --no-session-persistence: disable persistence
    if args.no_session_persistence:
        config.persist = False

    # --append-system-prompt: append to system prompt
    if args.append_system_prompt:
        config.system_prompt = (config.system_prompt or "") + "\n\n" + args.append_system_prompt

    # --resume: load a previous session
    if args.resume:
        config.session_id = args.resume

    # --bare: minimal mode — disable hooks, memory, plugins, MCP
    if args.bare:
        config.persist = False
        config.enable_mcp = False
        config.skill_dirs = []

    from salt_agent.agent import SaltAgent

    agent = SaltAgent(config)

    # --bare: clear hooks after agent creation
    if args.bare:
        from salt_agent.hooks import HookEngine
        agent.hooks = HookEngine()

    if args.interactive:
        try:
            asyncio.run(_interactive(agent, verbose=args.verbose, json_mode=args.json_mode))
        except KeyboardInterrupt:
            _write(f"\n{_c(_DIM, 'Goodbye!')}\n")
    else:
        tracker = TokenTracker(model=config.model)
        try:
            asyncio.run(
                _run_agent(
                    agent,
                    args.prompt,
                    verbose=args.verbose,
                    json_mode=args.json_mode,
                    tracker=tracker,
                )
            )
        except KeyboardInterrupt:
            _write(f"\n  {_c(_DIM, 'Interrupted.')}\n")
            sys.exit(130)


if __name__ == "__main__":
    main()
