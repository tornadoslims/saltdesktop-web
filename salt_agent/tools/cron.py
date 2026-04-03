"""Cron tools -- schedule, list, and cancel recurring/one-shot tasks.

Provides CronCreateTool, CronDeleteTool, and CronListTool for scheduling
commands to run on cron-like schedules within the agent session.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

if TYPE_CHECKING:
    from salt_agent.tasks.manager import TaskManager


# ---------------------------------------------------------------------------
# Shared cron schedule store
# ---------------------------------------------------------------------------

@dataclass
class CronJob:
    id: str
    cron: str
    prompt: str
    recurring: bool = True
    created_at: str = ""
    next_fire: str = ""


class CronStore:
    """In-memory store for cron jobs (session-scoped)."""

    def __init__(self) -> None:
        self._jobs: dict[str, CronJob] = {}

    def add(self, cron: str, prompt: str, recurring: bool = True) -> CronJob:
        job = CronJob(
            id=str(uuid.uuid4())[:8],
            cron=cron,
            prompt=prompt,
            recurring=recurring,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        human = _cron_to_human(cron)
        job.next_fire = human
        self._jobs[job.id] = job
        return job

    def remove(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None

    def get(self, job_id: str) -> CronJob | None:
        return self._jobs.get(job_id)

    def list_all(self) -> list[CronJob]:
        return list(self._jobs.values())

    def count(self) -> int:
        return len(self._jobs)


# Singleton store (session-scoped)
_store = CronStore()

MAX_JOBS = 50


def _cron_to_human(expr: str) -> str:
    """Convert a 5-field cron expression to a rough human-readable string."""
    parts = expr.strip().split()
    if len(parts) != 5:
        return expr

    minute, hour, dom, month, dow = parts

    if expr == "* * * * *":
        return "every minute"
    if minute.startswith("*/"):
        n = minute[2:]
        return f"every {n} minutes"
    if hour.startswith("*/"):
        n = hour[2:]
        return f"every {n} hours"
    if minute != "*" and hour != "*" and dom == "*" and month == "*" and dow == "*":
        return f"daily at {hour.zfill(2)}:{minute.zfill(2)}"
    if minute != "*" and hour != "*" and dow != "*" and dom == "*" and month == "*":
        days = {"0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed",
                "4": "Thu", "5": "Fri", "6": "Sat", "7": "Sun"}
        day_name = days.get(dow, dow)
        return f"every {day_name} at {hour.zfill(2)}:{minute.zfill(2)}"

    return f"cron({expr})"


def _validate_cron(expr: str) -> str | None:
    """Validate a 5-field cron expression. Returns error message or None."""
    parts = expr.strip().split()
    if len(parts) != 5:
        return f"Expected 5 fields (M H DoM Mon DoW), got {len(parts)}."

    ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
    names = ["minute", "hour", "day-of-month", "month", "day-of-week"]

    for i, (part, (lo, hi), name) in enumerate(zip(parts, ranges, names)):
        # Handle */N
        if part.startswith("*/"):
            try:
                n = int(part[2:])
                if n < 1:
                    return f"Invalid step value in {name}: {part}"
            except ValueError:
                return f"Invalid step value in {name}: {part}"
            continue
        if part == "*":
            continue
        # Handle comma-separated values
        for val in part.split(","):
            # Handle ranges like 1-5
            if "-" in val:
                try:
                    a, b = val.split("-", 1)
                    a, b = int(a), int(b)
                    if a < lo or b > hi or a > b:
                        return f"Range {val} out of bounds for {name} ({lo}-{hi})."
                except ValueError:
                    return f"Invalid range in {name}: {val}"
            else:
                try:
                    v = int(val)
                    if v < lo or v > hi:
                        return f"Value {v} out of bounds for {name} ({lo}-{hi})."
                except ValueError:
                    return f"Invalid value in {name}: {val}"
    return None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class CronCreateTool(Tool):
    """Schedule a command to run on a cron schedule."""

    def __init__(self, task_manager: TaskManager | None = None) -> None:
        self._tasks = task_manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="cron_create",
            description=(
                "Schedule a prompt to run on a cron schedule. "
                "Uses standard 5-field cron expressions: M H DoM Mon DoW "
                '(e.g. "*/5 * * * *" = every 5 min, "30 9 * * 1-5" = weekdays at 9:30). '
                "Set recurring=false for one-shot tasks that fire once then auto-delete. "
                "Jobs are session-scoped (lost when the agent exits)."
            ),
            params=[
                ToolParam("cron", "string", 'Standard 5-field cron expression: "M H DoM Mon DoW"'),
                ToolParam("prompt", "string", "The prompt to run at each fire time"),
                ToolParam(
                    "recurring", "boolean",
                    "true (default) = fire on every match; false = fire once then delete",
                    required=False,
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        cron_expr = kwargs.get("cron", "")
        prompt = kwargs.get("prompt", "")
        recurring = kwargs.get("recurring", True)

        if not cron_expr:
            return "Error: cron expression is required."
        if not prompt:
            return "Error: prompt is required."

        err = _validate_cron(cron_expr)
        if err:
            return f"Error: Invalid cron expression '{cron_expr}'. {err}"

        if _store.count() >= MAX_JOBS:
            return f"Error: Too many scheduled jobs (max {MAX_JOBS}). Cancel one first."

        job = _store.add(cron_expr, prompt, recurring)
        kind = "recurring" if recurring else "one-shot"
        human = _cron_to_human(cron_expr)
        return (
            f"Scheduled {kind} job {job.id} ({human}).\n"
            f"Session-only — the job is lost when the agent exits.\n"
            f"Use cron_delete to cancel."
        )


class CronDeleteTool(Tool):
    """Cancel a scheduled cron job."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="cron_delete",
            description="Cancel a scheduled cron job by its ID.",
            params=[
                ToolParam("id", "string", "Job ID returned by cron_create"),
            ],
        )

    def execute(self, **kwargs) -> str:
        job_id = kwargs.get("id", "")
        if not job_id:
            return "Error: id is required."
        if _store.remove(job_id):
            return f"Cancelled job {job_id}."
        return f"Error: No scheduled job with id '{job_id}'."


class CronListTool(Tool):
    """List all active cron jobs."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="cron_list",
            description="List all active scheduled cron jobs.",
            params=[],
        )

    def execute(self, **kwargs) -> str:
        jobs = _store.list_all()
        if not jobs:
            return "No scheduled jobs."
        lines = []
        for j in jobs:
            kind = "recurring" if j.recurring else "one-shot"
            human = _cron_to_human(j.cron)
            lines.append(f"[{j.id}] {human} ({kind}) — {j.prompt[:80]}")
        return "\n".join(lines)
