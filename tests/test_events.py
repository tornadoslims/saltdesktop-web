"""Tests for runtime.jb_events — event emission and filtering."""
from __future__ import annotations

from runtime.jb_events import emit_event, read_events, filter_events


class TestEmitEvent:
    def test_returns_event(self, tmp_data):
        event = emit_event("test_event")
        assert event["event_type"] == "test_event"
        assert event["ts"] is not None

    def test_with_ids(self, tmp_data):
        event = emit_event(
            "test_event",
            mission_id="m1",
            task_id="t1",
        )
        assert event["mission_id"] == "m1"
        assert event["task_id"] == "t1"

    def test_with_payload(self, tmp_data):
        event = emit_event("test_event", payload={"key": "value"})
        assert event["payload"]["key"] == "value"

    def test_persisted(self, tmp_data):
        emit_event("first")
        emit_event("second")
        events = read_events()
        assert len(events) == 2


class TestReadEvents:
    def test_empty(self, tmp_data):
        assert read_events() == []

    def test_order(self, tmp_data):
        emit_event("first")
        emit_event("second")
        events = read_events()
        assert events[0]["event_type"] == "first"
        assert events[1]["event_type"] == "second"


class TestFilterEvents:
    def test_by_type(self, tmp_data):
        emit_event("alpha")
        emit_event("beta")
        emit_event("alpha")
        results = filter_events(event_type="alpha")
        assert len(results) == 2

    def test_by_task_id(self, tmp_data):
        emit_event("x", task_id="t1")
        emit_event("x", task_id="t2")
        results = filter_events(task_id="t1")
        assert len(results) == 1

    def test_by_mission_id(self, tmp_data):
        emit_event("x", mission_id="m1")
        emit_event("x", mission_id="m2")
        results = filter_events(mission_id="m1")
        assert len(results) == 1

    def test_combined_filter(self, tmp_data):
        emit_event("x", task_id="t1", mission_id="m1")
        emit_event("x", task_id="t1", mission_id="m2")
        emit_event("x", task_id="t2", mission_id="m1")
        results = filter_events(task_id="t1", mission_id="m1")
        assert len(results) == 1
