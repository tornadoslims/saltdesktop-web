"""Tests for runtime.jb_plan_generate — idempotent regeneration, graph diff, component catalog."""
from __future__ import annotations

import json
from copy import deepcopy
from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import make_task

from runtime.jb_plan_generate import (
    _store_previous_draft,
    _build_previous_graph_context,
    _get_messages_since,
    compute_graph_diff,
    _build_component_catalog,
    build_generation_prompt,
    parse_items_from_response,
    generate_mission_plan,
)
from runtime.jb_missions import create_mission, get_mission, _update_mission


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_COMPONENTS = [
    {
        "name": "Gmail Connector",
        "type": "connector",
        "description": "Fetches emails from Gmail",
        "input_type": None,
        "output_type": "List[Email]",
        "config_fields": {"credentials_path": "str", "max_results": "int = 10"},
    },
    {
        "name": "Email Filter",
        "type": "processor",
        "description": "Filters emails by rules",
        "input_type": "List[Email]",
        "output_type": "List[Email]",
        "config_fields": {"filter_rules": "dict"},
    },
]

SAMPLE_CONNECTIONS = [
    {"from": "Gmail Connector", "to": "Email Filter", "label": "raw emails"},
]

SAMPLE_ITEMS = [
    {"goal": "Build Gmail connector", "type": "coding", "component": "Gmail Connector", "priority": 8},
    {"goal": "Build email filter", "type": "coding", "component": "Email Filter", "priority": 7},
]


# ---------------------------------------------------------------------------
# G1: Idempotent regeneration
# ---------------------------------------------------------------------------

class TestStorePreviousDraft:
    def test_stores_items_and_components(self, tmp_data):
        mission = {
            "items": SAMPLE_ITEMS,
            "components": SAMPLE_COMPONENTS,
            "connections": SAMPLE_CONNECTIONS,
        }
        result = _store_previous_draft(mission)
        assert result is not None
        assert len(result["items"]) == 2
        assert len(result["components"]) == 2
        assert len(result["connections"]) == 1

    def test_returns_none_when_empty(self, tmp_data):
        mission = {"items": [], "components": [], "connections": []}
        result = _store_previous_draft(mission)
        assert result is None

    def test_returns_none_when_missing(self, tmp_data):
        mission = {}
        result = _store_previous_draft(mission)
        assert result is None

    def test_deep_copies_data(self, tmp_data):
        items = [{"goal": "test", "type": "coding"}]
        mission = {"items": items, "components": [{"name": "X", "type": "processor"}]}
        result = _store_previous_draft(mission)
        # Mutating original should not affect draft
        items[0]["goal"] = "changed"
        assert result["items"][0]["goal"] == "test"


class TestClearDraft:
    def test_clears_mission_draft(self, tmp_data):
        mid = create_mission(goal="Test mission", status="planning")
        _update_mission(mid, {
            "items": SAMPLE_ITEMS,
            "components": SAMPLE_COMPONENTS,
            "connections": SAMPLE_CONNECTIONS,
        })
        from runtime.jb_plan_generate import _clear_draft
        _clear_draft(mid)

        mission = get_mission(mid)
        assert mission["items"] == []
        assert mission["components"] == []
        assert mission["connections"] == []


# ---------------------------------------------------------------------------
# G3: Previous graph context
# ---------------------------------------------------------------------------

class TestBuildPreviousGraphContext:
    def test_builds_context_from_previous_draft(self, tmp_data):
        mission = {
            "_previous_draft": {
                "components": SAMPLE_COMPONENTS,
                "connections": SAMPLE_CONNECTIONS,
            }
        }
        result = _build_previous_graph_context(mission)
        assert "Previous Architecture" in result
        assert "Gmail Connector" in result
        assert "Email Filter" in result
        assert "raw emails" in result

    def test_returns_empty_when_no_draft(self, tmp_data):
        assert _build_previous_graph_context({}) == ""
        assert _build_previous_graph_context({"_previous_draft": None}) == ""

    def test_returns_empty_when_no_components(self, tmp_data):
        mission = {"_previous_draft": {"components": [], "connections": []}}
        assert _build_previous_graph_context(mission) == ""

    def test_includes_config_fields(self, tmp_data):
        mission = {
            "_previous_draft": {
                "components": [SAMPLE_COMPONENTS[0]],
                "connections": [],
            }
        }
        result = _build_previous_graph_context(mission)
        assert "credentials_path" in result
        assert "max_results" in result


class TestGetMessagesSince:
    def test_filters_by_timestamp(self, tmp_data):
        history = [
            {"role": "user", "content": "Old message that is long enough", "timestamp": "2026-03-01T00:00:00Z"},
            {"role": "user", "content": "New message after generation happened", "timestamp": "2026-03-30T00:00:00Z"},
        ]
        result = _get_messages_since(history, "2026-03-15T00:00:00Z")
        assert "New message" in result
        assert "Old message" not in result

    def test_returns_empty_for_no_history(self, tmp_data):
        assert _get_messages_since([], "2026-03-15T00:00:00Z") == ""

    def test_returns_empty_for_no_timestamp(self, tmp_data):
        history = [{"role": "user", "content": "Some long enough message", "timestamp": "2026-03-30T00:00:00Z"}]
        assert _get_messages_since(history, None) == ""


