# runtime/jb_labels.py
#
# Single source of truth for all user-facing label translations.
# The frontend consumes these via the API to display human-friendly
# status names, icons, and role labels.

from __future__ import annotations

MISSION_PHASE_LABELS = {
    "planning": "Planning",
    "planned": "Ready to Build",
    "active": "Building",
    "complete": "Ready to Deploy",
    "deployed": "Running",
    "failed": "Failed",
    "cancelled": "Cancelled",
}

SERVICE_STATUS_LABELS = {
    "running": "Healthy",
    "paused": "Paused",
    "stopped": "Stopped",
    "error": "Problem",
}

COMPONENT_DISPLAY_STATUS = {
    "planned": "Planned",
    "building": "Building",
    "built": "Built",
    "testing": "Testing",
    "passing": "Built",       # collapse for CEO mode
    "failing": "Problem",
    "deployed": "Live",
}

WORKER_ROLE_LABELS = {
    "coding": {"label": "Coder", "icon": "hammer"},
    "research": {"label": "Researcher", "icon": "magnifier"},
    "document": {"label": "Writer", "icon": "pencil"},
    "analysis": {"label": "Analyst", "icon": "chart"},
}

COMPONENT_TYPE_ICONS = {
    "connector": "plug",
    "processor": "gear",
    "ai": "brain",
    "output": "arrow-right",
    "scheduler": "clock",
    "storage": "database",
    "config": "sliders",
}


def mission_label(status: str) -> str:
    """Return human-friendly mission phase label. Unknown statuses return titlecased input."""
    return MISSION_PHASE_LABELS.get(status, status.replace("_", " ").title())


def service_label(status: str) -> str:
    """Return human-friendly service status label."""
    return SERVICE_STATUS_LABELS.get(status, status.replace("_", " ").title())


def component_label(status: str) -> str:
    """Return human-friendly component display status."""
    return COMPONENT_DISPLAY_STATUS.get(status, status.replace("_", " ").title())


def worker_role(task_type: str) -> dict:
    """Return role dict with label and icon for a task type."""
    return WORKER_ROLE_LABELS.get(task_type, {"label": "Worker", "icon": "gear"})


def component_icon(comp_type: str) -> str:
    """Return icon name for a component type."""
    return COMPONENT_TYPE_ICONS.get(comp_type, "gear")
