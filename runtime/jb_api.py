"""
Salt Desktop Backend API Server.

FastAPI server on port 8718 that wraps the JBCP runtime modules.
Planning chat uses direct Anthropic/OpenAI SDK calls.
Building uses Claude Code CLI.

Usage:
    python -m runtime.jb_api
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from runtime.jb_common import DATA_DIR, BASE_DIR, utc_now_iso
from runtime.jb_event_bus import subscribe as event_subscribe, unsubscribe as event_unsubscribe, health_check as event_bus_health, emit as event_emit
from runtime.jb_components import list_components, get_component, build_graph
from runtime.jb_services import (
    list_services,
    get_service,
    create_service,
    pause_service,
    resume_service,
    stop_service,
    list_runs,
)
from runtime.jb_companies import (
    list_companies,
    get_company,
    create_company,
    update_company_name,
    update_company_description,
    attach_mission,
    set_focused_mission,
    ensure_mission_context,
    get_company_context_path,
    get_mission_context_path,
)
from runtime.jb_missions import (
    list_missions,
    get_mission,
    create_mission,
    approve_mission,
    mark_mission_status,
    _update_mission,
    _normalize_item,
)
from runtime.jb_queue import list_tasks, get_task, retry_task
from runtime.jb_credentials import credentials as cred_store, SERVICE_CATALOG

try:
    from runtime.jb_labels import mission_label, service_label
except ImportError:
    def mission_label(status: str) -> str:
        return status
    def service_label(status: str) -> str:
        return status

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VERSION = "0.4.0"
PORT = 8718
SECRETS_PATH = Path.home() / ".missionos" / "credentials" / "secrets.json"

_start_time = time.time()
_mock_mode = False

# Planning model settings (mutable at runtime via /api/settings/planning-model)
_planning_settings: dict[str, str] = {
    "provider": os.environ.get("SALT_PLANNING_PROVIDER", "openai"),
    "model": os.environ.get("SALT_PLANNING_MODEL", ""),  # empty = use provider default
}

_PROVIDER_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-5.4",
}


def _get_planning_provider() -> str:
    return _planning_settings["provider"]


def _get_planning_model() -> str:
    model = _planning_settings["model"]
    if model:
        return model
    return _PROVIDER_DEFAULT_MODELS.get(_get_planning_provider(), "gpt-4o")


def _read_openai_key() -> str | None:
    """Read the OpenAI API key from env or secrets."""
    key = os.environ.get("SALT_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    try:
        with open(SECRETS_PATH, "r", encoding="utf-8") as f:
            secrets = json.load(f)
        return secrets.get("openai_key") or secrets.get("openai_token") or secrets.get("openai_api_key")
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _read_anthropic_key() -> str | None:
    """Read the Anthropic API key from env or secrets."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        with open(SECRETS_PATH, "r", encoding="utf-8") as f:
            secrets = json.load(f)
        return secrets.get("anthropic_key") or secrets.get("anthropic_token")
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="JBCP Control Plane", version=VERSION, docs_url=None, redoc_url=None)

# Initialize SQLite database (creates tables if needed)
from runtime.jb_database import init_db
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:*",
        "http://127.0.0.1:*",
    ],
    allow_origin_regex=r"http://10\.0\.0\.\d{1,3}(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Mock mode endpoints
# ---------------------------------------------------------------------------

@app.post("/api/mock/enable")
async def enable_mock():
    global _mock_mode
    _mock_mode = True
    return {"mock": True}


@app.post("/api/mock/disable")
async def disable_mock():
    global _mock_mode
    _mock_mode = False
    return {"mock": False}


@app.get("/api/mock/status")
async def mock_status():
    return {"enabled": _mock_mode}


# ---------------------------------------------------------------------------
# Planning model settings endpoints
# ---------------------------------------------------------------------------

class PlanningModelRequest(BaseModel):
    provider: str | None = None
    model: str | None = None


@app.post("/api/settings/planning-model")
async def set_planning_model(req: PlanningModelRequest):
    global _planning_settings
    if req.provider and req.provider in ("anthropic", "openai"):
        _planning_settings["provider"] = req.provider
    if req.model is not None:
        _planning_settings["model"] = req.model
    return {
        "provider": _planning_settings["provider"],
        "model": _get_planning_model(),
    }


@app.get("/api/settings/planning-model")
async def get_planning_model():
    return {
        "provider": _planning_settings["provider"],
        "model": _get_planning_model(),
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateWorkspaceRequest(BaseModel):
    prompt: str | None = None
    name: str | None = None

class PatchWorkspaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None

class CreateMissionRequest(BaseModel):
    goal: str
    name: str | None = None

class ChatRequest(BaseModel):
    workspace_id: str
    mission_id: str | None = None
    message: str
    history: list[dict[str, Any]] | None = None

class PatchMemoryRequest(BaseModel):
    content: str

class PromoteWorkspaceRequest(BaseModel):
    name: str | None = None
    description: str = ""
    type: str = "manual"
    schedule: str | None = None
    entry_point: str = ""
    has_frontend: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _relative_time(iso_timestamp: str | None) -> str:
    """Convert an ISO timestamp to a human-readable relative time string."""
    if not iso_timestamp:
        return "never"
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 0:
            return "just now"
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        days = hours // 24
        if days < 30:
            return f"{days} day{'s' if days != 1 else ''} ago"
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    except (ValueError, TypeError):
        return "unknown"


def _compute_health(workspace_id: str) -> str:
    """Compute workspace health dot color.
    green: all missions complete or has running services
    yellow: any mission active (building)
    red: any mission failed
    gray: no missions or all idle/planning
    """
    missions = [m for m in list_missions() if m.get("company_id") == workspace_id]
    if not missions:
        return "gray"

    statuses = {m.get("status") for m in missions}

    # Red: any failed mission
    if "failed" in statuses:
        return "red"

    # Green: has running services
    try:
        services = list_services(workspace_id=workspace_id)
        if any(s.get("status") in ("running", "starting") for s in services):
            return "green"
    except Exception:
        pass

    # Green: all missions complete
    if statuses <= {"complete"}:
        return "green"

    # Yellow: any active mission
    if "active" in statuses:
        return "yellow"

    # Gray: planning, draft, blocked, cancelled, etc.
    return "gray"


def _compute_stage(c: dict[str, Any], missions: list, tasks: list) -> str:
    """Derive workspace stage from mission/task state."""
    cid = c["company_id"]
    has_planning = any(m.get("status") == "planning" for m in missions)
    has_active = any(m.get("status") == "active" for m in missions)

    active_tasks = [t for t in tasks if t.get("status") in ("pending", "dispatched", "running")]
    complete_tasks = [t for t in tasks if t.get("status") == "complete"]
    failed_tasks = [t for t in tasks if t.get("status") == "failed"]

    try:
        services = list_services(workspace_id=cid)
        if any(s.get("status") in ("running", "starting") for s in services):
            return "production"
    except Exception:
        pass

    if has_planning:
        return "planning"
    if active_tasks:
        return "building"
    if tasks and not active_tasks and complete_tasks:
        all_done = all(t.get("status") in ("complete", "failed", "suspect") for t in tasks)
        if all_done and failed_tasks:
            return "failed"
        if all_done:
            return "ready"
    if has_active and not tasks:
        return "building"
    return "idle"


def _company_to_workspace(c: dict[str, Any]) -> dict[str, Any]:
    """Rename company fields to workspace fields for the API."""
    cid = c["company_id"]
    missions = [m for m in list_missions() if m.get("company_id") == cid]
    tasks = [t for t in list_tasks() if t.get("company_id") == cid]
    active_tasks = [t for t in tasks if t.get("status") in ("pending", "dispatched", "running", "in_progress")]
    components = list_components(workspace_id=cid)
    stage = _compute_stage(c, missions, tasks)
    health = _compute_health(cid)

    # Compute last_activity_at: most recent updated_at from missions, or company's own
    activity_timestamps = [m.get("updated_at") for m in missions if m.get("updated_at")]
    activity_timestamps.append(c.get("updated_at"))
    activity_timestamps = [t for t in activity_timestamps if t]
    last_activity_at = max(activity_timestamps) if activity_timestamps else c.get("updated_at")

    return {
        "id": cid,
        "name": c.get("name"),
        "description": c.get("description"),
        "status": c.get("status", "active"),
        "stage": stage,
        "health": health,
        "focused_mission_id": c.get("focused_mission_id"),
        "mission_count": len(missions),
        "component_count": len(components),
        "active_task_count": len(active_tasks),
        "total_task_count": len(tasks),
        "mission_ids": c.get("mission_ids", []),
        "session_key": f"agent:main:jbcp-frontend:company:{cid}",
        "last_activity_at": last_activity_at,
        "last_activity": _relative_time(last_activity_at),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
    }


def _data_file_counts() -> dict[str, int]:
    """Count records in each JSON data file."""
    counts = {}
    for name in ("jb_companies", "jb_missions", "jb_queue"):
        fpath = DATA_DIR / f"{name}.json"
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            counts[name.replace("jb_", "")] = len(data) if isinstance(data, list) else 0
        except (OSError, json.JSONDecodeError):
            counts[name.replace("jb_", "")] = 0
    return counts


# ---------------------------------------------------------------------------
# TIER 1 — Direct data reads
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    if _mock_mode:
        from runtime.jb_mock_data import get_health
        return get_health()
    counts = _data_file_counts()
    tasks = list_tasks()
    active_tasks = [t for t in tasks if t.get("status") in ("pending", "dispatched", "running", "in_progress")]

    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - _start_time),
        "jbcp": {
            "status": "running",
            "workspaces": counts.get("companies", 0),
            "missions": counts.get("missions", 0),
            "active_tasks": len(active_tasks),
        },
        "event_bus": event_bus_health(),
        "version": VERSION,
    }


@app.get("/api/workspaces")
async def get_workspaces():
    if _mock_mode:
        from runtime.jb_mock_data import get_workspaces as mock_workspaces
        return mock_workspaces()
    companies = list_companies()
    return [_company_to_workspace(c) for c in companies]


