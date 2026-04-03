"""Tests for jb_ceo_translator — CEO-mode signal & task translation."""
from __future__ import annotations

import pytest

from runtime.jb_ceo_translator import (
    CeoActivity,
    translate_signal,
    translate_task_status,
    _resolve_component_name,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

COMPONENT_A = {
    "component_id": "comp-aaa",
    "name": "Email Parser",
    "type": "processor",
    "status": "building",
}

COMPONENT_B = {
    "component_id": "comp-bbb",
    "name": "Slack Connector",
    "type": "connector",
    "status": "planned",
}

TASK_A = {
    "id": "task-111",
    "status": "running",
    "component_id": "comp-aaa",
    "openclaw_session_id": "sess-1",
    "payload": {"goal": "build email parser"},
}

TASK_B = {
    "id": "task-222",
    "status": "pending",
    "payload": {"goal": "build slack connector", "component_id": "comp-bbb"},
    "openclaw_session_id": "sess-2",
}

TASK_LOOKUP = {
    "sess-1": TASK_A,
    "sess-2": TASK_B,
}

COMPONENT_LOOKUP = {
    "comp-aaa": COMPONENT_A,
    "comp-bbb": COMPONENT_B,
}


# ---------------------------------------------------------------------------
# _resolve_component_name
# ---------------------------------------------------------------------------

class TestResolveComponentName:
    def test_full_chain(self):
        signal = {"session_id": "sess-1"}
        assert _resolve_component_name(signal, TASK_LOOKUP, COMPONENT_LOOKUP) == "Email Parser"

    def test_component_id_in_payload(self):
        signal = {"session_id": "sess-2"}
        assert _resolve_component_name(signal, TASK_LOOKUP, COMPONENT_LOOKUP) == "Slack Connector"

    def test_no_task_lookup(self):
        signal = {"session_id": "sess-1"}
        assert _resolve_component_name(signal, None, COMPONENT_LOOKUP) is None

    def test_no_component_lookup(self):
        signal = {"session_id": "sess-1"}
        assert _resolve_component_name(signal, TASK_LOOKUP, None) is None

    def test_unknown_session(self):
        signal = {"session_id": "sess-unknown"}
        assert _resolve_component_name(signal, TASK_LOOKUP, COMPONENT_LOOKUP) is None

    def test_no_session_id(self):
        signal = {"signal": "tool_start"}
        assert _resolve_component_name(signal, TASK_LOOKUP, COMPONENT_LOOKUP) is None

    def test_task_without_component_id(self):
        task_lookup = {"sess-x": {"id": "task-x", "status": "running", "payload": {}}}
        signal = {"session_id": "sess-x"}
        assert _resolve_component_name(signal, task_lookup, COMPONENT_LOOKUP) is None

    def test_component_not_in_lookup(self):
        task_lookup = {"sess-x": {"id": "task-x", "component_id": "comp-missing", "payload": {}}}
        signal = {"session_id": "sess-x"}
        assert _resolve_component_name(signal, task_lookup, COMPONENT_LOOKUP) is None

    def test_empty_lookups(self):
        signal = {"session_id": "sess-1"}
        assert _resolve_component_name(signal, {}, {}) is None


# ---------------------------------------------------------------------------
# translate_signal — tool_start rules
# ---------------------------------------------------------------------------

class TestTranslateSignalToolStart:
    def test_write_label(self):
        signal = {"signal": "tool_start", "label": "write file", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "building"
        assert result.icon == "hammer"
        assert "Writing" in result.text
        assert result.component_name == "Email Parser"

    def test_edit_label(self):
        signal = {"signal": "tool_start", "label": "Edit code", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "building"
        assert "Writing" in result.text

    def test_write_no_component(self):
        signal = {"signal": "tool_start", "label": "write", "session_id": "sess-unknown"}
        result = translate_signal(signal)
        assert result.category == "building"
        assert result.text == "Writing"
        assert result.component_name is None

    def test_pytest_label(self):
        signal = {"signal": "tool_start", "label": "pytest tests/", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "testing"
        assert result.icon == "magnifier"
        assert "tests" in result.text.lower()

    def test_test_label(self):
        signal = {"signal": "tool_start", "label": "run test suite", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "testing"

    def test_read_label(self):
        signal = {"signal": "tool_start", "label": "Read file", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "reading"
        assert "Reviewing" in result.text

    def test_web_source(self):
        signal = {"signal": "tool_start", "source": "web", "label": "fetch", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "reading"
        assert result.text == "Researching"

    def test_http_source(self):
        signal = {"signal": "tool_start", "source": "http", "label": "fetch", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "reading"

    def test_http_in_label(self):
        signal = {"signal": "tool_start", "label": "http request to api", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "reading"
        assert result.text == "Researching"

    def test_tool_name_fallback_for_label(self):
        """When label is missing, falls back to tool name."""
        signal = {"signal": "tool_start", "tool": "write", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "building"
        assert "Writing" in result.text

    def test_unknown_tool_start_falls_through(self):
        """tool_start with unrecognized label falls to generic fallback."""
        signal = {"signal": "tool_start", "label": "some_custom_tool", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "building"
        assert result.component_name == "Email Parser"


# ---------------------------------------------------------------------------
# translate_signal — other signal types
# ---------------------------------------------------------------------------

class TestTranslateSignalOther:
    def test_llm_input(self):
        signal = {"signal": "llm_input", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "thinking"
        assert result.icon == "brain"
        assert result.text == "Thinking..."

    def test_tool_end_with_error(self):
        signal = {"signal": "tool_end", "error": "file not found", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "error"
        assert result.icon == "warning"
        assert "issue" in result.text.lower()

    def test_tool_end_no_error(self):
        """tool_end without error falls to generic fallback."""
        signal = {"signal": "tool_end", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        # Should not be error category
        assert result.category == "building"
        assert result.component_name == "Email Parser"

    def test_subagent_spawned(self):
        signal = {"signal": "subagent_spawned", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.category == "building"
        assert "worker" in result.text.lower()

    def test_fallback_with_component(self):
        signal = {"signal": "agent_turn", "session_id": "sess-1"}
        result = translate_signal(signal, TASK_LOOKUP, COMPONENT_LOOKUP)
        assert result.text == "Working on Email Parser"
        assert result.component_name == "Email Parser"

    def test_fallback_no_component(self):
        signal = {"signal": "agent_turn", "session_id": "sess-unknown"}
        result = translate_signal(signal)
        assert result.text == "AI is active"
        assert result.component_name is None
        assert result.icon == "hammer"

    def test_empty_signal(self):
        result = translate_signal({})
        assert result.text == "AI is active"
        assert result.category == "building"


# ---------------------------------------------------------------------------
# translate_signal — priority / ordering
# ---------------------------------------------------------------------------

class TestTranslateSignalPriority:
    def test_web_source_beats_write_label(self):
        """Web source should take priority over write in the label."""
        signal = {"signal": "tool_start", "source": "web", "label": "write to api"}
        result = translate_signal(signal)
        assert result.category == "reading"
        assert result.text == "Researching"

    def test_write_beats_read(self):
        """If label contains both 'write' and 'read', write wins (checked first)."""
        signal = {"signal": "tool_start", "label": "write after read"}
        result = translate_signal(signal)
        assert result.category == "building"


# ---------------------------------------------------------------------------
# translate_task_status
# ---------------------------------------------------------------------------

class TestTranslateTaskStatus:
    def test_complete_with_component(self):
        task = {"status": "complete"}
        result = translate_task_status(task, COMPONENT_A)
        assert result.category == "building"
        assert result.icon == "check"
        assert "Finished" in result.text
        assert "Email Parser" in result.text
        assert result.component_name == "Email Parser"

    def test_complete_no_component(self):
        task = {"status": "complete"}
        result = translate_task_status(task)
        assert result.icon == "check"
        assert result.text == "Finished building"
        assert result.component_name is None

    def test_failed_with_component(self):
        task = {"status": "failed"}
        result = translate_task_status(task, COMPONENT_A)
        assert result.category == "error"
        assert result.icon == "warning"
        assert "Email Parser" in result.text
        assert "attention" in result.text

    def test_failed_no_component(self):
        task = {"status": "failed"}
        result = translate_task_status(task)
        assert "A task" in result.text
        assert result.icon == "warning"

    def test_running(self):
        task = {"status": "running"}
        result = translate_task_status(task, COMPONENT_B)
        assert result.category == "building"
        assert result.icon == "hammer"
        assert "Started" in result.text
        assert "Slack Connector" in result.text

    def test_dispatched(self):
        task = {"status": "dispatched"}
        result = translate_task_status(task, COMPONENT_A)
        assert result.icon == "hammer"
        assert "Started" in result.text

    def test_in_progress(self):
        task = {"status": "in_progress"}
        result = translate_task_status(task, COMPONENT_A)
        assert result.icon == "hammer"

    def test_pending(self):
        task = {"status": "pending"}
        result = translate_task_status(task, COMPONENT_B)
        assert result.icon == "clock"
        assert "Slack Connector" in result.text
        assert "queued" in result.text

    def test_pending_no_component(self):
        task = {"status": "pending"}
        result = translate_task_status(task)
        assert result.text == "A task queued"
        assert result.icon == "clock"

    def test_suspect_status(self):
        task = {"status": "suspect"}
        result = translate_task_status(task, COMPONENT_A)
        assert result.icon == "clock"
        assert "queued" in result.text

    def test_no_status_defaults_to_pending(self):
        task = {}
        result = translate_task_status(task, COMPONENT_A)
        assert result.icon == "clock"


# ---------------------------------------------------------------------------
# CeoActivity dataclass
# ---------------------------------------------------------------------------

class TestCeoActivity:
    def test_fields(self):
        a = CeoActivity(text="hello", category="building", component_name="X", icon="hammer")
        assert a.text == "hello"
        assert a.category == "building"
        assert a.component_name == "X"
        assert a.icon == "hammer"

    def test_none_component(self):
        a = CeoActivity(text="hi", category="thinking", component_name=None, icon="brain")
        assert a.component_name is None

    def test_equality(self):
        a = CeoActivity("t", "c", None, "i")
        b = CeoActivity("t", "c", None, "i")
        assert a == b
