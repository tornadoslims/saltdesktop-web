"""Tests for expanded hooks, state store, plugin entry_points, and skill activation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Feature 1: Expanded Hook Events
# ---------------------------------------------------------------------------

class TestExpandedHookEvents:
    def test_hook_events_count_at_least_20(self):
        from salt_agent.hooks import HOOK_EVENTS
        assert len(HOOK_EVENTS) >= 20, f"Expected 20+ hook events, got {len(HOOK_EVENTS)}"

    def test_session_lifecycle_events_exist(self):
        from salt_agent.hooks import HOOK_EVENTS
        for event in ["session_start", "session_end", "session_resume"]:
            assert event in HOOK_EVENTS, f"Missing hook event: {event}"

    def test_turn_lifecycle_events_exist(self):
        from salt_agent.hooks import HOOK_EVENTS
        for event in ["turn_start", "turn_end", "turn_cancel"]:
            assert event in HOOK_EVENTS, f"Missing hook event: {event}"

    def test_memory_events_exist(self):
        from salt_agent.hooks import HOOK_EVENTS
        for event in ["memory_saved", "memory_deleted", "memory_surfaced"]:
            assert event in HOOK_EVENTS, f"Missing hook event: {event}"

    def test_subagent_events_exist(self):
        from salt_agent.hooks import HOOK_EVENTS
        for event in ["subagent_start", "subagent_end"]:
            assert event in HOOK_EVENTS, f"Missing hook event: {event}"

    def test_task_events_exist(self):
        from salt_agent.hooks import HOOK_EVENTS
        for event in ["task_created", "task_completed", "task_failed"]:
            assert event in HOOK_EVENTS, f"Missing hook event: {event}"

    def test_context_events_exist(self):
        from salt_agent.hooks import HOOK_EVENTS
        for event in ["context_compacted", "context_emergency"]:
            assert event in HOOK_EVENTS, f"Missing hook event: {event}"

    def test_file_events_exist(self):
        from salt_agent.hooks import HOOK_EVENTS
        for event in ["file_written", "file_edited", "file_deleted", "file_snapshot"]:
            assert event in HOOK_EVENTS, f"Missing hook event: {event}"

    def test_original_events_still_present(self):
        from salt_agent.hooks import HOOK_EVENTS
        originals = [
            "pre_tool_use", "post_tool_use", "pre_api_call", "post_api_call",
            "on_text_chunk", "on_error", "on_complete", "on_compaction",
            "on_permission_request",
        ]
        for event in originals:
            assert event in HOOK_EVENTS, f"Original event missing: {event}"

    def test_no_duplicate_events(self):
        from salt_agent.hooks import HOOK_EVENTS
        assert len(HOOK_EVENTS) == len(set(HOOK_EVENTS)), "Duplicate hook events found"

    def test_fire_new_event_types(self):
        """All new events can be fired without error."""
        from salt_agent.hooks import HookEngine, HOOK_EVENTS, HookResult

        engine = HookEngine()
        fired = []

        def listener(data):
            fired.append(data.get("event_name"))
            return HookResult(action="allow")

        new_events = [
            "session_start", "session_end", "session_resume",
            "turn_start", "turn_end", "turn_cancel",
            "memory_saved", "memory_deleted", "memory_surfaced",
            "subagent_start", "subagent_end",
            "task_created", "task_completed", "task_failed",
            "context_compacted", "context_emergency",
            "file_written", "file_edited", "file_deleted", "file_snapshot",
        ]
        for event in new_events:
            engine.on(event, listener)

        for event in new_events:
            result = engine.fire(event, {"event_name": event})
            assert result.action == "allow"

        assert len(fired) == len(new_events)
        assert set(fired) == set(new_events)


# ---------------------------------------------------------------------------
# Feature 2: Centralized State Store
# ---------------------------------------------------------------------------

class TestAgentState:
    def test_default_state_values(self):
        from salt_agent.state import AgentState
        state = AgentState()
        assert state.status == "idle"
        assert state.session_id == ""
        assert state.turn_count == 0
        assert state.message_count == 0
        assert state.total_cost == 0.0
        assert state.active_tasks == []
        assert state.files_written == []

    def test_state_fields_are_independent(self):
        """List fields should not be shared across instances."""
        from salt_agent.state import AgentState
        s1 = AgentState()
        s2 = AgentState()
        s1.active_tasks.append("task1")
        assert s2.active_tasks == []


class TestStateStore:
    def test_basic_update(self):
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(status="thinking")
        assert store.state.status == "thinking"

    def test_update_multiple_fields(self):
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(status="thinking", turn_count=3, session_id="abc")
        assert store.state.status == "thinking"
        assert store.state.turn_count == 3
        assert store.state.session_id == "abc"

    def test_subscriber_notified(self):
        from salt_agent.state import StateStore
        store = StateStore()
        changes = []
        store.subscribe(lambda field, value: changes.append((field, value)))
        store.update(status="executing_tool")
        assert changes == [("status", "executing_tool")]

    def test_subscriber_not_called_when_value_unchanged(self):
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(status="thinking")
        changes = []
        store.subscribe(lambda field, value: changes.append((field, value)))
        store.update(status="thinking")  # same value
        assert changes == []

    def test_multiple_subscribers(self):
        from salt_agent.state import StateStore
        store = StateStore()
        c1, c2 = [], []
        store.subscribe(lambda f, v: c1.append(f))
        store.subscribe(lambda f, v: c2.append(f))
        store.update(turn_count=1)
        assert c1 == ["turn_count"]
        assert c2 == ["turn_count"]

    def test_subscriber_exception_does_not_crash(self):
        from salt_agent.state import StateStore
        store = StateStore()

        def bad_cb(field, value):
            raise RuntimeError("boom")

        good_results = []
        store.subscribe(bad_cb)
        store.subscribe(lambda f, v: good_results.append(f))
        store.update(status="error")
        assert good_results == ["status"]

    def test_unsubscribe(self):
        from salt_agent.state import StateStore
        store = StateStore()
        changes = []
        cb = lambda f, v: changes.append(f)
        store.subscribe(cb)
        store.update(status="x")
        assert len(changes) == 1
        store.unsubscribe(cb)
        store.update(status="y")
        assert len(changes) == 1  # not called after unsubscribe

    def test_get_field(self):
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(session_id="test123")
        assert store.get("session_id") == "test123"
        assert store.get("nonexistent_field") is None

    def test_snapshot(self):
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(status="thinking", turn_count=5)
        snap = store.snapshot()
        assert isinstance(snap, dict)
        assert snap["status"] == "thinking"
        assert snap["turn_count"] == 5
        assert "session_id" in snap

    def test_ignore_unknown_fields(self):
        from salt_agent.state import StateStore
        store = StateStore()
        # Should not raise
        store.update(nonexistent_field="test")
        assert not hasattr(store.state, "nonexistent_field") or store.get("nonexistent_field") is None

    def test_list_field_update(self):
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(files_written=["a.py", "b.py"])
        assert store.state.files_written == ["a.py", "b.py"]

    def test_state_store_in_agent(self):
        """Agent should have a state attribute that is a StateStore."""
        from salt_agent.state import StateStore
        from salt_agent.agent import SaltAgent
        from salt_agent.config import AgentConfig

        config = AgentConfig(
            provider="anthropic",
            api_key="test",
            persist=False,
            working_directory="/tmp",
            enable_mcp=False,
        )
        with patch("salt_agent.providers.anthropic.AnthropicAdapter"):
            agent = SaltAgent(config)
        assert isinstance(agent.state, StateStore)
        assert agent.state.state.status == "idle"

    def test_budget_remaining_updates(self):
        """budget_remaining should update when total_cost changes."""
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(budget_remaining=5.0)
        assert store.state.budget_remaining == 5.0

    def test_files_read_tracks(self):
        """files_read state field should track read files."""
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(files_read=["a.py"])
        assert store.state.files_read == ["a.py"]
        store.update(files_read=["a.py", "b.py"])
        assert store.state.files_read == ["a.py", "b.py"]

    def test_mcp_state_fields(self):
        """mcp_servers and mcp_tools_count should be settable."""
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(mcp_servers=["puppeteer", "fs"], mcp_tools_count=5)
        assert store.state.mcp_servers == ["puppeteer", "fs"]
        assert store.state.mcp_tools_count == 5

    def test_active_tasks_and_subagents(self):
        """active_tasks and active_subagents should be settable."""
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(active_tasks=["t1", "t2"], active_subagents=3)
        assert store.state.active_tasks == ["t1", "t2"]
        assert store.state.active_subagents == 3

    def test_memory_files_count(self):
        from salt_agent.state import StateStore
        store = StateStore()
        store.update(memory_files_count=7)
        assert store.state.memory_files_count == 7

    def test_status_subscriber_for_status_bar(self):
        """Simulate cli.py status bar subscription pattern."""
        from salt_agent.state import StateStore
        store = StateStore()
        status_changes = []

        def on_change(field, value):
            if field == "status":
                status_changes.append(value)

        store.subscribe(on_change)
        store.update(status="thinking")
        store.update(status="executing_tool")
        store.update(current_tool="read")  # should NOT trigger
        store.update(status="idle")

        assert status_changes == ["thinking", "executing_tool", "idle"]


# ---------------------------------------------------------------------------
# Feature 3: Plugin entry_points Discovery
# ---------------------------------------------------------------------------

class TestPluginEntryPoints:
    def test_discover_calls_entry_points(self):
        """PluginManager.discover should attempt entry_points discovery."""
        from salt_agent.plugins import PluginManager, SaltPlugin

        class FakePlugin(SaltPlugin):
            def name(self): return "fake-ep-plugin"

        mgr = PluginManager(plugin_dirs=[])

        # Mock entry_points to return our fake plugin
        fake_ep = MagicMock()
        fake_ep.name = "fake"
        fake_ep.load.return_value = FakePlugin

        with patch("importlib.metadata.entry_points", return_value=[fake_ep]):
            plugins = mgr.discover()

        # Should have loaded the plugin from entry_points
        assert any(p.name() == "fake-ep-plugin" for p in plugins)

    def test_entry_points_error_does_not_crash(self):
        """Errors in entry_point loading should be captured, not raised."""
        from salt_agent.plugins import PluginManager

        mgr = PluginManager(plugin_dirs=[])

        with patch("importlib.metadata.entry_points", side_effect=ImportError("no metadata")):
            plugins = mgr.discover()

        assert plugins == []
        assert len(mgr.errors) > 0

    def test_entry_point_bad_class_captured(self):
        """An entry_point that doesn't return a SaltPlugin subclass is skipped."""
        from salt_agent.plugins import PluginManager

        fake_ep = MagicMock()
        fake_ep.name = "bad"
        fake_ep.load.return_value = str  # Not a SaltPlugin

        mgr = PluginManager(plugin_dirs=[])
        with patch("importlib.metadata.entry_points", return_value=[fake_ep]):
            plugins = mgr.discover()

        # str is not a SaltPlugin subclass, so no plugins loaded
        assert len(plugins) == 0

    def test_entry_point_instantiation_failure(self):
        """An entry_point class that fails to instantiate is captured."""
        from salt_agent.plugins import PluginManager, SaltPlugin

        class BadPlugin(SaltPlugin):
            def __init__(self):
                raise RuntimeError("init failed")
            def name(self): return "bad"

        fake_ep = MagicMock()
        fake_ep.name = "bad"
        fake_ep.load.return_value = BadPlugin

        mgr = PluginManager(plugin_dirs=[])
        with patch("importlib.metadata.entry_points", return_value=[fake_ep]):
            plugins = mgr.discover()

        assert len(plugins) == 0
        assert any("bad" in e for e in mgr.errors)

    def test_mixed_entry_points_and_directory(self, tmp_path: Path):
        """Both entry_points and directory plugins are discovered."""
        from salt_agent.plugins import PluginManager, SaltPlugin

        class EPPlugin(SaltPlugin):
            def name(self): return "ep-plugin"

        # Create a directory plugin
        plugin_code = '''
from salt_agent.plugins import SaltPlugin

class DirPlugin(SaltPlugin):
    def name(self): return "dir-plugin"
'''
        (tmp_path / "dir_plugin.py").write_text(plugin_code)

        fake_ep = MagicMock()
        fake_ep.name = "ep"
        fake_ep.load.return_value = EPPlugin

        mgr = PluginManager(plugin_dirs=[str(tmp_path)])
        with patch("importlib.metadata.entry_points", return_value=[fake_ep]):
            plugins = mgr.discover()

        names = {p.name() for p in plugins}
        assert "ep-plugin" in names
        assert "dir-plugin" in names


