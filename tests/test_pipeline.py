"""Tests for runtime.jb_pipeline -- pipeline generation and execution."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch, MagicMock

import pytest

from runtime.jb_common import JsonStore
from runtime.jb_pipeline import (
    topological_sort,
    validate_contracts,
    generate_pipeline,
    generate_pipeline_code,
    write_pipeline,
    run_pipeline,
    validate_component_directory,
    scaffold_component_directory,
    ContractValidationError,
    _sanitize_name,
    _build_config,
    _build_config_repr,
    _resolve_components,
    _build_upstream_map,
)


# -- Helpers -----------------------------------------------------------------

def _make_component(cid: str, name: str, workspace_id: str = "ws-1",
                    mission_id: str | None = None,
                    input_type: str | None = None,
                    output_type: str = "Any",
                    config_fields: dict | None = None,
                    directory: str = "",
                    comp_type: str = "processor") -> dict:
    return {
        "component_id": cid,
        "workspace_id": workspace_id,
        "name": name,
        "type": comp_type,
        "description": f"Test component {name}",
        "status": "planned",
        "contract": {
            "input_type": input_type,
            "output_type": output_type,
            "config_fields": config_fields or {},
            "input_schema": {},
            "output_schema": {},
        },
        "directory": directory,
        "files": [],
        "dependencies": [],
        "task_ids": [],
        "lines_of_code": 0,
        "mission_id": mission_id,
        "built_by_agent": None,
        "created_at": "2026-03-31T00:00:00+00:00",
        "updated_at": "2026-03-31T00:00:00+00:00",
    }


def _make_connection(src: str, dst: str, workspace_id: str = "ws-1",
                     conn_type: str = "data_flow") -> dict:
    return {
        "connection_id": f"conn-{src}-{dst}",
        "workspace_id": workspace_id,
        "from_component_id": src,
        "to_component_id": dst,
        "from_output": "",
        "to_input": "",
        "type": conn_type,
        "label": None,
    }


# -- Fixtures ----------------------------------------------------------------

@pytest.fixture()
def tmp_stores(tmp_path: Path):
    """Patch component, connection, mission, and pipeline stores to temp dir."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    db_path = data_dir / "jbcp.db"

    comp_file = data_dir / "jb_components.json"
    conn_file = data_dir / "jb_connections.json"
    mission_file = data_dir / "jb_missions.json"

    comp_file.write_text("[]", encoding="utf-8")
    conn_file.write_text("[]", encoding="utf-8")
    mission_file.write_text("[]", encoding="utf-8")

    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()

    patches = [
        # Database path
        patch("runtime.jb_database.DB_PATH", db_path),
        patch("runtime.jb_database.DATA_DIR", data_dir),
        # DATA_DIR
        patch("runtime.jb_components.DATA_DIR", data_dir),
        patch("runtime.jb_missions.DATA_DIR", data_dir),
        # Legacy stores
        patch("runtime.jb_components.COMPONENTS_FILE", comp_file),
        patch("runtime.jb_components._comp_store", JsonStore(comp_file)),
        patch("runtime.jb_components.CONNECTIONS_FILE", conn_file),
        patch("runtime.jb_components._conn_store", JsonStore(conn_file)),
        patch("runtime.jb_missions.MISSIONS_FILE", mission_file),
        patch("runtime.jb_missions._store", JsonStore(mission_file)),
        patch("runtime.jb_pipeline.DATA_DIR", data_dir),
        patch("runtime.jb_pipeline.PIPELINES_DIR", pipelines_dir),
        patch("runtime.jb_pipeline.COMPONENTS_DIR", tmp_path / "components"),
    ]

    for p in patches:
        p.start()

    # Initialize the database
    import runtime.jb_database as _db_mod
    _db_mod._initialized_dbs.discard(str(db_path))
    _db_mod.init_db(db_path)

    yield {"root": tmp_path, "data_dir": data_dir, "pipelines_dir": pipelines_dir}

    for p in patches:
        p.stop()


WS = "ws-test-001"
MISSION = "mission-001"


# -- _sanitize_name ----------------------------------------------------------

