# runtime/jb_pipeline.py
#
# Pipeline Generator + Runner for JBCP.
# Takes a mission's component graph, topologically sorts it,
# generates a standalone pipeline.py with config.json, and can
# execute the pipeline directly (in-process).
#
# "No framework. Just imports and function calls. The graph IS the code."

from __future__ import annotations

import importlib
import json
import re
import sys
import time
import traceback
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.jb_common import BASE_DIR, DATA_DIR, utc_now_iso


COMPONENTS_DIR = BASE_DIR / "components"
PIPELINES_DIR = BASE_DIR / "pipelines"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class ContractValidationError(Exception):
    """Raised when component contracts are incompatible across a connection."""
    pass


def _sanitize_name(name: str) -> str:
    """Convert component name to valid Python identifier / filesystem slug.

    Lowercase, replace spaces/hyphens with underscores, strip non-alphanumeric.
    """
    s = name.lower().strip()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    if s and s[0].isdigit():
        s = f"c_{s}"
    return s or "unnamed"


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------

def topological_sort(
    components: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort components by data-flow dependency order (Kahn's algorithm).

    Components with no inbound connections come first.
    Deterministic: ties broken alphabetically by component name.
    Raises ValueError on cycles.
    """
    if not components:
        return []

    id_to_comp = {c["component_id"]: c for c in components}
    comp_ids = set(id_to_comp.keys())

    adj: dict[str, list[str]] = {cid: [] for cid in comp_ids}
    in_degree: dict[str, int] = {cid: 0 for cid in comp_ids}

    for conn in connections:
        src = conn["from_component_id"]
        dst = conn["to_component_id"]
        if src in comp_ids and dst in comp_ids:
            adj[src].append(dst)
            in_degree[dst] += 1

    queue = sorted(
        [cid for cid, deg in in_degree.items() if deg == 0],
        key=lambda cid: id_to_comp[cid].get("name", ""),
    )
    result: list[str] = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in sorted(adj[node], key=lambda cid: id_to_comp[cid].get("name", "")):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
        queue.sort(key=lambda cid: id_to_comp[cid].get("name", ""))

    if len(result) != len(comp_ids):
        raise ValueError(
            f"Cycle detected in component graph. "
            f"Sorted {len(result)} of {len(comp_ids)} components."
        )

    return [id_to_comp[cid] for cid in result]


# ---------------------------------------------------------------------------
# Contract validation
# ---------------------------------------------------------------------------

def validate_contracts(
    components: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> list[str]:
    """Validate that connected components have compatible contracts.

    Returns list of warning strings.
    Raises ContractValidationError on critical incompatibility.
    """
    id_to_comp = {c["component_id"]: c for c in components}
    warnings: list[str] = []

    for conn in connections:
        src_id = conn["from_component_id"]
        dst_id = conn["to_component_id"]

        src = id_to_comp.get(src_id)
        dst = id_to_comp.get(dst_id)

        if src is None or dst is None:
            warnings.append(
                f"Connection references missing component: "
                f"from={src_id} to={dst_id}"
            )
            continue

        src_contract = src.get("contract", {})
        dst_contract = dst.get("contract", {})

        src_output = src_contract.get("output_type")
        dst_input = dst_contract.get("input_type")

        if not src_output or not dst_input:
            continue
        if src_output == "Any" or dst_input == "Any":
            continue
        if src_output != dst_input:
            msg = (
                f"Type mismatch: {src.get('name', src_id)} outputs "
                f"'{src_output}' but {dst.get('name', dst_id)} expects "
                f"'{dst_input}'"
            )
            raise ContractValidationError(msg)

    return warnings


# ---------------------------------------------------------------------------
# Internal: resolve mission components
# ---------------------------------------------------------------------------

def _resolve_components(mission_id: str) -> tuple[list[dict], list[dict]]:
    """Load and return (components, connections) for a mission.

    Uses committed component records when available; falls back to the
    draft components/connections stored on the mission object itself.
    """
    from runtime.jb_missions import get_mission
    from runtime.jb_components import list_components, list_connections

    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")

    workspace_id = mission.get("company_id") or mission_id

    # Try committed components first
    all_comps = list_components(workspace_id=workspace_id)
    components = [c for c in all_comps if c.get("mission_id") == mission_id]

    if components:
        comp_id_set = {c["component_id"] for c in components}
        all_conns = list_connections(workspace_id=workspace_id)
        connections = [
            cn for cn in all_conns
            if cn["from_component_id"] in comp_id_set
            and cn["to_component_id"] in comp_id_set
        ]
        return components, connections

    # Fall back to all workspace components
    if all_comps:
        comp_id_set = {c["component_id"] for c in all_comps}
        all_conns = list_connections(workspace_id=workspace_id)
        connections = [
            cn for cn in all_conns
            if cn["from_component_id"] in comp_id_set
            and cn["to_component_id"] in comp_id_set
        ]
        return all_comps, connections

    # Fall back to draft components on the mission
    draft_comps = mission.get("components", [])
    draft_conns = mission.get("connections", [])
    if draft_comps:
        # Synthesize component_id from name for consistency
        for c in draft_comps:
            if "component_id" not in c:
                c["component_id"] = _sanitize_name(c.get("name", ""))
        for cn in draft_conns:
            if "from_component_id" not in cn:
                cn["from_component_id"] = _sanitize_name(cn.get("from", ""))
            if "to_component_id" not in cn:
                cn["to_component_id"] = _sanitize_name(cn.get("to", ""))

    return draft_comps, draft_conns


def _build_upstream_map(
    sorted_components: list[dict],
    connections: list[dict],
) -> dict[int, int | None]:
    """Map each component index to the index of its first upstream source."""
    id_to_idx = {c["component_id"]: i for i, c in enumerate(sorted_components)}
    upstream: dict[int, int | None] = {}

    for idx, comp in enumerate(sorted_components):
        cid = comp["component_id"]
        src_id = None
        for conn in connections:
            if conn["to_component_id"] == cid:
                src_id = conn["from_component_id"]
                break
        if src_id and src_id in id_to_idx:
            upstream[idx] = id_to_idx[src_id]
        else:
            upstream[idx] = None

    return upstream


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------

def _build_config(components: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build per-component config from contract config_fields."""
    config: dict[str, dict[str, Any]] = {}
    for comp in components:
        slug = _sanitize_name(comp.get("name", ""))
        contract = comp.get("contract", {})
        config_fields = contract.get("config_fields", {})
        config[slug] = dict(config_fields) if isinstance(config_fields, dict) else {}
    return config


def _build_config_repr(config_fields: dict) -> str:
    """Build a Python dict repr for config fields with placeholder values."""
    if not config_fields:
        return "{}"
    items: list[str] = []
    for key, value in config_fields.items():
        if isinstance(value, str):
            items.append(f'"{key}": "{value}"')
        elif isinstance(value, (int, float, bool)):
            items.append(f'"{key}": {value}')
        else:
            items.append(f'"{key}": None  # TODO: configure')
    return "{" + ", ".join(items) + "}"


# ---------------------------------------------------------------------------
# Pipeline generation
# ---------------------------------------------------------------------------

def generate_pipeline(mission_id: str) -> str:
    """Generate a pipeline.py + config.json from a mission's component graph.

    Returns the file path of the generated pipeline.py.
    """
    from runtime.jb_missions import get_mission

    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")

    components, connections = _resolve_components(mission_id)
    if not components:
        raise ValueError("Mission has no components to generate a pipeline from")

    sorted_components = topological_sort(components, connections)
    upstream_map = _build_upstream_map(sorted_components, connections)

    # Build slug and name lists
    slugs: list[str] = []
    names: list[str] = []
    for comp in sorted_components:
        slugs.append(_sanitize_name(comp.get("name", "")))
        names.append(comp.get("name", "unnamed"))

    # Generate code
    now = datetime.now(timezone.utc).isoformat()
    count = len(sorted_components)
    mission_goal = mission.get("goal", mission_id)

    imports = "\n".join(
        f"from components.{s}.main import run as {s}" for s in slugs
    )

    steps: list[str] = []
    for idx, (slug, name) in enumerate(zip(slugs, names)):
        up = upstream_map.get(idx)
        input_expr = f"result_{up}" if up is not None else "None"
        steps.append(
            f"    # Step {idx + 1}: {name}\n"
            f"    result_{idx} = {slug}(\n"
            f"        config=configs.get(\"{slug}\", {{}}),\n"
            f"        input_data={input_expr},\n"
            f"        summary_chain=list(summary_chain)\n"
            f"    )\n"
            f"    summary_chain.append(result_{idx}.get(\"summary\", \"{name} completed\"))"
        )

    last_idx = count - 1
    steps_block = "\n\n".join(steps)

    code = (
        f'#!/usr/bin/env python3\n'
        f'"""Auto-generated pipeline for mission: {mission_goal}\n'
        f'Generated: {now}\n'
        f'Components: {count}\n'
        f'"""\n'
        f'import sys\n'
        f'import json\n'
        f'from pathlib import Path\n'
        f'\n'
        f'# Add workspace to path\n'
        f'BASE_DIR = Path(__file__).resolve().parent.parent.parent\n'
        f'sys.path.insert(0, str(BASE_DIR))\n'
        f'\n'
        f'{imports}\n'
        f'\n'
        f'\n'
        f'def main():\n'
        f'    # Load config\n'
        f'    config_path = Path(__file__).parent / "config.json"\n'
        f'    with open(config_path) as f:\n'
        f'        configs = json.load(f)\n'
        f'\n'
        f'    summary_chain = []\n'
        f'\n'
        f'{steps_block}\n'
        f'\n'
        f'    # Save results\n'
        f'    results = {{\n'
        f'        "summary_chain": summary_chain,\n'
        f'        "final_output": result_{last_idx},\n'
        f'        "status": "success"\n'
        f'    }}\n'
        f'\n'
        f'    results_path = Path(__file__).parent / "last_run.json"\n'
        f'    with open(results_path, "w") as f:\n'
        f'        json.dump(results, f, indent=2, default=str)\n'
        f'\n'
        f'    print(json.dumps({{"summary_chain": summary_chain}}, indent=2))\n'
        f'    return results\n'
        f'\n'
        f'\n'
        f'if __name__ == "__main__":\n'
        f'    main()\n'
    )

    # Write files
    pipeline_dir = PIPELINES_DIR / mission_id
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    pipeline_path = pipeline_dir / "pipeline.py"
    pipeline_path.write_text(code, encoding="utf-8")

    config = _build_config(sorted_components)
    config_path = pipeline_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    return str(pipeline_path)


# Alias for backward compat
def generate_pipeline_code(mission_id: str, mission_name: str = "unnamed") -> str:
    """Generate pipeline code as a string (legacy API)."""
    from runtime.jb_missions import get_mission

    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")

    components, connections = _resolve_components(mission_id)
    if not components:
        return _generate_empty_pipeline(mission_name or "unnamed")

    sorted_components = topological_sort(components, connections)
    upstream_map = _build_upstream_map(sorted_components, connections)

    # Build safe names
    safe_names: dict[str, str] = {}
    for comp in sorted_components:
        safe = _sanitize_name(comp["name"])
        base = safe
        counter = 2
        while safe in safe_names.values():
            safe = f"{base}_{counter}"
            counter += 1
        safe_names[comp["component_id"]] = safe

    # Build incoming map
    incoming: dict[str, list[str]] = {c["component_id"]: [] for c in sorted_components}
    comp_id_set = {c["component_id"] for c in sorted_components}
    for conn in connections:
        src = conn["from_component_id"]
        dst = conn["to_component_id"]
        if dst in incoming and src in comp_id_set:
            incoming[dst].append(src)

    goal = mission_name if mission_name != "unnamed" else (mission.get("goal", "unnamed") if mission else "unnamed")

    lines: list[str] = []
    lines.append("#!/usr/bin/env python3")
    lines.append(f'"""Auto-generated pipeline for mission: {goal}"""')
    lines.append("")
    lines.append("import sys")
    lines.append("import json")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("# Component imports")

    for comp in sorted_components:
        safe = safe_names[comp["component_id"]]
        directory = comp.get("directory", "").strip()
        if directory:
            module_path = directory.replace("/", ".").rstrip(".")
            lines.append(f"try:")
            lines.append(f"    from {module_path}.main import run as {safe}")
            lines.append(f"except ImportError:")
            lines.append(f"    def {safe}(**kwargs):")
            lines.append(f'        print(f"[STUB] {safe} called with {{kwargs}}")')
            lines.append(f"        return {{}}")
        else:
            lines.append(f"def {safe}(**kwargs):")
            lines.append(f'    """Stub for {comp["name"]} -- no directory configured."""')
            lines.append(f'    print(f"[STUB] {safe} called with {{kwargs}}")')
            lines.append(f"    return {{}}")
        lines.append("")

    lines.append("")
    lines.append("def pipeline():")
    lines.append(f'    """Execute the full pipeline for: {goal}"""')
    lines.append("    results = {}")
    lines.append("")

    for stage_num, comp in enumerate(sorted_components, 1):
        safe = safe_names[comp["component_id"]]
        contract = comp.get("contract", {})
        config_fields = contract.get("config_fields", {})
        config_repr = _build_config_repr(config_fields)

        sources = incoming.get(comp["component_id"], [])
        lines.append(f"    # Stage {stage_num}: {comp['name']}")

        if sources:
            src_safe = safe_names[sources[0]]
            lines.append(
                f"    results['{safe}'] = {safe}("
                f"config={config_repr}, "
                f"input_data=results['{src_safe}'])"
            )
        else:
            lines.append(
                f"    results['{safe}'] = {safe}(config={config_repr})"
            )
        lines.append("")

    if sorted_components:
        last_safe = safe_names[sorted_components[-1]["component_id"]]
        lines.append(f"    return results['{last_safe}']")
    else:
        lines.append("    return {}")

    lines.append("")
    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    try:")
    lines.append("        result = pipeline()")
    lines.append('        print(json.dumps({"status": "success", "result": str(result)}))')
    lines.append("    except Exception as e:")
    lines.append('        print(json.dumps({"status": "error", "error": str(e)}))')
    lines.append("        sys.exit(1)")
    lines.append("")

    return "\n".join(lines)


def _generate_empty_pipeline(mission_name: str) -> str:
    """Generate a pipeline with no components."""
    return (
        "#!/usr/bin/env python3\n"
        f'"""Auto-generated pipeline for mission: {mission_name}"""\n'
        "import sys, json\n"
        "\n"
        "def pipeline():\n"
        '    print("No components configured for this mission.")\n'
        "    return {}\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    result = pipeline()\n"
        '    print(json.dumps({"status": "success", "result": str(result)}))\n'
    )


def write_pipeline(mission_id: str, mission_name: str = "unnamed") -> Path:
    """Generate and write pipeline.py to the mission's pipeline directory.

    Returns: Path to the generated pipeline.py
    """
    path_str = generate_pipeline(mission_id)
    return Path(path_str)


# ---------------------------------------------------------------------------
# Pipeline runner (in-process)
# ---------------------------------------------------------------------------

def run_pipeline(mission_id: str, service_id: str | None = None) -> dict[str, Any]:
    """Execute a mission's pipeline in-process.

    1. Load/generate pipeline if not exists
    2. Execute each component in order
    3. Pipe data between components via connections
    4. Accumulate summary chain
    5. Save results to last_run.json
    6. If service_id provided, update service run tracking
    7. Return results dict
    """
    from runtime.jb_missions import get_mission

    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission not found: {mission_id}")

    # Ensure pipeline dir + config exist
    pipeline_dir = PIPELINES_DIR / mission_id
    config_path = pipeline_dir / "config.json"
    if not config_path.exists():
        generate_pipeline(mission_id)

    with open(config_path, "r", encoding="utf-8") as f:
        configs = json.load(f)

    # Resolve and sort
    components, connections = _resolve_components(mission_id)
    if not components:
        return {
            "mission_id": mission_id,
            "summary_chain": [],
            "final_output": {},
            "status": "error",
            "errors": [{"component": "none", "error": "No components found"}],
            "duration_ms": 0,
            "component_count": 0,
            "completed_at": utc_now_iso(),
        }

    sorted_components = topological_sort(components, connections)
    upstream_map = _build_upstream_map(sorted_components, connections)

    # Execute
    summary_chain: list[str] = []
    results_by_idx: dict[int, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    start_time = time.time()

    for idx, comp in enumerate(sorted_components):
        slug = _sanitize_name(comp.get("name", f"component_{idx}"))
        name = comp.get("name", slug)
        comp_config = configs.get(slug, {})

        upstream = upstream_map.get(idx)
        input_data = results_by_idx.get(upstream) if upstream is not None else None

        try:
            mod = importlib.import_module(f"components.{slug}.main")
            result = mod.run(
                config=comp_config,
                input_data=input_data,
                summary_chain=list(summary_chain),
            )
            if not isinstance(result, dict):
                result = {"output": result, "summary": f"{name} completed"}
        except Exception as exc:
            result = {
                "summary": f"{name} FAILED: {exc}",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            errors.append({"component": name, "error": str(exc)})

        results_by_idx[idx] = result
        summary_chain.append(result.get("summary", f"{name} completed"))

    elapsed_ms = int((time.time() - start_time) * 1000)
    last_idx = len(sorted_components) - 1
    status = "error" if errors else "success"

    run_result: dict[str, Any] = {
        "mission_id": mission_id,
        "summary_chain": summary_chain,
        "final_output": results_by_idx.get(last_idx, {}),
        "status": status,
        "errors": errors,
        "duration_ms": elapsed_ms,
        "component_count": len(sorted_components),
        "completed_at": utc_now_iso(),
    }

    # Save last_run.json
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    last_run_path = pipeline_dir / "last_run.json"
    last_run_path.write_text(
        json.dumps(run_result, indent=2, default=str), encoding="utf-8"
    )

    # Update service if provided
    if service_id:
        try:
            from runtime.jb_services import record_run, update_service
            run_id = record_run(
                service_id=service_id,
                status="success" if not errors else "error",
                duration_ms=elapsed_ms,
                output_preview=json.dumps(summary_chain)[:500],
                error=json.dumps(errors)[:500] if errors else None,
            )
            update_service(service_id, {
                "last_run_summary": summary_chain[-1] if summary_chain else None,
            })
            run_result["run_id"] = run_id
        except Exception:
            pass  # Service tracking failure should not break the pipeline

    return run_result


# ---------------------------------------------------------------------------
# Component directory helpers
# ---------------------------------------------------------------------------

def validate_component_directory(workspace_id: str, component_name: str) -> dict:
    """Check if a component has the required files.

    Returns: {"valid": bool, "missing": [str], "path": str}
    """
    safe = _sanitize_name(component_name)
    comp_dir = DATA_DIR / "companies" / workspace_id / "components" / safe

    required_files = ["contract.py", "main.py", "test_main.py"]
    missing = [f for f in required_files if not (comp_dir / f).exists()]

    return {
        "valid": len(missing) == 0,
        "missing": missing,
        "path": str(comp_dir),
    }


def scaffold_component_directory(workspace_id: str, component_name: str) -> Path:
    """Create component directory with template files if missing."""
    safe = _sanitize_name(component_name)
    comp_dir = DATA_DIR / "companies" / workspace_id / "components" / safe

    comp_dir.mkdir(parents=True, exist_ok=True)

    contract_path = comp_dir / "contract.py"
    if not contract_path.exists():
        contract_path.write_text(
            f'"""Contract for {component_name}."""\n'
            "\n"
            "CONTRACT = {\n"
            '    "input_type": "Any",\n'
            '    "output_type": "Any",\n'
            '    "config_fields": {},\n'
            '    "input_schema": {},\n'
            '    "output_schema": {},\n'
            "}\n",
            encoding="utf-8",
        )

    main_path = comp_dir / "main.py"
    if not main_path.exists():
        main_path.write_text(
            f'"""Main entry point for {component_name}."""\n'
            "\n"
            "\n"
            "def run(config=None, input_data=None, summary_chain=None):\n"
            '    """Execute this component.\n'
            "\n"
            "    Args:\n"
            "        config: Component configuration dict.\n"
            "        input_data: Input from upstream component (if any).\n"
            "        summary_chain: Accumulated summaries from prior steps.\n"
            "\n"
            "    Returns:\n"
            '        dict with at minimum: {"summary": "...", ...}\n'
            '    """\n'
            "    config = config or {}\n"
            "    # TODO: Implement component logic\n"
            '    return {"summary": "' + component_name + ' completed", "status": "ok"}\n',
            encoding="utf-8",
        )

    test_path = comp_dir / "test_main.py"
    if not test_path.exists():
        test_path.write_text(
            f'"""Tests for {component_name}."""\n'
            "\n"
            "from .main import run\n"
            "\n"
            "\n"
            "def test_run_returns_dict():\n"
            "    result = run()\n"
            "    assert isinstance(result, dict)\n"
            '    assert "summary" in result\n'
            "\n"
            "\n"
            "def test_run_with_config():\n"
            '    result = run(config={"key": "value"})\n'
            "    assert isinstance(result, dict)\n",
            encoding="utf-8",
        )

    return comp_dir


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="JBCP Pipeline Generator & Runner")
    parser.add_argument("--mission-id", required=True, help="Mission UUID")
    parser.add_argument("--generate", action="store_true", help="Generate pipeline only")
    parser.add_argument("--run", action="store_true", help="Run pipeline only")
    parser.add_argument("--service-id", default=None, help="Service ID for run tracking")
    args = parser.parse_args()

    if args.generate and args.run:
        parser.error("Use --generate or --run, not both (omit both to generate+run)")

    if args.generate:
        path = generate_pipeline(args.mission_id)
        print(f"Pipeline generated: {path}")
    elif args.run:
        result = run_pipeline(args.mission_id, args.service_id)
        print(json.dumps(result, indent=2, default=str))
    else:
        path = generate_pipeline(args.mission_id)
        print(f"Pipeline generated: {path}")
        result = run_pipeline(args.mission_id, args.service_id)
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