# ---------------------------------------------------------------------------
# Feature 4: Skill Conditional Activation
# ---------------------------------------------------------------------------

def _create_skill_dir(base: Path, name: str, content: str) -> Path:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


class TestSkillMetadata:
    def test_skill_has_metadata(self, tmp_path: Path):
        from salt_agent.skills.manager import SkillManager
        content = (
            "---\nname: test\ndescription: Test\n"
            "metadata:\n  requires:\n    bins: [git]\n"
            "---\nBody."
        )
        _create_skill_dir(tmp_path, "test", content)
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        skill = mgr.get("test")
        assert skill is not None
        assert skill.metadata is not None
        assert "metadata" in skill.metadata

    def test_skill_without_metadata(self, tmp_path: Path):
        from salt_agent.skills.manager import SkillManager
        content = "---\nname: simple\n---\nSimple skill."
        _create_skill_dir(tmp_path, "simple", content)
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        skill = mgr.get("simple")
        assert skill is not None


class TestSkillShouldActivate:
    def test_no_requirements_always_activates(self):
        from salt_agent.skills.manager import Skill, SkillManager
        skill = Skill(name="test", description="", content="", path=Path("."))
        assert SkillManager._should_activate(skill) is True

    def test_empty_metadata_activates(self):
        from salt_agent.skills.manager import Skill, SkillManager
        skill = Skill(name="test", description="", content="", path=Path("."), metadata={})
        assert SkillManager._should_activate(skill) is True

    def test_required_binary_present(self):
        from salt_agent.skills.manager import Skill, SkillManager
        # 'python3' or 'python' should exist in most test environments
        skill = Skill(
            name="test", description="", content="", path=Path("."),
            metadata={"requires": {"bins": ["python3"]}},
        )
        assert SkillManager._should_activate(skill) is True

    def test_required_binary_missing(self):
        from salt_agent.skills.manager import Skill, SkillManager
        skill = Skill(
            name="test", description="", content="", path=Path("."),
            metadata={"requires": {"bins": ["nonexistent_binary_xyz_123"]}},
        )
        assert SkillManager._should_activate(skill) is False

    def test_required_env_var_present(self):
        from salt_agent.skills.manager import Skill, SkillManager
        os.environ["SALT_TEST_VAR"] = "1"
        try:
            skill = Skill(
                name="test", description="", content="", path=Path("."),
                metadata={"requires": {"env": ["SALT_TEST_VAR"]}},
            )
            assert SkillManager._should_activate(skill) is True
        finally:
            del os.environ["SALT_TEST_VAR"]

    def test_required_env_var_missing(self):
        from salt_agent.skills.manager import Skill, SkillManager
        skill = Skill(
            name="test", description="", content="", path=Path("."),
            metadata={"requires": {"env": ["NONEXISTENT_ENV_VAR_XYZ"]}},
        )
        assert SkillManager._should_activate(skill) is False

    def test_os_platform_match(self):
        from salt_agent.skills.manager import Skill, SkillManager
        skill = Skill(
            name="test", description="", content="", path=Path("."),
            metadata={"os": [sys.platform]},
        )
        assert SkillManager._should_activate(skill) is True

    def test_os_platform_no_match(self):
        from salt_agent.skills.manager import Skill, SkillManager
        skill = Skill(
            name="test", description="", content="", path=Path("."),
            metadata={"os": ["fake_os_that_does_not_exist"]},
        )
        assert SkillManager._should_activate(skill) is False

    def test_combined_requirements_all_met(self):
        from salt_agent.skills.manager import Skill, SkillManager
        os.environ["SALT_COMBO_TEST"] = "1"
        try:
            skill = Skill(
                name="test", description="", content="", path=Path("."),
                metadata={
                    "requires": {
                        "bins": ["python3"],
                        "env": ["SALT_COMBO_TEST"],
                    },
                    "os": [sys.platform],
                },
            )
            assert SkillManager._should_activate(skill) is True
        finally:
            del os.environ["SALT_COMBO_TEST"]

    def test_combined_requirements_one_fails(self):
        from salt_agent.skills.manager import Skill, SkillManager
        skill = Skill(
            name="test", description="", content="", path=Path("."),
            metadata={
                "requires": {
                    "bins": ["python3"],
                    "env": ["NONEXISTENT_COMBO_VAR"],
                },
            },
        )
        assert SkillManager._should_activate(skill) is False

    def test_skill_filtered_during_discover(self, tmp_path: Path):
        """Skills with unmet requirements are not discovered."""
        from salt_agent.skills.manager import SkillManager
        content = (
            "---\nname: needs-fake\ndescription: Needs fake binary\n"
            "metadata:\n  requires:\n    bins: [fake_binary_not_found]\n"
            "---\nBody."
        )
        _create_skill_dir(tmp_path, "needs-fake", content)
        mgr = SkillManager(extra_dirs=[str(tmp_path)])
        assert mgr.get("needs-fake") is None