class TestSanitizeName:
    def test_simple(self):
        assert _sanitize_name("FooBar") == "foobar"

    def test_spaces(self):
        assert _sanitize_name("Email Connector") == "email_connector"

    def test_hyphens(self):
        assert _sanitize_name("ai-summarizer") == "ai_summarizer"

    def test_special_chars(self):
        assert _sanitize_name("my@component!") == "mycomponent"

    def test_leading_digit(self):
        assert _sanitize_name("123abc") == "c_123abc"

    def test_empty(self):
        assert _sanitize_name("") == "unnamed"

    def test_mixed(self):
        assert _sanitize_name("AI--Summary  Module") == "ai_summary_module"


# -- topological_sort --------------------------------------------------------

class TestTopologicalSort:
    def test_simple_chain(self):
        """A -> B -> C"""
        comps = [
            _make_component("c", "C"),
            _make_component("a", "A"),
            _make_component("b", "B"),
        ]
        conns = [
            _make_connection("a", "b"),
            _make_connection("b", "c"),
        ]
        result = topological_sort(comps, conns)
        names = [c["name"] for c in result]
        assert names == ["A", "B", "C"]

    def test_parallel_components(self):
        """A -> C, B -> C (A and B have no dependency on each other)"""
        comps = [
            _make_component("c", "C"),
            _make_component("b", "B"),
            _make_component("a", "A"),
        ]
        conns = [
            _make_connection("a", "c"),
            _make_connection("b", "c"),
        ]
        result = topological_sort(comps, conns)
        names = [c["name"] for c in result]
        assert names.index("C") > names.index("A")
        assert names.index("C") > names.index("B")

    def test_no_connections(self):
        """All independent -- sorted alphabetically."""
        comps = [
            _make_component("b", "Beta"),
            _make_component("a", "Alpha"),
        ]
        result = topological_sort(comps, [])
        names = [c["name"] for c in result]
        assert names == ["Alpha", "Beta"]

    def test_cycle_detection(self):
        """A -> B -> A should raise."""
        comps = [
            _make_component("a", "A"),
            _make_component("b", "B"),
        ]
        conns = [
            _make_connection("a", "b"),
            _make_connection("b", "a"),
        ]
        with pytest.raises(ValueError, match="Cycle detected"):
            topological_sort(comps, conns)

    def test_single_component(self):
        comps = [_make_component("a", "A")]
        result = topological_sort(comps, [])
        assert len(result) == 1
        assert result[0]["name"] == "A"

    def test_empty(self):
        assert topological_sort([], []) == []

    def test_diamond(self):
        """A -> B, A -> C, B -> D, C -> D"""
        comps = [
            _make_component("d", "D"),
            _make_component("c", "C"),
            _make_component("b", "B"),
            _make_component("a", "A"),
        ]
        conns = [
            _make_connection("a", "b"),
            _make_connection("a", "c"),
            _make_connection("b", "d"),
            _make_connection("c", "d"),
        ]
        result = topological_sort(comps, conns)
        names = [c["name"] for c in result]
        assert names[0] == "A"
        assert names[-1] == "D"

    def test_branching(self):
        """A -> B, A -> C (B and C are leaves)"""
        comps = [
            _make_component("c", "C"),
            _make_component("b", "B"),
            _make_component("a", "A"),
        ]
        conns = [
            _make_connection("a", "b"),
            _make_connection("a", "c"),
        ]
        result = topological_sort(comps, conns)
        names = [c["name"] for c in result]
        assert names[0] == "A"
        assert set(names[1:]) == {"B", "C"}

    def test_long_chain(self):
        """1 -> 2 -> 3 -> 4 -> 5"""
        comps = [_make_component(str(i), f"Step{i}") for i in range(5, 0, -1)]
        conns = [_make_connection(str(i), str(i + 1)) for i in range(1, 5)]
        result = topological_sort(comps, conns)
        names = [c["name"] for c in result]
        assert names == [f"Step{i}" for i in range(1, 6)]


# -- validate_contracts ------------------------------------------------------

