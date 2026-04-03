"""
Hook engine -- callbacks for tool execution, API calls, errors, and completion.
SaltAgent uses hooks to track agent progress and enforce permissions in real-time.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class HookResult:
    action: str = "allow"  # "allow", "block", "modify"
    reason: str = ""
    modified_input: dict | None = None


# Hook callback type: receives event dict, returns HookResult or None
HookCallback = Callable[[dict], HookResult | None]


class HookEngine:
    """Register and fire hooks for agent lifecycle events."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookCallback]] = {}

    def on(self, event: str, callback: HookCallback) -> None:
        """Register a hook callback for an event type."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)

    def off(self, event: str, callback: HookCallback) -> None:
        """Remove a hook callback."""
        if event in self._hooks:
            self._hooks[event] = [h for h in self._hooks[event] if h != callback]

    def fire(self, event: str, data: dict) -> HookResult:
        """Fire all hooks for an event. Returns first non-allow result, or allow."""
        for callback in self._hooks.get(event, []):
            try:
                result = callback(data)
                if result and result.action != "allow":
                    return result
            except Exception:
                pass  # hooks should not crash the agent
        return HookResult(action="allow")

    async def fire_async(self, event: str, data: dict) -> HookResult:
        """Fire hooks, supporting async callbacks."""
        for callback in self._hooks.get(event, []):
            try:
                result = callback(data)
                if asyncio.iscoroutine(result):
                    result = await result
                if result and result.action != "allow":
                    return result
            except Exception:
                pass
        return HookResult(action="allow")

    def register_shell_hook(self, event: str, command: str) -> None:
        """Register a shell command as a hook for an event type."""
        self.on(event, ShellHook(command))

    def register_http_hook(self, event: str, url: str, timeout: float = 5.0) -> None:
        """Register an HTTP webhook for an event."""
        self.on(event, HttpHook(url, timeout))


class ShellHook:
    """A hook that executes a shell command. Input/output via JSON stdin/stdout."""

    def __init__(self, command: str):
        self.command = command

    def __call__(self, data: dict) -> HookResult | None:
        import subprocess
        import json
        try:
            result = subprocess.run(
                self.command, shell=True,
                input=json.dumps(data),
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                response = json.loads(result.stdout)
                return HookResult(
                    action=response.get("action", "allow"),
                    reason=response.get("reason", ""),
                )
        except Exception:
            pass
        return None


class HttpHook:
    """A hook that fires an HTTP POST to a URL with JSON payload."""

    def __init__(self, url: str, timeout: float = 5.0):
        self.url = url
        self.timeout = timeout

    def __call__(self, data: dict) -> HookResult | None:
        import urllib.request
        import json

        try:
            payload = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                self.url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode())
                    action = body.get("action", "allow")
                    return HookResult(action=action, reason=body.get("reason", ""))
        except Exception:
            pass
        return None


# Event types
HOOK_EVENTS = [
    "pre_tool_use",           # Before a tool executes. Can block.
    "post_tool_use",          # After a tool executes. Informational.
    "pre_api_call",           # Before an LLM API call. Can modify messages.
    "post_api_call",          # After an LLM response. Informational.
    "on_text_chunk",          # Text streaming chunk. Informational.
    "on_error",               # Error occurred. Informational.
    "on_complete",            # Agent finished. Informational.
    "on_compaction",          # Context was compacted. Informational.
    "on_permission_request",  # Permission needed. Can respond.
]
