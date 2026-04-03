"""Shared fixtures for JBCP tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from runtime.jb_common import JsonStore


@pytest.fixture()
def tmp_data(tmp_path: Path):
    """Patch all runtime modules to use a temp directory with isolated SQLite DB."""
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    data_dir.mkdir()
    log_dir.mkdir()

    # Create a temp SQLite database
    db_path = data_dir / "jbcp.db"

    # Legacy JSON files (still needed for backward compat / JsonStore references)
    queue_file = data_dir / "jb_queue.json"
    missions_file = data_dir / "jb_missions.json"
    mappings_file = data_dir / "jb_company_mappings.json"
    companies_file = data_dir / "jb_companies.json"
    components_file = data_dir / "jb_components.json"
    connections_file = data_dir / "jb_connections.json"
    services_file = data_dir / "jb_services.json"
    events_file = log_dir / "jbcp_events.jsonl"
    signals_dir = data_dir / "signals"
    signals_dir.mkdir()
    signals_file = signals_dir / "jbcp_signals.jsonl"

    queue_file.write_text("[]", encoding="utf-8")
    missions_file.write_text("[]", encoding="utf-8")
    mappings_file.write_text("[]", encoding="utf-8")
    companies_file.write_text("[]", encoding="utf-8")
    components_file.write_text("[]", encoding="utf-8")
    connections_file.write_text("[]", encoding="utf-8")
    services_file.write_text("[]", encoding="utf-8")
    events_file.touch()
    signals_file.touch()

    patches = [
        # Database path — this is the critical one
        patch("runtime.jb_database.DB_PATH", db_path),
        patch("runtime.jb_database.DATA_DIR", data_dir),
        # DATA_DIR for all modules that reference it
        patch("runtime.jb_companies.DATA_DIR", data_dir),
        patch("runtime.jb_missions.DATA_DIR", data_dir),
        patch("runtime.jb_queue.DATA_DIR", data_dir),
        patch("runtime.jb_components.DATA_DIR", data_dir),
        patch("runtime.jb_services.DATA_DIR", data_dir),
        patch("runtime.jb_company_mapping.DATA_DIR", data_dir),
        # Legacy stores (kept for backward compat)
        patch("runtime.jb_queue.QUEUE_FILE", queue_file),
        patch("runtime.jb_queue._store", JsonStore(queue_file)),
        patch("runtime.jb_missions.MISSIONS_FILE", missions_file),
        patch("runtime.jb_missions._store", JsonStore(missions_file)),
        patch("runtime.jb_company_mapping.MAPPINGS_FILE", mappings_file),
        patch("runtime.jb_company_mapping._store", JsonStore(mappings_file)),
        patch("runtime.jb_companies.COMPANIES_FILE", companies_file),
        patch("runtime.jb_companies._store", JsonStore(companies_file)),
        patch("runtime.jb_components.COMPONENTS_FILE", components_file),
        patch("runtime.jb_components._comp_store", JsonStore(components_file)),
        patch("runtime.jb_components.CONNECTIONS_FILE", connections_file),
        patch("runtime.jb_components._conn_store", JsonStore(connections_file)),
        patch("runtime.jb_services.SERVICES_FILE", services_file),
        patch("runtime.jb_services._service_store", JsonStore(services_file)),
        # Events
        patch("runtime.jb_events.LOG_DIR", log_dir),
        patch("runtime.jb_events.EVENTS_FILE", events_file),
    ]

    for p in patches:
        p.start()

    # Initialize the database with tables (and clear cache so it re-inits)
    import runtime.jb_database as _db_mod
    _db_mod._initialized_dbs.discard(str(db_path))
    _db_mod.init_db(db_path)

    yield {
        "root": tmp_path,
        "data_dir": data_dir,
        "log_dir": log_dir,
        "db_path": db_path,
        "queue_file": queue_file,
        "missions_file": missions_file,
        "companies_file": companies_file,
        "components_file": components_file,
        "connections_file": connections_file,
        "services_file": services_file,
        "events_file": events_file,
        "signals_file": signals_file,
    }

    for p in patches:
        p.stop()


def make_task(**overrides: Any) -> dict[str, Any]:
    """Build a minimal task dict with sensible defaults."""
    task = {
        "type": "coding",
        "status": "pending",
        "priority": 5,
        "payload": {"goal": "test task"},
    }
    task.update(overrides)
    return task
