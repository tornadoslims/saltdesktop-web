"""Tests for runtime.jb_components -- component registry and connection graph."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from runtime.jb_common import JsonStore
from runtime.jb_components import (
    create_component,
    get_component,
    list_components,
    mark_component_status,
    attach_task,
    add_file,
    list_connections,
    create_connection,
    delete_connection,
    build_graph,
    check_component_lifecycle,
    VALID_COMPONENT_TYPES,
    VALID_COMPONENT_STATUSES,
)


@pytest.fixture()
def tmp_components(tmp_path: Path):
    """Patch component and connection stores to use temp directory with SQLite."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    db_path = data_dir / "jbcp.db"

    # Legacy JSON files
    components_file = data_dir / "jb_components.json"
    connections_file = data_dir / "jb_connections.json"
    components_file.write_text("[]", encoding="utf-8")
    connections_file.write_text("[]", encoding="utf-8")

    patches = [
        # Database path
        patch("runtime.jb_database.DB_PATH", db_path),
        patch("runtime.jb_database.DATA_DIR", data_dir),
        # DATA_DIR
        patch("runtime.jb_components.DATA_DIR", data_dir),
        # Legacy stores
        patch("runtime.jb_components.COMPONENTS_FILE", components_file),
        patch("runtime.jb_components._comp_store", JsonStore(components_file)),
        patch("runtime.jb_components.CONNECTIONS_FILE", connections_file),
        patch("runtime.jb_components._conn_store", JsonStore(connections_file)),
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


# -- CreateComponent ---------------------------------------------------------

class TestCreateComponent:
    def test_returns_id(self, tmp_components):
        cid = create_component(workspace_id=WS, name="Parser", type="processor")
        assert isinstance(cid, str)
        assert len(cid) > 0

    def test_preserves_name(self, tmp_components):
        cid = create_component(workspace_id=WS, name="Parser", type="processor")
        comp = get_component(cid)
        assert comp["name"] == "Parser"

    def test_preserves_type(self, tmp_components):
        cid = create_component(workspace_id=WS, name="Parser", type="processor")
        comp = get_component(cid)
        assert comp["type"] == "processor"

    def test_preserves_description(self, tmp_components):
        cid = create_component(
            workspace_id=WS, name="Parser", type="processor",
            description="Parses input data",
        )
        comp = get_component(cid)
        assert comp["description"] == "Parses input data"

    def test_validates_type(self, tmp_components):
        with pytest.raises(ValueError, match="Invalid component type"):
            create_component(workspace_id=WS, name="Bad", type="invalid_type")

    def test_all_valid_types_accepted(self, tmp_components):
        for t in VALID_COMPONENT_TYPES:
            cid = create_component(workspace_id=WS, name=f"Comp-{t}", type=t)
            assert cid

    def test_rejects_empty_name(self, tmp_components):
        with pytest.raises(ValueError, match="non-empty string"):
            create_component(workspace_id=WS, name="", type="processor")

    def test_rejects_whitespace_name(self, tmp_components):
        with pytest.raises(ValueError, match="non-empty string"):
            create_component(workspace_id=WS, name="   ", type="processor")

    def test_stores_contract(self, tmp_components):
        contract = {
            "input_type": "json",
            "output_type": "csv",
            "config_fields": {"delimiter": ","},
        }
        cid = create_component(
            workspace_id=WS, name="Converter", type="processor",
            contract=contract,
        )
        comp = get_component(cid)
        assert comp["contract"]["input_type"] == "json"
        assert comp["contract"]["output_type"] == "csv"
        assert comp["contract"]["config_fields"]["delimiter"] == ","

    def test_default_status_is_planned(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        comp = get_component(cid)
        assert comp["status"] == "planned"

    def test_requires_workspace_id(self, tmp_components):
        with pytest.raises(ValueError, match="workspace_id"):
            create_component(workspace_id="", name="X", type="processor")

    def test_mission_id_stored(self, tmp_components):
        cid = create_component(workspace_id=WS, name="Parser", type="processor")
        from runtime.jb_components import update_component
        updated = update_component(cid, {"mission_id": "mission-xyz-789"})
        assert updated["mission_id"] == "mission-xyz-789"
        comp = get_component(cid)
        assert comp["mission_id"] == "mission-xyz-789"

    def test_mission_id_defaults_none(self, tmp_components):
        cid = create_component(workspace_id=WS, name="Parser", type="processor")
        comp = get_component(cid)
        assert comp["mission_id"] is None


# -- GetComponent ------------------------------------------------------------

class TestGetComponent:
    def test_existing(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        comp = get_component(cid)
        assert comp is not None
        assert comp["component_id"] == cid

    def test_nonexistent(self, tmp_components):
        assert get_component("nonexistent-id") is None


# -- ListComponents ----------------------------------------------------------

class TestListComponents:
    def test_empty(self, tmp_components):
        assert list_components() == []

    def test_returns_all(self, tmp_components):
        create_component(workspace_id=WS, name="A", type="processor")
        create_component(workspace_id=WS, name="B", type="connector")
        assert len(list_components()) == 2

    def test_filter_by_workspace_id(self, tmp_components):
        create_component(workspace_id="ws-1", name="A", type="processor")
        create_component(workspace_id="ws-2", name="B", type="processor")
        create_component(workspace_id="ws-1", name="C", type="connector")

        ws1 = list_components(workspace_id="ws-1")
        ws2 = list_components(workspace_id="ws-2")
        assert len(ws1) == 2
        assert len(ws2) == 1
        assert all(c["workspace_id"] == "ws-1" for c in ws1)

    def test_filter_nonexistent_workspace(self, tmp_components):
        create_component(workspace_id=WS, name="A", type="processor")
        assert list_components(workspace_id="no-such-ws") == []


# -- ComponentStatus ---------------------------------------------------------

class TestComponentStatus:
    def test_mark_planned_to_building(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        result = mark_component_status(cid, "building")
        assert result["status"] == "building"

    def test_mark_building_to_built(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        mark_component_status(cid, "building")
        result = mark_component_status(cid, "built")
        assert result["status"] == "built"

    def test_mark_built_to_deployed(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        mark_component_status(cid, "built")
        result = mark_component_status(cid, "deployed")
        assert result["status"] == "deployed"

    def test_invalid_status_raises(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        with pytest.raises(ValueError, match="Invalid component status"):
            mark_component_status(cid, "bogus")

    def test_all_valid_statuses(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        for status in VALID_COMPONENT_STATUSES:
            result = mark_component_status(cid, status)
            assert result["status"] == status

    def test_status_persists(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        mark_component_status(cid, "deployed")
        comp = get_component(cid)
        assert comp["status"] == "deployed"


# -- AttachTask --------------------------------------------------------------

class TestAttachTask:
    def test_attach_task(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        result = attach_task(cid, "task-1")
        assert "task-1" in result["task_ids"]

    def test_attach_multiple(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        attach_task(cid, "task-1")
        result = attach_task(cid, "task-2")
        assert result["task_ids"] == ["task-1", "task-2"]

    def test_no_duplicates(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        attach_task(cid, "task-1")
        result = attach_task(cid, "task-1")
        assert result["task_ids"].count("task-1") == 1

    def test_nonexistent_component_raises(self, tmp_components):
        with pytest.raises(ValueError, match="Component not found"):
            attach_task("nonexistent", "task-1")


# -- AddFile -----------------------------------------------------------------

class TestAddFile:
    def test_add_file(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        result = add_file(cid, "src/parser.py")
        assert "src/parser.py" in result["files"]

    def test_add_multiple(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        add_file(cid, "src/parser.py")
        result = add_file(cid, "src/utils.py")
        assert len(result["files"]) == 2
        assert "src/parser.py" in result["files"]
        assert "src/utils.py" in result["files"]

    def test_no_duplicate_files(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        add_file(cid, "src/parser.py")
        result = add_file(cid, "src/parser.py")
        assert result["files"].count("src/parser.py") == 1

    def test_nonexistent_component_raises(self, tmp_components):
        with pytest.raises(ValueError, match="Component not found"):
            add_file("nonexistent", "file.py")


# -- Connections -------------------------------------------------------------

class TestConnections:
    def test_create_connection(self, tmp_components):
        c1 = create_component(workspace_id=WS, name="A", type="connector")
        c2 = create_component(workspace_id=WS, name="B", type="processor")
        conn_id = create_connection(workspace_id=WS, from_id=c1, to_id=c2)
        assert isinstance(conn_id, str)
        assert len(conn_id) > 0

    def test_list_connections(self, tmp_components):
        c1 = create_component(workspace_id=WS, name="A", type="connector")
        c2 = create_component(workspace_id=WS, name="B", type="processor")
        create_connection(workspace_id=WS, from_id=c1, to_id=c2)
        conns = list_connections()
        assert len(conns) == 1
        assert conns[0]["from_component_id"] == c1
        assert conns[0]["to_component_id"] == c2

    def test_delete_connection(self, tmp_components):
        c1 = create_component(workspace_id=WS, name="A", type="connector")
        c2 = create_component(workspace_id=WS, name="B", type="processor")
        conn_id = create_connection(workspace_id=WS, from_id=c1, to_id=c2)
        assert delete_connection(conn_id) is True
        assert list_connections() == []

    def test_delete_nonexistent(self, tmp_components):
        assert delete_connection("nonexistent") is False

    def test_filter_by_workspace_id(self, tmp_components):
        c1 = create_component(workspace_id="ws-1", name="A", type="connector")
        c2 = create_component(workspace_id="ws-1", name="B", type="processor")
        c3 = create_component(workspace_id="ws-2", name="C", type="processor")
        c4 = create_component(workspace_id="ws-2", name="D", type="output")

        create_connection(workspace_id="ws-1", from_id=c1, to_id=c2)
        create_connection(workspace_id="ws-2", from_id=c3, to_id=c4)

        assert len(list_connections(workspace_id="ws-1")) == 1
        assert len(list_connections(workspace_id="ws-2")) == 1
        assert len(list_connections()) == 2

    def test_connection_type_default(self, tmp_components):
        c1 = create_component(workspace_id=WS, name="A", type="connector")
        c2 = create_component(workspace_id=WS, name="B", type="processor")
        create_connection(workspace_id=WS, from_id=c1, to_id=c2)
        conn = list_connections()[0]
        assert conn["type"] == "data_flow"

    def test_connection_type_control_flow(self, tmp_components):
        c1 = create_component(workspace_id=WS, name="A", type="connector")
        c2 = create_component(workspace_id=WS, name="B", type="processor")
        create_connection(workspace_id=WS, from_id=c1, to_id=c2, type="control_flow")
        conn = list_connections()[0]
        assert conn["type"] == "control_flow"

    def test_invalid_connection_type_raises(self, tmp_components):
        with pytest.raises(ValueError, match="Invalid connection type"):
            create_connection(workspace_id=WS, from_id="a", to_id="b", type="bad")


# -- BuildGraph --------------------------------------------------------------

class TestBuildGraph:
    def test_empty_workspace(self, tmp_components):
        graph = build_graph("empty-ws")
        assert graph["nodes"] == []
        assert graph["edges"] == []

    def test_single_component(self, tmp_components):
        create_component(workspace_id=WS, name="Solo", type="processor")
        graph = build_graph(WS)
        assert len(graph["nodes"]) == 1
        assert graph["nodes"][0]["label"] == "Solo"
        assert graph["edges"] == []

    def test_connected_components_nodes_and_edges(self, tmp_components):
        c1 = create_component(workspace_id=WS, name="Source", type="connector")
        c2 = create_component(workspace_id=WS, name="Transform", type="processor")
        c3 = create_component(workspace_id=WS, name="Sink", type="output")
        create_connection(workspace_id=WS, from_id=c1, to_id=c2, label="raw data")
        create_connection(workspace_id=WS, from_id=c2, to_id=c3, label="processed")

        graph = build_graph(WS)
        assert len(graph["nodes"]) == 3
        assert len(graph["edges"]) == 2

        node_labels = {n["label"] for n in graph["nodes"]}
        assert node_labels == {"Source", "Transform", "Sink"}

        # Both from/to and source/target should be present
        edge_froms = {e["from"] for e in graph["edges"]}
        edge_sources = {e["source"] for e in graph["edges"]}
        assert c1 in edge_froms
        assert c2 in edge_froms
        assert edge_froms == edge_sources

    def test_component_status_reflected_in_node(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        mark_component_status(cid, "deployed")
        graph = build_graph(WS)
        node = graph["nodes"][0]
        assert node["status"] == "deployed"
        assert node["metadata"]["build_progress_percent"] == 100

    def test_building_status_progress(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        mark_component_status(cid, "building")
        graph = build_graph(WS)
        node = graph["nodes"][0]
        assert node["metadata"]["build_progress_percent"] == 25

    def test_node_type_matches_component(self, tmp_components):
        create_component(workspace_id=WS, name="AI Thing", type="ai")
        graph = build_graph(WS)
        assert graph["nodes"][0]["type"] == "ai"

    def test_node_has_enriched_fields(self, tmp_components):
        cid = create_component(
            workspace_id=WS, name="Enriched", type="processor",
            description="A test component",
            contract={"input_type": "json", "output_type": "csv", "config_fields": {"sep": ","}},
        )
        from runtime.jb_components import update_component
        update_component(cid, {"mission_id": "mission-abc"})

        graph = build_graph(WS)
        node = graph["nodes"][0]

        assert node["mission_id"] == "mission-abc"
        assert node["description"] == "A test component"
        assert node["contract"]["input_type"] == "json"
        assert node["contract"]["output_type"] == "csv"
        assert "sep" in node["contract"]["config_fields"]
        assert node["display_status"] == "Planned"
        assert node["is_active"] is False
        assert node["active_agent"] is None
        assert node["built_by"] is None
        assert "progress_percent" in node

    def test_display_status_uses_label(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        mark_component_status(cid, "deployed")
        graph = build_graph(WS)
        node = graph["nodes"][0]
        assert node["display_status"] == "Live"

    def test_edge_has_source_target(self, tmp_components):
        c1 = create_component(workspace_id=WS, name="A", type="connector")
        c2 = create_component(workspace_id=WS, name="B", type="processor")
        create_connection(workspace_id=WS, from_id=c1, to_id=c2, label="data")

        graph = build_graph(WS)
        edge = graph["edges"][0]
        assert edge["source"] == c1
        assert edge["target"] == c2
        # Backward compat: from/to still present
        assert edge["from"] == c1
        assert edge["to"] == c2

    def test_edge_display_label(self, tmp_components):
        c1 = create_component(workspace_id=WS, name="A", type="connector")
        c2 = create_component(workspace_id=WS, name="B", type="processor")
        create_connection(workspace_id=WS, from_id=c1, to_id=c2, label="raw_data")

        graph = build_graph(WS)
        edge = graph["edges"][0]
        assert edge["display_label"] == "Raw Data"

    def test_edge_label_auto_derived_from_contract(self, tmp_components):
        c1 = create_component(
            workspace_id=WS, name="Source", type="connector",
            contract={"output_type": "email_list"},
        )
        c2 = create_component(workspace_id=WS, name="Sink", type="output")
        create_connection(workspace_id=WS, from_id=c1, to_id=c2)  # no label

        graph = build_graph(WS)
        edge = graph["edges"][0]
        assert edge["label"] == "email_list"
        assert edge["display_label"] == "Email List"

    def test_progress_percent_from_tasks(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        attach_task(cid, "t1")
        attach_task(cid, "t2")
        attach_task(cid, "t3")
        attach_task(cid, "t4")

        def mock_get_task(tid):
            if tid in ("t1", "t2"):
                return {"status": "complete"}
            elif tid == "t3":
                return {"status": "running"}
            else:
                return {"status": "pending"}

        with patch("runtime.jb_queue.get_task", mock_get_task):
            graph = build_graph(WS)

        node = graph["nodes"][0]
        assert node["progress_percent"] == 50.0

    def test_is_active_with_running_task(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        attach_task(cid, "t1")

        mock_get = MagicMock(return_value={"status": "running"})
        with patch("runtime.jb_queue.get_task", mock_get):
            graph = build_graph(WS)

        node = graph["nodes"][0]
        assert node["is_active"] is True

    def test_is_active_with_dispatched_task(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        attach_task(cid, "t1")

        mock_get = MagicMock(return_value={"status": "dispatched"})
        with patch("runtime.jb_queue.get_task", mock_get):
            graph = build_graph(WS)

        node = graph["nodes"][0]
        assert node["is_active"] is True

    def test_is_active_false_with_only_complete_tasks(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        attach_task(cid, "t1")

        mock_get = MagicMock(return_value={"status": "complete"})
        with patch("runtime.jb_queue.get_task", mock_get):
            graph = build_graph(WS)

        node = graph["nodes"][0]
        assert node["is_active"] is False

    def test_progress_percent_no_tasks_uses_status_heuristic(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        mark_component_status(cid, "building")
        graph = build_graph(WS)
        node = graph["nodes"][0]
        # No tasks linked, falls back to status-based heuristic
        assert node["progress_percent"] == 25


# -- ComponentLifecycle ------------------------------------------------------

class TestComponentLifecycle:
    def test_all_tasks_complete_marks_built(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor", status="building")
        attach_task(cid, "t1")
        attach_task(cid, "t2")

        mock_get_task = MagicMock(return_value={"status": "complete"})
        with patch("runtime.jb_components.get_task", mock_get_task, create=True):
            # Patch the import inside check_component_lifecycle
            with patch.dict("sys.modules", {"runtime.jb_queue": MagicMock(get_task=mock_get_task)}):
                result = check_component_lifecycle(cid)

        assert result["new_status"] == "built"
        assert result["previous_status"] == "building"
        assert result["reason"] == "all tasks complete"

    def test_some_tasks_pending_no_change(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor", status="building")
        attach_task(cid, "t1")
        attach_task(cid, "t2")

        def mock_get(tid):
            if tid == "t1":
                return {"status": "complete"}
            return {"status": "pending"}

        mock_module = MagicMock()
        mock_module.get_task = mock_get
        with patch.dict("sys.modules", {"runtime.jb_queue": mock_module}):
            result = check_component_lifecycle(cid)

        assert result["new_status"] == "building"
        assert "in progress" in result["reason"]

    def test_no_tasks_linked(self, tmp_components):
        cid = create_component(workspace_id=WS, name="X", type="processor")
        # No tasks attached -- lifecycle import may or may not work
        # The function handles both cases
        result = check_component_lifecycle(cid)
        assert result["new_status"] == result["previous_status"]
        assert "no tasks" in result["reason"] or "not available" in result["reason"]

    def test_nonexistent_component_raises(self, tmp_components):
        with pytest.raises(ValueError, match="Component not found"):
            check_component_lifecycle("nonexistent")
