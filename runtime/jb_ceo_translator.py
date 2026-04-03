"""
CEO-mode translator: converts raw signal events and task status changes
into human-readable activity text for the Salt Desktop frontend.

The CEO doesn't care about tool names or session IDs — they want to know
"what is the AI doing right now?" in plain English.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CeoActivity:
    text: str                      # "Writing the email parsing logic"
    category: str                  # "building" | "testing" | "thinking" | "reading" | "error"
    component_name: Optional[str]  # "Email Parser" or None
    icon: str                      # "hammer" | "magnifier" | "brain" | "check" | "warning"


# -- Internal helpers --------------------------------------------------------

def _resolve_component_name(
    signal: dict[str, Any],
    task_lookup: dict[str, dict[str, Any]] | None = None,
    component_lookup: dict[str, dict[str, Any]] | None = None,
) -> Optional[str]:
    """Resolve signal -> task -> component -> name chain.

    Chain: signal['session_id'] -> task_lookup[session_id] -> task['component_id']
           -> component_lookup[component_id] -> component['name']
    """
    if not task_lookup or not component_lookup:
        return None

    session_id = signal.get("session_id")
    if not session_id:
        return None

    task = task_lookup.get(session_id)
    if not task:
        return None

    # component_id can be top-level or inside payload
    comp_id = task.get("component_id") or (task.get("payload") or {}).get("component_id")
    if not comp_id:
        return None

    component = component_lookup.get(comp_id)
    if not component:
        return None

    return component.get("name")


# -- Signal translation ------------------------------------------------------

_ICON_MAP = {
    "building": "hammer",
    "testing": "magnifier",
    "thinking": "brain",
    "reading": "magnifier",
    "error": "warning",
}


def translate_signal(
    signal: dict[str, Any],
    task_lookup: dict[str, dict[str, Any]] | None = None,
    component_lookup: dict[str, dict[str, Any]] | None = None,
) -> CeoActivity:
    """Translate a raw signal into CEO-friendly activity text.

    task_lookup: {session_id: task_dict} -- maps signal sessions to tasks
    component_lookup: {component_id: component_dict} -- maps component IDs to components

    Translation rules (evaluated in order):
    - tool_start + label contains "write" or "edit" -> building
    - tool_start + label contains "pytest" or "test" -> testing
    - tool_start + label contains "read"            -> reading
    - tool_start + source="web" or "http"           -> reading (research)
    - llm_input                                     -> thinking
    - tool_end + error                              -> error
    - subagent_spawned                              -> building (new worker)
    - Fallback                                      -> building
    """
    comp_name = _resolve_component_name(signal, task_lookup, component_lookup)
    sig = signal.get("signal")

    if sig == "tool_start":
        label = (signal.get("label") or signal.get("tool") or "").lower()
        source = (signal.get("source") or "").lower()

        # Web / HTTP research
        if source in ("web", "http") or "http" in label:
            return CeoActivity(
                text="Researching",
                category="reading",
                component_name=comp_name,
                icon="magnifier",
            )

        # Writing / editing
        if "write" in label or "edit" in label:
            suffix = f" {comp_name}" if comp_name else ""
            return CeoActivity(
                text=f"Writing{suffix}",
                category="building",
                component_name=comp_name,
                icon="hammer",
            )

        # Testing
        if "pytest" in label or "test" in label:
            return CeoActivity(
                text="Running tests",
                category="testing",
                component_name=comp_name,
                icon="magnifier",
            )

        # Reading / reviewing
        if "read" in label:
            return CeoActivity(
                text="Reviewing code",
                category="reading",
                component_name=comp_name,
                icon="magnifier",
            )

    if sig == "llm_input":
        return CeoActivity(
            text="Thinking...",
            category="thinking",
            component_name=comp_name,
            icon="brain",
        )

    if sig == "tool_end":
        error = signal.get("error")
        if error:
            return CeoActivity(
                text="Hit an issue, retrying",
                category="error",
                component_name=comp_name,
                icon="warning",
            )

    if sig == "subagent_spawned":
        return CeoActivity(
            text="Starting a new worker",
            category="building",
            component_name=comp_name,
            icon="hammer",
        )

    # Fallback
    if comp_name:
        return CeoActivity(
            text=f"Working on {comp_name}",
            category="building",
            component_name=comp_name,
            icon="hammer",
        )

    return CeoActivity(
        text="AI is active",
        category="building",
        component_name=None,
        icon="hammer",
    )


# -- Task status translation -------------------------------------------------

def translate_task_status(
    task: dict[str, Any],
    component: dict[str, Any] | None = None,
) -> CeoActivity:
    """Translate a task status change into CEO-friendly text.

    - complete -> "Finished building {component_name}" / building / check
    - failed   -> "{component_name} needs attention"    / error   / warning
    - running  -> "Started building {component_name}"   / building / hammer
    - pending  -> "{component_name} queued"             / building / clock
    """
    comp_name = (component or {}).get("name")
    status = task.get("status", "pending")

    if status == "complete":
        suffix = f" {comp_name}" if comp_name else ""
        return CeoActivity(
            text=f"Finished building{suffix}",
            category="building",
            component_name=comp_name,
            icon="check",
        )

    if status == "failed":
        subject = comp_name if comp_name else "A task"
        return CeoActivity(
            text=f"{subject} needs attention",
            category="error",
            component_name=comp_name,
            icon="warning",
        )

    if status in ("running", "dispatched", "in_progress"):
        suffix = f" {comp_name}" if comp_name else ""
        return CeoActivity(
            text=f"Started building{suffix}",
            category="building",
            component_name=comp_name,
            icon="hammer",
        )

    # pending, suspect, needs_review, or anything else
    subject = comp_name if comp_name else "A task"
    return CeoActivity(
        text=f"{subject} queued",
        category="building",
        component_name=comp_name,
        icon="clock",
    )
