"""Permission system -- rule-based tool call authorization."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class PermissionRule:
    """A single permission rule matching tool calls."""

    tool: str       # tool name or "*"
    pattern: str    # command pattern for bash, path pattern for write
    action: str     # "allow", "ask", "deny"


DEFAULT_RULES: list[PermissionRule] = [
    # Bash: dangerous commands
    PermissionRule("bash", "rm -rf *", "deny"),
    PermissionRule("bash", "sudo *", "deny"),
    PermissionRule("bash", "chmod *", "ask"),
    PermissionRule("bash", "kill *", "ask"),
    PermissionRule("bash", "git push *", "ask"),
    PermissionRule("bash", "git reset --hard*", "deny"),
    PermissionRule("bash", "pip install *", "ask"),
    # File writes outside working dir
    PermissionRule("write", "/etc/*", "deny"),
    PermissionRule("write", "/usr/*", "deny"),
    PermissionRule("write", "~/*", "ask"),  # outside working dir
    # Default: allow
    PermissionRule("*", "*", "allow"),
]


class PermissionSystem:
    """Check tool calls against permission rules."""

    def __init__(
        self,
        rules: list[PermissionRule] | None = None,
        ask_callback: Callable | None = None,
    ):
        self.rules = rules if rules is not None else list(DEFAULT_RULES)
        self.ask_callback = ask_callback  # Called when action is "ask"

    def check(self, tool_name: str, tool_input: dict) -> tuple[str, str]:
        """Check if a tool call is allowed.

        Returns (action, reason) where action is "allow" or "deny".
        """
        for rule in self.rules:
            if self._matches(rule, tool_name, tool_input):
                if rule.action == "deny":
                    return "deny", f"Blocked by rule: {rule.tool} {rule.pattern}"
                elif rule.action == "ask":
                    if self.ask_callback:
                        approved = self.ask_callback(
                            tool_name,
                            tool_input,
                            f"Permission needed: {tool_name}",
                        )
                        return ("allow" if approved else "deny"), "User decision"
                    return "allow", "No ask callback, defaulting to allow"
                else:
                    return "allow", ""
        return "allow", ""

    def _matches(
        self,
        rule: PermissionRule,
        tool_name: str,
        tool_input: dict,
    ) -> bool:
        """Check if a rule matches this tool call."""
        if rule.tool != "*" and rule.tool != tool_name:
            return False
        if rule.pattern == "*":
            return True
        # For bash: match command
        if tool_name == "bash":
            command = tool_input.get("command", "")
            return self._glob_match(rule.pattern, command)
        # For write/edit: match file path
        if tool_name in ("write", "edit"):
            path = tool_input.get("file_path", "")
            return self._glob_match(rule.pattern, path)
        return False

    @staticmethod
    def _glob_match(pattern: str, text: str) -> bool:
        """Simple glob matching with *."""
        return fnmatch.fnmatch(text, pattern)
