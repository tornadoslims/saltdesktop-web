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
import json
import os
import re
import shutil
import signal
import sys
import threading
import time
from pathlib import Path

from salt_agent.config import AgentConfig
from salt_agent.events import (
    AgentComplete,
    AgentError,
    TextChunk,
    ToolEnd,
    ToolStart,
    ToolUse,
)

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# ANSI escape codes
# ---------------------------------------------------------------------------
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


class Spinner:
    """Animated thinking spinner that runs in a background thread."""

    def __init__(self, message: str = "Thinking..."):
        self._message = message
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not _USE_COLOR:
            return
        self._running = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        if _USE_COLOR:
            _write(_CLEAR_LINE)

    def _animate(self) -> None:
        idx = 0
        while self._running:
            frame = _SPINNER[idx % len(_SPINNER)]
            _write(f"{_CLEAR_LINE}  {_c(_DIM, f'{frame} {self._message}')}")
            idx += 1
            time.sleep(0.08)


# ---------------------------------------------------------------------------
# Markdown renderer (ANSI, no dependencies)
# ---------------------------------------------------------------------------

def render_markdown(text: str) -> str:
    """Convert markdown to ANSI-formatted terminal text."""
    if not _USE_COLOR:
        return text

    lines = text.split("\n")
    result: list[str] = []
    in_code_block = False
    i = 0

    while i < len(lines):
        line = lines[i]

        # Code block toggle
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            if in_code_block:
                result.append("")  # blank line before code block
            else:
                result.append("")  # blank line after code block
            i += 1
            continue

        if in_code_block:
            result.append(f"  {_DIM}\u2502{_RESET} {_DIM}{line}{_RESET}")
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

    for path in ["~/.openclaw/secrets.json", "~/.saltdesktop/config.json"]:
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
    """Return a short human-readable description of a tool call."""
    name_lower = name.lower()
    if name_lower == "bash":
        cmd = tool_input.get("command", "")
        if len(cmd) > 60:
            cmd = cmd[:57] + "..."
        return f"bash {cmd}"
    if name_lower == "write":
        fp = tool_input.get("file_path", "")
        return f"write {_abbreviate_path(fp)}" if fp else "write"
    if name_lower == "edit":
        fp = tool_input.get("file_path", "")
        return f"edit {_abbreviate_path(fp)}" if fp else "edit"
    if name_lower == "read":
        fp = tool_input.get("file_path", "")
        return f"read {_abbreviate_path(fp)}" if fp else "read"
    if name_lower == "glob":
        pat = tool_input.get("pattern", "")
        return f"glob {pat}"
    if name_lower == "grep":
        pat = tool_input.get("pattern", "")
        return f"grep {pat}"
    if name_lower in ("list_files", "listfiles"):
        p = tool_input.get("path", ".")
        return f"ls {p}"
    return name


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


def _tool_result_brief(name: str, result: str, success: bool) -> str:
    """Return a brief one-line summary of a tool result."""
    if not success:
        # Trim error to one line
        first_line = result.strip().split("\n")[0]
        if len(first_line) > 80:
            first_line = first_line[:77] + "..."
        return first_line

    result = result.strip()
    if not result:
        return "done"

    name_lower = name.lower()
    if name_lower == "edit":
        return "applied edit"
    if name_lower == "write":
        lines = result.count("\n") + 1 if result else 0
        return f"wrote file"
    if name_lower == "bash":
        lines = result.split("\n")
        if len(lines) == 1 and len(lines[0]) < 80:
            return lines[0]
        return f"{len(lines)} lines of output"
    if name_lower == "read":
        lines = result.count("\n") + 1
        return f"{lines} lines"
    if name_lower == "glob":
        files = [l for l in result.split("\n") if l.strip()]
        return f"{len(files)} files"
    if name_lower == "grep":
        matches = [l for l in result.split("\n") if l.strip()]
        return f"{len(matches)} matches"

    # Generic: first line, truncated
    first_line = result.split("\n")[0]
    if len(first_line) > 60:
        first_line = first_line[:57] + "..."
    return first_line


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

