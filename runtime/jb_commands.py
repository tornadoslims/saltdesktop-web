# runtime/jb_commands.py
#
# Command handling for the API chat endpoint.
# Mirrors the plugin commands in Python.
# All mutations go through the same runtime modules.

from __future__ import annotations

import json
from typing import Any

from runtime.jb_companies import (
    get_company, list_companies, update_company_name,
    attach_mission, set_focused_mission, get_focused_mission_id,
)
from runtime.jb_missions import (
    create_mission, get_mission, list_missions, mark_mission_status,
    approve_mission,
)
from runtime.jb_event_bus import emit
from runtime.jb_companies import ensure_mission_context
from runtime.jb_queue import list_tasks, retry_task


def handle_command(message: str, workspace_id: str) -> dict[str, Any] | None:
    """
    Parse and handle a slash command from the API chat endpoint.

    Returns a dict with {text, command: True, command_type} if the message
    is a command, or None if it's a regular message.
    """
    msg = message.strip()
    if not msg.startswith("/"):
        return None

    parts = msg[1:].split(None, 1)
    command = parts[0].lower() if parts else ""
    args = parts[1].strip() if len(parts) > 1 else ""

    handlers = {
        "mission": _handle_mission,
        "contextmem": _handle_contextmem,
        "jbdebug": _handle_debug,
        "status": _handle_status,
    }

    handler = handlers.get(command)
    if not handler:
        return None  # Not a known command — pass through to agent

    result = handler(args, workspace_id)
    result["command"] = True
    result["command_type"] = f"{command}.{args.split()[0] if args else 'status'}"
    return result


def _handle_mission(args: str, workspace_id: str) -> dict[str, Any]:
    parts = args.split(None, 1)
    sub = parts[0] if parts else "current"
    rest = parts[1].strip() if len(parts) > 1 else ""

    company = get_company(workspace_id)
    if not company:
        return {"text": f"Workspace not found: {workspace_id}"}

    if sub in ("current", "status"):
        focused_id = company.get("focused_mission_id")
        focused = get_mission(focused_id) if focused_id else None
        text = f"**Workspace:** {company['name']}\n"
        text += f"**Focused Mission:** {focused['goal'] if focused else 'none'}\n"
        if focused:
            text += f"**Status:** {focused['status']}\n"
            items = focused.get("items", [])
            comps = focused.get("components", [])
            if focused["status"] == "planning":
                text += f"**Planning Mode:** ✎ active ({len(items)} items, {len(comps)} components)"
        return {"text": text}

    if sub == "list":
        missions = [m for m in list_missions() if m.get("company_id") == workspace_id]
        if not missions:
            return {"text": "No missions."}
        lines = []
        for m in missions:
            focused = " ← focused" if m["mission_id"] == company.get("focused_mission_id") else ""
            lines.append(f"• [{m['status']}] **{m['goal']}**{focused}")
        return {"text": f"**Missions:**\n" + "\n".join(lines)}

    if sub == "new":
        if not rest:
            return {"text": "What do you want to build? Tell me and I'll create a mission for it.\n\nExample: `/mission new Build a real-time crypto dashboard`"}

        # Check for existing planning mission
        missions = [m for m in list_missions() if m.get("company_id") == workspace_id]
        planning = next((m for m in missions if m["status"] == "planning"), None)
        if planning:
            return {"text": f"Already in planning mode for: **{planning['goal']}**\nUse `/mission approve` or `/mission cancel` first."}

        mid = create_mission(goal=rest, company_id=workspace_id, status="planning")
        attach_mission(workspace_id, mid)
        set_focused_mission(workspace_id, mid)
        ensure_mission_context(workspace_id, mid, goal=rest)

        emit("mission.created", workspace_id=workspace_id, mission_id=mid, goal=rest)

        return {
            "text": f"**Mission created: {rest}**\n"
                    f"You are now in **planning mode**.\n"
                    f"Chat about what you want to build. When ready, say `/mission generate`.\n"
                    f"You can regenerate as many times as you want.",
        }

    if sub in ("generate", "gen"):
        focused_id = company.get("focused_mission_id")
        focused = get_mission(focused_id) if focused_id else None
        if not focused or focused["status"] != "planning":
            return {"text": "No mission in planning mode. Start with `/mission new <goal>`"}

        from runtime.jb_plan_generate import generate_mission_plan
        session_key = f"agent:main:jbcp-frontend:company:{workspace_id}"
        result = generate_mission_plan(focused_id, session_key=session_key)
        if result.get("ok"):
            emit("mission.generated", workspace_id=workspace_id, mission_id=focused_id,
                 item_count=result.get("item_count", 0))
            return {"text": result.get("display", "Plan generated.")}
        else:
            return {"text": f"Generation failed: {result.get('error', 'unknown')}"}

    if sub in ("approve", "go"):
        focused_id = company.get("focused_mission_id")
        focused = get_mission(focused_id) if focused_id else None
        if not focused or focused["status"] not in ("planning", "planned"):
            return {"text": "No mission to approve. Generate a plan first."}
        if not focused.get("items"):
            return {"text": "Mission has no items. `/mission generate` first."}

        result = approve_mission(focused_id)
        comp_count = len(result.get("component_name_to_id", {}))
        emit("mission.approved", workspace_id=workspace_id, mission_id=focused_id,
             tasks_created=len(result["task_ids"]), components_created=comp_count)
        text = f"**Mission approved!** {len(result['task_ids'])} tasks enqueued."
        if comp_count:
            text += f" {comp_count} components created."
        return {"text": text}

    if sub == "cancel":
        focused_id = company.get("focused_mission_id")
        focused = get_mission(focused_id) if focused_id else None
        if not focused or focused["status"] not in ("planning", "planned"):
            return {"text": "No mission to cancel."}
        mark_mission_status(focused_id, "cancelled")
        emit("mission.cancelled", workspace_id=workspace_id, mission_id=focused_id)
        return {"text": f"Mission cancelled: **{focused['goal']}**"}

    if sub in ("switch", "focus"):
        if not rest:
            return {"text": "Usage: `/mission switch <name>`"}
        missions = [m for m in list_missions() if m.get("company_id") == workspace_id]
        needle = rest.lower()
        match = next(
            (m for m in missions if needle in m.get("goal", "").lower() or m.get("mission_id", "").startswith(needle)),
            None,
        )
        if not match:
            return {"text": f"No mission matching \"{rest}\" in this workspace."}
        set_focused_mission(workspace_id, match["mission_id"])
        emit("mission.switched", workspace_id=workspace_id, mission_id=match["mission_id"], goal=match["goal"])
        return {"text": f"Switched to: **{match['goal']}**"}

    if sub == "help":
        return {
            "text": "**Mission Commands:**\n"
                    "• `/mission` — show current mission status\n"
                    "• `/mission list` — list all missions\n"
                    "• `/mission new <goal>` — create mission + enter planning mode\n"
                    "• `/mission generate` — AI generates components + tasks from conversation\n"
                    "• `/mission approve` — approve and start building\n"
                    "• `/mission cancel` — cancel current mission\n"
                    "• `/mission switch <name>` — switch focused mission",
        }

    return {"text": f"Unknown: {sub}. Try `/mission help`"}