@app.post("/api/workspaces", status_code=201)
async def create_workspace(req: CreateWorkspaceRequest):
    name = req.name or (req.prompt[:60].strip() if req.prompt else "My Company")
    company_id = create_company(name=name)

    result = {
        "id": company_id,
        "name": name,
        "status": "active",
        "created_at": utc_now_iso(),
    }

    # If a prompt was provided, also create an initial mission
    if req.prompt:
        mission_id = create_mission(goal=req.prompt, company_id=company_id, status="planning")
        attach_mission(company_id, mission_id)
        set_focused_mission(company_id, mission_id)
        ensure_mission_context(company_id, mission_id, goal=req.prompt)
        result["mission_id"] = mission_id
        result["prompt"] = req.prompt

    return result


@app.patch("/api/workspaces/{workspace_id}")
async def patch_workspace(workspace_id: str, req: PatchWorkspaceRequest):
    try:
        updated = None
        if req.name is not None:
            updated = update_company_name(workspace_id, req.name)
        if req.description is not None:
            updated = update_company_description(workspace_id, req.description)
        if updated is None:
            company = get_company(workspace_id)
            if not company:
                raise ValueError(f"Company not found: {workspace_id}")
            updated = company
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _company_to_workspace(updated)


@app.get("/api/workspaces/{workspace_id}/missions")
async def get_workspace_missions(workspace_id: str):
    if _mock_mode:
        from runtime.jb_mock_data import get_workspace_missions as mock_missions
        return mock_missions(workspace_id)
    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")
    missions = [m for m in list_missions() if m.get("company_id") == workspace_id]
    for m in missions:
        m["phase_label"] = mission_label(m.get("status", ""))
    return missions


@app.post("/api/workspaces/{workspace_id}/missions", status_code=201)
async def create_workspace_mission(workspace_id: str, req: CreateMissionRequest):
    if _mock_mode:
        import uuid
        mission_id = f"mock-m-{uuid.uuid4().hex[:8]}"
        return {
            "ok": True,
            "mission_id": mission_id,
            "goal": req.goal,
        }
    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")

    mission_id = create_mission(goal=req.goal, company_id=workspace_id, status="planning")
    attach_mission(workspace_id, mission_id)
    set_focused_mission(workspace_id, mission_id)
    ensure_mission_context(workspace_id, mission_id, goal=req.goal)

    return {
        "ok": True,
        "mission_id": mission_id,
        "goal": req.goal,
    }


@app.get("/api/missions/{mission_id}/tasks")
async def get_mission_tasks(mission_id: str):
    if _mock_mode:
        from runtime.jb_mock_data import get_mission_tasks as mock_tasks
        return mock_tasks(mission_id)
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission not found: {mission_id}")
    tasks = [t for t in list_tasks() if t.get("mission_id") == mission_id]
    return tasks


@app.post("/api/missions/{mission_id}/generate")
def generate_mission_items(mission_id: str):
    """Generate mission plan (components + tasks) via the jbcp-worker agent."""
    from runtime.jb_plan_generate import generate_mission_plan

    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission not found: {mission_id}")
    if mission["status"] != "planning":
        raise HTTPException(status_code=400, detail=f"Mission not in planning state: {mission['status']}")

    company_id = mission.get("company_id")
    session_key = f"agent:main:jbcp-frontend:mission:{mission_id}"

    result = generate_mission_plan(mission_id, session_key=session_key)

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Generation failed"))

    event_emit("mission.generated", mission_id=mission_id, item_count=result.get("item_count", 0))
    return result


@app.post("/api/missions/{mission_id}/generate-preview")
async def generate_mission_preview(mission_id: str):
    """Lightweight plan preview for live draft graph during planning."""
    global _mock_mode

    if _mock_mode:
        return {
            "components": [
                {"name": "Gmail Connector", "type": "connector"},
                {"name": "Email Classifier", "type": "ai"},
                {"name": "Result Reporter", "type": "output"},
            ],
            "connections": [
                {"from": "Gmail Connector", "to": "Email Classifier", "label": "raw emails"},
                {"from": "Email Classifier", "to": "Result Reporter", "label": "classified emails"},
            ],
            "preview": True,
        }

    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission not found: {mission_id}")

    from runtime.jb_plan_generate import generate_preview

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, generate_preview, mission_id)

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Preview generation failed"))

    return result


@app.post("/api/missions/{mission_id}/approve")
async def approve_mission_endpoint(mission_id: str):
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission not found: {mission_id}")
    if mission["status"] not in ("planning", "planned"):
        raise HTTPException(status_code=400, detail=f"Mission not in approvable state: {mission['status']}")
    if not mission.get("items"):
        raise HTTPException(status_code=400, detail="Mission has no items. Generate first.")

    try:
        result = approve_mission(mission_id)
        event_emit("mission.approved", mission_id=mission_id, task_count=len(result["task_ids"]))
        return {
            "ok": True,
            "mission_id": mission_id,
            "task_ids": result["task_ids"],
            "task_count": len(result["task_ids"]),
            "component_count": len(result.get("component_name_to_id", {})),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/missions/{mission_id}/build")
async def build_mission(mission_id: str):
    """Trigger building all pending tasks for a mission using Claude Code CLI."""
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission not found: {mission_id}")
    if mission["status"] != "active":
        raise HTTPException(status_code=400, detail=f"Mission must be active to build, currently: {mission['status']}")

    from runtime.jb_builder import dispatch_build_tasks

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, dispatch_build_tasks, mission_id)
    return {"ok": True, "mission_id": mission_id, "results": results}


@app.get("/api/commands")
async def list_commands():
    """List all available slash commands with their subcommands and descriptions."""
    return {
        "commands": [
            {
                "name": "/mission",
                "description": "Manage missions (planning, building, tracking)",
                "subcommands": [
                    {"name": "new <goal>", "description": "Create a new mission and enter planning mode. Chat about what to build, then /mission generate."},
                    {"name": "generate", "description": "AI generates components and tasks from the conversation. Can be run multiple times to refine."},
                    {"name": "approve", "description": "Approve the generated plan and start building. Creates components and enqueues tasks."},
                    {"name": "cancel", "description": "Cancel the current mission."},
                    {"name": "list", "description": "List all missions in this workspace."},
                    {"name": "switch <name>", "description": "Switch the focused mission by name or ID prefix."},
                    {"name": "(no args)", "description": "Show current mission status, planning mode, item/component counts."},
                ],
            },
            {
                "name": "/status",
                "description": "Quick workspace status: mission count, task counts (active/complete/failed), focused mission.",
            },
            {
                "name": "/contextmem",
                "description": "Show JBCP context injection stats: company context size, mission context size, total injection chars.",
            },
            {
                "name": "/jbdebug",
                "description": "Toggle debug settings (debug_footer, debug_signals, debug_tool_blocks).",
                "subcommands": [
                    {"name": "(no args)", "description": "Show all debug settings and their current state."},
                    {"name": "<setting>", "description": "Toggle a specific debug setting on/off."},
                ],
            },
        ],
        "workflow": [
            "1. /mission new <describe what you want to build>",
            "2. Chat with Santiago about requirements and architecture",
            "3. /mission generate — AI creates components + tasks",
            "4. Review the plan, chat more if needed, /mission generate again to refine",
            "5. /mission approve — starts building (creates real tasks)",
        ],
    }


@app.post("/api/missions/{mission_id}/cancel")
async def cancel_mission_endpoint(mission_id: str):
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission not found: {mission_id}")
    try:
        # Cancel pending/running tasks belonging to this mission
        from runtime.jb_queue import _update_task
        tasks = [t for t in list_tasks() if t.get("mission_id") == mission_id]
        cancelled_tasks = 0
        for t in tasks:
            if t.get("status") in ("pending", "dispatched", "running", "in_progress"):
                try:
                    _update_task(t["id"], {"status": "failed", "error": "Mission cancelled"})
                    cancelled_tasks += 1
                except Exception:
                    pass
        mark_mission_status(mission_id, "cancelled")
        event_emit("mission.cancelled", mission_id=mission_id, cancelled_tasks=cancelled_tasks)
        return {"ok": True, "mission_id": mission_id, "cancelled_tasks": cancelled_tasks}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/workspaces/{workspace_id}/prompt-debug")