# ---------------------------------------------------------------------------
# G4: Graph diff
# ---------------------------------------------------------------------------

class TestComputeGraphDiff:
    def test_all_added_when_no_previous(self, tmp_data):
        mission = {
            "components": SAMPLE_COMPONENTS,
            "_previous_draft": None,
        }
        diff = compute_graph_diff(mission)
        assert len(diff) == 2
        assert all(d["change"] == "added" for d in diff)

    def test_unchanged_components(self, tmp_data):
        mission = {
            "components": SAMPLE_COMPONENTS,
            "_previous_draft": {"components": deepcopy(SAMPLE_COMPONENTS)},
        }
        diff = compute_graph_diff(mission)
        assert all(d["change"] == "unchanged" for d in diff)

    def test_detects_added_component(self, tmp_data):
        prev = [SAMPLE_COMPONENTS[0]]
        curr = deepcopy(SAMPLE_COMPONENTS)  # has 2 components
        mission = {
            "components": curr,
            "_previous_draft": {"components": prev},
        }
        diff = compute_graph_diff(mission)
        added = [d for d in diff if d["change"] == "added"]
        assert len(added) == 1
        assert added[0]["name"] == "Email Filter"

    def test_detects_removed_component(self, tmp_data):
        prev = deepcopy(SAMPLE_COMPONENTS)  # has 2
        curr = [SAMPLE_COMPONENTS[0]]  # has 1
        mission = {
            "components": curr,
            "_previous_draft": {"components": prev},
        }
        diff = compute_graph_diff(mission)
        removed = [d for d in diff if d["change"] == "removed"]
        assert len(removed) == 1
        assert removed[0]["name"] == "Email Filter"

    def test_detects_modified_component(self, tmp_data):
        prev = deepcopy(SAMPLE_COMPONENTS)
        curr = deepcopy(SAMPLE_COMPONENTS)
        curr[0]["output_type"] = "List[FilteredEmail]"  # changed
        mission = {
            "components": curr,
            "_previous_draft": {"components": prev},
        }
        diff = compute_graph_diff(mission)
        gmail = [d for d in diff if d["name"] == "Gmail Connector"]
        assert len(gmail) == 1
        assert gmail[0]["change"] == "modified"

    def test_empty_components(self, tmp_data):
        mission = {"components": [], "_previous_draft": {"components": []}}
        diff = compute_graph_diff(mission)
        assert diff == []


# ---------------------------------------------------------------------------
# E4: Component catalog
# ---------------------------------------------------------------------------

class TestBuildComponentCatalog:
    def test_returns_empty_when_no_components(self, tmp_data):
        with patch("runtime.jb_plan_generate.list_components", return_value=[]):
            result = _build_component_catalog()
        assert result == ""

    def test_filters_to_reusable_statuses(self, tmp_data):
        components = [
            {"component_id": "c1", "workspace_id": "w1", "name": "Built One", "type": "connector",
             "status": "built", "contract": {"output_type": "List[Email]", "config_fields": {"key": "str"}}},
            {"component_id": "c2", "workspace_id": "w1", "name": "Planned One", "type": "processor",
             "status": "planned", "contract": {}},
            {"component_id": "c3", "workspace_id": "w1", "name": "Deployed One", "type": "ai",
             "status": "deployed", "contract": {"output_type": "Analysis", "config_fields": {}}},
        ]
        with patch("runtime.jb_plan_generate.list_components", return_value=components):
            result = _build_component_catalog()

        assert "Built One" in result
        assert "Deployed One" in result
        assert "Planned One" not in result
        assert "Available components" in result

    def test_caps_at_20(self, tmp_data):
        components = [
            {"component_id": f"c{i}", "workspace_id": "w1", "name": f"Comp {i}", "type": "processor",
             "status": "built", "contract": {"output_type": "Any", "config_fields": {}}}
            for i in range(30)
        ]
        with patch("runtime.jb_plan_generate.list_components", return_value=components):
            result = _build_component_catalog()

        # Should have header + 20 component lines
        lines = result.strip().split("\n")
        assert len(lines) == 21  # 1 header + 20 components


# ---------------------------------------------------------------------------
# Generation prompt
# ---------------------------------------------------------------------------

class TestBuildGenerationPrompt:
    def test_basic_prompt(self, tmp_data):
        prompt = build_generation_prompt(
            mission_goal="Build email checker",
            chat_history=[],
            existing_items=[],
        )
        assert "Build email checker" in prompt
        assert "components" in prompt

    def test_includes_previous_context_on_regen(self, tmp_data):
        mission = {
            "_previous_draft": {
                "components": SAMPLE_COMPONENTS,
                "connections": SAMPLE_CONNECTIONS,
            },
        }
        with patch("runtime.jb_plan_generate._build_component_catalog", return_value=""):
            prompt = build_generation_prompt(
                mission_goal="Build email checker",
                chat_history=[],
                existing_items=[],
                mission=mission,
            )
        assert "Previous Architecture" in prompt
        assert "Gmail Connector" in prompt

    def test_includes_catalog(self, tmp_data):
        catalog = "Available components you can reuse:\n- Gmail Connector (connector): output=List[Email]"
        with patch("runtime.jb_plan_generate._build_component_catalog", return_value=catalog):
            prompt = build_generation_prompt(
                mission_goal="Build something",
                chat_history=[],
                existing_items=[],
            )
        assert "Available components you can reuse" in prompt
        assert "Gmail Connector" in prompt