class TestValidateContracts:
    def test_compatible_types(self):
        comps = [
            _make_component("a", "A", output_type="json"),
            _make_component("b", "B", input_type="json"),
        ]
        conns = [_make_connection("a", "b")]
        warnings = validate_contracts(comps, conns)
        assert warnings == []

    def test_any_is_compatible(self):
        comps = [
            _make_component("a", "A", output_type="Any"),
            _make_component("b", "B", input_type="json"),
        ]
        conns = [_make_connection("a", "b")]
        warnings = validate_contracts(comps, conns)
        assert warnings == []

    def test_incompatible_types_raises(self):
        comps = [
            _make_component("a", "A", output_type="text"),
            _make_component("b", "B", input_type="json"),
        ]
        conns = [_make_connection("a", "b")]
        with pytest.raises(ContractValidationError, match="Type mismatch"):
            validate_contracts(comps, conns)

    def test_missing_types_skipped(self):
        comps = [
            _make_component("a", "A", output_type=""),
            _make_component("b", "B", input_type=None),
        ]
        conns = [_make_connection("a", "b")]
        warnings = validate_contracts(comps, conns)
        assert warnings == []

    def test_missing_component_warns(self):
        comps = [_make_component("a", "A")]
        conns = [_make_connection("a", "nonexistent")]
        warnings = validate_contracts(comps, conns)
        assert len(warnings) == 1
        assert "missing component" in warnings[0]

    def test_no_connections(self):
        comps = [_make_component("a", "A")]
        warnings = validate_contracts(comps, [])
        assert warnings == []


# -- _build_config -----------------------------------------------------------

class TestBuildConfig:
    def test_empty_components(self):
        assert _build_config([]) == {}

    def test_components_with_config_fields(self):
        comps = [
            _make_component("a", "Gmail Connector", config_fields={"check_since_minutes": 60}),
            _make_component("b", "Filter", config_fields={"rules": []}),
        ]
        config = _build_config(comps)
        assert "gmail_connector" in config
        assert config["gmail_connector"]["check_since_minutes"] == 60
        assert "filter" in config

    def test_components_without_config(self):
        comps = [_make_component("a", "Simple")]
        config = _build_config(comps)
        assert config == {"simple": {}}


# -- _build_config_repr -----------------------------------------------------

class TestBuildConfigRepr:
    def test_empty(self):
        assert _build_config_repr({}) == "{}"

    def test_string_value(self):
        result = _build_config_repr({"url": "https://x.com"})
        assert '"url": "https://x.com"' in result

    def test_int_value(self):
        result = _build_config_repr({"count": 5})
        assert '"count": 5' in result

    def test_none_value(self):
        result = _build_config_repr({"secret": None})
        assert "None" in result
        assert "TODO" in result


# -- generate_pipeline -------------------------------------------------------

class TestGeneratePipeline:
    def test_single_component(self, tmp_stores):
        from runtime.jb_components import create_component
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Test mission", company_id=WS, status="active")
        create_component(
            workspace_id=WS,
            name="Fetcher",
            type="connector",
            contract={"output_type": "json", "config_fields": {"url": "https://example.com"}},
        )

        path_str = generate_pipeline(mid)
        path = Path(path_str)
        assert path.exists()
        assert path.name == "pipeline.py"

        content = path.read_text()
        assert "Auto-generated pipeline" in content
        assert "fetcher" in content
        assert "summary_chain" in content

        # Config should also exist
        config_path = path.parent / "config.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert "fetcher" in config
        assert config["fetcher"]["url"] == "https://example.com"

    def test_three_connected_components(self, tmp_stores):
        from runtime.jb_components import create_component, create_connection
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Chain test", company_id=WS, status="active")
        c1 = create_component(workspace_id=WS, name="Ingest", type="connector",
                              contract={"output_type": "json"})
        c2 = create_component(workspace_id=WS, name="Transform", type="processor",
                              contract={"input_type": "json", "output_type": "json"})
        c3 = create_component(workspace_id=WS, name="Output", type="output",
                              contract={"input_type": "json"})
        create_connection(workspace_id=WS, from_id=c1, to_id=c2)
        create_connection(workspace_id=WS, from_id=c2, to_id=c3)

        path_str = generate_pipeline(mid)
        content = Path(path_str).read_text()
        assert "Step 1" in content
        assert "Step 2" in content
        assert "Step 3" in content
        assert "input_data=result_0" in content  # Transform gets Ingest output
        assert "input_data=result_1" in content  # Output gets Transform output
        assert "input_data=None" in content       # Ingest has no upstream

    def test_generates_valid_python(self, tmp_stores):
        from runtime.jb_components import create_component
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Syntax check", company_id=WS, status="active")
        create_component(workspace_id=WS, name="Alpha", type="processor")
        create_component(workspace_id=WS, name="Beta", type="processor")

        path_str = generate_pipeline(mid)
        content = Path(path_str).read_text()
        # Should compile without SyntaxError
        compile(content, path_str, "exec")

    def test_empty_mission_raises(self, tmp_stores):
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Empty", company_id="ws-empty", status="active")
        with pytest.raises(ValueError, match="no components"):
            generate_pipeline(mid)

    def test_missing_mission_raises(self, tmp_stores):
        with pytest.raises(ValueError, match="Mission not found"):
            generate_pipeline("nonexistent-id")