async def prompt_debug(workspace_id: str):
    """Show the full prompt injection tree for a workspace — what JBCP sends to the LLM."""
    if _mock_mode:
        from runtime.jb_mock_data import get_prompt_debug
        return get_prompt_debug(workspace_id)
    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")

    focused_id = company.get("focused_mission_id")
    focused = get_mission(focused_id) if focused_id else None

    sections = []
    total_chars = 0

    # Company context
    cc_path = get_company_context_path(workspace_id)
    cc_content = ""
    if cc_path.exists():
        try:
            cc_content = cc_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    # Filter header-only lines (same as plugin readTextSync)
    cc_lines = [l for l in cc_content.split("\n") if l.strip() and not l.strip().startswith("#")]
    cc_effective = "\n".join(cc_lines)
    sections.append({
        "name": "Company Context",
        "type": "company_context",
        "chars": len(cc_effective),
        "preview": cc_effective[:200] if cc_effective else "(empty — only headers)",
        "source": str(cc_path),
        "injected": len(cc_effective) > 0,
    })
    total_chars += len(cc_effective)

    # Mission context
    mc_content = ""
    mc_goal = ""
    if focused:
        mc_goal = focused.get("goal", "")
        mc_path = focused.get("context_path")
        if not mc_path and focused_id:
            mc_path = str(get_mission_context_path(workspace_id, focused_id))
        if mc_path:
            from pathlib import Path
            mp = Path(mc_path)
            if mp.exists():
                try:
                    mc_raw = mp.read_text(encoding="utf-8").strip()
                    mc_lines = [l for l in mc_raw.split("\n") if l.strip() and not l.strip().startswith("#")]
                    mc_content = "\n".join(mc_lines)
                except OSError:
                    pass

    sections.append({
        "name": "Mission Context",
        "type": "mission_context",
        "mission_id": focused_id,
        "mission_goal": mc_goal,
        "chars": len(mc_content),
        "preview": mc_content[:200] if mc_content else "(empty — only headers)",
        "source": str(get_mission_context_path(workspace_id, focused_id)) if focused_id else None,
        "injected": len(mc_content) > 0 or bool(mc_goal),
    })
    total_chars += len(mc_content)

    # Planning mode block
    planning_active = focused and focused.get("status") == "planning"
    if planning_active:
        items = focused.get("items", [])
        components = focused.get("components", [])
        connections = focused.get("connections", [])
        blocked_tools = ["exec", "write", "edit", "process", "subagents", "cron", "web_fetch", "web_search"]

        # Estimate the planning block size (same structure as plugin injects)
        planning_text_estimate = 600  # base instructions
        planning_text_estimate += sum(50 + len(c.get("name", "")) + len(c.get("description", "")[:100]) for c in components)
        planning_text_estimate += sum(30 + len(cn.get("from", "")) + len(cn.get("to", "")) for cn in connections)
        planning_text_estimate += sum(20 + len(i.get("goal", "")) for i in items)

        sections.append({
            "name": "Planning Mode Block",
            "type": "planning_block",
            "active": True,
            "chars": planning_text_estimate,
            "components_count": len(components),
            "connections_count": len(connections),
            "items_count": len(items),
            "blocked_tools": blocked_tools,
            "preview": f"PLANNING MODE for: \"{mc_goal}\" — {len(components)} components, {len(items)} tasks, {len(blocked_tools)} tools blocked",
        })
        total_chars += planning_text_estimate

    # Chat history estimate from SQLite
    history_count = None
    try:
        from runtime.jb_database import get_chat_messages
        chat_key = focused_id or workspace_id
        msgs = get_chat_messages(chat_key)
        history_count = len(msgs)
    except Exception:
        pass

    sections.append({
        "name": "Chat History",
        "type": "chat_history",
        "message_count": history_count,
        "chars": None,
        "note": "Stored in local SQLite database.",
    })

    return {
        "workspace_id": workspace_id,
        "sections": sections,
        "total_injection_chars": total_chars,
        "planning_mode": planning_active,
        "focused_mission": {
            "id": focused_id,
            "goal": mc_goal,
            "status": focused.get("status") if focused else None,
        } if focused else None,
    }


@app.get("/api/agents")
async def get_agents(detail: str = "ceo"):
    if _mock_mode:
        from runtime.jb_mock_data import get_agents as mock_agents
        return mock_agents()
    # No signal-based agent tracking; return empty list
    return []


@app.get("/api/missions/{mission_id}/context")
async def get_mission_context(mission_id: str):
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission not found: {mission_id}")
    company_id = mission.get("company_id")
    return _build_context_summary(company_id=company_id, mission_id=mission_id)


@app.post("/api/tasks/{task_id}/retry")
async def retry_task_endpoint(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    try:
        updated = retry_task(task_id)
        return {"ok": True, "task": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/workspaces/{workspace_id}/memory")
async def get_workspace_memory(workspace_id: str):
    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")

    # Read company context
    company_ctx_path = get_company_context_path(workspace_id)
    company_context = None
    if company_ctx_path.exists():
        try:
            company_context = company_ctx_path.read_text(encoding="utf-8")
        except OSError:
            pass

    # Read mission context for the focused mission
    mission_context = None
    focused_id = company.get("focused_mission_id")
    if focused_id:
        mission_ctx_path = get_mission_context_path(workspace_id, focused_id)
        if mission_ctx_path.exists():
            try:
                mission_context = mission_ctx_path.read_text(encoding="utf-8")
            except OSError:
                pass

    return {
        "workspace_id": workspace_id,
        "company_context": company_context,
        "company_context_path": str(company_ctx_path),
        "mission_context": mission_context,
        "focused_mission_id": focused_id,
    }


@app.patch("/api/workspaces/{workspace_id}/memory")
async def patch_workspace_memory(workspace_id: str, req: PatchMemoryRequest):
    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")

    ctx_path = get_company_context_path(workspace_id)
    ctx_path.parent.mkdir(parents=True, exist_ok=True)
    ctx_path.write_text(req.content, encoding="utf-8")

    return {"ok": True, "path": str(ctx_path), "chars": len(req.content)}


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def _read_context_file(path: Path | str | None, max_chars: int = 4000) -> str | None:
    """Read a markdown context file, return content or None."""
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        content = p.read_text(encoding="utf-8").strip()
        if not content:
            return None
        lines = [l.strip() for l in content.split("\n") if l.strip() and not l.strip().startswith("#")]
        if not lines:
            return None
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[... truncated]"
        return content
    except (OSError, UnicodeDecodeError):
        return None


def _build_context_summary(
    company_id: str | None = None,
    mission_id: str | None = None,
) -> dict[str, Any]:
    """Build a summary of context injection for a workspace/mission."""
    summary: dict[str, Any] = {
        "company": None,
        "company_context": None,
        "company_context_chars": 0,
        "mission": None,
        "mission_context": None,
        "mission_context_chars": 0,
    }

    if company_id:
        company = get_company(company_id)
        if company:
            summary["company"] = {"id": company_id, "name": company.get("name")}
            ctx = _read_context_file(get_company_context_path(company_id))
            if ctx:
                summary["company_context"] = ctx
                summary["company_context_chars"] = len(ctx)

    if mission_id:
        mission = get_mission(mission_id)
        if mission:
            summary["mission"] = {
                "id": mission_id,
                "goal": mission.get("goal"),
                "constraints": mission.get("constraints", []),
            }
            ctx_path = mission.get("context_path")
            if not ctx_path and company_id:
                ctx_path = str(get_mission_context_path(company_id, mission_id))
            ctx = _read_context_file(ctx_path)
            if ctx:
                summary["mission_context"] = ctx
                summary["mission_context_chars"] = len(ctx)

    summary["total_injection_chars"] = (
        summary["company_context_chars"] + summary["mission_context_chars"]
    )

    return summary


# ---------------------------------------------------------------------------
# TIER 2 — Chat (direct LLM)
# ---------------------------------------------------------------------------

def _build_chat_context(workspace_id: str, mission_id: str | None = None) -> str:
    """Build the system context for LLM chat calls.

    This replaces the plugin's ``before_prompt_build`` hook for REST-based
    chat (Salt Desktop), which bypasses plugin hooks entirely.
    """
    parts: list[str] = []

    # 1. Base identity
    parts.append(
        "You are Santiago, an AI assistant helping the user build and manage "
        "their AI agents in Salt Desktop.\n\n"
        "IMPORTANT: Keep responses SHORT and conversational. "
        "Use 2-5 sentences per response. Ask ONE question at a time. "
        "Don't list every possible option — suggest the best default and ask if the user wants to change it. "
        "Be direct, not verbose."
    )

    # 2. Company context
    company = get_company(workspace_id)
    if company:
        parts.append(f"\n## Current Company: {company.get('name', 'Unknown')}")
        desc = company.get("description", "")
        if desc:
            parts.append(f"Description: {desc}")

        ctx_path = get_company_context_path(workspace_id)
        if ctx_path.exists():
            ctx_text = ctx_path.read_text(encoding="utf-8").strip()
            if ctx_text:
                parts.append(f"\n### Company Context:\n{ctx_text[:2000]}")

    # 3. Mission context
    mission = None
    if mission_id:
        mission = get_mission(mission_id)
        if mission:
            parts.append(f"\n## Current Mission: {mission.get('goal', 'Unknown')}")
            parts.append(f"Status: {mission.get('status', 'unknown')}")

            components = mission.get("components", [])
            if components:
                parts.append(f"Components planned: {len(components)}")
                for c in components:
                    parts.append(f"  - {c.get('name', '?')} ({c.get('type', '?')})")

            mission_ctx = get_mission_context_path(workspace_id, mission_id)
            if mission_ctx.exists():
                mctx_text = mission_ctx.read_text(encoding="utf-8").strip()
                if mctx_text:
                    parts.append(f"\n### Mission Context:\n{mctx_text[:2000]}")

    # 4. Planning mode
    if mission and mission.get("status") == "planning":
        parts.append(
            "\n## PLANNING MODE — ACTIVE\n\n"
            "You are in PLANNING MODE for this mission. Your job:\n"
            "- Discuss requirements with the user\n"
            "- Ask clarifying questions\n"
            "- Help them think through what they want to build\n"
            "- Suggest components and architecture\n"
            "- DO NOT write code, create files, or start building anything\n\n"
            "The user will click \"Lock It In\" in the UI when they're ready "
            "to finalize the plan.\n"
            "Until then, ONLY DISCUSS AND PLAN.\n\n"
            "You CANNOT and SHOULD NOT attempt to build, code, or execute "
            "anything during planning mode."
        )

    # 5. Connected services
    connected = cred_store.list_connected()
    if connected:
        parts.append(f"\n## Connected Services: {', '.join(connected)}")
        parts.append(
            "These services have OAuth tokens or API keys available. "
            "Components can use them."
        )

    # 6. Existing built components
    all_components = list_components(workspace_id=workspace_id) if workspace_id else []
    if all_components:
        built = [c for c in all_components if c.get("status") == "built"]
        if built:
            parts.append(f"\n## Existing Components ({len(built)} built):")
            for c in built:
                parts.append(
                    f"  - {c.get('name')} ({c.get('type')}) "
                    f"— {c.get('lines_of_code', 0)} lines"
                )

    return "\n".join(parts)


@app.post("/api/chat")
async def chat_proxy(req: ChatRequest):
    # Intercept commands before proxying to agent
    from runtime.jb_commands import handle_command
    cmd_result = handle_command(req.message, workspace_id=req.workspace_id)
    if cmd_result:
        async def stream_command():
            yield f"data: {json.dumps({'content': cmd_result['text'], 'command': True, 'command_type': cmd_result.get('command_type', 'unknown')})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            stream_command(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # All chat goes through direct LLM call
    mission = None
    if req.mission_id:
        mission = get_mission(req.mission_id)

    return StreamingResponse(
        _stream_planning_chat(req, mission),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_planning_chat(req: ChatRequest, mission: dict | None):
    """Direct LLM API call (Anthropic or OpenAI).

    Reads chat history from SQLite, calls the configured LLM provider with
    streaming, and saves both the user message and the assistant response
    to the local DB.

    SSE format matches OpenAI-compatible chunks so the frontend needs no changes.
    """
    from runtime.jb_database import get_chat_messages, save_chat_message

    provider = _get_planning_provider()
    model = _get_planning_model()

    # Build system prompt
    system_context = _build_chat_context(req.workspace_id, req.mission_id)

    # Use mission_id for chat history storage; fall back to workspace_id
    chat_key = req.mission_id or req.workspace_id

    # Get chat history from SQLite
    history = get_chat_messages(chat_key, limit=30)

    # Build messages array
    messages: list[dict[str, str]] = []
    for msg in history:
        if msg["role"] in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": req.message})

    # Save user message to SQLite
    save_chat_message(chat_key, "user", req.message)

    full_response = ""

    if provider == "openai":
        # --- OpenAI path ---
        from openai import OpenAI
        import openai as openai_module

        api_key = _read_openai_key()
        if not api_key:
            yield f"data: {json.dumps({'error': True, 'detail': 'OpenAI API key not configured. Set SALT_OPENAI_API_KEY or OPENAI_API_KEY.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        client = OpenAI(api_key=api_key)

        # OpenAI uses system message in the messages array
        openai_messages = [{"role": "system", "content": system_context}]
        openai_messages.extend(messages)

        try:
            # Use max_completion_tokens for newer models, max_tokens for older
            token_param = {}
            if "gpt-5" in model or "o1" in model or "o3" in model:
                token_param["max_completion_tokens"] = 4096
            else:
                token_param["max_tokens"] = 4096
            stream = client.chat.completions.create(
                model=model,
                messages=openai_messages,
                stream=True,
                **token_param,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_response += delta.content
                    sse_chunk = {
                        "id": "chatcmpl_planning",
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {"content": delta.content}}],
                    }
                    yield f"data: {json.dumps(sse_chunk)}\n\n"
        except openai_module.APIError as e:
            yield f"data: {json.dumps({'error': True, 'detail': f'OpenAI API error: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'error': True, 'detail': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

    else:
        # --- Anthropic path (default) ---
        import anthropic

        api_key = _read_anthropic_key()
        if not api_key:
            yield f"data: {json.dumps({'error': True, 'detail': 'Anthropic API key not configured. Set ANTHROPIC_API_KEY environment variable.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        client = anthropic.Anthropic(api_key=api_key)

        try:
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system_context,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    sse_chunk = {
                        "id": "chatcmpl_planning",
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {"content": text}}],
                    }
                    yield f"data: {json.dumps(sse_chunk)}\n\n"
        except anthropic.APIError as e:
            yield f"data: {json.dumps({'error': True, 'detail': f'Anthropic API error: {e.message}'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'error': True, 'detail': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

    # Save assistant response to SQLite
    if full_response:
        save_chat_message(chat_key, "assistant", full_response)

    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

