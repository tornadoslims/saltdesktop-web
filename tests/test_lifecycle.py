"""Tests for mission lifecycle — auto-completion and compaction triggers."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from runtime.jb_common import JsonStore
from runtime.jb_queue import enqueue, mark_complete, mark_failed, mark_dispatched
from runtime.jb_missions import create_mission, get_mission, attach_task
from runtime.jb_compaction import check_mission_lifecycle
from tests.conftest import make_task


@pytest.fixture()
def tmp_lifecycle(tmp_path):
    """Full stack fixture for lifecycle tests."""
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    data_dir.mkdir()
    log_dir.mkdir()

    db_path = data_dir / "jbcp.db"

    queue_file = data_dir / "jb_queue.json"
    missions_file = data_dir / "jb_missions.json"
    events_file = log_dir / "jbcp_events.jsonl"

    for f in [queue_file, missions_file]:
        f.write_text("[]", encoding="utf-8")
    events_file.touch()

    patches = [
        # Database path
        patch("runtime.jb_database.DB_PATH", db_path),
        patch("runtime.jb_database.DATA_DIR", data_dir),
        # DATA_DIR
        patch("runtime.jb_queue.DATA_DIR", data_dir),
        patch("runtime.jb_missions.DATA_DIR", data_dir),
        # Legacy stores
        patch("runtime.jb_queue.QUEUE_FILE", queue_file),
        patch("runtime.jb_queue._store", JsonStore(queue_file)),
        patch("runtime.jb_missions.MISSIONS_FILE", missions_file),
        patch("runtime.jb_missions._store", JsonStore(missions_file)),
        patch("runtime.jb_events.LOG_DIR", log_dir),
        patch("runtime.jb_events.EVENTS_FILE", events_file),
    ]

    for p in patches:
        p.start()

    # Initialize the database
    import runtime.jb_database as _db_mod
    _db_mod._initialized_dbs.discard(str(db_path))
    _db_mod.init_db(db_path)

    yield {"data_dir": data_dir}
    for p in patches:
        p.stop()


class TestMissionLifecycle:
    def test_all_complete_marks_mission_complete(self, tmp_lifecycle):
        mid = create_mission(goal="Test", status="active")
        t1 = enqueue(make_task(mission_id=mid))
        t2 = enqueue(make_task(mission_id=mid))
        attach_task(mid, t1)
        attach_task(mid, t2)

        mark_complete(t1)
        mark_complete(t2)

        result = check_mission_lifecycle(mid)
        assert result["changed"] is True
        assert result["status"] == "complete"
        assert get_mission(mid)["status"] == "complete"

    def test_mix_complete_and_retryable_stays_active(self, tmp_lifecycle):
        """Failed task with retries left keeps mission active."""
        mid = create_mission(goal="Test", status="active")
        t1 = enqueue(make_task(mission_id=mid))
        t2 = enqueue(make_task(mission_id=mid, max_retries=3))
        attach_task(mid, t1)
        attach_task(mid, t2)

        mark_complete(t1)
        mark_failed(t2, error="boom")  # retry_count=1, max=3 → retryable

        result = check_mission_lifecycle(mid)
        assert result["changed"] is False
        assert result["status"] == "active"

    def test_mix_complete_and_exhausted_marks_failed(self, tmp_lifecycle):
        """Failed task with no retries left marks mission failed."""
        mid = create_mission(goal="Test", status="active")
        t1 = enqueue(make_task(mission_id=mid))
        t2 = enqueue(make_task(mission_id=mid, max_retries=0))
        attach_task(mid, t1)
        attach_task(mid, t2)

        mark_complete(t1)
        mark_failed(t2, error="boom", increment_retry=False)

        result = check_mission_lifecycle(mid)
        assert result["changed"] is True
        assert result["status"] == "failed"

    def test_pending_tasks_keep_active(self, tmp_lifecycle):
        mid = create_mission(goal="Test", status="active")
        t1 = enqueue(make_task(mission_id=mid))
        t2 = enqueue(make_task(mission_id=mid))
        attach_task(mid, t1)
        attach_task(mid, t2)

        mark_complete(t1)
        # t2 still pending

        result = check_mission_lifecycle(mid)
        assert result["changed"] is False
        assert result["status"] == "active"

    def test_running_tasks_keep_active(self, tmp_lifecycle):
        mid = create_mission(goal="Test", status="active")
        t1 = enqueue(make_task(mission_id=mid))
        attach_task(mid, t1)
        mark_dispatched(t1)

        result = check_mission_lifecycle(mid)
        assert result["changed"] is False
        assert result["status"] == "active"

    def test_no_tasks_stays_active(self, tmp_lifecycle):
        mid = create_mission(goal="Test", status="active")
        result = check_mission_lifecycle(mid)
        assert result["changed"] is False

    def test_already_complete_no_change(self, tmp_lifecycle):
        from runtime.jb_missions import mark_mission_status
        mid = create_mission(goal="Test", status="active")
        mark_mission_status(mid, "complete")
        result = check_mission_lifecycle(mid)
        assert result["changed"] is False

    def test_nonexistent_mission(self, tmp_lifecycle):
        result = check_mission_lifecycle("nope")
        assert result["ok"] is False