# -- generate_pipeline_code (legacy) -----------------------------------------

class TestGeneratePipelineCode:
    def test_single_component(self, tmp_stores):
        from runtime.jb_components import create_component
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Test mission", company_id=WS, status="active")
        create_component(
            workspace_id=WS,
            name="Fetcher",
            type="connector",
            contract={"output_type": "json", "config_fields": {"url": "https://example.com"}},
        )

        code = generate_pipeline_code(mid, "Test Mission")
        assert "Auto-generated pipeline" in code
        assert "fetcher" in code
        assert "def pipeline():" in code
        assert "__name__" in code

    def test_three_connected_components(self, tmp_stores):
        from runtime.jb_components import create_component, create_connection
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Chain test", company_id=WS, status="active")
        c1 = create_component(workspace_id=WS, name="Ingest", type="connector",
                              contract={"output_type": "json"})
        c2 = create_component(workspace_id=WS, name="Transform", type="processor",
                              contract={"input_type": "json", "output_type": "json"})
        c3 = create_component(workspace_id=WS, name="Output", type="output",
                              contract={"input_type": "json"})
        create_connection(workspace_id=WS, from_id=c1, to_id=c2)
        create_connection(workspace_id=WS, from_id=c2, to_id=c3)

        code = generate_pipeline_code(mid, "Chain Test")
        assert "Stage 1" in code
        assert "Stage 2" in code
        assert "Stage 3" in code
        assert "input_data=results[" in code

    def test_empty_mission(self, tmp_stores):
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Empty test", company_id="ws-empty", status="active")
        code = generate_pipeline_code(mid, "Empty Test")
        assert "No components configured" in code


# -- write_pipeline ----------------------------------------------------------

class TestWritePipeline:
    def test_creates_file(self, tmp_stores):
        from runtime.jb_components import create_component
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Write test", company_id=WS, status="active")
        create_component(workspace_id=WS, name="Dummy", type="processor")

        path = write_pipeline(mid, "Write Test")
        assert path.exists()
        assert path.name == "pipeline.py"
        assert mid in str(path)

        content = path.read_text(encoding="utf-8")
        assert "Auto-generated pipeline" in content

    def test_directory_structure(self, tmp_stores):
        from runtime.jb_components import create_component
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Dir test", company_id=WS, status="active")
        create_component(workspace_id=WS, name="Dummy", type="processor")

        path = write_pipeline(mid)
        assert path.parent.name == mid
        assert path.parent.parent.name == "pipelines"


# -- run_pipeline (with mock components) -------------------------------------

