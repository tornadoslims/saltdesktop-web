# runtime/jb_compaction.py
#
# Compaction agent: after tasks complete, updates mission_context.md
# so the next task dispatched gets richer context.
#
# Also handles mission lifecycle (auto-complete when all tasks done).

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.jb_common import utc_now_iso, DATA_DIR
from runtime.jb_queue import list_tasks, get_task
from runtime.jb_missions import get_mission, mark_mission_status, update_mission_summary
from runtime.jb_companies import (
    get_company, get_company_context_path, get_mission_context_path, ensure_mission_context,
)
from runtime.jb_events import emit_event

VENV_PYTHON = str(Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python")


def compact_mission(mission_id: str) -> dict[str, Any]:
    """
    Update mission_context.md based on completed tasks.

    Reads the mission's tasks, builds a summary prompt,
    dispatches to jbcp-worker to write the updated context.
    """
    mission = get_mission(mission_id)
    if not mission:
        return {"ok": False, "error": f"Mission not found: {mission_id}"}

    company_id = mission.get("company_id")
    goal = mission.get("goal", "")
    task_ids = mission.get("task_ids", [])

    # Gather task info
    tasks_info = []
    for tid in task_ids:
        task = get_task(tid)
        if task:
            tasks_info.append({
                "id": tid[:12],
                "status": task.get("status"),
                "type": task.get("type"),
                "goal": task.get("payload", {}).get("goal", ""),
            })

    completed = [t for t in tasks_info if t["status"] == "complete"]
    pending = [t for t in tasks_info if t["status"] == "pending"]
    failed = [t for t in tasks_info if t["status"] == "failed"]

    # Read current context
    current_context = ""
    if company_id:
        ctx_path = ensure_mission_context(company_id, mission_id, goal=goal)
        try:
            current_context = ctx_path.read_text(encoding="utf-8")
        except Exception:
            current_context = ""

    # Build compaction prompt
    prompt_parts = [
        "JBCP Compaction Task",
        "",
        f"Mission: {goal}",
        f"Mission ID: {mission_id}",
        "",
        f"Completed tasks ({len(completed)}):",
    ]
    for t in completed:
        prompt_parts.append(f"  - [{t['type']}] {t['goal']}")

    if pending:
        prompt_parts.append(f"\nPending tasks ({len(pending)}):")
        for t in pending:
            prompt_parts.append(f"  - [{t['type']}] {t['goal']}")

    if failed:
        prompt_parts.append(f"\nFailed tasks ({len(failed)}):")
        for t in failed:
            prompt_parts.append(f"  - [{t['type']}] {t['goal']}")

    if current_context and current_context.strip() != f"# Mission Context\n\n## Goal: {goal}":
        prompt_parts.append(f"\nCurrent mission context:\n{current_context}")

    prompt_parts += [
        "",
        "Your job: Write an updated mission_context.md that captures:",
        "- What has been accomplished so far",
        "- What is still pending",
        "- Any blockers or failures to note",
        "- Key decisions or insights from completed work",
        "",
        "Write the content as markdown. Be concise but complete.",
        f"Write the file to: {ctx_path}",
        "",
        "Output ONLY the file content, nothing else.",
    ]

    prompt = "\n".join(prompt_parts)

    # Write a simple context update (no LLM call needed for compaction)
    try:
        context_lines = [
            f"# Mission Context\n",
            f"## Goal: {goal}\n",
            f"## Status\n",
            f"Completed: {len(completed)} tasks\n",
            f"Pending: {len(pending)} tasks\n",
            f"Failed: {len(failed)} tasks\n",
        ]
        if completed:
            context_lines.append("\n## Completed Work\n")
            for t in completed:
                context_lines.append(f"- [{t['type']}] {t['goal']}\n")
        if pending:
            context_lines.append("\n## Remaining Work\n")
            for t in pending:
                context_lines.append(f"- [{t['type']}] {t['goal']}\n")
        if failed:
            context_lines.append("\n## Failed Tasks\n")
            for t in failed:
                context_lines.append(f"- [{t['type']}] {t['goal']}\n")

        if company_id:
            ctx_path.write_text("".join(context_lines), encoding="utf-8")

        emit_event(
            "mission_compacted",
            mission_id=mission_id,
            payload={"completed_tasks": len(completed), "pending_tasks": len(pending)},
        )
        return {"ok": True, "mission_id": mission_id, "compacted": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_mission_lifecycle(mission_id: str) -> dict[str, Any]:
    """
    Check if a mission should be auto-completed or marked failed.

    Rules:
    - All tasks complete → mission complete
    - All tasks complete or failed, at least one failed → mission failed
    - Mix of complete and pending → still active
    """
    mission = get_mission(mission_id)
    if not mission:
        return {"ok": False, "error": f"Mission not found: {mission_id}"}

    if mission["status"] not in ("active", "blocked"):
        return {"ok": True, "changed": False, "status": mission["status"]}

    task_ids = mission.get("task_ids", [])
    if not task_ids:
        return {"ok": True, "changed": False, "status": mission["status"]}

    statuses = []
    for tid in task_ids:
        task = get_task(tid)
        if task:
            statuses.append(task.get("status"))

    if not statuses:
        return {"ok": True, "changed": False, "status": mission["status"]}

    terminal = {"complete", "failed", "suspect"}
    active = {"pending", "dispatched", "running", "in_progress"}

    any_active = any(s in active for s in statuses)
    all_terminal = all(s in terminal for s in statuses)
    any_failed = any(s in ("failed", "suspect") for s in statuses)

    # Don't mark terminal if there are still active tasks
    if any_active:
        return {"ok": True, "changed": False, "status": "active"}

    # Check if any failed tasks still have retries left
    if any_failed:
        has_retryable = False
        for tid in task_ids:
            task = get_task(tid)
            if task and task.get("status") == "failed":
                if task.get("retry_count", 0) < task.get("max_retries", 3):
                    has_retryable = True
                    break
        if has_retryable:
            # Don't mark mission failed yet — retries are available
            return {"ok": True, "changed": False, "status": "active"}

    if all_terminal:
        if any_failed:
            mark_mission_status(mission_id, "failed")
            emit_event("mission_failed", mission_id=mission_id,
                       payload={"task_statuses": statuses})
            return {"ok": True, "changed": True, "status": "failed"}
        else:
            mark_mission_status(mission_id, "complete")
            emit_event("mission_completed", mission_id=mission_id,
                       payload={"task_count": len(statuses)})
            return {"ok": True, "changed": True, "status": "complete"}

    return {"ok": True, "changed": False, "status": mission["status"]}


def run_compaction_sweep() -> list[dict[str, Any]]:
    """
    Run compaction for all active missions that have recently completed tasks.
    Also check mission lifecycle for auto-completion.
    """
    from runtime.jb_missions import list_missions

    results = []
    missions = list_missions()

    for mission in missions:
        if mission["status"] not in ("active", "blocked"):
            continue

        mid = mission["mission_id"]
        task_ids = mission.get("task_ids", [])
        if not task_ids:
            continue

        # Check lifecycle first
        lifecycle = check_mission_lifecycle(mid)
        results.append({"mission_id": mid, "action": "lifecycle", **lifecycle})

        # Compact if there are completed tasks
        has_completed = any(
            (t := get_task(tid)) is not None and t.get("status") == "complete"
            for tid in task_ids
        )
        if has_completed and lifecycle.get("status") in ("active", "complete"):
            compact = compact_mission(mid)
            results.append({"mission_id": mid, "action": "compact", **compact})

    return results


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="JBCP Compaction Agent")
    parser.add_argument("--mission-id", help="Compact a specific mission")
    parser.add_argument("--sweep", action="store_true", help="Sweep all active missions")
    parser.add_argument("--lifecycle-only", action="store_true", help="Only check lifecycle, no compaction")
    args = parser.parse_args()

    if args.mission_id:
        if args.lifecycle_only:
            result = check_mission_lifecycle(args.mission_id)
        else:
            result = compact_mission(args.mission_id)
        print(json.dumps(result, default=str), flush=True)
    elif args.sweep:
        if args.lifecycle_only:
            from runtime.jb_missions import list_missions
            for m in list_missions():
                if m["status"] in ("active", "blocked"):
                    result = check_mission_lifecycle(m["mission_id"])
                    print(json.dumps({"mission_id": m["mission_id"], **result}, default=str), flush=True)
        else:
            results = run_compaction_sweep()
            for r in results:
                print(json.dumps(r, default=str), flush=True)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
