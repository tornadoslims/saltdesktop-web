"""Tests for Phase 5 features: auto mode, image/PDF reading, model fallback,
plan mode, session search, and diff preview."""

from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from salt_agent.config import AgentConfig
from salt_agent.hooks import HookEngine, HookResult
from salt_agent.permissions import PermissionRule, PermissionSystem
from salt_agent.persistence import SessionPersistence
from salt_agent.tools.read import ReadTool


# =============================================================================
# Feature 1: Auto Mode
# =============================================================================


class TestAutoMode:
    def test_auto_mode_config_default_false(self):
        config = AgentConfig()
        assert config.auto_mode is False

    def test_auto_mode_always_allows(self):
        """When auto_mode is True, all tool calls are allowed."""
        ps = PermissionSystem(auto_mode=True)
        action, reason = ps.check("bash", {"command": "rm -rf /tmp/stuff"})
        assert action == "allow"
        assert reason == "auto mode"

    def test_auto_mode_allows_sudo(self):
        """Auto mode allows even sudo commands."""
        ps = PermissionSystem(auto_mode=True)
        action, reason = ps.check("bash", {"command": "sudo reboot"})
        assert action == "allow"

    def test_auto_mode_off_still_blocks(self):
        """With auto_mode off, dangerous commands are still blocked."""
        ps = PermissionSystem(auto_mode=False)
        action, reason = ps.check("bash", {"command": "rm -rf /everything"})
        assert action == "deny"

    def test_auto_mode_allows_write_to_etc(self):
        """Auto mode allows writing to /etc."""
        ps = PermissionSystem(auto_mode=True)
        action, reason = ps.check("write", {"file_path": "/etc/passwd"})
        assert action == "allow"

    def test_auto_mode_toggle(self):
        """Auto mode can be toggled."""
        ps = PermissionSystem(auto_mode=False)
        assert ps.auto_mode is False
        ps.auto_mode = True
        action, _ = ps.check("bash", {"command": "sudo rm -rf /"})
        assert action == "allow"
        ps.auto_mode = False
        action, _ = ps.check("bash", {"command": "sudo rm -rf /"})
        assert action == "deny"

    def test_config_auto_mode_flag(self):
        """AgentConfig accepts auto_mode."""
        config = AgentConfig(auto_mode=True)
        assert config.auto_mode is True


# =============================================================================
# Feature 2: Image/PDF Reading
# =============================================================================


class TestImageReading:
    def test_detects_image_extensions(self):
        """ReadTool detects image files by extension."""
        from salt_agent.tools.read import _IMAGE_EXTENSIONS
        for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]:
            assert ext in _IMAGE_EXTENSIONS

    def test_read_image_returns_base64_info(self, tmp_path):
        """Reading an image returns base64 info and stores pending image."""
        img_path = tmp_path / "test.png"
        # Create a small fake PNG (not valid PNG data, but enough for testing)
        img_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        img_path.write_bytes(img_data)

        tool = ReadTool(working_directory=str(tmp_path))
        result = tool.execute(file_path=str(img_path))

        assert "[Image file:" in result
        assert "base64 encoded" in result
        assert str(len(img_data)) in result

        # Check pending images
        assert len(tool._pending_images) == 1
        img = tool._pending_images[0]
        assert img["media_type"] == "image/png"
        assert img["base64_data"] == base64.b64encode(img_data).decode("ascii")

    def test_read_jpg_image(self, tmp_path):
        """Reading a JPG sets correct media type."""
        img_path = tmp_path / "photo.jpg"
        img_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)

        tool = ReadTool()
        result = tool.execute(file_path=str(img_path))
        assert "[Image file:" in result
        assert len(tool._pending_images) == 1
        assert tool._pending_images[0]["media_type"] == "image/jpeg"

    def test_image_tracked_as_read(self, tmp_path):
        """Image files are tracked in files_read."""
        img_path = tmp_path / "test.gif"
        img_path.write_bytes(b"GIF89a" + b"\x00" * 20)

        tool = ReadTool()
        tool.execute(file_path=str(img_path))
        assert str(img_path.resolve()) in tool.files_read

    def test_pending_images_cleared(self, tmp_path):
        """Pending images can be cleared."""
        img_path = tmp_path / "test.webp"
        img_path.write_bytes(b"RIFF" + b"\x00" * 20)

        tool = ReadTool()
        tool.execute(file_path=str(img_path))
        assert len(tool._pending_images) == 1
        tool._pending_images.clear()
        assert len(tool._pending_images) == 0