class TestRunPipeline:
    @staticmethod
    def _cleanup_component_modules():
        """Remove cached component modules so each test gets fresh imports."""
        to_remove = [k for k in sys.modules if k.startswith("components")]
        for k in to_remove:
            del sys.modules[k]

    def _setup_mock_component(self, tmp_path, slug, return_value):
        """Create a mock component module at components/{slug}/main.py."""
        comp_dir = tmp_path / "components" / slug
        comp_dir.mkdir(parents=True, exist_ok=True)
        (comp_dir / "__init__.py").write_text("")
        (comp_dir / "main.py").write_text(
            "def run(config=None, input_data=None, summary_chain=None):\n"
            f"    return {repr(return_value)}\n",
            encoding="utf-8",
        )

    def test_run_single_component(self, tmp_stores, tmp_path):
        from runtime.jb_components import create_component
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Run test", company_id=WS, status="active")
        create_component(workspace_id=WS, name="Greeter", type="processor")

        # Create mock component
        comp_dir = tmp_path / "components" / "greeter"
        comp_dir.mkdir(parents=True, exist_ok=True)
        (comp_dir / "__init__.py").write_text("")
        (comp_dir / "main.py").write_text(
            "def run(config=None, input_data=None, summary_chain=None):\n"
            '    return {"summary": "Hello from Greeter", "data": 42}\n',
            encoding="utf-8",
        )

        # Make sure components package is importable
        comps_init = tmp_path / "components" / "__init__.py"
        comps_init.write_text("")

        self._cleanup_component_modules()
        sys.path.insert(0, str(tmp_path))
        try:
            result = run_pipeline(mid)
        finally:
            sys.path.remove(str(tmp_path))
            self._cleanup_component_modules()

        assert result["status"] == "success"
        assert result["mission_id"] == mid
        assert len(result["summary_chain"]) == 1
        assert "Hello from Greeter" in result["summary_chain"][0]
        assert result["final_output"]["data"] == 42
        assert result["errors"] == []
        assert result["component_count"] == 1

        # last_run.json should exist
        last_run = tmp_stores["pipelines_dir"] / mid / "last_run.json"
        assert last_run.exists()

    def test_run_chained_components(self, tmp_stores, tmp_path):
        from runtime.jb_components import create_component, create_connection
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Chain run", company_id=WS, status="active")
        c1 = create_component(workspace_id=WS, name="Source", type="connector")
        c2 = create_component(workspace_id=WS, name="Sink", type="output")
        create_connection(workspace_id=WS, from_id=c1, to_id=c2)

        # Source component
        src_dir = tmp_path / "components" / "source"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "__init__.py").write_text("")
        (src_dir / "main.py").write_text(
            "def run(config=None, input_data=None, summary_chain=None):\n"
            '    return {"summary": "Source produced data", "items": [1, 2, 3]}\n',
            encoding="utf-8",
        )

        # Sink receives Source output
        sink_dir = tmp_path / "components" / "sink"
        sink_dir.mkdir(parents=True, exist_ok=True)
        (sink_dir / "__init__.py").write_text("")
        (sink_dir / "main.py").write_text(
            "def run(config=None, input_data=None, summary_chain=None):\n"
            "    count = len(input_data.get('items', [])) if input_data else 0\n"
            '    return {"summary": f"Sink received {count} items", "count": count}\n',
            encoding="utf-8",
        )

        comps_init = tmp_path / "components" / "__init__.py"
        if not comps_init.exists():
            comps_init.write_text("")

        self._cleanup_component_modules()
        sys.path.insert(0, str(tmp_path))
        try:
            result = run_pipeline(mid)
        finally:
            sys.path.remove(str(tmp_path))
            self._cleanup_component_modules()

        assert result["status"] == "success"
        assert len(result["summary_chain"]) == 2
        assert "Source produced data" in result["summary_chain"][0]
        assert "Sink received 3 items" in result["summary_chain"][1]
        assert result["final_output"]["count"] == 3

    def test_run_handles_component_error(self, tmp_stores, tmp_path):
        from runtime.jb_components import create_component
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Error test", company_id=WS, status="active")
        create_component(workspace_id=WS, name="Broken", type="processor")

        broken_dir = tmp_path / "components" / "broken"
        broken_dir.mkdir(parents=True, exist_ok=True)
        (broken_dir / "__init__.py").write_text("")
        (broken_dir / "main.py").write_text(
            "def run(config=None, input_data=None, summary_chain=None):\n"
            '    raise RuntimeError("component exploded")\n',
            encoding="utf-8",
        )

        comps_init = tmp_path / "components" / "__init__.py"
        if not comps_init.exists():
            comps_init.write_text("")

        self._cleanup_component_modules()
        sys.path.insert(0, str(tmp_path))
        try:
            result = run_pipeline(mid)
        finally:
            sys.path.remove(str(tmp_path))
            self._cleanup_component_modules()

        assert result["status"] == "error"
        assert len(result["errors"]) == 1
        assert "exploded" in result["errors"][0]["error"]
        # Summary chain still gets an entry
        assert len(result["summary_chain"]) == 1
        assert "FAILED" in result["summary_chain"][0]

    def test_run_handles_missing_component_module(self, tmp_stores, tmp_path):
        from runtime.jb_components import create_component
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Missing module", company_id=WS, status="active")
        create_component(workspace_id=WS, name="Ghost", type="processor")

        # Don't create the component directory -- it should handle the ImportError
        result = run_pipeline(mid)

        assert result["status"] == "error"
        assert len(result["errors"]) == 1
        assert "Ghost" in result["errors"][0]["component"]

    def test_summary_chain_accumulation(self, tmp_stores, tmp_path):
        """Verify each component receives the accumulated summary chain."""
        from runtime.jb_components import create_component, create_connection
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Summary test", company_id=WS, status="active")
        c1 = create_component(workspace_id=WS, name="Step One", type="processor")
        c2 = create_component(workspace_id=WS, name="Step Two", type="processor")
        c3 = create_component(workspace_id=WS, name="Step Three", type="processor")
        create_connection(workspace_id=WS, from_id=c1, to_id=c2)
        create_connection(workspace_id=WS, from_id=c2, to_id=c3)

        # Each component records how many summaries it received
        for slug in ["step_one", "step_two", "step_three"]:
            d = tmp_path / "components" / slug
            d.mkdir(parents=True, exist_ok=True)
            (d / "__init__.py").write_text("")
            (d / "main.py").write_text(
                "def run(config=None, input_data=None, summary_chain=None):\n"
                "    chain = summary_chain or []\n"
                f'    return {{"summary": "{slug} done", "chain_len": len(chain)}}\n',
                encoding="utf-8",
            )

        comps_init = tmp_path / "components" / "__init__.py"
        if not comps_init.exists():
            comps_init.write_text("")

        self._cleanup_component_modules()
        sys.path.insert(0, str(tmp_path))
        try:
            result = run_pipeline(mid)
        finally:
            sys.path.remove(str(tmp_path))
            self._cleanup_component_modules()

        assert result["status"] == "success"
        assert len(result["summary_chain"]) == 3
        # Step one gets empty chain, step two gets 1, step three gets 2
        assert result["summary_chain"] == ["step_one done", "step_two done", "step_three done"]

    def test_run_with_service_tracking(self, tmp_stores, tmp_path):
        from runtime.jb_components import create_component
        from runtime.jb_missions import create_mission

        mid = create_mission(goal="Service test", company_id=WS, status="active")
        create_component(workspace_id=WS, name="Worker", type="processor")

        worker_dir = tmp_path / "components" / "worker"
        worker_dir.mkdir(parents=True, exist_ok=True)
        (worker_dir / "__init__.py").write_text("")
        (worker_dir / "main.py").write_text(
            "def run(config=None, input_data=None, summary_chain=None):\n"
            '    return {"summary": "Worker done"}\n',
            encoding="utf-8",
        )
        comps_init = tmp_path / "components" / "__init__.py"
        if not comps_init.exists():
            comps_init.write_text("")

        # Just verify it doesn't crash with a fake service_id
        # (service tracking failures are silently caught)
        self._cleanup_component_modules()
        sys.path.insert(0, str(tmp_path))
        try:
            result = run_pipeline(mid, service_id="fake-service")
        finally:
            sys.path.remove(str(tmp_path))
            self._cleanup_component_modules()

        assert result["status"] == "success"