class TestFrontmatterParsing:
    def test_parse_nested_metadata(self):
        from salt_agent.skills.manager import SkillManager
        text = "name: commit\ndescription: Create a commit\nmetadata:\n  requires:\n    bins: [git]"
        result = SkillManager._parse_frontmatter(text)
        assert result["name"] == "commit"
        assert result["description"] == "Create a commit"
        assert isinstance(result["metadata"], dict)
        assert "requires" in result["metadata"]

    def test_parse_inline_list(self):
        from salt_agent.skills.manager import SkillManager
        text = "os: [darwin, linux]"
        result = SkillManager._parse_frontmatter(text)
        assert result["os"] == ["darwin", "linux"]

    def test_parse_simple_key_value(self):
        from salt_agent.skills.manager import SkillManager
        text = "name: test\ndescription: A test"
        result = SkillManager._parse_frontmatter(text)
        assert result["name"] == "test"
        assert result["description"] == "A test"

    def test_parse_empty(self):
        from salt_agent.skills.manager import SkillManager
        result = SkillManager._parse_frontmatter("")
        assert result == {}


# ---------------------------------------------------------------------------
# Integration: hooks fired from task manager
# ---------------------------------------------------------------------------

class TestTaskManagerHooks:
    def test_task_created_hook_fires(self):
        from salt_agent.tasks.manager import TaskManager
        from salt_agent.hooks import HookEngine

        parent = MagicMock()
        parent.hooks = HookEngine()
        parent.config.provider = "anthropic"
        parent.config.model = "test"
        parent.config.api_key = "key"
        parent.config.working_directory = "/tmp"

        fired = []
        parent.hooks.on("task_created", lambda d: fired.append(d))

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            from salt_agent.events import AgentComplete, TextChunk
            agent_mock = MagicMock()
            async def fake_run(prompt):
                yield TextChunk(text="done")
                yield AgentComplete(final_text="done", turns=1, tools_used=[])
            agent_mock.run = fake_run
            mock_factory.return_value = lambda **kw: agent_mock

            mgr = TaskManager(parent)
            task = mgr.create_task("test task")

        assert len(fired) == 1
        assert fired[0]["task_id"] == task.id

    def test_task_completed_hook_fires(self):
        from salt_agent.tasks.manager import TaskManager
        from salt_agent.hooks import HookEngine

        parent = MagicMock()
        parent.hooks = HookEngine()
        parent.config.provider = "anthropic"
        parent.config.model = "test"
        parent.config.api_key = "key"
        parent.config.working_directory = "/tmp"

        fired = []
        parent.hooks.on("task_completed", lambda d: fired.append(d))

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            from salt_agent.events import AgentComplete, TextChunk
            agent_mock = MagicMock()
            async def fake_run(prompt):
                yield TextChunk(text="done")
                yield AgentComplete(final_text="done", turns=1, tools_used=[])
            agent_mock.run = fake_run
            mock_factory.return_value = lambda **kw: agent_mock

            mgr = TaskManager(parent)
            task = mgr.create_task("test task")
            task._thread.join(timeout=5)

        assert len(fired) == 1
        assert fired[0]["task_id"] == task.id

    def test_task_failed_hook_fires(self):
        from salt_agent.tasks.manager import TaskManager
        from salt_agent.hooks import HookEngine

        parent = MagicMock()
        parent.hooks = HookEngine()
        parent.config.provider = "anthropic"
        parent.config.model = "test"
        parent.config.api_key = "key"
        parent.config.working_directory = "/tmp"

        fired = []
        parent.hooks.on("task_failed", lambda d: fired.append(d))

        with patch("salt_agent.subagent._get_create_agent") as mock_factory:
            agent_mock = MagicMock()
            async def fake_run(prompt):
                raise RuntimeError("boom")
                yield  # noqa
            agent_mock.run = fake_run
            mock_factory.return_value = lambda **kw: agent_mock

            mgr = TaskManager(parent)
            task = mgr.create_task("failing task")
            task._thread.join(timeout=5)

        assert len(fired) == 1
        assert "boom" in fired[0]["error"]