@app.get("/api/workspaces/{workspace_id}/chat/history")
async def get_chat_history(workspace_id: str, mission_id: str = None):
    """Fetch conversation history from local SQLite."""
    if _mock_mode:
        from runtime.jb_mock_data import get_chat_history as mock_chat
        return mock_chat(workspace_id)

    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail="Workspace not found")

    chat_key = mission_id or workspace_id
    from runtime.jb_database import get_chat_messages
    messages = get_chat_messages(chat_key)
    return {
        "messages": messages,
        "session_key": f"local:{chat_key}",
        "total": len(messages),
    }


@app.delete("/api/workspaces/{workspace_id}/chat/history")
async def clear_chat_history(workspace_id: str, mission_id: str = None):
    """Clear chat history from local SQLite."""
    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail="Workspace not found")

    chat_key = mission_id or workspace_id
    from runtime.jb_database import clear_chat_messages
    clear_chat_messages(chat_key)
    return {"ok": True, "session_key": f"local:{chat_key}"}


# ---------------------------------------------------------------------------
# TIER 3 — SSE signal stream
# ---------------------------------------------------------------------------

@app.get("/api/events/stream")
async def events_stream(detail: str = "full", mission_id: str = None):
    """
    Unified SSE stream of ALL system events:
    - JBCP state changes (mission/plan/task/component mutations) via in-memory bus
    - Agent activity (tool calls, turns, sessions) via signal file tailing
    - System health keepalive every 15 seconds
    - Mock signals every 3-5 seconds when mock mode is enabled

    Query params:
    - detail: "ceo" to translate signals via CEO translator, "full" for raw (default)
    - mission_id: filter events to only those matching this mission
    """
    queue = event_subscribe()

    def _maybe_filter(event: dict) -> dict | None:
        """Apply mission filtering to an event."""
        if mission_id:
            event_mission = event.get("mission_id")
            if event_mission and event_mission != mission_id:
                return None
        if detail == "ceo":
            try:
                from runtime.jb_ceo_translator import translate_signal
                activity = translate_signal(event, {}, {})
                event_out = {**event, "ceo_text": activity.text, "ceo_category": activity.category,
                         "ceo_icon": activity.icon, "ceo_component": activity.component_name}
                return event_out
            except Exception:
                pass
        return event

    async def stream():
        import random as _rng

        tick = 0
        mock_tick = 0
        mock_interval = _rng.randint(6, 10)
        try:
            while True:
                # Check in-memory bus for events (non-blocking)
                try:
                    event = queue.get_nowait()
                    event = _maybe_filter(event)
                    if event is not None:
                        yield f"data: {json.dumps(event, default=str)}\n\n"
                    continue
                except asyncio.QueueEmpty:
                    pass

                if _mock_mode:
                    mock_tick += 1
                    if mock_tick >= mock_interval:
                        mock_tick = 0
                        mock_interval = _rng.randint(6, 10)
                        try:
                            from runtime.jb_mock_data import get_next_mock_signal
                            signal = get_next_mock_signal()
                            sig_type = signal.get("signal", "")
                            event_type = {
                                "agent_turn": "agent.turn",
                                "tool_start": "tool_start",
                                "tool_end": "tool_end",
                                "llm_input": "llm_input",
                                "llm_output": "llm_output",
                            }.get(sig_type, f"signal.{sig_type}")
                            event = {"type": event_type, **signal}
                            event = _maybe_filter(event)
                            if event is not None:
                                yield f"data: {json.dumps(event, default=str)}\n\n"
                        except Exception:
                            pass

                # Sleep briefly then check again
                await asyncio.sleep(0.5)

                # Keepalive every 30 ticks (~15 seconds at 0.5s sleep)
                tick += 1
                if tick >= 30:
                    tick = 0
                    yield ": keepalive\n\n"
                    if not _mock_mode:
                        tasks = list_tasks()
                        active = sum(1 for t in tasks if t.get("status") in ("pending", "dispatched", "running"))
                        health = {
                            "type": "system.health",
                            "timestamp": utc_now_iso(),
                            "workspaces": len(list_companies()),
                            "tasks_active": active,
                            "agents_active": 0,
                        }
                        yield f"data: {json.dumps(health)}\n\n"
                    else:
                        health = {
                            "type": "system.health",
                            "timestamp": utc_now_iso(),
                            "workspaces": 2,
                            "tasks_active": 1,
                            "agents_active": 1,
                        }
                        yield f"data: {json.dumps(health)}\n\n"
        finally:
            event_unsubscribe(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/signals/push")
async def push_signal(request: Request):
    """Accept a signal via HTTP POST and push it to the in-memory event bus."""
    signal = await request.json()
    sig_type = signal.get("signal", "")
    event_type = f"signal.{sig_type}" if sig_type else "signal.unknown"
    event_emit(event_type, **{k: v for k, v in signal.items() if k != "signal"})
    try:
        from runtime.jb_database import log_signal
        log_signal(signal)
    except Exception:
        pass
    return {"ok": True}


# ---------------------------------------------------------------------------
# TIER 4 — Stubs
# ---------------------------------------------------------------------------

@app.get("/api/workspaces/{workspace_id}/components")
async def get_workspace_components(workspace_id: str):
    if _mock_mode:
        from runtime.jb_mock_data import get_workspace_components as mock_components
        return mock_components(workspace_id)
    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")
    return list_components(workspace_id=workspace_id)


@app.get("/api/workspaces/{workspace_id}/graph")
async def get_workspace_graph(workspace_id: str, mission_id: str = None):
    if _mock_mode:
        from runtime.jb_mock_data import get_workspace_graph as mock_graph
        return mock_graph(workspace_id)
    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")
    graph = build_graph(workspace_id)
    if mission_id:
        # Filter to components belonging to this mission
        mission_comp_ids = {c["component_id"] for c in list_components(workspace_id=workspace_id)
                           if c.get("mission_id") == mission_id}
        if mission_comp_ids:
            graph["nodes"] = [n for n in graph["nodes"] if n["id"] in mission_comp_ids]
            node_ids = {n["id"] for n in graph["nodes"]}
            graph["edges"] = [e for e in graph["edges"]
                              if e.get("source", e.get("from")) in node_ids
                              and e.get("target", e.get("to")) in node_ids]
    return graph


@app.get("/api/settings")
async def get_settings():
    all_components = list_components()
    all_services = list_services()

    return {
        "jbcp": {
            "workspace_path": str(BASE_DIR),
            "data_path": str(DATA_DIR),
            "version": VERSION,
            "component_count": len(all_components),
            "service_count": len(all_services),
        },
        "planning": {
            "provider": _get_planning_provider(),
            "model": _get_planning_model(),
        },
    }


@app.get("/api/live")
async def get_live():
    services = list_services()
    live = [s for s in services if s.get("status") in ("running", "starting") or s.get("health") == "healthy"]
    return live


@app.get("/api/usage")
async def get_usage():
    """Aggregate token usage from signal data."""
    try:
        from runtime.jb_database import query_signals
        signals = query_signals(limit=5000, signal_type="llm_output")
    except Exception:
        signals = []

    total_in = 0
    total_out = 0
    by_model: dict[str, dict] = {}
    by_agent: dict[str, dict] = {}

    for s in signals:
        usage = s.get("usage") or {}
        inp = usage.get("input", 0) or 0
        out = usage.get("output", 0) or 0
        total_in += inp
        total_out += out

        model = s.get("model", "unknown")
        if model not in by_model:
            by_model[model] = {"model": model, "tokens_in": 0, "tokens_out": 0}
        by_model[model]["tokens_in"] += inp
        by_model[model]["tokens_out"] += out

        agent = s.get("agent_id", "unknown")
        if agent not in by_agent:
            by_agent[agent] = {"agent_id": agent, "tokens_in": 0, "tokens_out": 0}
        by_agent[agent]["tokens_in"] += inp
        by_agent[agent]["tokens_out"] += out

    # Rough cost estimate: $3/M input, $15/M output (Sonnet pricing)
    cost = (total_in / 1_000_000 * 3.0) + (total_out / 1_000_000 * 15.0)

    return {
        "period": "all",
        "total_tokens_in": total_in,
        "total_tokens_out": total_out,
        "total_cost_usd": round(cost, 4),
        "by_model": list(by_model.values()),
        "by_agent": list(by_agent.values()),
        "by_workspace": [],
    }


@app.post("/api/workspaces/{workspace_id}/promote", status_code=201)
async def promote_workspace(workspace_id: str, req: PromoteWorkspaceRequest | None = None):
    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")

    workspace_name = (req.name if req and req.name else company.get("name")) or workspace_id
    description = req.description if req else ""
    svc_type = req.type if req else "manual"
    schedule = req.schedule if req else None
    entry_point = req.entry_point if req else ""
    has_frontend = req.has_frontend if req else False

    try:
        service_id = create_service(
            workspace_id=workspace_id,
            name=workspace_name,
            description=description,
            type=svc_type,
            schedule=schedule,
            entry_point=entry_point,
            has_frontend=has_frontend,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    service = get_service(service_id)
    return service


@app.get("/api/components")
async def global_components(type: str = None, status: str = None):
    """List all components globally, optionally filtered by type and/or status."""
    from runtime.jb_components import list_components as lc
    comps = lc(workspace_id=None)
    if type:
        comps = [c for c in comps if c.get("type") == type]
    if status:
        comps = [c for c in comps if c.get("status") == status]
    return comps


@app.get("/api/components/library")
async def component_library():
    """Component library grouped by type."""
    from runtime.jb_components import list_components as lc
    comps = lc(workspace_id=None)
    grouped: dict[str, list] = {}
    for c in comps:
        t = c.get("type", "other")
        if t not in grouped:
            grouped[t] = []
        grouped[t].append({
            "id": c["component_id"], "name": c.get("name"), "type": t,
            "status": c.get("status"), "workspace_id": c.get("workspace_id"),
            "lines_of_code": c.get("lines_of_code", 0),
        })
    return {"types": grouped, "total": len(comps)}


@app.get("/api/components/{component_id}")
async def get_component_detail(component_id: str):
    comp = get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail=f"Component not found: {component_id}")
    return comp


@app.get("/api/services")
async def get_services(workspace_id: str = None):
    if _mock_mode:
        from runtime.jb_mock_data import get_services as mock_services
        svcs = mock_services()
        if workspace_id:
            svcs = [s for s in svcs if s.get("workspace_id") == workspace_id]
        return svcs
    services = list_services(workspace_id=workspace_id)
    for s in services:
        s["status_label"] = service_label(s.get("status", ""))
    return services


@app.get("/api/services/{service_id}")
async def get_service_detail(service_id: str):
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail=f"Service not found: {service_id}")
    return svc


