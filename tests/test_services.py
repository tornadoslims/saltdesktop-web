"""Tests for runtime.jb_services -- service registry, lifecycle, runs, and ports."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from runtime.jb_common import JsonStore
from runtime.jb_services import (
    create_service,
    get_service,
    list_services,
    update_service,
    mark_service_status,
    start_service,
    stop_service,
    pause_service,
    resume_service,
    record_run,
    list_runs,
    get_run,
    allocate_port,
    release_port,
    VALID_SERVICE_STATUSES,
    VALID_SERVICE_TYPES,
)


@pytest.fixture()
def tmp_services(tmp_path: Path):
    """Patch service and run stores to use temp directory with SQLite."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    db_path = data_dir / "jbcp.db"

    # Legacy JSON files
    services_file = data_dir / "jb_services.json"
    runs_file = data_dir / "jb_service_runs.json"
    services_file.write_text("[]", encoding="utf-8")
    runs_file.write_text("[]", encoding="utf-8")

    patches = [
        # Database path
        patch("runtime.jb_database.DB_PATH", db_path),
        patch("runtime.jb_database.DATA_DIR", data_dir),
        # DATA_DIR
        patch("runtime.jb_services.DATA_DIR", data_dir),
        # Legacy stores
        patch("runtime.jb_services.SERVICES_FILE", services_file),
        patch("runtime.jb_services._service_store", JsonStore(services_file)),
        patch("runtime.jb_services.RUNS_FILE", runs_file),
        patch("runtime.jb_services._run_store", JsonStore(runs_file)),
    ]

    for p in patches:
        p.start()

    # Initialize the database (and clear cache so it re-inits)
    import runtime.jb_database as _db_mod
    _db_mod._initialized_dbs.discard(str(db_path))
    _db_mod.init_db(db_path)

    yield {"root": tmp_path, "data_dir": data_dir}

    for p in patches:
        p.stop()


WS = "ws-test-001"


# -- CreateService -----------------------------------------------------------

