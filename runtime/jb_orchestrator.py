from __future__ import annotations

import time
import argparse
import logging

from runtime.jb_common import LOG_DIR
from runtime.jb_queue import get_pending, get_running, get_dispatched, get_retryable, retry_task, mark_complete, mark_failed
from runtime.jb_events import emit_event
from runtime.jb_builder import build_component_sync
from runtime.jb_compaction import check_mission_lifecycle, compact_mission

ORCHESTRATOR_LOG = LOG_DIR / "orchestrator.log"


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("jb_orchestrator")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(ORCHESTRATOR_LOG)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# ---------------------------------------------------------------------------
# Phase 1: Dispatch — pick up pending tasks and build via Claude Code
# ---------------------------------------------------------------------------

def dispatch_pending(logger: logging.Logger) -> set[str]:
    """Dispatch pending tasks via Claude Code builder. Returns set of mission IDs that had tasks complete."""
    from runtime.jb_components import get_component, list_components
    from runtime.jb_missions import get_mission

    tasks = get_pending()
    completed_missions: set[str] = set()
    if not tasks:
        return completed_missions

    print(f"  Dispatch: {len(tasks)} pending task(s)", flush=True)

    for task in tasks:
        task_id = task.get("id")
        task_type = task.get("type", "unknown")
        goal = task.get("payload", {}).get("goal", "")

        print(f"    -> {task_id} ({task_type}) -- {goal[:80]}", flush=True)
        logger.info("dispatching | id=%s | type=%s", task_id, task_type)

        try:
            # Resolve component and mission for this task
            mission_id = task.get("mission_id")
            mission = get_mission(mission_id) if mission_id else {}
            if not mission:
                mission = {"goal": ""}

            comp_name = task.get("payload", {}).get("component", "")
            component_id = task.get("payload", {}).get("component_id", "")
            component = None

            if component_id:
                component = get_component(component_id)
            if not component and comp_name and mission.get("company_id"):
                components = list_components(workspace_id=mission["company_id"])
                for c in components:
                    if c.get("name") == comp_name or c.get("name", "").lower() == comp_name.lower():
                        component = c
                        break

            if not component:
                component = {
                    "name": comp_name or "unknown",
                    "type": "processor",
                    "component_id": component_id or "",
                    "contract": {},
                }

            result = build_component_sync(task, component, mission)
            outcome = result.get("status", "failed")

            if outcome == "complete":
                print(f"      [ok] completed -- {result.get('lines', '?')} lines", flush=True)
                logger.info("completed | id=%s | lines=%s", task_id, result.get("lines"))
                if task.get("mission_id"):
                    completed_missions.add(task["mission_id"])
            else:
                error = result.get("error", "unknown")
                print(f"      [fail] -- {error[:120]}", flush=True)
                logger.error("failed | id=%s | error=%s", task_id, error[:200])

        except Exception as e:
            logger.exception("dispatch error | id=%s | error=%s", task_id, e)
            print(f"      [fail] dispatch error: {e}", flush=True)
            emit_event(
                "task_dispatch_error",
                mission_id=task.get("mission_id"),
                task_id=task_id,
                payload={"error": str(e)},
            )

    return completed_missions


# ---------------------------------------------------------------------------
# Phase 2: Reconcile — check on running/dispatched tasks
# ---------------------------------------------------------------------------

def reconcile_running(logger: logging.Logger) -> None:
    """Reconcile running/dispatched tasks.

    With the Claude Code builder, tasks complete synchronously so there
    shouldn't normally be lingering running tasks. But if a previous
    orchestrator run crashed mid-build, tasks may be stuck.  We check
    whether the component directory has a main.py and reconcile accordingly.
    """
    from runtime.jb_common import BASE_DIR

    tasks = get_running() + get_dispatched()
    if not tasks:
        return

    print(f"  Reconcile: {len(tasks)} running/dispatched task(s)", flush=True)

    for task in tasks:
        task_id = task.get("id")
        status = task.get("status")
        comp_name = task.get("payload", {}).get("component", "")

        print(f"    Checking: {task_id} ({status}) component={comp_name}", flush=True)
        logger.info("reconcile check | id=%s | component=%s", task_id, comp_name)

        try:
            # Check if the component was actually built (files exist)
            if comp_name:
                from runtime.jb_builder import _slugify, COMPONENTS_DIR
                comp_dir = COMPONENTS_DIR / _slugify(comp_name)
                main_py = comp_dir / "main.py"

                if main_py.exists():
                    mark_complete(task_id)
                    emit_event(
                        "task_completed",
                        mission_id=task.get("mission_id"),
                        task_id=task_id,
                        payload={"reconciled": True, "reason": "main.py found"},
                    )
                    print(f"      [ok] reconciled as complete (files exist)", flush=True)
                    logger.info("reconciled complete | id=%s", task_id)
                else:
                    # No files -- likely a crashed build, mark failed
                    mark_failed(task_id, error="Build appears to have crashed (no main.py)")
                    emit_event(
                        "task_failed",
                        mission_id=task.get("mission_id"),
                        task_id=task_id,
                        payload={"reconciled": True, "reason": "no_files"},
                    )
                    print(f"      [fail] reconciled as failed (no files)", flush=True)
                    logger.info("reconciled failed | id=%s", task_id)
            else:
                # No component name -- can't check, leave as-is
                print(f"    ? no component name, skipping", flush=True)
                logger.warning("reconcile skip | id=%s | no component name", task_id)

        except Exception as e:
            logger.exception("reconcile error | id=%s | error=%s", task_id, e)
            print(f"      [fail] reconcile error: {e}", flush=True)


