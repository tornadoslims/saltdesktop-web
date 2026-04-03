"""
Component Builder -- uses Claude Code CLI to build components.

Spawns Claude Code in --print mode with JSON output, parses results,
and updates component/task status.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from runtime.jb_common import BASE_DIR, utc_now_iso
from runtime.jb_queue import _update_task
from runtime.jb_components import update_component
from runtime.jb_event_bus import emit as event_emit

logger = logging.getLogger("jb_builder")

CLAUDE_CLI = "claude"
COMPONENTS_DIR = BASE_DIR / "components"
COMPONENTS_DIR.mkdir(parents=True, exist_ok=True)

BUILDER_SYSTEM_PROMPT = """You are a component builder for Salt Desktop. Your job is to write a single component.

RULES:
1. Write the component code to the CURRENT WORKING DIRECTORY
2. Create these files:
   - main.py -- with a `def run(config: dict, input_data: dict | None = None, summary_chain: list | None = None) -> dict` function
   - contract.py -- with dataclass definitions for Config, Input, Output types
   - test_main.py -- with tests for the run() function
3. The run() function MUST return a dict that includes a "summary" key with a human-readable string
4. Use the CredentialStore for any API credentials:
   ```python
   from runtime.jb_credentials import credentials
   creds = credentials.get("gmail")  # Returns dict with access_token etc.
   ```
5. Keep it simple, clean, well-tested
6. After writing code, run the tests to verify they pass

DECISIONS:
After completing, list any significant technical decisions you made and why.
"""

BUILD_TIMEOUT = 300  # 5 minutes


def build_component_sync(task: dict, component: dict, mission: dict) -> dict:
    """
    Spawn Claude Code CLI to build a component.
    Returns {"status": "complete"|"failed", "output": str, "decisions": str}
    """
    comp_name = component.get("name", "unknown")
    comp_type = component.get("type", "processor")
    comp_slug = _slugify(comp_name)
    target_dir = COMPONENTS_DIR / comp_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    # Build the prompt
    contract = component.get("contract", {})
    prompt = _build_prompt(task, component, mission, target_dir)

    # Resolve IDs
    task_id = task.get("id") or task.get("task_id")
    component_id = component.get("component_id")

    # Update status to building
    try:
        _update_task(task_id, {"status": "running"})
    except Exception:
        pass

    if component_id:
        try:
            update_component(component_id, {
                "status": "building",
                "directory": str(target_dir),
            })
        except Exception:
            pass

    # Emit event
    event_emit("task.building", task_id=task_id, component_name=comp_name,
               message=f"Building {comp_name}")

    # Run Claude Code CLI
    cmd = [
        CLAUDE_CLI,
        "-p", prompt,
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--append-system-prompt", BUILDER_SYSTEM_PROMPT,
    ]

    env = os.environ.copy()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(target_dir),
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT,
            env=env,
        )

        output = result.stdout
        stderr = result.stderr

        # Check if component files were created
        main_py = target_dir / "main.py"
        if main_py.exists():
            lines = len(main_py.read_text().splitlines())
            files = [str(f.name) for f in target_dir.iterdir() if f.suffix == ".py"]

            # Extract decisions from output
            decisions = _extract_decisions(output)

            # Update component as built
            if component_id:
                try:
                    update_component(component_id, {
                        "status": "built",
                        "lines_of_code": lines,
                        "files": files,
                        "directory": str(target_dir),
                        "built_by_agent": "claude-code",
                    })
                except Exception as e:
                    logger.warning("Failed to update component: %s", e)

            # Update task as complete
            try:
                _update_task(task_id, {
                    "status": "complete",
                    "error": None,
                })
            except Exception as e:
                logger.warning("Failed to update task: %s", e)

            event_emit("task.complete", task_id=task_id,
                       component_name=comp_name,
                       message=f"{comp_name} built -- {lines} lines, {len(files)} files")

            return {
                "status": "complete",
                "output": output[:2000],
                "decisions": decisions,
                "files": files,
                "lines": lines,
                "directory": str(target_dir),
            }
        else:
            # main.py not created -- build failed
            error = f"main.py not created. stderr: {stderr[:500]}"
            _mark_build_failed(task_id, component_id, comp_name, error)
            return {"status": "failed", "output": output[:2000], "error": error}

    except subprocess.TimeoutExpired:
        error = f"Build timed out after {BUILD_TIMEOUT}s"
        _mark_build_failed(task_id, component_id, comp_name, error)
        return {"status": "failed", "error": error}

    except Exception as e:
        error = str(e)
        _mark_build_failed(task_id, component_id, comp_name, error)
        return {"status": "failed", "error": error}


def dispatch_build_tasks(mission_id: str) -> list[dict]:
    """
    Dispatch all pending tasks for a mission using Claude Code.
    Returns list of results.
    """
    from runtime.jb_queue import list_tasks
    from runtime.jb_components import get_component, list_components
    from runtime.jb_missions import get_mission

    mission = get_mission(mission_id)
    if not mission:
        return [{"error": f"Mission not found: {mission_id}"}]

    tasks = list_tasks()
    mission_tasks = [
        t for t in tasks
        if t.get("mission_id") == mission_id
        and t.get("status") in ("pending", "dispatched")
    ]

    if not mission_tasks:
        return [{"message": "No pending tasks"}]

    workspace_id = mission.get("company_id")
    components = list_components(workspace_id=workspace_id) if workspace_id else []
    comp_map = {c.get("name"): c for c in components}
    comp_id_map = {c.get("component_id"): c for c in components}

    event_emit("mission.building", mission_id=mission_id,
               message=f"Building {len(mission_tasks)} component(s)")

    results = []
    for task in mission_tasks:
        # Find matching component by name or component_id
        comp_name = task.get("payload", {}).get("component", "")
        component_id = task.get("payload", {}).get("component_id", "")
        component = None

        if component_id:
            component = comp_id_map.get(component_id)
        if not component and comp_name:
            component = comp_map.get(comp_name)
            # Fuzzy match
            if not component:
                for c in components:
                    if c.get("name", "").lower() == comp_name.lower():
                        component = c
                        break

        if not component:
            component = {
                "name": comp_name or "unknown",
                "type": "processor",
                "component_id": "",
                "contract": {},
            }

        result = build_component_sync(task, component, mission)
        results.append(result)

    # Check if all complete
    all_complete = all(r.get("status") == "complete" for r in results)
    if all_complete and results:
        event_emit("mission.built", mission_id=mission_id,
                   message=f"All {len(results)} component(s) built successfully")

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert component name to directory-safe slug."""
    return name.lower().replace(" ", "_").replace("-", "_").replace("/", "_")