class TestCreateService:
    def test_returns_id(self, tmp_services):
        sid = create_service(workspace_id=WS, name="Worker")
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_preserves_fields(self, tmp_services):
        sid = create_service(
            workspace_id=WS,
            name="Worker",
            description="Background worker",
            type="daemon",
            directory="/opt/worker",
            entry_point="main.py",
        )
        svc = get_service(sid)
        assert svc["name"] == "Worker"
        assert svc["description"] == "Background worker"
        assert svc["type"] == "daemon"
        assert svc["directory"] == "/opt/worker"
        assert svc["entry_point"] == "main.py"
        assert svc["workspace_id"] == WS

    def test_validates_type(self, tmp_services):
        with pytest.raises(ValueError, match="Invalid service type"):
            create_service(workspace_id=WS, name="Bad", type="invalid_type")

    def test_all_valid_types_accepted(self, tmp_services):
        for t in VALID_SERVICE_TYPES:
            sid = create_service(workspace_id=WS, name=f"Svc-{t}", type=t)
            assert sid

    def test_validates_status(self, tmp_services):
        # create_service always starts as "stopped", but normalize validates
        # We test via mark_service_status instead
        sid = create_service(workspace_id=WS, name="X")
        with pytest.raises(ValueError, match="Invalid service status"):
            mark_service_status(sid, "bogus")

    def test_rejects_empty_name(self, tmp_services):
        with pytest.raises(ValueError, match="non-empty string"):
            create_service(workspace_id=WS, name="")

    def test_rejects_whitespace_name(self, tmp_services):
        with pytest.raises(ValueError, match="non-empty string"):
            create_service(workspace_id=WS, name="   ")

    def test_default_status_is_stopped(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        svc = get_service(sid)
        assert svc["status"] == "stopped"

    def test_requires_workspace_id(self, tmp_services):
        with pytest.raises(ValueError, match="workspace_id"):
            create_service(workspace_id="", name="X")

    def test_has_frontend_defaults_false(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        svc = get_service(sid)
        assert svc["has_frontend"] is False

    def test_has_frontend_true(self, tmp_services):
        sid = create_service(
            workspace_id=WS, name="Dashboard",
            has_frontend=True, frontend_path="/app/dashboard",
        )
        svc = get_service(sid)
        assert svc["has_frontend"] is True
        assert svc["frontend_path"] == "/app/dashboard"

    def test_mission_id_stored(self, tmp_services):
        sid = create_service(workspace_id=WS, name="Worker", mission_id="mission-abc-123")
        svc = get_service(sid)
        assert svc["mission_id"] == "mission-abc-123"

    def test_mission_id_defaults_none(self, tmp_services):
        sid = create_service(workspace_id=WS, name="Worker")
        svc = get_service(sid)
        assert svc["mission_id"] is None


# -- GetService --------------------------------------------------------------

class TestGetService:
    def test_existing(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        svc = get_service(sid)
        assert svc is not None
        assert svc["service_id"] == sid

    def test_nonexistent(self, tmp_services):
        assert get_service("nonexistent-id") is None


# -- ListServices ------------------------------------------------------------

class TestListServices:
    def test_empty(self, tmp_services):
        assert list_services() == []

    def test_returns_all(self, tmp_services):
        create_service(workspace_id=WS, name="A")
        create_service(workspace_id=WS, name="B")
        assert len(list_services()) == 2

    def test_filter_by_workspace_id(self, tmp_services):
        create_service(workspace_id="ws-1", name="A")
        create_service(workspace_id="ws-2", name="B")
        create_service(workspace_id="ws-1", name="C")

        ws1 = list_services(workspace_id="ws-1")
        ws2 = list_services(workspace_id="ws-2")
        assert len(ws1) == 2
        assert len(ws2) == 1
        assert all(s["workspace_id"] == "ws-1" for s in ws1)

    def test_filter_nonexistent_workspace(self, tmp_services):
        create_service(workspace_id=WS, name="A")
        assert list_services(workspace_id="no-such-ws") == []


# -- ServiceStatus -----------------------------------------------------------

class TestServiceStatus:
    def test_mark_stopped_to_running(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        result = mark_service_status(sid, "running")
        assert result["status"] == "running"

    def test_mark_running_to_paused(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        mark_service_status(sid, "running")
        result = mark_service_status(sid, "paused")
        assert result["status"] == "paused"

    def test_mark_paused_to_stopped(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        mark_service_status(sid, "paused")
        result = mark_service_status(sid, "stopped")
        assert result["status"] == "stopped"

    def test_invalid_status_raises(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        with pytest.raises(ValueError, match="Invalid service status"):
            mark_service_status(sid, "bogus")

    def test_all_valid_statuses(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        for status in VALID_SERVICE_STATUSES:
            result = mark_service_status(sid, status)
            assert result["status"] == status

    def test_status_persists(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        mark_service_status(sid, "running")
        svc = get_service(sid)
        assert svc["status"] == "running"


# -- ServiceLifecycle --------------------------------------------------------

class TestServiceLifecycle:
    def test_start_service(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        result = start_service(sid)
        assert result["status"] == "starting"

    def test_start_already_running_raises(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        mark_service_status(sid, "running")
        with pytest.raises(ValueError, match="already running"):
            start_service(sid)

    def test_stop_service(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        mark_service_status(sid, "running")
        result = stop_service(sid)
        assert result["status"] == "stopped"
        assert result["pid"] is None

    def test_stop_already_stopped_raises(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        with pytest.raises(ValueError, match="already stopped"):
            stop_service(sid)

    def test_pause_service(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        mark_service_status(sid, "running")
        result = pause_service(sid)
        assert result["status"] == "paused"

    def test_pause_not_running_raises(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        with pytest.raises(ValueError, match="Can only pause a running"):
            pause_service(sid)

    def test_resume_service(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        mark_service_status(sid, "paused")
        result = resume_service(sid)
        assert result["status"] == "running"

    def test_resume_not_paused_raises(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        with pytest.raises(ValueError, match="Can only resume a paused"):
            resume_service(sid)

    def test_nonexistent_service_raises(self, tmp_services):
        with pytest.raises(ValueError, match="Service not found"):
            start_service("nonexistent")

    def test_full_lifecycle(self, tmp_services):
        """stopped -> starting -> running -> paused -> running -> stopped"""
        sid = create_service(workspace_id=WS, name="FullCycle")
        assert get_service(sid)["status"] == "stopped"

        start_service(sid)
        assert get_service(sid)["status"] == "starting"

        mark_service_status(sid, "running")
        assert get_service(sid)["status"] == "running"

        pause_service(sid)
        assert get_service(sid)["status"] == "paused"

        resume_service(sid)
        assert get_service(sid)["status"] == "running"

        stop_service(sid)
        assert get_service(sid)["status"] == "stopped"


# -- RunTracking -------------------------------------------------------------

class TestRunTracking:
    def test_record_run(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        run_id = record_run(sid, status="success", duration_ms=1200)
        assert isinstance(run_id, str)
        assert len(run_id) > 0

    def test_list_runs(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        record_run(sid, status="success", duration_ms=100)
        record_run(sid, status="error", error="Timeout")
        runs = list_runs(sid)
        assert len(runs) == 2

    def test_limit_works(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        for i in range(5):
            record_run(sid, status="success", duration_ms=i * 100)
        runs = list_runs(sid, limit=3)
        assert len(runs) == 3

    def test_get_run(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        run_id = record_run(sid, status="success", duration_ms=500)
        run = get_run(run_id)
        assert run is not None
        assert run["run_id"] == run_id
        assert run["status"] == "success"
        assert run["duration_ms"] == 500

    def test_get_run_nonexistent(self, tmp_services):
        assert get_run("nonexistent") is None

    def test_record_run_updates_service_stats(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        record_run(sid, status="success", duration_ms=100)
        svc = get_service(sid)
        assert svc["run_count"] == 1
        assert svc["last_run"] is not None

    def test_error_run_increments_error_count(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        record_run(sid, status="error", error="Boom")
        svc = get_service(sid)
        assert svc["error_count"] == 1

    def test_record_run_nonexistent_service_raises(self, tmp_services):
        with pytest.raises(ValueError, match="Service not found"):
            record_run("nonexistent", status="success")

    def test_runs_ordered_most_recent_first(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        r1 = record_run(sid, status="success")
        r2 = record_run(sid, status="success")
        runs = list_runs(sid)
        # r2 was recorded after r1, so should come first
        assert runs[0]["run_id"] == r2

    def test_tokens_used_tracked(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        run_id = record_run(sid, status="success", tokens_used=1500)
        run = get_run(run_id)
        assert run["tokens_used"] == 1500


# -- PortManagement ----------------------------------------------------------

class TestPortManagement:
    def test_allocate_port_returns_number(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        port = allocate_port(sid)
        assert isinstance(port, int)
        assert port >= 9000

    def test_allocate_multiple_gets_different_ports(self, tmp_services):
        s1 = create_service(workspace_id=WS, name="A")
        s2 = create_service(workspace_id=WS, name="B")
        s3 = create_service(workspace_id=WS, name="C")

        p1 = allocate_port(s1)
        p2 = allocate_port(s2)
        p3 = allocate_port(s3)

        assert len({p1, p2, p3}) == 3  # all different

    def test_release_port(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        port = allocate_port(sid)
        release_port(sid)
        svc = get_service(sid)
        assert svc["port"] is None

    def test_allocate_after_release_reuses_port(self, tmp_services):
        s1 = create_service(workspace_id=WS, name="A")
        s2 = create_service(workspace_id=WS, name="B")

        p1 = allocate_port(s1)
        allocate_port(s2)
        release_port(s1)

        # Create new service, should get the released port
        s3 = create_service(workspace_id=WS, name="C")
        p3 = allocate_port(s3)
        assert p3 == p1  # reused the released port

    def test_allocate_idempotent(self, tmp_services):
        sid = create_service(workspace_id=WS, name="X")
        p1 = allocate_port(sid)
        p2 = allocate_port(sid)
        assert p1 == p2  # same port returned

    def test_nonexistent_service_raises(self, tmp_services):
        with pytest.raises(ValueError, match="Service not found"):
            allocate_port("nonexistent")

    def test_release_nonexistent_raises(self, tmp_services):
        with pytest.raises(ValueError, match="Service not found"):
            release_port("nonexistent")
