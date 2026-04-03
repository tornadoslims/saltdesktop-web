"""
End-to-end integration test: full lifecycle from company creation to mission approval.

Tests the complete flow:
1. Create company
2. Create mission (enters planning mode)
3. Generate plan (components + tasks on the mission)
4. Verify mission structure
5. Approve mission (creates component records, enqueues tasks)
6. Verify everything is wired (components, tasks, graph)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from runtime.jb_common import JsonStore


@pytest.fixture()
def full_stack(tmp_path):
    """Patch ALL stores to use temp directories."""
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    data_dir.mkdir()
    log_dir.mkdir()

    files = {
        "companies": data_dir / "jb_companies.json",
        "mappings": data_dir / "jb_company_mappings.json",
        "missions": data_dir / "jb_missions.json",
        "queue": data_dir / "jb_queue.json",
        "components": data_dir / "jb_components.json",
        "connections": data_dir / "jb_connections.json",
        "services": data_dir / "jb_services.json",
        "service_runs": data_dir / "jb_service_runs.json",
        "events": log_dir / "jbcp_events.jsonl",
        "wake": data_dir / "jb_wake_requests.jsonl",
    }

    for f in files.values():
        if f.suffix == ".json":
            f.write_text("[]", encoding="utf-8")
        else:
            f.touch()

    patches = [
        patch("runtime.jb_queue.QUEUE_FILE", files["queue"]),
        patch("runtime.jb_queue._store", JsonStore(files["queue"])),
        patch("runtime.jb_missions.MISSIONS_FILE", files["missions"]),
        patch("runtime.jb_missions._store", JsonStore(files["missions"])),
        patch("runtime.jb_companies.DATA_DIR", data_dir),
        patch("runtime.jb_companies.COMPANIES_FILE", files["companies"]),
        patch("runtime.jb_companies._store", JsonStore(files["companies"])),
        patch("runtime.jb_company_mapping.MAPPINGS_FILE", files["mappings"]),
        patch("runtime.jb_company_mapping._store", JsonStore(files["mappings"])),
        patch("runtime.jb_components.COMPONENTS_FILE", files["components"]),
        patch("runtime.jb_components._comp_store", JsonStore(files["components"])),
        patch("runtime.jb_components.CONNECTIONS_FILE", files["connections"]),
        patch("runtime.jb_components._conn_store", JsonStore(files["connections"])),
        patch("runtime.jb_services.SERVICES_FILE", files["services"]),
        patch("runtime.jb_services._service_store", JsonStore(files["services"])),
        patch("runtime.jb_services.RUNS_FILE", files["service_runs"]),
        patch("runtime.jb_services._run_store", JsonStore(files["service_runs"])),
        patch("runtime.jb_events.LOG_DIR", log_dir),
        patch("runtime.jb_events.EVENTS_FILE", files["events"]),
        patch("runtime.jb_wake.DATA_DIR", data_dir),
        patch("runtime.jb_wake.WAKE_FILE", files["wake"]),
    ]

    for p in patches:
        p.start()

    yield {"root": tmp_path, "data_dir": data_dir, "files": files}

    for p in patches:
        p.stop()


MOCK_WORKER_RESPONSE = {
    "components": [
        {"name": "Gmail Connector", "type": "connector", "description": "Fetches emails",
         "output_type": "List[RawEmail]", "output_fields": {"message_id": "str", "subject": "str"},
         "config_fields": {"credentials_path": "str"}, "dependencies": []},
        {"name": "Email Parser", "type": "processor", "description": "Parses emails",
         "input_type": "List[RawEmail]", "output_type": "List[ParsedEmail]",
         "dependencies": ["Gmail Connector"]},
        {"name": "Slack Alerter", "type": "output", "description": "Sends to Slack",
         "input_type": "List[ParsedEmail]", "config_fields": {"webhook_url": "str"},
         "dependencies": ["Email Parser"]},
    ],
    "connections": [
        {"from": "Gmail Connector", "to": "Email Parser", "label": "raw emails"},
        {"from": "Email Parser", "to": "Slack Alerter", "label": "parsed emails"},
    ],
    "tasks": [
        {"goal": "Build Gmail OAuth2 handler", "component": "Gmail Connector", "type": "coding", "priority": 9},
        {"goal": "Build email polling loop", "component": "Gmail Connector", "type": "coding", "priority": 8},
        {"goal": "Parse email headers and body", "component": "Email Parser", "type": "coding", "priority": 7},
        {"goal": "Detect reply vs new thread", "component": "Email Parser", "type": "coding", "priority": 6},
        {"goal": "Build Slack webhook sender", "component": "Slack Alerter", "type": "coding", "priority": 5},
        {"goal": "Write integration tests", "component": "Slack Alerter", "type": "coding", "priority": 4},
    ],
}


class TestFullLifecycle:
    def test_complete_lifecycle(self, full_stack):
        from runtime.jb_companies import create_company, get_company, list_companies, attach_mission, set_focused_mission
        from runtime.jb_company_mapping import create_mapping, get_company_id_by_external
        from runtime.jb_missions import create_mission, get_mission, list_missions, approve_mission
        from runtime.jb_queue import list_tasks
        from runtime.jb_components import list_components, list_connections, build_graph

        # 1. Create company
        company_id = create_company(name="email-bot-project")
        create_mapping("frontend", "company:1234567890", company_id)
        assert get_company_id_by_external("frontend", "company:1234567890") == company_id

        # 2. Create mission in planning mode
        mission_id = create_mission(
            goal="Build email alert bot with Gmail and Slack",
            company_id=company_id,
            status="planning",
        )
        attach_mission(company_id, mission_id)
        set_focused_mission(company_id, mission_id)

        mission = get_mission(mission_id)
        assert mission["status"] == "planning"
        assert mission["items"] == []

        # 3. Generate plan (mock worker)
        from runtime.jb_plan_generate import generate_mission_plan

        def mock_call_worker(prompt):
            return {"ok": True, "text": json.dumps(MOCK_WORKER_RESPONSE)}

        with patch("runtime.jb_plan_generate.call_worker", side_effect=mock_call_worker):
            result = generate_mission_plan(mission_id)

        assert result["ok"]
        assert result["item_count"] == 6
        assert len(result["components"]) == 3

        # 4. Verify mission has items and components
        mission = get_mission(mission_id)
        assert mission["status"] == "planning"
        assert len(mission["items"]) == 6
        assert len(mission["components"]) == 3
        assert len(mission["connections"]) == 2

        comp_names = [c["name"] for c in mission["components"]]
        assert "Gmail Connector" in comp_names

        # 5. Approve mission
        result = approve_mission(mission_id)
        assert len(result["task_ids"]) == 6
        assert len(result["component_name_to_id"]) == 3

        mission = get_mission(mission_id)
        assert mission["status"] == "active"

        # 6. Verify components, tasks, graph
        components = list_components(workspace_id=company_id)
        assert len(components) == 3

        connections = list_connections(workspace_id=company_id)
        assert len(connections) == 2

        tasks = list_tasks()
        mission_tasks = [t for t in tasks if t.get("mission_id") == mission_id]
        assert len(mission_tasks) == 6
        for t in mission_tasks:
            assert t["status"] == "pending"

        graph = build_graph(company_id)
        assert len(graph["nodes"]) == 3
        assert len(graph["edges"]) == 2


class TestPlanRegeneration:
    def test_regenerate_replaces_items(self, full_stack):
        from runtime.jb_companies import create_company
        from runtime.jb_missions import create_mission, get_mission
        from runtime.jb_plan_generate import generate_mission_plan

        company_id = create_company(name="test-regen")
        mission_id = create_mission(goal="Test regeneration", company_id=company_id, status="planning")

        # First generation
        response_v1 = {
            "components": [{"name": "Comp A", "type": "processor", "description": "v1", "dependencies": []}],
            "tasks": [{"goal": "Build v1", "component": "Comp A", "type": "coding", "priority": 5}],
        }

        with patch("runtime.jb_plan_generate.call_worker", return_value={"ok": True, "text": json.dumps(response_v1)}):
            result = generate_mission_plan(mission_id)
        assert result["ok"]

        mission = get_mission(mission_id)
        assert len(mission["items"]) == 1
        assert mission["items"][0]["goal"] == "Build v1"

        # Second generation (refined)
        response_v2 = {
            "components": [
                {"name": "Comp A", "type": "processor", "description": "v2", "dependencies": []},
                {"name": "Comp B", "type": "output", "description": "new", "dependencies": ["Comp A"]},
            ],
            "tasks": [
                {"goal": "Build v2 refined", "component": "Comp A", "type": "coding", "priority": 5},
                {"goal": "Build output", "component": "Comp B", "type": "coding", "priority": 4},
            ],
        }

        with patch("runtime.jb_plan_generate.call_worker", return_value={"ok": True, "text": json.dumps(response_v2)}):
            result = generate_mission_plan(mission_id)
        assert result["ok"]

        mission = get_mission(mission_id)
        assert len(mission["items"]) == 2
        assert mission["items"][0]["goal"] == "Build v2 refined"
        assert mission["status"] == "planning"


class TestCommandLifecycle:
    def test_mission_commands(self, full_stack):
        from runtime.jb_companies import create_company
        from runtime.jb_commands import handle_command

        company_id = create_company(name="cmd-test")

        # /mission new
        result = handle_command("/mission new Build a test bot", workspace_id=company_id)
        assert result is not None
        assert "Mission created" in result["text"]

        # /mission (status)
        result = handle_command("/mission", workspace_id=company_id)
        assert "Planning Mode" in result["text"] or "planning" in result["text"].lower()

        # /mission cancel
        result = handle_command("/mission cancel", workspace_id=company_id)
        assert "cancelled" in result["text"].lower()

        # /status
        result = handle_command("/status", workspace_id=company_id)
        assert "cmd-test" in result["text"]

        # Regular message — not a command
        result = handle_command("hello world", workspace_id=company_id)
        assert result is None
