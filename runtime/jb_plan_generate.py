"""
Mission plan generation: reads chat history, dispatches to jbcp-worker,
parses structured components/connections/tasks, saves to mission.

Usage:
    python -m runtime.jb_plan_generate --mission-id <id> --session-key <key>

Outputs JSON: {"ok": true, "items": [...], "display": "readable plan text"}
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from typing import Any

from runtime.jb_common import utc_now_iso
from runtime.jb_missions import get_mission, _update_mission, _normalize_item
from runtime.jb_components import list_components


# ---------------------------------------------------------------------------
# G1: Idempotent regeneration helpers
# ---------------------------------------------------------------------------

def _store_previous_draft(mission: dict) -> dict | None:
    """Store current draft as _previous_draft for diffing. Returns the previous draft."""
    items = mission.get("items") or []
    components = mission.get("components") or []
    connections = mission.get("connections") or []

    if not items and not components:
        return None

    previous_draft = {
        "items": deepcopy(items),
        "components": deepcopy(components),
        "connections": deepcopy(connections),
        "generated_at": mission.get("_last_generated_at"),
    }
    return previous_draft


def _clear_draft(mission_id: str) -> None:
    """Clear items, components, connections on mission to prepare for regeneration."""
    _update_mission(mission_id, {
        "items": [],
        "components": [],
        "connections": [],
    })


# ---------------------------------------------------------------------------
# G3: Previous graph context for prompt
# ---------------------------------------------------------------------------

def _build_previous_graph_context(mission: dict) -> str:
    """Build prompt section describing the previous architecture."""
    prev = mission.get("_previous_draft")
    if not prev:
        return ""

    components = prev.get("components") or []
    connections = prev.get("connections") or []

    if not components:
        return ""

    parts = ["## Previous Architecture (refine based on user feedback below)"]
    parts.append("Components:")
    for comp in components:
        name = comp.get("name", "?")
        ctype = comp.get("type", "?")
        input_type = comp.get("input_type", "None")
        output_type = comp.get("output_type", "Any")
        config_fields = list((comp.get("config_fields") or {}).keys())
        config_str = ", ".join(config_fields) if config_fields else "none"
        parts.append(f"- {name} ({ctype}): input={input_type}, output={output_type}, config=[{config_str}]")

    if connections:
        parts.append("")
        parts.append("Connections:")
        for conn in connections:
            src = conn.get("from", "?")
            tgt = conn.get("to", "?")
            label = conn.get("label", "")
            label_str = f": {label}" if label else ""
            parts.append(f"- {src} -> {tgt}{label_str}")

    return "\n".join(parts)


def _get_messages_since(chat_history: list[dict], since_timestamp: str | None) -> str:
    """Get chat messages since the last generation for context."""
    if not chat_history or not since_timestamp:
        return ""

    new_messages = []
    for msg in chat_history:
        msg_ts = msg.get("timestamp") or msg.get("ts") or msg.get("created_at") or ""
        if msg_ts and msg_ts > since_timestamp:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            if content and len(content) > 10:
                new_messages.append(f"[{role}]: {content[:500]}")

    if not new_messages:
        return ""

    parts = ["## User Messages Since Last Generation"]
    parts.extend(new_messages)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# G4: Graph diff computation
# ---------------------------------------------------------------------------

def compute_graph_diff(mission: dict) -> list[dict]:
    """Compare current draft to _previous_draft.

    Returns list of: {"name": str, "type": str, "change": "added"|"removed"|"modified"|"unchanged"}
    Match by name+type. "modified" if contract fields changed.
    """
    prev = mission.get("_previous_draft")
    current_components = mission.get("components") or []

    if not prev:
        # Everything is new
        return [
            {"name": c.get("name", "?"), "type": c.get("type", "?"), "change": "added"}
            for c in current_components
        ]

    prev_components = prev.get("components") or []

    # Build lookup by (name, type) for previous
    prev_by_key: dict[tuple[str, str], dict] = {}
    for c in prev_components:
        key = (c.get("name", ""), c.get("type", ""))
        prev_by_key[key] = c

    # Build lookup for current
    current_by_key: dict[tuple[str, str], dict] = {}
    for c in current_components:
        key = (c.get("name", ""), c.get("type", ""))
        current_by_key[key] = c

    diff: list[dict] = []

    # Check current components against previous
    for key, comp in current_by_key.items():
        name, ctype = key
        if key not in prev_by_key:
            diff.append({"name": name, "type": ctype, "change": "added"})
        else:
            prev_comp = prev_by_key[key]
            # Compare contract-relevant fields
            changed = False
            for field in ("input_type", "output_type", "config_fields", "output_fields", "description"):
                curr_val = comp.get(field)
                prev_val = prev_comp.get(field)
                if curr_val != prev_val:
                    changed = True
                    break
            diff.append({"name": name, "type": ctype, "change": "modified" if changed else "unchanged"})

    # Check for removed components
    for key in prev_by_key:
        if key not in current_by_key:
            name, ctype = key
            diff.append({"name": name, "type": ctype, "change": "removed"})

    return diff


# ---------------------------------------------------------------------------
# E4: Component catalog for reuse awareness
# ---------------------------------------------------------------------------

def _build_component_catalog() -> str:
    """Build compact summary of all built/passing/deployed components across all workspaces.

    Cap at 20 components. Filter to status in (built, passing, deployed).
    Return empty string if no reusable components exist.
    """
    all_components = list_components()
    reusable = [
        c for c in all_components
        if c.get("status") in ("built", "passing", "deployed")
    ]

    if not reusable:
        return ""

    # Cap at 20
    reusable = reusable[:20]

    parts = ["Available components you can reuse:"]
    for comp in reusable:
        name = comp.get("name", "?")
        ctype = comp.get("type", "?")
        contract = comp.get("contract") or {}
        output_type = contract.get("output_type", "Any")
        input_type = contract.get("input_type", "None")
        config_keys = list((contract.get("config_fields") or {}).keys())
        config_str = ", ".join(config_keys) if config_keys else "none"

        line = f"- {name} ({ctype})"
        if input_type and input_type != "None":
            line += f": input={input_type}"
        line += f", output={output_type}, config=[{config_str}]"
        parts.append(line)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Chat history fetching
# ---------------------------------------------------------------------------

def fetch_chat_history(mission_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Fetch recent chat history from local SQLite."""
    try:
        from runtime.jb_database import get_chat_messages
        return get_chat_messages(mission_id, limit=limit)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def build_generation_prompt(
    mission_goal: str,
    chat_history: list[dict],
    existing_items: list[dict],
    mission: dict | None = None,
) -> str:
    """Build a prompt for the worker to generate plan items."""
    parts = [
        "You are a project planner. Based on the conversation below, create a structured execution plan.",
        "",
        f"Mission: {mission_goal}",
        "",
    ]

    # E4: Inject component catalog for reuse awareness
    catalog = _build_component_catalog()
    if catalog:
        parts.append(catalog)
        parts.append("")

    # G3: Inject previous architecture context when regenerating
    if mission:
        prev_context = _build_previous_graph_context(mission)
        if prev_context:
            parts.append(prev_context)
            parts.append("")

            # Messages since last generation
            since_ts = (mission.get("_previous_draft") or {}).get("generated_at")
            new_msgs = _get_messages_since(chat_history, since_ts)
            if new_msgs:
                parts.append(new_msgs)
                parts.append("")

            parts.append("## Instructions")
            parts.append("Update the architecture based on the user's feedback. Keep components that work, modify or remove those they asked about, add new ones as needed.")
            parts.append("")

    if chat_history:
        parts.append("=== CONVERSATION CONTEXT ===")
        for msg in chat_history[-30:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            if content and len(content) > 20:
                parts.append(f"[{role}]: {content[:500]}")
        parts.append("=== END CONVERSATION ===")
        parts.append("")

    if existing_items and not (mission and mission.get("_previous_draft")):
        parts.append("Previous plan (refine/replace this):")
        for i, item in enumerate(existing_items, 1):
            parts.append(f"  {i}. [{item.get('type')}] {item.get('goal')}")
        parts.append("")

    parts += [
        "Design a system architecture with components, connections, and tasks.",
        "",
        "Respond with ONLY a JSON object (no markdown, no explanation) in this exact format:",
        '{',
        '  "components": [',
        '    {"name": "Component Name", "type": "connector|processor|ai|output|scheduler|storage|config",',
        '     "description": "what it does",',
        '     "output_type": "List[Something]", "output_fields": {"field": "type"},',
        '     "config_fields": {"key": "type = default"},',
        '     "dependencies": ["Other Component Name"]},',
        '    ...',
        '  ],',
        '  "connections": [',
        '    {"from": "Component A", "to": "Component B", "label": "data description"},',
        '    ...',
        '  ],',
        '  "tasks": [',
        '    {"goal": "specific actionable goal", "component": "Component Name", "type": "coding", "priority": 8},',
        '    ...',
        '  ]',
        '}',
        "",
        "Valid component types: connector, processor, ai, output, scheduler, storage, config",
        "Valid task types: coding, research, document, analysis",
        "Priority: 1-10 (10 = highest, runs first)",
        "",
        "RULES:",
        "- Create 2-8 components representing logical pieces of the system",
        "- Each component should have a clear input/output contract",
        "- Connections define data flow between components",
        "- Create 3-10 concrete tasks, each referencing a component by name",
        "- Each task must be specific enough to execute without clarification",
        "- One clear goal per task, not compound goals",
        "- Order by dependency (things that must happen first get higher priority)",
        "- Output ONLY the JSON object, no markdown, no explanation",
    ]

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Worker invocation and response parsing
# ---------------------------------------------------------------------------

def call_worker(prompt: str) -> dict[str, Any]:
    """Call the LLM directly to generate plan items."""
    return _call_llm_direct(prompt)


def parse_items_from_response(text: str) -> dict[str, Any]:
    """Extract components, connections, and tasks from worker response text."""
    cleaned = text.strip()

    # Strip markdown code fences
    if "```" in cleaned:
        lines = cleaned.split("\n")
        in_block = False
        json_lines: list[str] = []
        for line in lines:
            if line.strip().startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                json_lines.append(line)
        if json_lines:
            cleaned = "\n".join(json_lines).strip()

    parsed = _try_parse_structured(cleaned)
    if parsed is not None:
        return parsed

    obj_start = cleaned.find("{")
    obj_end = cleaned.rfind("}")
    if obj_start >= 0 and obj_end > obj_start:
        parsed = _try_parse_structured(cleaned[obj_start:obj_end + 1])
        if parsed is not None:
            return parsed

    # Fallback: flat JSON array
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start >= 0 and end > start:
        try:
            items = json.loads(cleaned[start:end + 1])
            if isinstance(items, list):
                return {"components": [], "connections": [], "tasks": items}
        except json.JSONDecodeError:
            pass

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return {"components": [], "connections": [], "tasks": data}
        if isinstance(data, dict) and "items" in data:
            return {"components": [], "connections": [], "tasks": data["items"]}
    except json.JSONDecodeError:
        pass

    return {"components": [], "connections": [], "tasks": []}


def _try_parse_structured(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    has_components = isinstance(data.get("components"), list)
    has_tasks = isinstance(data.get("tasks"), list)
    if not has_components and not has_tasks:
        if isinstance(data.get("items"), list):
            return {"components": [], "connections": [], "tasks": data["items"]}
        return None

    return {
        "components": list(data.get("components") or []),
        "connections": list(data.get("connections") or []),
        "tasks": list(data.get("tasks") or data.get("items") or []),
    }


# ---------------------------------------------------------------------------
# Main generation entry point
# ---------------------------------------------------------------------------

def generate_mission_plan(mission_id: str, session_key: str | None = None) -> dict[str, Any]:
    """Main entry: generate plan items for a mission."""
    mission = get_mission(mission_id)
    if not mission:
        return {"ok": False, "error": f"Mission not found: {mission_id}"}
    if mission["status"] != "planning":
        return {"ok": False, "error": f"Mission not in planning state: {mission['status']}"}

    # G1: Idempotent regeneration — store previous draft if one exists
    has_existing = bool(mission.get("items") or mission.get("components"))
    if has_existing:
        previous_draft = _store_previous_draft(mission)
        _update_mission(mission_id, {"_previous_draft": previous_draft})
        _clear_draft(mission_id)
        # Re-read mission with _previous_draft stored
        mission = get_mission(mission_id)

    # Fetch chat history from SQLite
    chat_history = fetch_chat_history(mission_id, limit=50)

    # Build prompt and call worker
    prompt = build_generation_prompt(
        mission_goal=mission["goal"],
        chat_history=chat_history,
        existing_items=mission.get("items", []),
        mission=mission,
    )

    result = call_worker(prompt)
    if not result["ok"]:
        return result

    # Parse structured response
    parsed = parse_items_from_response(result["text"])
    raw_tasks = parsed.get("tasks", [])
    raw_components = parsed.get("components", [])
    raw_connections = parsed.get("connections", [])

    if not raw_tasks:
        return {
            "ok": False,
            "error": "Could not parse plan items from worker response",
            "raw_response": result["text"][:500],
        }

    # Normalize task items
    items = []
    for raw in raw_tasks:
        try:
            items.append(_normalize_item(raw))
        except ValueError:
            continue

    if not items:
        return {"ok": False, "error": "No valid items after normalization"}

    # Save to mission
    update_fields: dict[str, Any] = {
        "items": items,
        "components": raw_components,
        "connections": raw_connections,
        "_last_generated_at": utc_now_iso(),
    }

    _update_mission(mission_id, update_fields)

    # G4: Compute diff if we had a previous draft
    mission = get_mission(mission_id)
    diff = compute_graph_diff(mission)
    if diff:
        _update_mission(mission_id, {"_last_diff": diff})

    # Build display text
    display_lines = [f"**Mission: {mission['goal']}**\n"]

    if raw_components:
        display_lines.append(f"**Components** ({len(raw_components)}):")
        for comp in raw_components:
            display_lines.append(f"  - [{comp.get('type', '?')}] {comp.get('name', '?')}")
        display_lines.append("")

    if raw_connections:
        display_lines.append(f"**Connections** ({len(raw_connections)}):")
        for conn in raw_connections:
            label = conn.get("label", "")
            display_lines.append(f"  - {conn.get('from')} -> {conn.get('to')}" + (f" ({label})" if label else ""))
        display_lines.append("")

    # G4: Show diff markers if available
    if diff and has_existing:
        changes = [d for d in diff if d["change"] != "unchanged"]
        if changes:
            display_lines.append("**Changes from previous:**")
            for d in changes:
                marker = {"added": "+", "removed": "-", "modified": "~"}.get(d["change"], "?")
                display_lines.append(f"  [{marker}] {d['name']} ({d['type']})")
            display_lines.append("")

    display_lines.append(f"**Tasks** ({len(items)}):")
    for i, item in enumerate(items, 1):
        comp_ref = f" @{item['component']}" if item.get("component") else ""
        display_lines.append(f"  {i}. [{item['type']}] {item['goal']}{comp_ref}")

    display_lines.append(f"\nSay **'/mission approve'** when ready to start building.")

    return {
        "ok": True,
        "mission_id": mission_id,
        "item_count": len(items),
        "items": items,
        "components": raw_components,
        "connections": raw_connections,
        "diff": diff if has_existing else None,
        "display": "\n".join(display_lines),
    }


# Keep backward compat alias
generate_plan = generate_mission_plan


# ---------------------------------------------------------------------------
# Lightweight preview for live draft graph
# ---------------------------------------------------------------------------

PREVIEW_PROMPT_TEMPLATE = """Based on this conversation, what components would this system need?
Return ONLY valid JSON, no other text:
{{
  "components": [
    {{"name": "Gmail Connector", "type": "connector"}},
    {{"name": "Email Classifier", "type": "ai"}},
    {{"name": "Result Reporter", "type": "output"}}
  ],
  "connections": [
    {{"from": "Gmail Connector", "to": "Email Classifier", "label": "raw emails"}},
    {{"from": "Email Classifier", "to": "Result Reporter", "label": "classified emails"}}
  ]
}}

Component types: connector, processor, ai, output, scheduler, storage

Mission goal: {goal}

=== CONVERSATION ===
{chat_text}
=== END ===
"""


def _call_llm_direct(prompt: str, system: str = "") -> dict[str, Any]:
    """Call the configured LLM provider directly (same provider as planning chat).

    Returns {"ok": True, "text": "..."} or {"ok": False, "error": "..."}.
    """
    import os

    provider = os.environ.get("SALT_PLANNING_PROVIDER", "anthropic")
    model = os.environ.get("SALT_PLANNING_MODEL", "")

    # Try to read runtime settings from jb_api if loaded
    try:
        from runtime.jb_api import _get_planning_provider, _get_planning_model
        provider = _get_planning_provider()
        model = _get_planning_model()
    except ImportError:
        pass

    if not model:
        defaults = {"anthropic": "claude-sonnet-4-20250514", "openai": "gpt-4o"}
        model = defaults.get(provider, "gpt-4o")

    if provider == "openai":
        try:
            from openai import OpenAI
            from runtime.jb_api import _read_openai_key
            api_key = _read_openai_key()
            if not api_key:
                return {"ok": False, "error": "OpenAI API key not configured"}
            client = OpenAI(api_key=api_key)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            token_param = {}
            if "gpt-5" in model or "o1" in model or "o3" in model:
                token_param["max_completion_tokens"] = 2048
            else:
                token_param["max_tokens"] = 2048
            resp = client.chat.completions.create(model=model, messages=messages, **token_param)
            text = resp.choices[0].message.content or ""
            return {"ok": True, "text": text}
        except Exception as e:
            return {"ok": False, "error": f"OpenAI error: {e}"}
    else:
        try:
            import anthropic
            from runtime.jb_api import _read_anthropic_key
            api_key = _read_anthropic_key()
            if not api_key:
                return {"ok": False, "error": "Anthropic API key not configured"}
            client = anthropic.Anthropic(api_key=api_key)
            kwargs: dict[str, Any] = {"model": model, "max_tokens": 2048, "messages": [{"role": "user", "content": prompt}]}
            if system:
                kwargs["system"] = system
            resp = client.messages.create(**kwargs)
            text = resp.content[0].text if resp.content else ""
            return {"ok": True, "text": text}
        except Exception as e:
            return {"ok": False, "error": f"Anthropic error: {e}"}


def generate_preview(mission_id: str) -> dict[str, Any]:
    """
    Lightweight plan preview -- returns component names + connections only.
    No tasks, no full contracts. Used for live draft graph during planning.
    Uses direct LLM call (same provider/model as planning chat).
    """
    mission = get_mission(mission_id)
    if not mission:
        return {"ok": False, "error": f"Mission not found: {mission_id}"}

    # Fetch chat history from SQLite
    chat_history = fetch_chat_history(mission_id, limit=20)

    # Build compact chat text
    chat_lines: list[str] = []
    for msg in chat_history[-15:]:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )
        if content and len(content) > 10:
            chat_lines.append(f"[{role}]: {content[:300]}")

    chat_text = "\n".join(chat_lines) if chat_lines else ""

    # Don't generate preview if there's no real conversation
    if not chat_text or len(chat_lines) < 2:
        return {"ok": True, "components": [], "connections": [], "preview": True, "reason": "not enough conversation yet"}

    prompt = PREVIEW_PROMPT_TEMPLATE.format(
        goal=mission.get("goal", ""),
        chat_text=chat_text,
    )

    # Direct LLM call (same provider/model as planning chat)
    result = _call_llm_direct(prompt)
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "Preview generation failed")}

    # Parse -- reuse the structured parser, just extract components/connections
    parsed = parse_items_from_response(result["text"])
    components = parsed.get("components", [])
    connections = parsed.get("connections", [])

    # Strip down to just name + type for components
    slim_components = [
        {"name": c.get("name", "?"), "type": c.get("type", "processor")}
        for c in components
    ]
    slim_connections = [
        {
            "from": c.get("from", ""),
            "to": c.get("to", ""),
            "label": c.get("label", ""),
        }
        for c in connections
    ]

    return {
        "ok": True,
        "components": slim_components,
        "connections": slim_connections,
        "preview": True,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate mission plan items")
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--session-key", help="(deprecated) Session key")
    # Legacy support
    parser.add_argument("--plan-id", help="Legacy: treated as mission-id")
    args = parser.parse_args()

    mid = args.mission_id or args.plan_id
    result = generate_mission_plan(mid, args.session_key)
    print(json.dumps(result, default=str), flush=True)


if __name__ == "__main__":
    main()