class TestPDFReading:
    def test_read_pdf_fallback_raw(self, tmp_path):
        """PDF reading falls back to raw text when pdftotext is not available."""
        pdf_path = tmp_path / "test.pdf"
        # Write some text that looks like a raw text PDF
        pdf_path.write_text("%PDF-1.4\nSome content\nMore content\n%%EOF", encoding="utf-8")

        tool = ReadTool()
        result = tool.execute(file_path=str(pdf_path))
        assert "PDF:" in result
        assert "test.pdf" in result
        # Should contain the raw text
        assert "Some content" in result

    def test_pdf_tracked_as_read(self, tmp_path):
        """PDF files are tracked in files_read."""
        pdf_path = tmp_path / "doc.pdf"
        pdf_path.write_text("%PDF-1.4\nHello\n%%EOF", encoding="utf-8")

        tool = ReadTool()
        tool.execute(file_path=str(pdf_path))
        assert str(pdf_path.resolve()) in tool.files_read

    def test_pdf_does_not_create_pending_image(self, tmp_path):
        """PDFs do not go into pending_images."""
        pdf_path = tmp_path / "doc.pdf"
        pdf_path.write_text("%PDF-1.4\nContent\n%%EOF", encoding="utf-8")

        tool = ReadTool()
        tool.execute(file_path=str(pdf_path))
        assert len(tool._pending_images) == 0

    def test_read_pdf_with_pdftotext(self, tmp_path):
        """Test PDF reading when pdftotext is available (mocked)."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 binary data")

        tool = ReadTool()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Extracted text\nLine 2\n"

        with patch("salt_agent.tools.read.subprocess.run", return_value=mock_result):
            result = tool.execute(file_path=str(pdf_path))
            assert "pdftotext" in result
            assert "Extracted text" in result


# =============================================================================
# Feature 3: Model Fallback
# =============================================================================


class TestModelFallback:
    def test_fallback_model_config_default_empty(self):
        config = AgentConfig()
        assert config.fallback_model == ""

    def test_fallback_model_config_set(self):
        config = AgentConfig(fallback_model="gpt-4o-mini")
        assert config.fallback_model == "gpt-4o-mini"

    def test_anthropic_adapter_accepts_fallback(self):
        """AnthropicAdapter stores fallback_model."""
        from salt_agent.providers.anthropic import AnthropicAdapter
        adapter = AnthropicAdapter(api_key="test-key", fallback_model="claude-3-haiku-20240307")
        assert adapter.fallback_model == "claude-3-haiku-20240307"

    def test_openai_adapter_accepts_fallback(self):
        """OpenAIAdapter stores fallback_model."""
        from salt_agent.providers.openai_provider import OpenAIAdapter
        adapter = OpenAIAdapter(api_key="test-key", fallback_model="gpt-4o-mini")
        assert adapter.fallback_model == "gpt-4o-mini"

    def test_anthropic_adapter_no_fallback_by_default(self):
        from salt_agent.providers.anthropic import AnthropicAdapter
        adapter = AnthropicAdapter(api_key="test-key")
        assert adapter.fallback_model == ""

    def test_openai_adapter_no_fallback_by_default(self):
        from salt_agent.providers.openai_provider import OpenAIAdapter
        adapter = OpenAIAdapter(api_key="test-key")
        assert adapter.fallback_model == ""


# =============================================================================
# Feature 4: Plan Mode
# =============================================================================


class TestPlanMode:
    def test_plan_mode_config_default_false(self):
        config = AgentConfig()
        assert config.plan_mode is False

    def test_plan_mode_blocks_non_todo_tools(self):
        """In plan mode, only todo_write is allowed."""
        ps = PermissionSystem(plan_mode=True)

        # todo_write should be allowed
        action, reason = ps.check("todo_write", {"tasks": []})
        assert action == "allow"

        # bash should be blocked
        action, reason = ps.check("bash", {"command": "ls"})
        assert action == "deny"
        assert "Plan mode" in reason

        # read should be blocked
        action, reason = ps.check("read", {"file_path": "/tmp/x"})
        assert action == "deny"

        # write should be blocked
        action, reason = ps.check("write", {"file_path": "/tmp/x", "content": "test"})
        assert action == "deny"

        # edit should be blocked
        action, reason = ps.check("edit", {"file_path": "/tmp/x", "old_string": "a", "new_string": "b"})
        assert action == "deny"

    def test_plan_mode_off_allows_tools(self):
        """When plan mode is off, tools work normally."""
        ps = PermissionSystem(plan_mode=False)
        action, _ = ps.check("bash", {"command": "ls"})
        assert action == "allow"

    def test_plan_mode_toggle(self):
        """Plan mode can be toggled."""
        ps = PermissionSystem(plan_mode=False)
        action, _ = ps.check("bash", {"command": "ls"})
        assert action == "allow"

        ps.plan_mode = True
        action, _ = ps.check("bash", {"command": "ls"})
        assert action == "deny"
        # todo_write still allowed
        action, _ = ps.check("todo_write", {"tasks": []})
        assert action == "allow"

        ps.plan_mode = False
        action, _ = ps.check("bash", {"command": "ls"})
        assert action == "allow"

    def test_auto_mode_overrides_plan_mode(self):
        """Auto mode takes precedence over plan mode."""
        ps = PermissionSystem(auto_mode=True, plan_mode=True)
        action, reason = ps.check("bash", {"command": "ls"})
        assert action == "allow"
        assert reason == "auto mode"


# =============================================================================
# Feature 5: Session Search
# =============================================================================


class TestSessionSearch:
    def test_search_finds_matching_content(self, tmp_path):
        """search_sessions finds content in session files."""
        sp = SessionPersistence(session_id="test-session", sessions_dir=str(tmp_path))
        # Write some events
        sp.save_event("tool_use", {"tool": "bash", "command": "build gmail connector"})
        sp.save_event("completion", {"text": "The gmail connector is ready"})
        sp.save_event("tool_use", {"tool": "read", "file": "README.md"})

        results = sp.search_sessions("gmail")
        assert len(results) >= 1
        assert any("gmail" in r["preview"].lower() for r in results)

    def test_search_returns_empty_for_no_match(self, tmp_path):
        """search_sessions returns empty list when nothing matches."""
        sp = SessionPersistence(session_id="test-session", sessions_dir=str(tmp_path))
        sp.save_event("tool_use", {"tool": "bash", "command": "ls"})

        results = sp.search_sessions("nonexistent_xyz_query")
        assert results == []

    def test_search_respects_max_results(self, tmp_path):
        """search_sessions respects max_results parameter."""
        sp = SessionPersistence(session_id="test-session", sessions_dir=str(tmp_path))
        for i in range(20):
            sp.save_event("tool_use", {"tool": "bash", "command": f"test command {i}"})

        results = sp.search_sessions("test command", max_results=5)
        assert len(results) == 5

    def test_search_case_insensitive(self, tmp_path):
        """search_sessions is case insensitive."""
        sp = SessionPersistence(session_id="test-session", sessions_dir=str(tmp_path))
        sp.save_event("tool_use", {"tool": "bash", "command": "Build React App"})

        results = sp.search_sessions("build react")
        assert len(results) >= 1

    def test_search_across_multiple_sessions(self, tmp_path):
        """search_sessions searches across multiple session files."""
        sp1 = SessionPersistence(session_id="session-1", sessions_dir=str(tmp_path))
        sp1.save_event("tool_use", {"tool": "bash", "command": "deploy frontend"})

        sp2 = SessionPersistence(session_id="session-2", sessions_dir=str(tmp_path))
        sp2.save_event("tool_use", {"tool": "bash", "command": "deploy backend"})

        # Search from either session (uses same sessions_dir)
        results = sp1.search_sessions("deploy")
        assert len(results) >= 2

    def test_search_result_structure(self, tmp_path):
        """Search results have the expected fields."""
        sp = SessionPersistence(session_id="test-session", sessions_dir=str(tmp_path))
        sp.save_event("tool_use", {"tool": "bash", "command": "unique_marker_xyz"})

        results = sp.search_sessions("unique_marker_xyz")
        assert len(results) == 1
        r = results[0]
        assert "session_id" in r
        assert "line" in r
        assert "type" in r
        assert "preview" in r
        assert "timestamp" in r
        assert r["session_id"] == "test-session"
        # type may be "tool_use" (old format) or "event" (new search index format)
        assert r["type"] in ("tool_use", "event", "checkpoint")

    def test_search_empty_directory(self, tmp_path):
        """Search on empty sessions directory returns empty list."""
        sessions_dir = tmp_path / "empty_sessions"
        sessions_dir.mkdir()
        sp = SessionPersistence(session_id="test", sessions_dir=str(sessions_dir))
        # Don't save anything
        results = sp.search_sessions("anything")
        assert results == []


# =============================================================================
# Feature 6: Diff Preview
# =============================================================================


class TestDiffPreview:
    def test_diff_preview_hook_allows_by_default(self):
        """Diff preview hook returns None (allow) for non-edit tools."""
        from salt_agent.hooks import HookResult

        config = AgentConfig(auto_mode=False)

        # Simulate the hook logic
        def _diff_preview_hook(data: dict):
            tool_name = data.get("tool_name", "")
            tool_input = data.get("tool_input", {})
            if tool_name in ("edit", "multi_edit") and not config.auto_mode:
                old = tool_input.get("old_string", "")
                new = tool_input.get("new_string", "")
                if old and new:
                    return HookResult(action="block", reason="Would prompt user")
            return None

        # Non-edit tool
        result = _diff_preview_hook({"tool_name": "bash", "tool_input": {"command": "ls"}})
        assert result is None

    def test_diff_preview_blocks_edit_when_not_auto(self):
        """Diff preview would block edit when not in auto mode (simulated)."""
        from salt_agent.hooks import HookResult

        config = AgentConfig(auto_mode=False)

        def _diff_preview_hook(data: dict):
            tool_name = data.get("tool_name", "")
            tool_input = data.get("tool_input", {})
            if tool_name in ("edit", "multi_edit") and not config.auto_mode:
                old = tool_input.get("old_string", "")
                new = tool_input.get("new_string", "")
                if old and new:
                    # In real CLI, this would prompt the user
                    return HookResult(action="block", reason="Would prompt user")
            return None

        result = _diff_preview_hook({
            "tool_name": "edit",
            "tool_input": {
                "file_path": "/tmp/test.py",
                "old_string": "def foo():",
                "new_string": "def bar():",
            },
        })
        assert result is not None
        assert result.action == "block"

    def test_diff_preview_skips_in_auto_mode(self):
        """Diff preview skips when auto mode is on."""
        from salt_agent.hooks import HookResult

        config = AgentConfig(auto_mode=True)

        def _diff_preview_hook(data: dict):
            tool_name = data.get("tool_name", "")
            tool_input = data.get("tool_input", {})
            if tool_name in ("edit", "multi_edit") and not config.auto_mode:
                old = tool_input.get("old_string", "")
                new = tool_input.get("new_string", "")
                if old and new:
                    return HookResult(action="block", reason="Would prompt user")
            return None

        result = _diff_preview_hook({
            "tool_name": "edit",
            "tool_input": {
                "file_path": "/tmp/test.py",
                "old_string": "def foo():",
                "new_string": "def bar():",
            },
        })
        assert result is None

    def test_diff_preview_registered_on_hook_engine(self):
        """The diff preview hook can be registered on the hook engine."""
        engine = HookEngine()

        def mock_hook(data):
            if data.get("tool_name") == "edit":
                return HookResult(action="block", reason="test")
            return None

        engine.on("pre_tool_use", mock_hook)
        result = engine.fire("pre_tool_use", {
            "tool_name": "edit",
            "tool_input": {"old_string": "a", "new_string": "b"},
        })
        assert result.action == "block"

    def test_diff_preview_allows_edit_without_old_new(self):
        """Diff preview allows edit with empty old/new strings."""
        from salt_agent.hooks import HookResult

        config = AgentConfig(auto_mode=False)

        def _diff_preview_hook(data: dict):
            tool_name = data.get("tool_name", "")
            tool_input = data.get("tool_input", {})
            if tool_name in ("edit", "multi_edit") and not config.auto_mode:
                old = tool_input.get("old_string", "")
                new = tool_input.get("new_string", "")
                if old and new:
                    return HookResult(action="block", reason="Would prompt")
            return None

        result = _diff_preview_hook({
            "tool_name": "edit",
            "tool_input": {"file_path": "/tmp/test.py", "old_string": "", "new_string": ""},
        })
        assert result is None


# =============================================================================
# Integration: Config fields present
# =============================================================================


class TestConfigFields:
    def test_all_new_config_fields_exist(self):
        """All new config fields are present with correct defaults."""
        config = AgentConfig()
        assert hasattr(config, "auto_mode")
        assert hasattr(config, "fallback_model")
        assert hasattr(config, "plan_mode")
        assert config.auto_mode is False
        assert config.fallback_model == ""
        assert config.plan_mode is False

    def test_permission_system_accepts_new_params(self):
        """PermissionSystem accepts auto_mode and plan_mode."""
        ps = PermissionSystem(auto_mode=True, plan_mode=False)
        assert ps.auto_mode is True
        assert ps.plan_mode is False