@app.post("/api/services/{service_id}/pause")
async def pause_service_endpoint(service_id: str):
    try:
        updated = pause_service(service_id)
        return {"ok": True, "service": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/services/{service_id}/resume")
async def resume_service_endpoint(service_id: str):
    try:
        updated = resume_service(service_id)
        return {"ok": True, "service": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/services/{service_id}/stop")
async def stop_service_endpoint(service_id: str):
    try:
        updated = stop_service(service_id)
        return {"ok": True, "service": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/services/{service_id}/undeploy")
async def undeploy_service_endpoint(service_id: str):
    """Stop a service and revert its linked mission back to complete status."""
    if _mock_mode:
        return {
            "ok": True,
            "service": {"service_id": service_id, "status": "stopped"},
            "mission": {"mission_id": None, "status": "complete"},
        }
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail=f"Service not found: {service_id}")
    try:
        # Stop the service if not already stopped
        if svc["status"] != "stopped":
            svc = stop_service(service_id)

        # Find and revert the linked mission
        mission_result = None
        mission_id = svc.get("mission_id")
        if mission_id:
            mission = get_mission(mission_id)
            if mission:
                try:
                    mark_mission_status(mission_id, "complete")
                    mission_result = {"mission_id": mission_id, "status": "complete"}
                except ValueError:
                    mission_result = {"mission_id": mission_id, "status": mission.get("status")}

        event_emit("service.undeployed", service_id=service_id, mission_id=mission_id)
        return {"ok": True, "service": svc, "mission": mission_result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/services/{service_id}/report")
async def service_report_endpoint(service_id: str, request: Request):
    """Accept a run report for a service and store it on the run history."""
    body = await request.json()

    if _mock_mode:
        event_emit(
            "service.report",
            service_id=service_id,
            summary_chain=body.get("summary_chain"),
            status=body.get("status"),
        )
        return {
            "ok": True,
            "service_id": service_id,
            "report_stored": True,
        }

    from runtime.jb_services import record_run, update_service
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail=f"Service not found: {service_id}")

    # Record the run with output from the report
    summary_chain = body.get("summary_chain", [])
    run_output = body.get("run_output", {})
    status = body.get("status", "success")

    output_preview = " -> ".join(summary_chain) if summary_chain else None
    run_status = "success" if status == "success" else "error"

    run_id = record_run(
        service_id=service_id,
        status=run_status,
        output_preview=output_preview,
    )

    # Store last_run_summary on the service
    if summary_chain:
        update_service(service_id, {"last_run_summary": summary_chain[-1] if summary_chain else None})

    event_emit(
        "service.report",
        service_id=service_id,
        run_id=run_id,
        summary_chain=summary_chain,
        status=status,
    )

    return {
        "ok": True,
        "service_id": service_id,
        "run_id": run_id,
        "report_stored": True,
    }


@app.get("/api/services/{service_id}/runs")
async def get_service_runs(service_id: str):
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail=f"Service not found: {service_id}")
    return list_runs(service_id)


@app.get("/api/agents/stream")
async def agents_stream():
    raise HTTPException(status_code=501, detail="Agent code streaming not implemented yet")


# ---------------------------------------------------------------------------
# API Documentation
# ---------------------------------------------------------------------------

@app.get("/api/reference")
async def api_reference():
    return {
        "api_version": VERSION,
        "base_url": f"http://localhost:{PORT}",
        "endpoints": [
            {
                "method": "GET",
                "path": "/api/health",
                "description": "Health check. Returns system status, uptime, and counts of workspaces, missions, and active tasks.",
                "query_params": None,
                "request_body": None,
                "response": {
                    "status": "ok",
                    "uptime_seconds": 3600,
                    "jbcp": {
                        "status": "running",
                        "workspaces": 2,
                        "missions": 5,
                        "active_tasks": 1,
                    },
                    "version": VERSION,
                },
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/workspaces",
                "description": "List all workspaces (internally called companies). Each workspace includes its id, name, status, focused_mission_id, mission_count, active_task_count, mission_ids, session_key, created_at, and updated_at.",
                "query_params": None,
                "request_body": None,
                "response": [
                    {
                        "id": "string (company_id / workspace_id)",
                        "name": "string | null",
                        "status": "string (e.g. 'active')",
                        "focused_mission_id": "string | null",
                        "mission_count": 0,
                        "active_task_count": 0,
                        "mission_ids": ["string"],
                        "session_key": "agent:main:jbcp-frontend:company:{id}",
                        "created_at": "ISO-8601 string | null",
                        "updated_at": "ISO-8601 string | null",
                    }
                ],
                "status": "implemented",
            },
            {
                "method": "POST",
                "path": "/api/workspaces",
                "description": "Create a new workspace. Also creates a default mission from the prompt, attaches it, sets it as focused, and ensures mission context.",
                "query_params": None,
                "request_body": {
                    "prompt": {"type": "string", "required": True, "description": "The initial goal/prompt for this workspace's first mission."},
                    "name": {"type": "string | null", "required": False, "description": "Workspace name. Defaults to first 60 chars of prompt if omitted."},
                },
                "response": {
                    "id": "string (new workspace_id)",
                    "name": "string",
                    "status": "active",
                    "mission_id": "string (auto-created mission_id)",
                    "prompt": "string",
                    "created_at": "ISO-8601 string",
                },
                "status": "implemented",
            },
            {
                "method": "PATCH",
                "path": "/api/workspaces/{workspace_id}",
                "description": "Rename a workspace. Returns 404 if workspace not found.",
                "query_params": None,
                "request_body": {
                    "name": {"type": "string", "required": True, "description": "New name for the workspace."},
                },
                "response": {
                    "_note": "Returns the full workspace object (same shape as GET /api/workspaces items).",
                    "id": "string",
                    "name": "string",
                    "status": "string",
                    "focused_mission_id": "string | null",
                    "mission_count": 0,
                    "active_task_count": 0,
                    "mission_ids": ["string"],
                    "session_key": "string",
                    "created_at": "ISO-8601 string | null",
                    "updated_at": "ISO-8601 string | null",
                },
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/workspaces/{workspace_id}/missions",
                "description": "List all missions belonging to a workspace. Returns raw mission objects from the missions data store. 404 if workspace not found.",
                "query_params": None,
                "request_body": None,
                "response": [
                    {
                        "_note": "Raw mission objects. Fields depend on jb_missions storage format.",
                        "mission_id": "string",
                        "company_id": "string",
                        "goal": "string",
                        "status": "string",
                        "created_at": "ISO-8601 string",
                    }
                ],
                "status": "implemented",
            },
            {
                "method": "POST",
                "path": "/api/workspaces/{workspace_id}/missions",
                "description": "Create a new mission in a workspace. Attaches it, sets it as focused, ensures context, and auto-creates a drafting plan for the mission. Returns 404 if workspace not found.",
                "query_params": None,
                "request_body": {
                    "goal": {"type": "string", "required": True, "description": "The mission goal."},
                },
                "response": {
                    "ok": True,
                    "mission_id": "string",
                    "plan_id": "string (auto-created plan_id)",
                    "goal": "string",
                },
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/missions/{mission_id}/tasks",
                "description": "List all tasks belonging to a mission. Returns raw task objects from the queue. 404 if mission not found.",
                "query_params": None,
                "request_body": None,
                "response": [
                    {
                        "_note": "Raw task objects from jb_queue.",
                        "task_id": "string",
                        "mission_id": "string",
                        "company_id": "string",
                        "status": "string (pending | dispatched | running | in_progress | done | failed)",
                        "created_at": "ISO-8601 string",
                    }
                ],
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/missions/{mission_id}/plan",
                "description": "Get the current plan for a mission. Returns the best-priority plan (drafting > complete > enacted > cancelled). Returns null (JSON null) if no plan exists. Falls back to searching by company_id if no direct mission_id match.",
                "query_params": None,
                "request_body": None,
                "response": {
                    "_note": "A single plan object or null.",
                    "plan_id": "string",
                    "mission_id": "string | null",
                    "company_id": "string",
                    "title": "string",
                    "status": "string (drafting | complete | enacted | cancelled)",
                    "items": ["list of plan items"],
                    "created_at": "ISO-8601 string",
                },
                "status": "implemented",
            },
            {
                "method": "POST",
                "path": "/api/missions/{mission_id}/plan/approve",
                "description": "Approve and enact a mission's plan. If the plan is still 'drafting', it is first marked complete (must have items). Then the plan is enacted, which creates tasks. Returns 404 if no approvable plan found, 400 if plan has no items or enact fails.",
                "query_params": None,
                "request_body": None,
                "response": {
                    "ok": True,
                    "plan_id": "string",
                    "mission_id": "string",
                    "task_ids": ["string"],
                    "task_count": 3,
                },
                "status": "implemented",
            },
            {
                "method": "POST",
                "path": "/api/missions/{mission_id}/plan/cancel",
                "description": "Cancel a mission's active plan (must be in 'drafting' or 'complete' status). Returns 404 if no cancellable plan found, 400 on cancel failure.",
                "query_params": None,
                "request_body": None,
                "response": {
                    "ok": True,
                    "plan_id": "string",
                },
                "status": "implemented",
            },
            {
                "method": "POST",
                "path": "/api/missions/{mission_id}/plan/generate",
                "description": "Generate plan items by calling the jbcp-worker agent. Blocks until generation completes (10-30s). Returns components, connections, and tasks. 404 if no drafting plan found.",
                "query_params": None,
                "request_body": None,
                "response": {
                    "ok": True,
                    "plan_id": "string",
                    "item_count": 9,
                    "items": [{"item_id": "string", "goal": "string", "type": "coding", "component": "string", "priority": 8}],
                    "components": [{"name": "string", "type": "connector", "description": "string"}],
                    "connections": [{"from": "string", "to": "string", "label": "string"}],
                    "display": "string (human-readable plan text)",
                },
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/agents",
                "description": "List all agent states derived from signals. Includes status (coding/thinking/idle/offline), current model, workspace, file, activity label, source type, token usage, and subagents.",
                "query_params": None,
                "request_body": None,
                "response": [
                    {
                        "agent_id": "string",
                        "name": "string (e.g. 'Santiago', 'JBCP Worker')",
                        "type": "string (primary/worker/subagent)",
                        "status": "string (coding/thinking/idle/offline)",
                        "current_model": "string|null (e.g. 'claude-sonnet-4-6')",
                        "current_workspace": "string|null (company_id)",
                        "current_file": "string|null (filename being touched)",
                        "current_label": "string|null (e.g. 'write: parser.py', 'thinking (claude-opus-4-6)', 'python: pytest tests/')",
                        "current_source": "string|null (claude-code/bash/llm/web/browser/subprocess)",
                        "total_tokens_used": 0,
                        "active_sessions": 0,
                        "total_turns": 0,
                        "subagents": [],
                    }
                ],
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/missions/{mission_id}/context",
                "description": "Get the full context summary for a mission. 404 if mission not found.",
                "query_params": None,
                "request_body": None,
                "response": {
                    "_note": "Context summary object. Shape depends on build_context_summary output.",
                },
                "status": "implemented",
            },
            {
                "method": "POST",
                "path": "/api/tasks/{task_id}/retry",
                "description": "Retry a failed task. Resets the task status so it can be re-dispatched. 404 if task not found, 400 if retry fails (e.g. task not in a retryable state).",
                "query_params": None,
                "request_body": None,
                "response": {
                    "ok": True,
                    "task": {
                        "_note": "The updated task object.",
                        "task_id": "string",
                        "status": "string",
                    },
                },
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/workspaces/{workspace_id}/memory",
                "description": "Read the memory/context files for a workspace. Returns the company-level context text and the focused mission's context text. 404 if workspace not found.",
                "query_params": None,
                "request_body": None,
                "response": {
                    "workspace_id": "string",
                    "company_context": "string | null (raw text content of company context file)",
                    "company_context_path": "string (filesystem path)",
                    "mission_context": "string | null (raw text content of focused mission context file)",
                    "focused_mission_id": "string | null",
                },
                "status": "implemented",
            },
            {
                "method": "PATCH",
                "path": "/api/workspaces/{workspace_id}/memory",
                "description": "Overwrite the company-level context/memory file for a workspace. Creates parent directories if needed. 404 if workspace not found.",
                "query_params": None,
                "request_body": {
                    "content": {"type": "string", "required": True, "description": "The full text content to write to the company context file."},
                },
                "response": {
                    "ok": True,
                    "path": "string (filesystem path written)",
                    "chars": 1234,
                },
                "status": "implemented",
            },
            {
                "method": "POST",
                "path": "/api/chat",
                "description": "Send a chat message. Returns a Server-Sent Events (SSE) stream. Each SSE event is a 'data: ...' line containing a JSON chunk (OpenAI-compatible streaming format). The stream ends with 'data: [DONE]'.",
                "query_params": None,
                "request_body": {
                    "workspace_id": {"type": "string", "required": True, "description": "The workspace ID, used to construct the session_key."},
                    "mission_id": {"type": "string | null", "required": False, "description": "Optional mission ID (currently sent as metadata context)."},
                    "message": {"type": "string", "required": True, "description": "The user's chat message."},
                    "history": {"type": "array of {role: string, content: string} | null", "required": False, "description": "Optional conversation history to prepend."},
                },
                "response": {
                    "_note": "SSE stream (text/event-stream). Each line: 'data: {JSON}' or 'data: [DONE]'. Error events have {error: true, detail: string}.",
                },
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/signals/stream",
                "description": "SSE stream of real-time signals. Tails the signals JSONL file and emits each new signal as an SSE event. Sends keepalive comments every 15 seconds. Stream runs indefinitely until the client disconnects.",
                "query_params": None,
                "request_body": None,
                "response": {
                    "_note": "SSE stream (text/event-stream). Each event: 'data: {signal JSON object}'. Keepalives: ': keepalive'.",
                },
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/workspaces/{workspace_id}/components",
                "description": "List all components belonging to a workspace via jb_components.list_components. Returns 404 if workspace not found.",
                "query_params": None,
                "request_body": None,
                "response": [{"component_id": "string", "workspace_id": "string", "name": "string", "type": "string", "status": "string"}],
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/workspaces/{workspace_id}/graph",
                "description": "Get the dependency graph (nodes and edges) for a workspace via jb_components.build_graph. Returns 404 if workspace not found.",
                "query_params": None,
                "request_body": None,
                "response": {"nodes": [{"id": "string", "type": "string", "label": "string", "status": "string"}], "edges": [{"from": "string", "to": "string", "type": "string"}]},
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/settings",
                "description": "Get system settings. Returns JBCP paths/version and planning model config.",
                "query_params": None,
                "request_body": None,
                "response": {
                    "jbcp": {
                        "workspace_path": "string (filesystem path)",
                        "data_path": "string (filesystem path)",
                        "version": VERSION,
                        "component_count": 0,
                        "service_count": 0,
                    },
                    "planning": {
                        "provider": "string",
                        "model": "string",
                    },
                },
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/live",
                "description": "Get live/running services. Returns services with status 'running' or 'starting', or health 'healthy'.",
                "query_params": None,
                "request_body": None,
                "response": [{"service_id": "string", "name": "string", "status": "string", "health": "string"}],
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/usage",
                "description": "Get token/cost usage statistics. Currently a stub that returns zeroed counters.",
                "query_params": None,
                "request_body": None,
                "response": {
                    "period": "today",
                    "total_tokens_in": 0,
                    "total_tokens_out": 0,
                    "total_cost_usd": 0.0,
                    "by_model": [],
                    "by_agent": [],
                    "by_workspace": [],
                },
                "status": "stub",
            },
            {
                "method": "POST",
                "path": "/api/workspaces/{workspace_id}/promote",
                "description": "Promote a workspace to a deployed service via jb_services.create_service. Returns 404 if workspace not found, 400 on validation error.",
                "query_params": None,
                "request_body": {
                    "name": {"type": "string | null", "required": False, "description": "Service name. Defaults to workspace name."},
                    "description": {"type": "string", "required": False, "description": "Service description."},
                    "type": {"type": "string", "required": False, "description": "Service type (manual, scheduled, daemon, webhook). Default: manual."},
                    "schedule": {"type": "string | null", "required": False, "description": "Cron schedule for scheduled services."},
                    "entry_point": {"type": "string", "required": False, "description": "Entry point script/module."},
                    "has_frontend": {"type": "boolean", "required": False, "description": "Whether the service has a frontend."},
                },
                "response": {"service_id": "string", "workspace_id": "string", "name": "string", "status": "stopped"},
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/components/{component_id}",
                "description": "Get detailed view of a single component by ID. Returns 404 if not found.",
                "query_params": None,
                "request_body": None,
                "response": {"component_id": "string", "workspace_id": "string", "name": "string", "type": "string", "status": "string", "contract": {}, "files": [], "dependencies": []},
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/services",
                "description": "List all registered services via jb_services.list_services.",
                "query_params": None,
                "request_body": None,
                "response": [{"service_id": "string", "workspace_id": "string", "name": "string", "status": "string", "type": "string"}],
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/services/{service_id}",
                "description": "Get detailed view of a single service by ID. Returns 404 if not found.",
                "query_params": None,
                "request_body": None,
                "response": {"service_id": "string", "workspace_id": "string", "name": "string", "status": "string", "type": "string", "run_count": 0, "error_count": 0},
                "status": "implemented",
            },
            {
                "method": "POST",
                "path": "/api/services/{service_id}/pause",
                "description": "Pause a running service. Returns 400 if service is not running or not found.",
                "query_params": None,
                "request_body": None,
                "response": {"ok": True, "service": {"service_id": "string", "status": "paused"}},
                "status": "implemented",
            },
            {
                "method": "POST",
                "path": "/api/services/{service_id}/resume",
                "description": "Resume a paused service. Returns 400 if service is not paused or not found.",
                "query_params": None,
                "request_body": None,
                "response": {"ok": True, "service": {"service_id": "string", "status": "running"}},
                "status": "implemented",
            },
            {
                "method": "POST",
                "path": "/api/services/{service_id}/stop",
                "description": "Stop a service. Returns 400 if service is already stopped or not found.",
                "query_params": None,
                "request_body": None,
                "response": {"ok": True, "service": {"service_id": "string", "status": "stopped"}},
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/services/{service_id}/runs",
                "description": "List run history for a service (most recent first, up to 20). Returns 404 if service not found.",
                "query_params": None,
                "request_body": None,
                "response": [{"run_id": "string", "service_id": "string", "status": "string", "started_at": "ISO-8601", "duration_ms": 0}],
                "status": "implemented",
            },
            {
                "method": "GET",
                "path": "/api/agents/stream",
                "description": "SSE stream of agent code/activity. Not yet implemented. Planned: will stream real-time llm_input/llm_output/tool_start/tool_end signals as SSE events.",
                "query_params": None,
                "request_body": None,
                "response": {"detail": "Agent code streaming not implemented yet"},
                "status": "stub",
            },
            {
                "method": "GET",
                "path": "/api/reference",
                "description": "This endpoint. Returns a complete JSON API reference documenting every endpoint.",
                "query_params": None,
                "request_body": None,
                "response": {"_note": "This JSON object."},
                "status": "implemented",
            },
        ],
        "signal_types": {
            "_note": "Signal types that can be pushed via POST /api/signals/push. These flow through GET /api/events/stream as SSE events.",
            "session_start": {"fields": ["session_id", "session_key", "agent_id", "trigger"]},
            "session_end": {"fields": ["session_id", "session_key", "agent_id", "message_count", "duration_ms"]},
            "agent_turn": {"fields": ["session_id", "session_key", "agent_id", "model", "trigger", "success", "error", "duration_ms"]},
            "llm_input": {
                "description": "Fires when a request is sent to the LLM. Use to show 'thinking...' in the UI.",
                "fields": ["session_id", "session_key", "agent_id", "run_id", "model", "provider", "prompt_chars", "history_count", "images_count"],
            },
            "llm_output": {
                "description": "Fires when the LLM response is complete. Includes token usage and a text preview.",
                "fields": ["session_id", "session_key", "agent_id", "run_id", "model", "provider", "text_preview", "text_chars", "usage"],
                "usage_fields": ["input", "output", "cacheRead", "cacheWrite", "total"],
            },
            "tool_start": {
                "description": "Fires when a tool call begins. Includes source type and human-readable label.",
                "fields": ["session_id", "session_key", "agent_id", "run_id", "tool", "source", "label", "params"],
                "source_values": ["claude-code", "bash", "http", "web", "browser", "subprocess", "llm"],
                "label_examples": ["write: parser.py", "python: pytest tests/", "search: gmail api oauth", "thinking (claude-opus-4-6)"],
            },
            "tool_end": {
                "description": "Fires when a tool call completes. Includes truncated result preview (up to 500 chars).",
                "fields": ["session_id", "session_key", "agent_id", "run_id", "tool", "ok", "error", "duration_ms", "result_preview", "result_chars"],
            },
            "subagent_spawned": {"fields": ["child_session_key", "agent_id", "label", "mode", "run_id"]},
            "subagent_ended": {"fields": ["target_session_key", "target_kind", "reason", "outcome", "error", "run_id"]},
            "message_received": {"fields": ["channel", "conversation_id", "from"]},
        },
    }


# ---------------------------------------------------------------------------
# Salt Desktop v1 — Dashboard endpoints (C2-C5)
# ---------------------------------------------------------------------------

@app.get("/api/dashboard/running")
async def dashboard_running():
    """All running services across all workspaces."""
    services = list_services()
    running = [s for s in services if s.get("status") in ("running", "starting")]
    # Enrich with workspace name
    companies = {c["company_id"]: c for c in list_companies()}
    for s in running:
        ws = companies.get(s.get("workspace_id"))
        s["workspace_name"] = ws.get("name") if ws else None
        s["status_label"] = service_label(s.get("status", ""))
    return running


@app.get("/api/dashboard/building")
async def dashboard_building():
    """All active missions across all workspaces."""
    from runtime.jb_missions import compute_mission_progress
    companies = list_companies()
    result = []
    for c in companies:
        missions = [m for m in list_missions() if m.get("company_id") == c["company_id"]]
        for m in missions:
            if m.get("status") in ("planning", "planned", "active"):
                progress = compute_mission_progress(m["mission_id"])
                result.append({
                    "mission_id": m["mission_id"],
                    "goal": m.get("goal", ""),
                    "status": m["status"],
                    "phase_label": mission_label(m["status"]),
                    "workspace_id": c["company_id"],
                    "workspace_name": c.get("name"),
                    "progress": progress,
                })
    return result


@app.get("/api/dashboard/recent")
async def dashboard_recent(since: str = None, limit: int = 20):
    """Recent events formatted for human consumption."""
    from runtime.jb_events import read_events
    events = read_events()
    if since:
        events = [e for e in events if e.get("timestamp", "") >= since]
    events = events[-limit:]
    # Translate via CEO translator
    translated = []
    for e in events:
        translated.append({
            "type": e.get("type", ""),
            "text": e.get("message") or e.get("type", "Event"),
            "timestamp": e.get("timestamp"),
            "mission_id": e.get("mission_id"),
            "task_id": e.get("task_id"),
        })
    return translated


@app.get("/api/dashboard/heartbeat")
async def dashboard_heartbeat():
    """Quick heartbeat: active workers + running services count."""
    tasks = list_tasks()
    running_tasks = sum(1 for t in tasks if t.get("status") in ("running", "dispatched", "in_progress"))
    services = list_services()
    running_services = sum(1 for s in services if s.get("status") in ("running", "starting"))
    # Latest few events
    try:
        from runtime.jb_events import read_events
        recent = read_events()[-5:]
    except Exception:
        recent = []
    return {
        "active_workers": running_tasks,
        "running_services": running_services,
        "latest_events": [{"type": e.get("type"), "timestamp": e.get("timestamp")} for e in recent],
    }


# ---------------------------------------------------------------------------
# Salt Desktop v1 — Swarm endpoints (C6-C7)
# ---------------------------------------------------------------------------

@app.get("/api/dashboard/swarm")
async def dashboard_swarm():
    """Full swarm view."""
    try:
        from runtime.jb_swarm import get_swarm
        return get_swarm()
    except ImportError:
        return {"building": [], "running": []}


@app.get("/api/missions/{mission_id}/swarm")
async def mission_swarm(mission_id: str):
    """Swarm view filtered to a specific mission."""
    try:
        from runtime.jb_swarm import get_swarm
        return get_swarm(mission_id=mission_id)
    except ImportError:
        return {"building": [], "running": []}


# ---------------------------------------------------------------------------
# Salt Desktop v1 — Deploy/Undeploy/Start (C8-C10)
# ---------------------------------------------------------------------------

@app.post("/api/missions/{mission_id}/deploy")
async def deploy_mission(mission_id: str, request: Request):
    """Deploy a completed mission as a service."""
    body = await request.json()
    service_type = body.get("service_type", "manual")
    schedule = body.get("schedule")

    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission["status"] != "complete":
        raise HTTPException(status_code=400, detail=f"Mission must be complete to deploy, currently: {mission['status']}")

    from runtime.jb_missions import mark_deployed

    service_id = create_service(
        workspace_id=mission.get("company_id") or mission_id,
        name=mission.get("goal", "Unnamed Service")[:50],
        type=service_type,
        schedule=schedule,
        mission_id=mission_id,
    )
    mark_deployed(mission_id)
    event_emit("mission.deployed", mission_id=mission_id, service_id=service_id)
    return {"ok": True, "service_id": service_id, "mission_status": "deployed"}


@app.post("/api/services/{service_id}/undeploy")
async def undeploy_service(service_id: str):
    """Stop service and return mission to complete."""
    from runtime.jb_missions import mark_undeployed

    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    stop_service(service_id)
    mission_id = svc.get("mission_id")
    if mission_id:
        try:
            mark_undeployed(mission_id)
        except ValueError:
            pass  # Mission may not be in deployed state
    return {"ok": True, "mission_id": mission_id, "mission_status": "complete"}


@app.post("/api/services/{service_id}/start")
async def start_service_endpoint(service_id: str):
    """Start a stopped service."""
    from runtime.jb_services import start_service
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    try:
        start_service(service_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "status": "starting"}


# ---------------------------------------------------------------------------
# Salt Desktop v1 — Mission/Component/Workspace (C11-C18)
# ---------------------------------------------------------------------------

@app.get("/api/missions/{mission_id}/progress")
async def mission_progress(mission_id: str):
    """Compute mission build progress from task statuses."""
    from runtime.jb_missions import compute_mission_progress
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return compute_mission_progress(mission_id)


@app.patch("/api/components/{component_id}")
async def patch_component(component_id: str, request: Request):
    """Update component fields (currently supports status)."""
    body = await request.json()
    from runtime.jb_components import mark_component_status
    comp = get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    if "status" in body:
        try:
            mark_component_status(component_id, body["status"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return get_component(component_id)


@app.get("/api/workspaces/{workspace_id}/detail")
async def workspace_detail(workspace_id: str):
    """Rich workspace detail with categorized missions and agents."""
    company = get_company(workspace_id)
    if not company:
        raise HTTPException(status_code=404, detail="Workspace not found")

    missions = [m for m in list_missions() if m.get("company_id") == workspace_id]

    try:
        ws_services = list_services(workspace_id=workspace_id)
    except Exception:
        ws_services = []

    agents = [s for s in ws_services if s.get("status") == "running"]
    active = [m for m in missions if m.get("status") in ("planning", "planned", "active")]
    completed = [m for m in missions if m.get("status") == "complete"]
    deployed = [m for m in missions if m.get("status") == "deployed"]

    return {
        "id": workspace_id,
        "name": company.get("name", "Unnamed"),
        "description": company.get("description"),
        "agents": [{"name": s.get("name"), "status": "running", "service_id": s["service_id"]} for s in agents],
        "missions": [{"mission_id": m["mission_id"], "name": m.get("goal", "")[:60], "status": m["status"],
                       "phase_label": mission_label(m["status"])} for m in active + deployed],
        "completed": [{"mission_id": m["mission_id"], "name": m.get("goal", "")[:60]} for m in completed],
    }


@app.patch("/api/workspaces/{workspace_id}/description")
async def update_workspace_description(workspace_id: str, request: Request):
    """Update workspace description."""
    body = await request.json()
    desc = body.get("description", "")
    from runtime.jb_companies import update_company_description
    try:
        company = update_company_description(workspace_id, desc)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "description": company.get("description")}


@app.get("/api/workspaces/{workspace_id}/tasks")
async def workspace_tasks(workspace_id: str, status: str = None):
    """All tasks across all missions in a workspace."""
    missions = [m for m in list_missions() if m.get("company_id") == workspace_id]
    all_tasks = []
    for m in missions:
        tasks = [t for t in list_tasks() if t.get("mission_id") == m["mission_id"]]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        all_tasks.extend(tasks)
    return all_tasks


# ---------------------------------------------------------------------------
# Salt Desktop v1 — Task/Component file endpoints (C25-C28)
# ---------------------------------------------------------------------------

@app.get("/api/tasks/{task_id}/signals")
async def task_signals(task_id: str):
    """Signal timeline for a specific task (returns empty -- signals removed)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return []


@app.get("/api/tasks/{task_id}/files")
async def task_files(task_id: str):
    """Files created/modified by a task."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # Check component directory for files
    comp_name = task.get("payload", {}).get("component", "")
    if not comp_name:
        return []
    try:
        from runtime.jb_builder import _slugify, COMPONENTS_DIR
        comp_dir = COMPONENTS_DIR / _slugify(comp_name)
        if comp_dir.exists():
            files: set[str] = set()
            for f in comp_dir.rglob("*"):
                if f.is_file():
                    files.add(str(f.relative_to(comp_dir)))
            return sorted(files)
    except Exception:
        pass
    return []


@app.get("/api/components/{component_id}/files")
async def component_files(component_id: str):
    """List files in a component's directory."""
    comp = get_component(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    return {"component_id": component_id, "files": comp.get("files", []),
            "note": "File listing from component record"}


@app.post("/api/services/{service_id}/report")
async def service_report(service_id: str, request: Request):
    """Store a report on a service record."""
    body = await request.json()
    svc = get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    # TODO: store report on service record when report storage is implemented
    return {"ok": True}


# ---------------------------------------------------------------------------
# Salt Desktop v1 — Try It / Graph / Layout (F4, G2, G5, H4)
# ---------------------------------------------------------------------------

@app.post("/api/missions/{mission_id}/try")
async def try_mission(mission_id: str):
    """Generate pipeline and run once."""
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission["status"] not in ("complete", "deployed"):
        raise HTTPException(status_code=400, detail=f"Mission must be complete to try, currently: {mission['status']}")
    try:
        from runtime.jb_pipeline import run_pipeline
        result = run_pipeline(mission_id)
        return result
    except ImportError:
        return {"error": "Pipeline runner not yet available", "exit_code": -1}
    except Exception as e:
        return {"error": str(e), "exit_code": -1}


@app.post("/api/missions/{mission_id}/pipeline/generate")
async def generate_mission_pipeline(mission_id: str):
    """Generate a pipeline.py from the mission's component graph."""
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    try:
        from runtime.jb_pipeline import generate_pipeline
        path = generate_pipeline(mission_id)
        return {"pipeline_path": path, "mission_id": mission_id, "status": "generated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/missions/{mission_id}/pipeline/run")
async def run_mission_pipeline(mission_id: str):
    """Execute the mission's pipeline once (the 'Try It' button)."""
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    try:
        from runtime.jb_pipeline import run_pipeline
        result = run_pipeline(mission_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/missions/{mission_id}/graph")
async def mission_graph(mission_id: str):
    """Mission's component graph -- draft (before approval) or committed (after)."""
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")

    if mission["status"] in ("planning", "planned"):
        # Draft mode: return components/connections from mission object
        draft_components = mission.get("components", [])
        draft_connections = mission.get("connections", [])
        nodes = [{"id": c.get("name", f"node-{i}"), "label": c.get("name", ""),
                  "type": c.get("type", "processor"), "status": "planned",
                  "display_status": "Planned", "is_draft": True}
                 for i, c in enumerate(draft_components)]
        edges = [{"source": conn.get("from", ""), "target": conn.get("to", ""),
                  "label": conn.get("label", ""), "type": conn.get("type", "data_flow")}
                 for conn in draft_connections]
        diff = mission.get("_last_diff", [])
        return {"nodes": nodes, "edges": edges, "is_draft": True, "diff": diff or []}
    else:
        # Committed: use build_graph filtered to this mission's components
        workspace_id = mission.get("company_id")
        if not workspace_id:
            return {"nodes": [], "edges": [], "is_draft": False}
        graph = build_graph(workspace_id)
        # Filter to components with matching mission_id
        mission_comp_ids = {c["component_id"] for c in list_components(workspace_id=workspace_id)
                           if c.get("mission_id") == mission_id}
        if mission_comp_ids:
            graph["nodes"] = [n for n in graph["nodes"] if n["id"] in mission_comp_ids]
            node_ids = {n["id"] for n in graph["nodes"]}
            graph["edges"] = [e for e in graph["edges"]
                              if e.get("source", e.get("from")) in node_ids
                              and e.get("target", e.get("to")) in node_ids]
        graph["is_draft"] = False
        return graph


_GRAPH_LAYOUTS_FILE = DATA_DIR / "jb_graph_layouts.json"


def _load_graph_layouts() -> dict:
    try:
        with open(_GRAPH_LAYOUTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_graph_layouts(data: dict) -> None:
    _GRAPH_LAYOUTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_GRAPH_LAYOUTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


@app.patch("/api/missions/{mission_id}/graph-layout")
async def update_graph_layout(mission_id: str, request: Request):
    """Persist graph node positions for a mission."""
    body = await request.json()
    positions = body.get("positions", {})
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    layouts = _load_graph_layouts()
    layouts[mission_id] = positions
    _save_graph_layouts(layouts)
    return {"ok": True}


@app.get("/api/missions/{mission_id}/graph-layout")
async def get_graph_layout(mission_id: str):
    """Retrieve persisted graph node positions for a mission."""
    mission = get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    layouts = _load_graph_layouts()
    return {"positions": layouts.get(mission_id, {})}


# ---------------------------------------------------------------------------
# Web UI — serve static files from webui/
# ---------------------------------------------------------------------------

WEBUI_DIR = BASE_DIR / "webui"

@app.get("/")
async def webui_root():
    """Serve the web dashboard."""
    index = WEBUI_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "JBCP API Server", "webui": "not found — create webui/index.html", "docs": "/api/reference"}

# Mount static files for JS/CSS (must be after all API routes)
if WEBUI_DIR.exists():
    app.mount("/pages", StaticFiles(directory=str(WEBUI_DIR / "pages")), name="pages")
    app.mount("/components", StaticFiles(directory=str(WEBUI_DIR / "components")), name="components")
    app.mount("/static", StaticFiles(directory=str(WEBUI_DIR)), name="static")

# ---------------------------------------------------------------------------
# Web UI v2
# ---------------------------------------------------------------------------

WEBUI_V2_DIR = BASE_DIR / "webui-v2"


@app.get("/v2")
async def webui_v2_root():
    index = WEBUI_V2_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"error": "webui-v2 not found"}


if WEBUI_V2_DIR.exists():
    app.mount("/v2/static", StaticFiles(directory=str(WEBUI_V2_DIR)), name="v2-static")
    if (WEBUI_V2_DIR / "views").exists():
        app.mount("/v2/views", StaticFiles(directory=str(WEBUI_V2_DIR / "views")), name="v2-views")


# ---------------------------------------------------------------------------
# Connections (credential store)
# ---------------------------------------------------------------------------


@app.get("/api/connections")
async def list_connections():
    """List all known services with connection status."""
    return cred_store.list_all()


@app.get("/api/connections/{service_id}")
async def get_connection(service_id: str):
    """Get connection status for a service. Never exposes raw tokens."""
    connected = cred_store.is_connected(service_id)
    info = SERVICE_CATALOG.get(service_id, {})
    return {
        "id": service_id,
        "name": info.get("name", service_id),
        "type": info.get("type", "unknown"),
        "category": info.get("category", "other"),
        "connected": connected,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "runtime.jb_api:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info",
    )