def _print_banner(config: AgentConfig, tool_names: list[str]) -> None:
    """Print the startup banner box."""
    home = os.path.expanduser("~")
    wd = os.path.abspath(config.working_directory)
    display_dir = wd.replace(home, "~") if wd.startswith(home) else wd
    model = config.model or "(default)"
    provider_display = f"{config.provider.capitalize()} ({model})"
    tools_display = ", ".join(tool_names)

    # Content lines as (display_text, visual_width) tuples
    # Emoji takes 2 terminal columns, so we track visual width separately
    title = f"\U0001f9c2 SaltAgent v{__version__}"
    content_lines = [
        (title, len(title) + 1),  # +1 for emoji extra column width
        ("", 0),
        (f"Provider: {provider_display}", None),
        (f"Directory: {display_dir}", None),
        (f"Tools: {tools_display}", None),
        ("", 0),
        ("Type your request, or /help for commands.", None),
    ]
    # Fill in None visual widths with len
    content_lines = [(t, w if w is not None else len(t)) for t, w in content_lines]

    max_len = max(w for _, w in content_lines) + 4
    box_width = max(max_len, 50)

    _write("\n")
    _write(f"  {_c(_DIM, '\u256d' + '\u2500' * box_width + '\u256e')}\n")
    _write(f"  {_c(_DIM, '\u2502')}{' ' * box_width}{_c(_DIM, '\u2502')}\n")

    for text, vis_width in content_lines:
        if not text:
            _write(f"  {_c(_DIM, '\u2502')}{' ' * box_width}{_c(_DIM, '\u2502')}\n")
        else:
            padding = box_width - vis_width - 2  # -2 for left indent
            display = text
            if text.startswith("\U0001f9c2"):
                display = _c(_BOLD, text)
            _write(f"  {_c(_DIM, '\u2502')}  {display}{' ' * padding}{_c(_DIM, '\u2502')}\n")

    _write(f"  {_c(_DIM, '\u2502')}{' ' * box_width}{_c(_DIM, '\u2502')}\n")
    _write(f"  {_c(_DIM, '\u2570' + '\u2500' * box_width + '\u256f')}\n")
    _write("\n")


# ---------------------------------------------------------------------------
# Slash command handlers
# ---------------------------------------------------------------------------

_SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/clear": "Clear conversation history",
    "/compact": "Compress context (summarize old turns)",
    "/mode": "Show/change agent mode",
    "/tools": "List available tools",
    "/cost": "Show token usage this session",
    "/history": "Show conversation summary",
    "/quit": "Exit",
}


def _handle_slash_command(
    cmd: str,
    agent,
    tracker: TokenTracker,
    verbose: bool,
) -> bool | None:
    """Handle a slash command. Returns True if handled, None to quit, False if not a command."""
    parts = cmd.strip().split(None, 1)
    command = parts[0].lower()
    # arg = parts[1] if len(parts) > 1 else ""

    if command == "/help":
        _write("\n")
        _write(f"  {_c(_BOLD, 'Commands')}\n\n")
        for slash, desc in _SLASH_COMMANDS.items():
            _write(f"  {_c(_CYAN, slash):20s}  {_c(_DIM, desc)}\n")
        _write("\n")
        return True

    if command in ("/quit", "/exit", "/q"):
        return None

    if command == "/clear":
        from salt_agent.context import ContextManager
        agent.context = ContextManager(
            context_window=agent.config.context_window,
            max_tool_result_chars=agent.config.max_tool_result_chars,
        )
        if agent.config.system_prompt:
            agent.context.set_system(agent.config.system_prompt)
        _write(f"\n  {_c(_DIM, 'Context cleared.')}\n\n")
        return True

    if command == "/tools":
        _write("\n")
        _write(f"  {_c(_BOLD, 'Available Tools')}\n\n")
        for name in sorted(agent.tools.names()):
            _write(f"  {_c(_CYAN, name)}\n")
        _write("\n")
        return True

    if command == "/cost":
        _write("\n")
        info = tracker.format()
        if info:
            _write(f"  {_c(_DIM, info)}\n")
        else:
            _write(f"  {_c(_DIM, 'No tokens used yet.')}\n")
        _write("\n")
        return True

    if command == "/mode":
        _write(f"\n  {_c(_DIM, 'Mode: default (modes not yet implemented)')}\n\n")
        return True

    if command == "/compact":
        _write(f"\n  {_c(_DIM, 'Context compaction not yet implemented.')}\n\n")
        return True

    if command == "/history":
        _write(f"\n  {_c(_DIM, 'History summary not yet implemented.')}\n\n")
        return True

    return False


# ---------------------------------------------------------------------------
# Event rendering
# ---------------------------------------------------------------------------

