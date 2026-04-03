"""Tests for runtime.jb_queue — task CRUD and state transitions."""
from __future__ import annotations

import pytest
from tests.conftest import make_task

from runtime.jb_queue import (
    enqueue,
    get_task,
    list_tasks,
    get_pending,
    get_dispatched,
    get_running,
    mark_dispatched,
    mark_running,
    mark_in_progress,
    mark_complete,
    mark_failed,
    mark_suspect,
    mark_needs_review,
    attach_subagent_session,
    attach_external_process,
    touch_external_process,
)


# -- Basic CRUD ------------------------------------------------------------

class TestEnqueue:
    def test_enqueue_returns_id(self, tmp_data):
        task_id = enqueue(make_task())
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    def test_enqueue_sets_pending(self, tmp_data):
        task_id = enqueue(make_task())
        task = get_task(task_id)
        assert task["status"] == "pending"

    def test_enqueue_preserves_goal(self, tmp_data):
        task_id = enqueue(make_task(payload={"goal": "build the thing"}))
        task = get_task(task_id)
        assert task["payload"]["goal"] == "build the thing"

    def test_enqueue_sets_timestamps(self, tmp_data):
        task_id = enqueue(make_task())
        task = get_task(task_id)
        assert task["created_at"] is not None
        assert task["updated_at"] is not None

    def test_enqueue_default_priority(self, tmp_data):
        task_id = enqueue(make_task())
        task = get_task(task_id)
        assert task["priority"] == 5

    def test_enqueue_custom_priority(self, tmp_data):
        task_id = enqueue(make_task(priority=9))
        task = get_task(task_id)
        assert task["priority"] == 9

    def test_enqueue_multiple(self, tmp_data):
        id1 = enqueue(make_task(payload={"goal": "first"}))
        id2 = enqueue(make_task(payload={"goal": "second"}))
        assert id1 != id2
        assert len(list_tasks()) == 2


class TestGetTask:
    def test_get_existing(self, tmp_data):
        task_id = enqueue(make_task())
        assert get_task(task_id) is not None

    def test_get_nonexistent(self, tmp_data):
        assert get_task("does-not-exist") is None


class TestListTasks:
    def test_empty(self, tmp_data):
        assert list_tasks() == []

    def test_returns_all(self, tmp_data):
        enqueue(make_task())
        enqueue(make_task())
        enqueue(make_task())
        assert len(list_tasks()) == 3


# -- Query helpers ----------------------------------------------------------

class TestGetPending:
    def test_returns_only_pending(self, tmp_data):
        id1 = enqueue(make_task())
        id2 = enqueue(make_task())
        mark_dispatched(id1)
        pending = get_pending()
        assert len(pending) == 1
        assert pending[0]["id"] == id2

    def test_sorted_by_priority(self, tmp_data):
        low = enqueue(make_task(priority=1))
        high = enqueue(make_task(priority=9))
        mid = enqueue(make_task(priority=5))
        pending = get_pending()
        assert [t["id"] for t in pending] == [high, mid, low]


class TestGetDispatched:
    def test_returns_only_dispatched(self, tmp_data):
        id1 = enqueue(make_task())
        id2 = enqueue(make_task())
        mark_dispatched(id1)
        dispatched = get_dispatched()
        assert len(dispatched) == 1
        assert dispatched[0]["id"] == id1


class TestGetRunning:
    def test_returns_only_running(self, tmp_data):
        id1 = enqueue(make_task())
        id2 = enqueue(make_task())
        mark_dispatched(id1)
        mark_running(id1)
        running = get_running()
        assert len(running) == 1
        assert running[0]["id"] == id1


# -- Status transitions ----------------------------------------------------

class TestStatusTransitions:
    def test_pending_to_dispatched(self, tmp_data):
        task_id = enqueue(make_task())
        result = mark_dispatched(task_id, assigned_to="worker")
        assert result["status"] == "dispatched"
        assert result["assigned_to"] == "worker"

    def test_dispatched_to_running(self, tmp_data):
        task_id = enqueue(make_task())
        mark_dispatched(task_id)
        result = mark_running(task_id)
        assert result["status"] == "running"

    def test_dispatched_to_complete(self, tmp_data):
        task_id = enqueue(make_task())
        mark_dispatched(task_id)
        result = mark_complete(task_id)
        assert result["status"] == "complete"
        assert result["error"] is None

    def test_running_to_complete(self, tmp_data):
        task_id = enqueue(make_task())
        mark_dispatched(task_id)
        mark_running(task_id)
        result = mark_complete(task_id)
        assert result["status"] == "complete"

    def test_dispatched_to_failed(self, tmp_data):
        task_id = enqueue(make_task())
        mark_dispatched(task_id)
        result = mark_failed(task_id, error="boom")
        assert result["status"] == "failed"
        assert result["error"] == "boom"
        assert result["retry_count"] == 1

    def test_failed_increments_retry(self, tmp_data):
        task_id = enqueue(make_task())
        mark_failed(task_id, error="first")
        result = mark_failed(task_id, error="second")
        assert result["retry_count"] == 2

    def test_failed_no_increment(self, tmp_data):
        task_id = enqueue(make_task())
        result = mark_failed(task_id, error="once", increment_retry=False)
        assert result["retry_count"] == 0

    def test_mark_suspect(self, tmp_data):
        task_id = enqueue(make_task())
        mark_dispatched(task_id)
        result = mark_suspect(task_id, error="stale")
        assert result["status"] == "suspect"
        assert result["error"] == "stale"

    def test_mark_needs_review(self, tmp_data):
        task_id = enqueue(make_task())
        result = mark_needs_review(task_id, error="process gone")
        assert result["status"] == "needs_review"

    def test_invalid_task_raises(self, tmp_data):
        with pytest.raises(ValueError, match="Task not found"):
            mark_dispatched("nonexistent")


# -- Session lineage -------------------------------------------------------

class TestLineage:
    def test_attach_subagent_session(self, tmp_data):
        task_id = enqueue(make_task())
        result = attach_subagent_session(task_id, "sub-456")
        assert result["subagent_session_id"] == "sub-456"

    def test_attach_external_process(self, tmp_data):
        task_id = enqueue(make_task())
        result = attach_external_process(task_id, "claude_code", pid=1234)
        ext = result["external_process"]
        assert ext["type"] == "claude_code"
        assert ext["pid"] == 1234
        assert ext["status"] == "running"

    def test_touch_external_process(self, tmp_data):
        task_id = enqueue(make_task())
        attach_external_process(task_id, "claude_code", pid=1234)
        result = touch_external_process(task_id, status="done")
        assert result["external_process"]["status"] == "done"

    def test_touch_missing_process_raises(self, tmp_data):
        task_id = enqueue(make_task())
        with pytest.raises(ValueError, match="no external_process"):
            touch_external_process(task_id)


# -- Validation -------------------------------------------------------------

class TestValidation:
    def test_invalid_status_raises(self, tmp_data):
        with pytest.raises(ValueError, match="Invalid task status"):
            enqueue(make_task(status="bogus"))

    def test_invalid_payload_raises(self, tmp_data):
        with pytest.raises(ValueError, match="payload must be a dictionary"):
            enqueue({"type": "test", "payload": "not a dict"})
