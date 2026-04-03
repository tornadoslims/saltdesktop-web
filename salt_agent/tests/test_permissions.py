"""Tests for the permission system."""

from unittest.mock import MagicMock

import pytest

from salt_agent.permissions import DEFAULT_RULES, PermissionRule, PermissionSystem


class TestPermissionDefaults:
    def test_allow_by_default(self):
        """Default rules allow normal tool calls."""
        ps = PermissionSystem()
        action, reason = ps.check("read", {"file_path": "/tmp/test.py"})
        assert action == "allow"

    def test_deny_rm_rf(self):
        """rm -rf is denied."""
        ps = PermissionSystem()
        action, reason = ps.check("bash", {"command": "rm -rf /tmp/stuff"})
        assert action == "deny"
        assert "Blocked" in reason

    def test_deny_sudo(self):
        """sudo commands are denied."""
        ps = PermissionSystem()
        action, reason = ps.check("bash", {"command": "sudo apt install foo"})
        assert action == "deny"

    def test_deny_git_reset_hard(self):
        """git reset --hard is denied."""
        ps = PermissionSystem()
        action, reason = ps.check("bash", {"command": "git reset --hard HEAD~1"})
        assert action == "deny"

    def test_deny_write_to_etc(self):
        """Writing to /etc is denied."""
        ps = PermissionSystem()
        action, reason = ps.check("write", {"file_path": "/etc/passwd"})
        assert action == "deny"

    def test_deny_write_to_usr(self):
        """Writing to /usr is denied."""
        ps = PermissionSystem()
        action, reason = ps.check("write", {"file_path": "/usr/bin/something"})
        assert action == "deny"


class TestPermissionAsk:
    def test_ask_pip_install_approved(self):
        """pip install asks the callback, approved."""
        callback = MagicMock(return_value=True)
        ps = PermissionSystem(ask_callback=callback)
        action, reason = ps.check("bash", {"command": "pip install requests"})
        assert action == "allow"
        assert reason == "User decision"
        callback.assert_called_once()

    def test_ask_pip_install_denied(self):
        """pip install asks the callback, denied."""
        callback = MagicMock(return_value=False)
        ps = PermissionSystem(ask_callback=callback)
        action, reason = ps.check("bash", {"command": "pip install requests"})
        assert action == "deny"
        assert reason == "User decision"

    def test_ask_chmod(self):
        """chmod asks for permission."""
        callback = MagicMock(return_value=True)
        ps = PermissionSystem(ask_callback=callback)
        action, reason = ps.check("bash", {"command": "chmod 755 script.sh"})
        assert action == "allow"
        callback.assert_called_once()

    def test_ask_kill(self):
        """kill asks for permission."""
        callback = MagicMock(return_value=False)
        ps = PermissionSystem(ask_callback=callback)
        action, reason = ps.check("bash", {"command": "kill 12345"})
        assert action == "deny"

    def test_ask_git_push(self):
        """git push asks for permission."""
        callback = MagicMock(return_value=True)
        ps = PermissionSystem(ask_callback=callback)
        action, reason = ps.check("bash", {"command": "git push origin main"})
        assert action == "allow"
        callback.assert_called_once()

    def test_no_callback_defaults_to_allow(self):
        """No ask_callback defaults to allow for 'ask' rules."""
        ps = PermissionSystem(ask_callback=None)
        action, reason = ps.check("bash", {"command": "pip install requests"})
        assert action == "allow"
        assert "No ask callback" in reason


class TestPermissionPatternMatching:
    def test_glob_match_simple(self):
        """Simple glob matching works."""
        assert PermissionSystem._glob_match("rm -rf *", "rm -rf /tmp") is True
        assert PermissionSystem._glob_match("rm -rf *", "ls") is False

    def test_glob_match_wildcard(self):
        """Wildcard matches anything."""
        assert PermissionSystem._glob_match("*", "anything at all") is True

    def test_glob_match_path(self):
        """Path patterns work for file writes."""
        assert PermissionSystem._glob_match("/etc/*", "/etc/passwd") is True
        assert PermissionSystem._glob_match("/etc/*", "/tmp/file") is False

    def test_tool_mismatch_skips_rule(self):
        """Rules for different tools don't match."""
        ps = PermissionSystem(rules=[
            PermissionRule("bash", "*", "deny"),
        ])
        # "read" tool should not match a bash-only rule
        action, reason = ps.check("read", {"file_path": "/tmp/test"})
        assert action == "allow"

    def test_write_path_matching(self):
        """Write tool matches on file_path."""
        ps = PermissionSystem(rules=[
            PermissionRule("write", "/secret/*", "deny"),
            PermissionRule("*", "*", "allow"),
        ])
        action, _ = ps.check("write", {"file_path": "/secret/keys.txt"})
        assert action == "deny"

        action, _ = ps.check("write", {"file_path": "/tmp/safe.txt"})
        assert action == "allow"

    def test_edit_tool_uses_file_path(self):
        """Edit tool also matches on file_path."""
        ps = PermissionSystem(rules=[
            PermissionRule("edit", "/etc/*", "deny"),
            PermissionRule("*", "*", "allow"),
        ])
        action, _ = ps.check("edit", {"file_path": "/etc/hosts"})
        assert action == "deny"


class TestCustomRules:
    def test_custom_rules_override_defaults(self):
        """Custom rules replace defaults entirely."""
        ps = PermissionSystem(rules=[
            PermissionRule("*", "*", "deny"),  # deny everything
        ])
        action, _ = ps.check("read", {"file_path": "/tmp/test"})
        assert action == "deny"

    def test_empty_rules_allow_everything(self):
        """Empty rules list allows everything (no rules match)."""
        ps = PermissionSystem(rules=[])
        action, _ = ps.check("bash", {"command": "rm -rf /"})
        assert action == "allow"

    def test_first_matching_rule_wins(self):
        """First matching rule determines the outcome."""
        ps = PermissionSystem(rules=[
            PermissionRule("bash", "pip install *", "deny"),
            PermissionRule("bash", "pip install *", "allow"),
        ])
        action, _ = ps.check("bash", {"command": "pip install requests"})
        assert action == "deny"


class TestPermissionHookIntegration:
    def test_permission_hook_blocks_denied_tool(self):
        """Permission system integrates with hooks to block denied tools."""
        from salt_agent.hooks import HookEngine, HookResult

        ps = PermissionSystem(rules=[
            PermissionRule("bash", "rm *", "deny"),
            PermissionRule("*", "*", "allow"),
        ])
        engine = HookEngine()

        def permission_hook(data):
            action, reason = ps.check(
                data.get("tool_name", ""),
                data.get("tool_input", {}),
            )
            if action == "deny":
                return HookResult(action="block", reason=reason)
            return None

        engine.on("pre_tool_use", permission_hook)

        # rm should be blocked
        result = engine.fire("pre_tool_use", {
            "tool_name": "bash",
            "tool_input": {"command": "rm /tmp/file"},
        })
        assert result.action == "block"

        # ls should be allowed
        result = engine.fire("pre_tool_use", {
            "tool_name": "bash",
            "tool_input": {"command": "ls /tmp"},
        })
        assert result.action == "allow"
