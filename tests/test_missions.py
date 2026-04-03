"""Tests for runtime.jb_missions — mission CRUD and task linking."""
from __future__ import annotations

import pytest

from runtime.jb_missions import (
    create_mission,
    get_mission,
    list_missions,
    attach_task,
    mark_mission_status,
    update_mission_summary,
    add_source_artifact,
    mark_deployed,
    mark_undeployed,
)


# -- Basic CRUD ------------------------------------------------------------

class TestCreateMission:
    def test_returns_id(self, tmp_data):
        mid = create_mission(goal="Build the thing")
        assert isinstance(mid, str)
        assert len(mid) > 0

    def test_default_active(self, tmp_data):
        mid = create_mission(goal="Build the thing")
        m = get_mission(mid)
        assert m["status"] == "planning"

    def test_preserves_goal(self, tmp_data):
        mid = create_mission(goal="Integrate Telegram")
        m = get_mission(mid)
        assert m["goal"] == "Integrate Telegram"

    def test_with_constraints(self, tmp_data):
        mid = create_mission(goal="Build", constraints=["no external deps", "python only"])
        m = get_mission(mid)
        assert len(m["constraints"]) == 2
        assert "python only" in m["constraints"]

    def test_with_summary(self, tmp_data):
        mid = create_mission(goal="Build", summary="A brief summary")
        m = get_mission(mid)
        assert m["summary"] == "A brief summary"

    def test_empty_goal_raises(self, tmp_data):
        with pytest.raises(ValueError, match="non-empty string"):
            create_mission(goal="")

    def test_invalid_status_raises(self, tmp_data):
        with pytest.raises(ValueError, match="Invalid mission status"):
            create_mission(goal="Build", status="bogus")


class TestGetMission:
    def test_existing(self, tmp_data):
        mid = create_mission(goal="Test")
        assert get_mission(mid) is not None

    def test_nonexistent(self, tmp_data):
        assert get_mission("does-not-exist") is None


class TestListMissions:
    def test_empty(self, tmp_data):
        assert list_missions() == []

    def test_returns_all(self, tmp_data):
        create_mission(goal="One")
        create_mission(goal="Two")
        assert len(list_missions()) == 2


# -- Status -----------------------------------------------------------------

class TestMissionStatus:
    def test_mark_completed(self, tmp_data):
        mid = create_mission(goal="Build")
        result = mark_mission_status(mid, "complete")
        assert result["status"] == "complete"

    def test_mark_paused(self, tmp_data):
        mid = create_mission(goal="Build")
        result = mark_mission_status(mid, "blocked")
        assert result["status"] == "blocked"

    def test_invalid_status_raises(self, tmp_data):
        mid = create_mission(goal="Build")
        with pytest.raises(ValueError, match="Invalid mission status"):
            mark_mission_status(mid, "bogus")

    def test_nonexistent_raises(self, tmp_data):
        with pytest.raises(ValueError, match="Mission not found"):
            mark_mission_status("nope", "active")


# -- Task linking -----------------------------------------------------------

class TestAttachTask:
    def test_attach_task(self, tmp_data):
        mid = create_mission(goal="Build")
        result = attach_task(mid, "task-1")
        assert "task-1" in result["task_ids"]

    def test_attach_multiple(self, tmp_data):
        mid = create_mission(goal="Build")
        attach_task(mid, "task-1")
        result = attach_task(mid, "task-2")
        assert result["task_ids"] == ["task-1", "task-2"]

    def test_no_duplicates(self, tmp_data):
        mid = create_mission(goal="Build")
        attach_task(mid, "task-1")
        result = attach_task(mid, "task-1")
        assert result["task_ids"].count("task-1") == 1

    def test_nonexistent_mission_raises(self, tmp_data):
        with pytest.raises(ValueError, match="Mission not found"):
            attach_task("nope", "task-1")


# -- Summary ----------------------------------------------------------------

class TestUpdateSummary:
    def test_set_summary(self, tmp_data):
        mid = create_mission(goal="Build")
        result = update_mission_summary(mid, "Progress is good")
        assert result["summary"] == "Progress is good"

    def test_clear_summary(self, tmp_data):
        mid = create_mission(goal="Build", summary="Old")
        result = update_mission_summary(mid, None)
        assert result["summary"] is None


# -- Source artifacts -------------------------------------------------------

class TestSourceArtifacts:
    def test_add_artifact(self, tmp_data):
        mid = create_mission(goal="Build")
        result = add_source_artifact(mid, "file", "/path/to/thing", description="the thing")
        assert len(result["source_artifacts"]) == 1
        assert result["source_artifacts"][0]["type"] == "file"
        assert result["source_artifacts"][0]["path"] == "/path/to/thing"

    def test_add_multiple(self, tmp_data):
        mid = create_mission(goal="Build")
        add_source_artifact(mid, "file", "/a")
        result = add_source_artifact(mid, "url", "/b")
        assert len(result["source_artifacts"]) == 2


# -- Deployment workflow ----------------------------------------------------

class TestDeployedStatus:
    def test_mark_deployed_from_complete(self, tmp_data):
        mid = create_mission(goal="Build")
        mark_mission_status(mid, "complete")
        result = mark_deployed(mid)
        assert result["status"] == "deployed"

    def test_mark_deployed_persists(self, tmp_data):
        mid = create_mission(goal="Build")
        mark_mission_status(mid, "complete")
        mark_deployed(mid)
        m = get_mission(mid)
        assert m["status"] == "deployed"

    def test_mark_deployed_from_planning_raises(self, tmp_data):
        mid = create_mission(goal="Build")
        with pytest.raises(ValueError, match="Can only deploy from 'complete'"):
            mark_deployed(mid)

    def test_mark_deployed_from_active_raises(self, tmp_data):
        mid = create_mission(goal="Build", status="active")
        with pytest.raises(ValueError, match="Can only deploy from 'complete'"):
            mark_deployed(mid)

    def test_mark_deployed_nonexistent_raises(self, tmp_data):
        with pytest.raises(ValueError, match="Mission not found"):
            mark_deployed("nonexistent")

    def test_mark_undeployed(self, tmp_data):
        mid = create_mission(goal="Build")
        mark_mission_status(mid, "complete")
        mark_deployed(mid)
        result = mark_undeployed(mid)
        assert result["status"] == "complete"

    def test_mark_undeployed_from_complete_raises(self, tmp_data):
        mid = create_mission(goal="Build")
        mark_mission_status(mid, "complete")
        with pytest.raises(ValueError, match="Can only undeploy from 'deployed'"):
            mark_undeployed(mid)

    def test_mark_undeployed_nonexistent_raises(self, tmp_data):
        with pytest.raises(ValueError, match="Mission not found"):
            mark_undeployed("nonexistent")