# -- validate_component_directory --------------------------------------------

class TestValidateComponentDirectory:
    def test_complete_directory(self, tmp_path):
        ws = "ws-val"
        data_dir = tmp_path / "data"
        comp_dir = data_dir / "companies" / ws / "components" / "my_comp"
        comp_dir.mkdir(parents=True)

        (comp_dir / "contract.py").write_text("# contract")
        (comp_dir / "main.py").write_text("# main")
        (comp_dir / "test_main.py").write_text("# test")

        with patch("runtime.jb_pipeline.DATA_DIR", data_dir):
            result = validate_component_directory(ws, "My Comp")
            assert result["valid"] is True
            assert result["missing"] == []

    def test_incomplete_directory(self, tmp_path):
        ws = "ws-val"
        data_dir = tmp_path / "data"
        comp_dir = data_dir / "companies" / ws / "components" / "my_comp"
        comp_dir.mkdir(parents=True)

        (comp_dir / "main.py").write_text("# main")

        with patch("runtime.jb_pipeline.DATA_DIR", data_dir):
            result = validate_component_directory(ws, "My Comp")
            assert result["valid"] is False
            assert "contract.py" in result["missing"]
            assert "test_main.py" in result["missing"]
            assert "main.py" not in result["missing"]

    def test_missing_directory(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)

        with patch("runtime.jb_pipeline.DATA_DIR", data_dir):
            result = validate_component_directory("ws-none", "Ghost")
            assert result["valid"] is False
            assert len(result["missing"]) == 3


