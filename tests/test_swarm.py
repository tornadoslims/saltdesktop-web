"""Tests for runtime.jb_swarm — swarm view layer."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from runtime.jb_common import JsonStore, utc_now_iso
from runtime.jb_swarm import (
    get_swarm,
    _build_workers_by_mission,
    _build_running_services,
    _format_schedule,
    _relative_time,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_swarm(tmp_path: Path):
    """Patch all stores used by swarm view to use temp directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    db_path = data_dir / "jbcp.db"

    queue_file = data_dir / "jb_queue.json"
    missions_file = data_dir / "jb_missions.json"
    components_file = data_dir / "jb_components.json"
    connections_file = data_dir / "jb_connections.json"
    services_file = data_dir / "jb_services.json"
    runs_file = data_dir / "jb_service_runs.json"
    companies_file = data_dir / "jb_companies.json"

    for f in [queue_file, missions_file, components_file, connections_file,
              services_file, runs_file, companies_file]:
        f.write_text("[]", encoding="utf-8")

    patches = [
        # Database path
        patch("runtime.jb_database.DB_PATH", db_path),
        patch("runtime.jb_database.DATA_DIR", data_dir),
        # DATA_DIR
        patch("runtime.jb_queue.DATA_DIR", data_dir),
        patch("runtime.jb_missions.DATA_DIR", data_dir),
        patch("runtime.jb_components.DATA_DIR", data_dir),
        patch("runtime.jb_services.DATA_DIR", data_dir),
        patch("runtime.jb_companies.DATA_DIR", data_dir),
        patch("runtime.jb_company_mapping.DATA_DIR", data_dir),
        # Legacy stores
        patch("runtime.jb_queue.QUEUE_FILE", queue_file),
        patch("runtime.jb_queue._store", JsonStore(queue_file)),
        patch("runtime.jb_missions.MISSIONS_FILE", missions_file),
        patch("runtime.jb_missions._store", JsonStore(missions_file)),
        patch("runtime.jb_components.COMPONENTS_FILE", components_file),
        patch("runtime.jb_components._comp_store", JsonStore(components_file)),
        patch("runtime.jb_components.CONNECTIONS_FILE", connections_file),
        patch("runtime.jb_components._conn_store", JsonStore(connections_file)),
        patch("runtime.jb_services.SERVICES_FILE", services_file),
        patch("runtime.jb_services._service_store", JsonStore(services_file)),
        patch("runtime.jb_services.RUNS_FILE", runs_file),
        patch("runtime.jb_services._run_store", JsonStore(runs_file)),
        patch("runtime.jb_companies.COMPANIES_FILE", companies_file),
        patch("runtime.jb_companies._store", JsonStore(companies_file)),
    ]

    for p in patches:
        p.start()

    # Initialize the database
    import runtime.jb_database as _db_mod
    _db_mod._initialized_dbs.discard(str(db_path))
    _db_mod.init_db(db_path)

    yield {"root": tmp_path, "data_dir": data_dir}

    for p in patches:
        p.stop()


def _create_mission(mission_id: str, goal: str, company_id: str = "co-1", status: str = "active"):
    from runtime.jb_database import get_db, _json_dumps
    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO missions
               (mission_id, company_id, goal, summary, status,
                constraints, source_artifacts, task_ids, items,
                components, connections, origin, delivery,
                context_path, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (mission_id, company_id, goal, None, status,
             "[]", "[]", "[]", "[]", "[]", "[]", None, None, None, now, now),
        )


