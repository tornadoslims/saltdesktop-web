"""Tests for the hook engine."""

import asyncio

import pytest

from salt_agent.hooks import HookEngine, HookResult, HOOK_EVENTS


class TestHookEngineRegistration:
    def test_register_and_fire(self):
        engine = HookEngine()
        called = []

        def callback(data):
            called.append(data)
            return HookResult(action="allow")

        engine.on("pre_tool_use", callback)
        result = engine.fire("pre_tool_use", {"tool": "read"})
        assert result.action == "allow"
        assert len(called) == 1
        assert called[0] == {"tool": "read"}

    def test_multiple_hooks_same_event(self):
        engine = HookEngine()
        calls = []

        def cb1(data):
            calls.append("cb1")
            return HookResult(action="allow")

        def cb2(data):
            calls.append("cb2")
            return HookResult(action="allow")

        engine.on("post_tool_use", cb1)
        engine.on("post_tool_use", cb2)
        engine.fire("post_tool_use", {})
        assert calls == ["cb1", "cb2"]

    def test_no_hooks_returns_allow(self):
        engine = HookEngine()
        result = engine.fire("pre_tool_use", {})
        assert result.action == "allow"


class TestHookEngineBlocking:
    def test_pre_tool_use_blocks(self):
        engine = HookEngine()

        def blocker(data):
            return HookResult(action="block", reason="Not allowed")

        engine.on("pre_tool_use", blocker)
        result = engine.fire("pre_tool_use", {"tool": "bash"})
        assert result.action == "block"
        assert result.reason == "Not allowed"

    def test_first_non_allow_wins(self):
        engine = HookEngine()
        calls = []

        def allow_hook(data):
            calls.append("allow")
            return HookResult(action="allow")

        def block_hook(data):
            calls.append("block")
            return HookResult(action="block", reason="Blocked!")

        def never_called(data):
            calls.append("never")
            return HookResult(action="allow")

        engine.on("pre_tool_use", allow_hook)
        engine.on("pre_tool_use", block_hook)
        engine.on("pre_tool_use", never_called)

        result = engine.fire("pre_tool_use", {})
        assert result.action == "block"
        # The third hook should not have been called
        assert "never" not in calls

    def test_modify_action(self):
        engine = HookEngine()

        def modifier(data):
            return HookResult(
                action="modify",
                modified_input={"command": "echo safe"},
            )

        engine.on("pre_tool_use", modifier)
        result = engine.fire("pre_tool_use", {"command": "rm -rf /"})
        assert result.action == "modify"
        assert result.modified_input == {"command": "echo safe"}


class TestHookEngineErrorResilience:
    def test_hook_exception_does_not_crash(self):
        engine = HookEngine()
        called_after = []

        def bad_hook(data):
            raise ValueError("Hook crashed!")

        def good_hook(data):
            called_after.append(True)
            return HookResult(action="allow")

        engine.on("pre_tool_use", bad_hook)
        engine.on("pre_tool_use", good_hook)

        result = engine.fire("pre_tool_use", {})
        assert result.action == "allow"
        assert len(called_after) == 1

    def test_hook_returns_none_treated_as_allow(self):
        engine = HookEngine()

        def returns_none(data):
            return None

        engine.on("pre_tool_use", returns_none)
        result = engine.fire("pre_tool_use", {})
        assert result.action == "allow"


class TestHookEngineRemoval:
    def test_off_removes_hook(self):
        engine = HookEngine()
        calls = []

        def callback(data):
            calls.append(True)
            return HookResult(action="allow")

        engine.on("pre_tool_use", callback)
        engine.fire("pre_tool_use", {})
        assert len(calls) == 1

        engine.off("pre_tool_use", callback)
        engine.fire("pre_tool_use", {})
        assert len(calls) == 1  # Not called again

    def test_off_nonexistent_hook_no_error(self):
        engine = HookEngine()

        def callback(data):
            pass

        # Should not raise
        engine.off("pre_tool_use", callback)

    def test_off_nonexistent_event_no_error(self):
        engine = HookEngine()

        def callback(data):
            pass

        engine.off("nonexistent_event", callback)


class TestHookEngineAsync:
    def test_fire_async_basic(self):
        engine = HookEngine()
        calls = []

        def sync_callback(data):
            calls.append("sync")
            return HookResult(action="allow")

        engine.on("pre_tool_use", sync_callback)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                engine.fire_async("pre_tool_use", {"tool": "read"})
            )
        finally:
            loop.close()

        assert result.action == "allow"
        assert len(calls) == 1

    def test_fire_async_with_async_callback(self):
        engine = HookEngine()
        calls = []

        async def async_callback(data):
            calls.append("async")
            return HookResult(action="allow")

        engine.on("pre_api_call", async_callback)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                engine.fire_async("pre_api_call", {})
            )
        finally:
            loop.close()

        assert result.action == "allow"
        assert len(calls) == 1

    def test_fire_async_block(self):
        engine = HookEngine()

        def blocker(data):
            return HookResult(action="block", reason="Nope")

        engine.on("pre_tool_use", blocker)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                engine.fire_async("pre_tool_use", {})
            )
        finally:
            loop.close()

        assert result.action == "block"


class TestHttpHook:
    def test_http_hook_sends_post(self):
        """HttpHook should POST JSON to the given URL."""
        from salt_agent.hooks import HttpHook
        from unittest.mock import patch, MagicMock
        import json

        hook = HttpHook("http://example.com/hook", timeout=2.0)

        # Mock urlopen to return a 200 response with allow action
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"action": "allow", "reason": "ok"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = hook({"tool": "bash"})

        assert mock_urlopen.called
        assert result is not None
        assert result.action == "allow"
        assert result.reason == "ok"

    def test_http_hook_block_action(self):
        """HttpHook should return block when server responds with block."""
        from salt_agent.hooks import HttpHook
        from unittest.mock import patch, MagicMock
        import json

        hook = HttpHook("http://example.com/hook")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"action": "block", "reason": "forbidden"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = hook({"tool": "bash"})

        assert result.action == "block"
        assert result.reason == "forbidden"

    def test_http_hook_handles_timeout(self):
        """HttpHook should return None on timeout (no crash)."""
        from salt_agent.hooks import HttpHook
        from unittest.mock import patch
        import urllib.error

        hook = HttpHook("http://example.com/hook", timeout=0.001)

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = hook({"tool": "bash"})

        assert result is None

    def test_http_hook_handles_connection_error(self):
        """HttpHook should return None on connection error."""
        from salt_agent.hooks import HttpHook
        from unittest.mock import patch

        hook = HttpHook("http://example.com/hook")

        with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")):
            result = hook({"tool": "bash"})

        assert result is None

    def test_register_http_hook(self):
        """HookEngine.register_http_hook should add an HttpHook."""
        from salt_agent.hooks import HttpHook
        engine = HookEngine()
        engine.register_http_hook("pre_tool_use", "http://example.com/hook")
        # Verify hook is registered
        hooks = engine._hooks.get("pre_tool_use", [])
        assert len(hooks) == 1
        assert isinstance(hooks[0], HttpHook)
        assert hooks[0].url == "http://example.com/hook"


class TestHookEvents:
    def test_hook_events_list_populated(self):
        assert len(HOOK_EVENTS) > 0
        assert "pre_tool_use" in HOOK_EVENTS
        assert "post_tool_use" in HOOK_EVENTS
        assert "on_complete" in HOOK_EVENTS
        assert "on_error" in HOOK_EVENTS
