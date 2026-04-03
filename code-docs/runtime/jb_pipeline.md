# runtime/jb_pipeline.py

**Path:** `runtime/jb_pipeline.py` (771 lines)
**Purpose:** Pipeline generator and runner. Takes a mission's component graph, topologically sorts it, generates a standalone `pipeline.py` with `config.json`, and can execute the pipeline in-process.

## Key Concept
"No framework. Just imports and function calls. The graph IS the code."

## Constants

- `COMPONENTS_DIR`: `BASE_DIR / "components"` -- built component code
- `PIPELINES_DIR`: `BASE_DIR / "pipelines"` -- generated pipeline files

## Classes

### `ContractValidationError(Exception)`
Raised when connected components have incompatible contracts (type mismatch).

## Core Functions

### `topological_sort(components, connections) -> list[dict]`
Sorts components by data-flow dependency using Kahn's algorithm. Components with no inbound connections come first. Ties broken alphabetically. Raises `ValueError` on cycles.

### `validate_contracts(components, connections) -> list[str]`
Validates connected components have compatible `output_type -> input_type`. Returns warnings for missing components. Raises `ContractValidationError` on type mismatches (skips "Any" types).

### `generate_pipeline(mission_id) -> str`
Generates `pipeline.py` and `config.json` from a mission's component graph:
1. Resolves components via `_resolve_components()`
2. Topologically sorts them
3. Builds upstream map (which component feeds into which)
4. Generates Python code with imports, step-by-step execution, summary chain accumulation
5. Writes to `pipelines/{mission_id}/pipeline.py` and `config.json`
Returns path to generated file.

### `run_pipeline(mission_id, service_id=None) -> dict`
Executes a pipeline in-process:
1. Ensures pipeline dir and config exist
2. Resolves and sorts components
3. For each component: `importlib.import_module(f"components.{slug}.main")`, calls `mod.run(config, input_data, summary_chain)`
4. Pipes output from upstream components
5. Saves `last_run.json`
6. If `service_id` provided, records a run and updates service stats
Returns: `{mission_id, summary_chain, final_output, status, errors, duration_ms, component_count}`

### `generate_pipeline_code(mission_id, mission_name) -> str`
Legacy API that generates pipeline code as a string (not written to disk). Generates stub functions for components without directories.

### `write_pipeline(mission_id, mission_name) -> Path`
Convenience wrapper: generates and returns the Path.

## Component Directory Helpers

### `validate_component_directory(workspace_id, component_name) -> dict`
Checks if a component has the required files (`contract.py`, `main.py`, `test_main.py`). Returns `{valid, missing, path}`.

### `scaffold_component_directory(workspace_id, component_name) -> Path`
Creates component directory with template files if missing. Templates include a `run()` function stub, contract definition, and basic tests.

## Internal Helpers

- `_sanitize_name(name)`: Converts to valid Python identifier / filesystem slug
- `_resolve_components(mission_id)`: Loads components/connections from committed records or falls back to draft data on the mission object
- `_build_upstream_map(sorted_components, connections)`: Maps each component index to its first upstream source index
- `_build_config(components)`: Builds per-component config dict from contract config_fields
- `_generate_empty_pipeline(mission_name)`: Generates a no-op pipeline

## CLI

```bash
python -m runtime.jb_pipeline --mission-id <UUID> [--generate] [--run] [--service-id <UUID>]
```
