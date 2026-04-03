# tests/test_labels.py

import pytest

from runtime.jb_labels import (
    MISSION_PHASE_LABELS,
    SERVICE_STATUS_LABELS,
    COMPONENT_DISPLAY_STATUS,
    WORKER_ROLE_LABELS,
    COMPONENT_TYPE_ICONS,
    mission_label,
    service_label,
    component_label,
    worker_role,
    component_icon,
)


# ---------------------------------------------------------------------------
# mission_label
# ---------------------------------------------------------------------------

class TestMissionLabel:
    @pytest.mark.parametrize("status,expected", list(MISSION_PHASE_LABELS.items()))
    def test_known_statuses(self, status, expected):
        assert mission_label(status) == expected

    def test_unknown_status_titlecased(self):
        assert mission_label("waiting_for_approval") == "Waiting For Approval"

    def test_unknown_simple(self):
        assert mission_label("mystery") == "Mystery"


# ---------------------------------------------------------------------------
# service_label
# ---------------------------------------------------------------------------

class TestServiceLabel:
    @pytest.mark.parametrize("status,expected", list(SERVICE_STATUS_LABELS.items()))
    def test_known_statuses(self, status, expected):
        assert service_label(status) == expected

    def test_unknown_status_titlecased(self):
        assert service_label("degraded") == "Degraded"

    def test_unknown_underscore(self):
        assert service_label("health_check_failed") == "Health Check Failed"


# ---------------------------------------------------------------------------
# component_label
# ---------------------------------------------------------------------------

class TestComponentLabel:
    @pytest.mark.parametrize("status,expected", list(COMPONENT_DISPLAY_STATUS.items()))
    def test_known_statuses(self, status, expected):
        assert component_label(status) == expected

    def test_unknown_status_titlecased(self):
        assert component_label("archived") == "Archived"

    def test_passing_collapses_to_built(self):
        """passing and built both display as 'Built' (CEO mode collapse)."""
        assert component_label("passing") == "Built"
        assert component_label("built") == "Built"

    def test_failing_shows_problem(self):
        assert component_label("failing") == "Problem"


# ---------------------------------------------------------------------------
# worker_role
# ---------------------------------------------------------------------------

class TestWorkerRole:
    @pytest.mark.parametrize("task_type,expected", list(WORKER_ROLE_LABELS.items()))
    def test_known_roles(self, task_type, expected):
        result = worker_role(task_type)
        assert result["label"] == expected["label"]
        assert result["icon"] == expected["icon"]

    def test_unknown_role_returns_default(self):
        result = worker_role("deployment")
        assert result == {"label": "Worker", "icon": "gear"}

    def test_unknown_role_has_both_keys(self):
        result = worker_role("some_new_type")
        assert "label" in result
        assert "icon" in result


# ---------------------------------------------------------------------------
# component_icon
# ---------------------------------------------------------------------------

class TestComponentIcon:
    @pytest.mark.parametrize("comp_type,expected", list(COMPONENT_TYPE_ICONS.items()))
    def test_known_types(self, comp_type, expected):
        assert component_icon(comp_type) == expected

    def test_unknown_type_returns_gear(self):
        assert component_icon("widget") == "gear"

    def test_unknown_type_does_not_crash(self):
        assert isinstance(component_icon(""), str)