def _render_event(
    event,
    *,
    verbose: bool = False,
    spinner: Spinner | None = None,
    tracker: TokenTracker | None = None,
    text_started: list[bool] | None = None,
) -> None:
    """Render a single agent event to the terminal."""

    if isinstance(event, TextChunk):
        if spinner:
            spinner.stop()
        if text_started is not None and not text_started[0]:
            _write("\n")
            text_started[0] = True
        # Render markdown inline - accumulate would be better but chunk-by-chunk
        # works for streaming. We apply inline formatting to each chunk.
        rendered = _render_inline(event.text)
        _write(rendered)

    elif isinstance(event, ToolStart):
        if spinner:
            spinner.stop()
        brief = _tool_brief(event.tool_name, event.tool_input)
        _write(f"\n  {_c(_CYAN, f'\u26a1 {brief}')}\n")
        if verbose:
            for k, v in event.tool_input.items():
                val = str(v)
                if len(val) > 120:
                    val = val[:117] + "..."
                _write(f"    {_c(_DIM, f'{k}: {val}')}\n")

    elif isinstance(event, ToolEnd):
        summary = _tool_result_brief(event.tool_name, event.result, event.success)
        if event.success:
            _write(f"    {_c(_DIM + _GREEN, f'\u2713 {summary}')}\n")
        else:
            _write(f"    {_c(_RED, f'\u2717 {summary}')}\n")
        if verbose and event.result.strip():
            for line in event.result.strip().splitlines()[:10]:
                _write(f"    {_c(_DIM, f'  {line}')}\n")
            if len(event.result.strip().splitlines()) > 10:
                _write(f"    {_c(_DIM, f'  ... ({len(event.result.strip().splitlines())} lines)')}\n")

    elif isinstance(event, AgentError):
        if spinner:
            spinner.stop()
        if event.recoverable:
            _write(f"\n  {_c(_YELLOW, f'\u274c {event.error}')}\n")
        else:
            _write(f"\n  {_c(_RED, f'\u274c {event.error}')}\n")

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
            )
    finally:
        if spinner:
            spinner.stop()

    # End with newline if text was streamed
    if text_started[0]:
        _write("\n")

    # Show cost
    if tracker:
        _print_cost_line(tracker)


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

async def _interactive(
    agent,
    *,
    verbose: bool = False,
    json_mode: bool = False,
) -> None:
    # Print banner
    tool_names = sorted(agent.tools.names())
    _print_banner(agent.config, tool_names)

    tracker = TokenTracker(model=agent.config.model)

    # Enable readline for history and line editing
    try:
        import readline  # noqa: F401
    except ImportError:
        pass

    # Build prompt prefix
    home = os.path.expanduser("~")
    wd = os.path.abspath(agent.config.working_directory)
    display_dir = wd.replace(home, "~") if wd.startswith(home) else wd

    while True:
        try:
            prompt_str = f"{_c(_CYAN, display_dir)} {_c(_DIM, '>')} " if _USE_COLOR else f"{display_dir} > "
            line = input(prompt_str)
        except EOFError:
            _write(f"\n{_c(_DIM, 'Goodbye!')}\n")
            return
        except KeyboardInterrupt:
            _write("\n")
            continue

        # Multi-line support: lines ending with backslash
        while line.endswith("\\"):
            try:
                cont_prompt = f"{_c(_DIM, '... >')} " if _USE_COLOR else "... > "
                continuation = input(cont_prompt)
                line = line[:-1] + "\n" + continuation
            except EOFError:
                break
            except KeyboardInterrupt:
                _write("\n")
                line = ""
                break

        line = line.strip()
        if not line:
            continue

        # Slash commands
        if line.startswith("/"):
            result = _handle_slash_command(line, agent, tracker, verbose)
            if result is None:
                _write(f"{_c(_DIM, 'Goodbye!')}\n")
                return
            if result:
                continue
            # Unknown command
            _write(f"\n  {_c(_YELLOW, f'Unknown command: {line.split()[0]}. Type /help for available commands.')}\n\n")
            continue

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
            _write(f"\n  {_c(_DIM, 'Interrupted.')}\n\n")
            continue
        except Exception as e:
            _write(f"\n  {_c(_RED, f'\u274c {e}')}\n\n")
            continue

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
    )

    from salt_agent.agent import SaltAgent

    agent = SaltAgent(config)

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