def _create_task(task_id: str, mission_id: str, status: str = "running",
                 task_type: str = "coding", component: str = "", company_id: str = "co-1"):
    from runtime.jb_database import get_db, _json_dumps
    now = utc_now_iso()
    origin = _json_dumps({"surface": None, "session_id": None, "thread_id": None})
    delivery = _json_dumps({"mode": "reply_to_origin"})
    payload = _json_dumps({"goal": "test goal", "component": component})
    with get_db() as conn:
        conn.execute(
            """INSERT INTO tasks
               (id, company_id, mission_id, type, status, priority,
                assigned_to, retry_count, max_retries, error,
                created_at, updated_at, origin, delivery,
                openclaw_session_id, parent_session_id, subagent_session_id,
                external_process, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, company_id, mission_id, task_type, status, 5,
             None, 0, 3, None, now, now, origin, delivery,
             None, None, None, None, payload),
        )


def _create_service(service_id: str, name: str, workspace_id: str = "co-1",
                    status: str = "running", schedule: str = None,
                    run_count: int = 0, last_run: str = None):
    from runtime.jb_database import get_db
    now = utc_now_iso()
    svc_type = "scheduled" if schedule else "daemon"
    with get_db() as conn:
        conn.execute(
            """INSERT INTO services
               (service_id, workspace_id, name, description, status, type,
                schedule, directory, entry_point, has_frontend, frontend_path,
                port, pid, last_run, last_run_status, last_run_duration_ms,
                next_run, health, run_count, mission_id, last_run_summary,
                error_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (service_id, workspace_id, name, "", status, svc_type,
             schedule, "", "", 0, None,
             None, None, last_run, None, None, None,
             "unknown", run_count, None, None, 0, now, now),
        )


def _create_company(company_id: str, name: str):
    from runtime.jb_database import get_db
    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO companies
               (company_id, name, description, status, focused_mission_id,
                mission_ids, company_context_path, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (company_id, name, None, "active", None, "[]", None, now, now),
        )


# ---------------------------------------------------------------------------
# get_swarm — empty state
# ---------------------------------------------------------------------------

class TestGetSwarmEmpty:
    def test_empty_returns_structure(self, tmp_swarm):
        result = get_swarm()
        assert result == {"building": [], "running": []}

    def test_empty_with_mission_id_filter(self, tmp_swarm):
        result = get_swarm(mission_id="nonexistent")
        assert result == {"building": [], "running": []}


# ---------------------------------------------------------------------------
# get_swarm — with running tasks
# ---------------------------------------------------------------------------

class TestGetSwarmWithTasks:
    def test_running_tasks_appear_in_building(self, tmp_swarm):
        _create_mission("m-1", "Build Slack Analyzer")
        _create_task("t-1", "m-1", status="running", component="Email Parser")
        _create_task("t-2", "m-1", status="pending", component="Slack Connector")

        result = get_swarm()
        assert len(result["building"]) == 1

        group = result["building"][0]
        assert group["mission_id"] == "m-1"
        assert group["mission_name"] == "Build Slack Analyzer"
        assert len(group["workers"]) == 2

        # Check worker structure
        worker = group["workers"][0]
        assert "task_id" in worker
        assert "role" in worker
        assert "role_icon" in worker
        assert "component_name" in worker
        assert "status" in worker
        assert "activity" in worker
        assert "lines_of_code" in worker
        assert "started_at" in worker

    def test_dispatched_tasks_shown_as_running(self, tmp_swarm):
        _create_mission("m-1", "Test Mission")
        _create_task("t-1", "m-1", status="dispatched")

        result = get_swarm()
        worker = result["building"][0]["workers"][0]
        assert worker["status"] == "running"

    def test_complete_tasks_within_30min_included(self, tmp_swarm):
        _create_mission("m-1", "Test Mission")
        # Create a completed task with recent updated_at (the default is now)
        _create_task("t-1", "m-1", status="complete")

        result = get_swarm()
        assert len(result["building"]) == 1
        assert result["building"][0]["workers"][0]["status"] == "complete"

    def test_mission_id_filter(self, tmp_swarm):
        _create_mission("m-1", "Mission One")
        _create_mission("m-2", "Mission Two")
        _create_task("t-1", "m-1", status="running")
        _create_task("t-2", "m-2", status="running")

        result = get_swarm(mission_id="m-1")
        assert len(result["building"]) == 1
        assert result["building"][0]["mission_id"] == "m-1"
        assert len(result["building"][0]["workers"]) == 1

    def test_worker_role_from_task_type(self, tmp_swarm):
        _create_mission("m-1", "Test Mission")
        _create_task("t-1", "m-1", status="running", task_type="research")

        result = get_swarm()
        worker = result["building"][0]["workers"][0]
        assert worker["role"] == "Researcher"
        assert worker["role_icon"] == "magnifier"

    def test_component_name_from_payload(self, tmp_swarm):
        _create_mission("m-1", "Test Mission")
        _create_task("t-1", "m-1", status="running", component="Gmail Connector")

        result = get_swarm()
        worker = result["building"][0]["workers"][0]
        assert worker["component_name"] == "Gmail Connector"


# ---------------------------------------------------------------------------
# _build_workers_by_mission — grouping
# ---------------------------------------------------------------------------

class TestBuildWorkersByMission:
    def test_groups_by_mission(self, tmp_swarm):
        _create_mission("m-1", "Mission Alpha")
        _create_mission("m-2", "Mission Beta")
        _create_task("t-1", "m-1", status="running")
        _create_task("t-2", "m-1", status="pending")
        _create_task("t-3", "m-2", status="running")

        result = _build_workers_by_mission()
        assert len(result) == 2

        ids = {g["mission_id"] for g in result}
        assert ids == {"m-1", "m-2"}

        for group in result:
            if group["mission_id"] == "m-1":
                assert len(group["workers"]) == 2
            else:
                assert len(group["workers"]) == 1

    def test_progress_reflects_tasks(self, tmp_swarm):
        _create_mission("m-1", "Test Mission")
        _create_task("t-1", "m-1", status="complete")
        _create_task("t-2", "m-1", status="running")

        result = _build_workers_by_mission()
        progress = result[0]["progress"]
        assert progress["completed"] == 1
        assert progress["total"] == 2
        assert progress["percent"] == 50.0


# ---------------------------------------------------------------------------
# _build_running_services
# ---------------------------------------------------------------------------

class TestBuildRunningServices:
    def test_returns_running_services(self, tmp_swarm):
        _create_company("co-1", "Work Automation Co.")
        _create_service("svc-1", "Gmail Checker", schedule="*/15 * * * *",
                        run_count=142, last_run=utc_now_iso())

        result = _build_running_services()
        assert len(result) == 1

        svc = result[0]
        assert svc["service_id"] == "svc-1"
        assert svc["name"] == "Gmail Checker"
        assert svc["workspace_name"] == "Work Automation Co."
        assert svc["status_label"] == "Healthy"
        assert svc["schedule_label"] == "every 15 minutes"
        assert svc["run_count"] == 142
        assert svc["last_run_ago"] is not None

    def test_excludes_stopped_services(self, tmp_swarm):
        _create_service("svc-1", "Stopped Service", status="stopped")

        result = _build_running_services()
        assert len(result) == 0

    def test_no_schedule_returns_none(self, tmp_swarm):
        _create_service("svc-1", "Daemon Service", status="running")

        result = _build_running_services()
        assert result[0]["schedule_label"] is None


# ---------------------------------------------------------------------------
# _format_schedule — cron to human-friendly
# ---------------------------------------------------------------------------

class TestFormatSchedule:
    def test_every_15_minutes(self):
        assert _format_schedule("*/15 * * * *") == "every 15 minutes"

    def test_every_minute(self):
        assert _format_schedule("*/1 * * * *") == "every minute"

    def test_every_hour(self):
        assert _format_schedule("0 * * * *") == "every hour"

    def test_every_hour_at_minute(self):
        assert _format_schedule("30 * * * *") == "every hour at :30"

    def test_every_n_hours(self):
        assert _format_schedule("0 */2 * * *") == "every 2 hours"

    def test_every_1_hour_via_step(self):
        assert _format_schedule("0 */1 * * *") == "every hour"

    def test_daily_at_9am(self):
        assert _format_schedule("0 9 * * *") == "daily at 9:00 AM"

    def test_daily_at_2pm(self):
        assert _format_schedule("0 14 * * *") == "daily at 2:00 PM"

    def test_daily_at_midnight(self):
        assert _format_schedule("0 0 * * *") == "daily at 12:00 AM"

    def test_daily_at_noon(self):
        assert _format_schedule("0 12 * * *") == "daily at 12:00 PM"

    def test_weekly_on_monday(self):
        assert _format_schedule("0 9 * * 1") == "weekly on Monday at 9:00 AM"

    def test_weekly_on_sunday_zero(self):
        assert _format_schedule("0 9 * * 0") == "weekly on Sunday at 9:00 AM"

    def test_weekly_on_sunday_seven(self):
        assert _format_schedule("0 9 * * 7") == "weekly on Sunday at 9:00 AM"

    def test_unknown_pattern_returned_as_is(self):
        expr = "0 9 1 * *"  # monthly
        assert _format_schedule(expr) == expr

    def test_empty_string(self):
        assert _format_schedule("") == ""

    def test_none(self):
        assert _format_schedule(None) == ""

    def test_non_standard_parts(self):
        expr = "0 9 1-15 * *"
        assert _format_schedule(expr) == expr


# ---------------------------------------------------------------------------
# _relative_time — ISO timestamp to "X ago"
# ---------------------------------------------------------------------------

class TestRelativeTime:
    def test_just_now(self):
        now = datetime.now(timezone.utc).isoformat()
        assert _relative_time(now) == "just now"

    def test_seconds_ago(self):
        ts = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        assert _relative_time(ts) == "30 seconds ago"

    def test_one_minute_ago(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=1, seconds=10)).isoformat()
        assert _relative_time(ts) == "1 minute ago"

    def test_minutes_ago(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=8)).isoformat()
        assert _relative_time(ts) == "8 minutes ago"

    def test_one_hour_ago(self):
        ts = (datetime.now(timezone.utc) - timedelta(hours=1, minutes=5)).isoformat()
        assert _relative_time(ts) == "1 hour ago"

    def test_hours_ago(self):
        ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        assert _relative_time(ts) == "3 hours ago"

    def test_one_day_ago(self):
        ts = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        assert _relative_time(ts) == "1 day ago"

    def test_days_ago(self):
        ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        assert _relative_time(ts) == "5 days ago"

    def test_invalid_timestamp(self):
        assert _relative_time("not-a-date") == "unknown"

    def test_future_timestamp(self):
        ts = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        assert _relative_time(ts) == "just now"