def _handle_contextmem(args: str, workspace_id: str) -> dict[str, Any]:
    company = get_company(workspace_id)
    if not company:
        return {"text": "Workspace not found."}

    mid = company.get("focused_mission_id")
    mission = get_mission(mid) if mid else None
    text = f"**Context for {company['name']}**\n\n"
    text += f"**Mission:** {mission['goal'] if mission else 'none'}\n"
    text += f"**Status:** {mission['status'] if mission else 'n/a'}"
    return {"text": text}


def _handle_debug(args: str, workspace_id: str) -> dict[str, Any]:
    from runtime.jb_common import DATA_DIR
    settings_file = DATA_DIR / "jbcp_settings.json"

    try:
        settings = json.loads(settings_file.read_text()) if settings_file.exists() else {}
    except Exception:
        settings = {}

    defaults = {"debug_footer": False, "debug_signals": False, "debug_tool_blocks": False}
    settings = {**defaults, **settings}

    parts = args.split()
    sub = parts[0] if parts else "status"

    if sub == "status":
        lines = [f"{'✅' if v else '⬜'} `{k}`: {'ON' if v else 'OFF'}" for k, v in settings.items()]
        return {"text": f"**Debug Settings:**\n" + "\n".join(lines) + "\n\nToggle: `/jbdebug <setting>`"}

    if sub in settings:
        settings[sub] = not settings[sub]
        settings_file.write_text(json.dumps(settings, indent=2))
        return {"text": f"**{sub}** is now **{'ON' if settings[sub] else 'OFF'}**"}

    return {"text": f"Unknown setting: {sub}. Try `/jbdebug`"}


def _handle_status(args: str, workspace_id: str) -> dict[str, Any]:
    company = get_company(workspace_id)
    if not company:
        return {"text": "Workspace not found."}

    missions = [m for m in list_missions() if m.get("company_id") == workspace_id]
    tasks = [t for t in list_tasks() if t.get("company_id") == workspace_id]

    active_tasks = [t for t in tasks if t["status"] in ("pending", "dispatched", "running")]
    complete_tasks = [t for t in tasks if t["status"] == "complete"]
    failed_tasks = [t for t in tasks if t["status"] == "failed"]

    text = f"**Workspace: {company['name']}**\n"
    text += f"Missions: {len(missions)} | Tasks: {len(tasks)}\n"
    text += f"Active: {len(active_tasks)} | Complete: {len(complete_tasks)} | Failed: {len(failed_tasks)}"

    focused_id = company.get("focused_mission_id")
    if focused_id:
        focused = get_mission(focused_id)
        if focused:
            text += f"\n\n**Focused:** {focused['goal']} [{focused['status']}]"

    return {"text": text}
