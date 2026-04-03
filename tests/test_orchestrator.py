"""Tests for runtime.jb_orchestrator — dispatch and reconcile phases."""
from __future__ import annotations

import json
import logging
from unittest.mock import patch, MagicMock

import pytest
from tests.conftest import make_task

from runtime.jb_queue import enqueue, get_task, mark_dispatched, mark_running


@pytest.fixture()
def logger():
    return logging.getLogger("test_orchestrator")


class TestDispatchPending:
    def test_dispatches_pending_tasks(self, tmp_data, logger):
        from runtime.jb_orchestrator import dispatch_pending

        enqueue(make_task(payload={"goal": "test dispatch", "component": "test_comp"}))

        mock_result = {"status": "complete", "lines": 50}
        with patch("runtime.jb_orchestrator.build_component_sync", return_value=mock_result):
            completed = dispatch_pending(logger)
        # Should not raise

    def test_skips_when_no_pending(self, tmp_data, logger):
        from runtime.jb_orchestrator import dispatch_pending
        completed = dispatch_pending(logger)
        assert len(completed) == 0

    def test_handles_dispatch_error(self, tmp_data, logger):
        from runtime.jb_orchestrator import dispatch_pending
        enqueue(make_task())

        def _raise(task, component, mission):
            raise RuntimeError("connection failed")

        with patch("runtime.jb_orchestrator.build_component_sync", side_effect=_raise):
            # Should not raise — errors are caught
            dispatch_pending(logger)


class TestReconcileRunning:
    def test_reconciles_running_task_with_files(self, tmp_data, logger):
        from runtime.jb_orchestrator import reconcile_running
        task_id = enqueue(make_task(payload={"component": "test_comp"}))
        mark_dispatched(task_id)
        mark_running(task_id)

        # Create actual component directory with main.py to simulate built component
        import tempfile
        from pathlib import Path
        with patch("runtime.jb_builder.COMPONENTS_DIR", Path(tmp_data["data_dir"]) / "components"):
            comp_dir = Path(tmp_data["data_dir"]) / "components" / "test_comp"
            comp_dir.mkdir(parents=True)
            (comp_dir / "main.py").write_text("# test", encoding="utf-8")
            reconcile_running(logger)

        task = get_task(task_id)
        assert task["status"] == "complete"

    def test_skips_when_nothing_running(self, tmp_data, logger):
        from runtime.jb_orchestrator import reconcile_running
        reconcile_running(logger)  # Should not raise


class TestRunOnce:
    def test_runs_all_phases(self, tmp_data, logger):
        from runtime.jb_orchestrator import run_once

        mock_result = {"status": "complete", "lines": 50}
        with patch("runtime.jb_orchestrator.build_component_sync", return_value=mock_result):
            run_once(logger)