def _extract_decisions(output: str) -> str:
    """Extract DECISIONS section from Claude Code output."""
    for marker in ("DECISIONS:", "DECISIONS"):
        if marker in output:
            idx = output.index(marker)
            return output[idx:idx + 1000].strip()
    return ""


def _build_prompt(task: dict, component: dict, mission: dict, target_dir: Path) -> str:
    """Build the prompt sent to Claude Code CLI."""
    comp_name = component.get("name", "unknown")
    comp_type = component.get("type", "processor")
    contract = component.get("contract", {})
    description = component.get("description", "")

    goal = task.get("goal") or task.get("payload", {}).get("goal", "Build this component")
    mission_goal = mission.get("goal", "")

    constraints = task.get("payload", {}).get("constraints", [])
    constraints_str = "\n".join(f"- {c}" for c in constraints) if constraints else "None"

    prompt = f"""Build a {comp_type} component called "{comp_name}".

## Goal
{goal}

## Component Details
- Type: {comp_type}
- Target directory: {target_dir}
{f'- Description: {description}' if description else ''}

## Contract
- Input type: {contract.get('input_type', 'any')}
- Output type: {contract.get('output_type', 'any')}
- Config fields: {json.dumps(contract.get('config_fields', {}))}
- Input schema: {json.dumps(contract.get('input_schema', {}))}
- Output schema: {json.dumps(contract.get('output_schema', {}))}

## Mission Context
{mission_goal}

## Constraints
{constraints_str}

Write main.py, contract.py, and test_main.py. Then run the tests.
"""
    return prompt


def _mark_build_failed(task_id: str | None, component_id: str | None,
                       comp_name: str, error: str) -> None:
    """Mark a build as failed in both task and component."""
    if task_id:
        try:
            _update_task(task_id, {"status": "failed", "error": error[:500]})
        except Exception:
            pass
    if component_id:
        try:
            update_component(component_id, {"status": "failing"})
        except Exception:
            pass

    event_emit("task.failed", task_id=task_id, component_name=comp_name,
               message=f"{comp_name} failed to build", error=error[:300])