# ---------------------------------------------------------------------------
# Full generation flow (mocked worker)
# ---------------------------------------------------------------------------

class TestGenerateMissionPlan:
    def _mock_worker_response(self):
        return json.dumps({
            "components": [
                {"name": "Fetcher", "type": "connector", "description": "Fetches data",
                 "output_type": "List[Data]", "config_fields": {"url": "str"}},
            ],
            "connections": [],
            "tasks": [
                {"goal": "Build the fetcher component", "type": "coding", "component": "Fetcher", "priority": 8},
            ],
        })

    def test_first_generation(self, tmp_data):
        mid = create_mission(goal="Build a data pipeline", status="planning")

        with patch("runtime.jb_plan_generate.call_worker") as mock_worker, \
             patch("runtime.jb_plan_generate._build_component_catalog", return_value=""):
            mock_worker.return_value = {"ok": True, "text": self._mock_worker_response()}
            result = generate_mission_plan(mid)

        assert result["ok"] is True
        assert result["item_count"] == 1
        assert result["diff"] is None  # No previous draft

    def test_regeneration_stores_previous_draft(self, tmp_data):
        mid = create_mission(goal="Build a data pipeline", status="planning")

        # First generation
        _update_mission(mid, {
            "items": [{"item_id": "i1", "title": "Old task", "goal": "Old task", "type": "coding",
                        "component": "", "constraints": [], "dependencies": [], "priority": 5}],
            "components": [{"name": "OldComp", "type": "processor"}],
            "connections": [],
        })

        with patch("runtime.jb_plan_generate.call_worker") as mock_worker, \
             patch("runtime.jb_plan_generate._build_component_catalog", return_value=""):
            mock_worker.return_value = {"ok": True, "text": self._mock_worker_response()}
            result = generate_mission_plan(mid)

        assert result["ok"] is True
        assert result["diff"] is not None

        # Check that previous draft was stored
        mission = get_mission(mid)
        assert mission["_previous_draft"] is not None
        assert mission["_previous_draft"]["components"][0]["name"] == "OldComp"

    def test_diff_shows_changes(self, tmp_data):
        mid = create_mission(goal="Build a data pipeline", status="planning")

        # Set up existing components
        _update_mission(mid, {
            "items": [{"item_id": "i1", "title": "X", "goal": "Build X", "type": "coding",
                        "component": "OldComp", "constraints": [], "dependencies": [], "priority": 5}],
            "components": [{"name": "OldComp", "type": "processor"}],
            "connections": [],
        })

        with patch("runtime.jb_plan_generate.call_worker") as mock_worker, \
             patch("runtime.jb_plan_generate._build_component_catalog", return_value=""):
            mock_worker.return_value = {"ok": True, "text": self._mock_worker_response()}
            result = generate_mission_plan(mid)

        diff = result["diff"]
        assert diff is not None
        names = {d["name"] for d in diff}
        assert "Fetcher" in names  # added
        assert "OldComp" in names  # removed

        added = [d for d in diff if d["change"] == "added"]
        removed = [d for d in diff if d["change"] == "removed"]
        assert len(added) >= 1
        assert len(removed) >= 1

    def test_not_found(self, tmp_data):
        result = generate_mission_plan("nonexistent")
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_wrong_status(self, tmp_data):
        mid = create_mission(goal="Test", status="planning")
        _update_mission(mid, {"status": "active"})
        result = generate_mission_plan(mid)
        assert result["ok"] is False
        assert "not in planning" in result["error"]


# ---------------------------------------------------------------------------
# Parse items (existing functionality, ensuring no regression)
# ---------------------------------------------------------------------------

class TestParseItemsFromResponse:
    def test_structured_json(self, tmp_data):
        text = json.dumps({
            "components": [{"name": "X", "type": "connector"}],
            "connections": [{"from": "X", "to": "Y"}],
            "tasks": [{"goal": "Do X", "type": "coding"}],
        })
        result = parse_items_from_response(text)
        assert len(result["components"]) == 1
        assert len(result["tasks"]) == 1

    def test_markdown_fenced(self, tmp_data):
        text = "```json\n" + json.dumps({
            "components": [], "connections": [],
            "tasks": [{"goal": "Do X", "type": "coding"}],
        }) + "\n```"
        result = parse_items_from_response(text)
        assert len(result["tasks"]) == 1

    def test_flat_array(self, tmp_data):
        text = json.dumps([{"goal": "Do X", "type": "coding"}])
        result = parse_items_from_response(text)
        assert len(result["tasks"]) == 1