# ---------------------------------------------------------------------------
# Phase 3: Retry — requeue failed tasks that have retries left
# ---------------------------------------------------------------------------

def retry_failed(logger: logging.Logger) -> None:
    retryable = get_retryable()
    if not retryable:
        return

    print(f"  Retry: {len(retryable)} retryable task(s)", flush=True)

    for task in retryable:
        task_id = task.get("id")
        retry_count = task.get("retry_count", 0)
        max_retries = task.get("max_retries", 3)

        print(f"    ↻ {task_id[:12]}... retry {retry_count}/{max_retries}", flush=True)
        logger.info("retrying | id=%s | attempt=%s/%s", task_id, retry_count, max_retries)

        try:
            retry_task(task_id)
            emit_event(
                "task_retried",
                mission_id=task.get("mission_id"),
                task_id=task_id,
                payload={"retry_count": retry_count, "max_retries": max_retries},
            )
        except Exception as e:
            logger.error("retry failed | id=%s | error=%s", task_id, e)
            print(f"    ✗ retry error: {e}", flush=True)


# ---------------------------------------------------------------------------
# Phase 4: Lifecycle — check missions for auto-completion, trigger compaction
# ---------------------------------------------------------------------------

def check_lifecycles(logger: logging.Logger) -> None:
    from runtime.jb_missions import list_missions

    missions = list_missions()
    active = [m for m in missions if m.get("status") in ("active", "blocked")]
    if not active:
        return

    for mission in active:
        mid = mission["mission_id"]
        result = check_mission_lifecycle(mid)
        if result.get("changed"):
            new_status = result.get("status")
            print(f"  Lifecycle: {mid[:12]}... → {new_status}", flush=True)
            logger.info("lifecycle | id=%s | status=%s", mid, new_status)


# ---------------------------------------------------------------------------
# Phase 5: Compact — update mission context for missions with completed tasks
# ---------------------------------------------------------------------------

def compact_completed(mission_ids: set[str], logger: logging.Logger) -> None:
    if not mission_ids:
        return

    print(f"  Compact: {len(mission_ids)} mission(s) with newly completed tasks", flush=True)

    for mid in mission_ids:
        try:
            result = compact_mission(mid)
            if result.get("ok"):
                print(f"    ✓ compacted: {mid[:12]}...", flush=True)
                logger.info("compacted | mission=%s", mid)
            else:
                print(f"    ✗ compact failed: {mid[:12]}... — {result.get('error', '?')[:80]}", flush=True)
                logger.error("compact failed | mission=%s | error=%s", mid, result.get("error"))
        except Exception as e:
            logger.error("compact error | mission=%s | error=%s", mid, e)
            print(f"    ✗ compact error: {e}", flush=True)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_once(logger: logging.Logger) -> None:
    pending = len(get_pending())
    running = len(get_running()) + len(get_dispatched())
    retryable = len(get_retryable())

    print(f"JBCP Orchestrator: {pending} pending, {running} running/dispatched, {retryable} retryable", flush=True)
    logger.info("run_once | pending=%s | running=%s | retryable=%s", pending, running, retryable)

    retry_failed(logger)
    completed_missions = dispatch_pending(logger)
    reconcile_running(logger)
    check_lifecycles(logger)
    compact_completed(completed_missions, logger)


def main() -> None:
    parser = argparse.ArgumentParser(description="JBCP Orchestrator")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds")
    args = parser.parse_args()

    logger = setup_logging()

    print("JBCP Orchestrator started", flush=True)
    logger.info("started | once=%s | interval=%s", args.once, args.interval)

    if args.once:
        run_once(logger)
        return

    while True:
        try:
            run_once(logger)
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nJBCP Orchestrator stopped", flush=True)
            break
        except Exception as e:
            logger.exception("orchestrator loop error: %s", e)
            print(f"Orchestrator error: {e}", flush=True)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