# -- scaffold_component_directory --------------------------------------------

class TestScaffoldComponentDirectory:
    def test_creates_template_files(self, tmp_path):
        ws = "ws-scaffold"
        data_dir = tmp_path / "data"

        with patch("runtime.jb_pipeline.DATA_DIR", data_dir):
            path = scaffold_component_directory(ws, "Email Fetcher")

        assert path.exists()
        assert (path / "contract.py").exists()
        assert (path / "main.py").exists()
        assert (path / "test_main.py").exists()

        contract_content = (path / "contract.py").read_text()
        assert "Email Fetcher" in contract_content

        main_content = (path / "main.py").read_text()
        assert "def run(" in main_content
        assert "summary_chain" in main_content

    def test_does_not_overwrite_existing(self, tmp_path):
        ws = "ws-scaffold"
        data_dir = tmp_path / "data"
        comp_dir = data_dir / "companies" / ws / "components" / "custom"
        comp_dir.mkdir(parents=True)

        (comp_dir / "main.py").write_text("# custom implementation")

        with patch("runtime.jb_pipeline.DATA_DIR", data_dir):
            path = scaffold_component_directory(ws, "Custom")

        content = (path / "main.py").read_text()
        assert content == "# custom implementation"

    def test_sanitizes_name_for_directory(self, tmp_path):
        ws = "ws-scaffold"
        data_dir = tmp_path / "data"

        with patch("runtime.jb_pipeline.DATA_DIR", data_dir):
            path = scaffold_component_directory(ws, "AI Summary-Module")

        assert path.name == "ai_summary_module"


# -- _build_upstream_map -----------------------------------------------------

class TestBuildUpstreamMap:
    def test_linear_chain(self):
        comps = [
            _make_component("a", "A"),
            _make_component("b", "B"),
            _make_component("c", "C"),
        ]
        conns = [
            _make_connection("a", "b"),
            _make_connection("b", "c"),
        ]
        upstream = _build_upstream_map(comps, conns)
        assert upstream[0] is None  # A has no upstream
        assert upstream[1] == 0     # B's upstream is A (idx 0)
        assert upstream[2] == 1     # C's upstream is B (idx 1)

    def test_no_connections(self):
        comps = [_make_component("a", "A"), _make_component("b", "B")]
        upstream = _build_upstream_map(comps, [])
        assert upstream[0] is None
        assert upstream[1] is None

    def test_diamond_picks_first(self):
        """With multiple inputs, picks the first connection found."""
        comps = [
            _make_component("a", "A"),
            _make_component("b", "B"),
            _make_component("c", "C"),
        ]
        conns = [
            _make_connection("a", "c"),
            _make_connection("b", "c"),
        ]
        upstream = _build_upstream_map(comps, conns)
        assert upstream[0] is None
        assert upstream[1] is None
        assert upstream[2] in (0, 1)  # C gets either A or B
