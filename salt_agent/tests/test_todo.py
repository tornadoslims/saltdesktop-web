"""Tests for the TodoWriteTool."""

import pytest

from salt_agent.tools.todo import TodoWriteTool


class TestTodoWriteCreate:
    def test_create_tasks(self):
        tool = TodoWriteTool()
        result = tool.execute(tasks=[
            {"content": "Write tests", "status": "pending"},
            {"content": "Fix bug", "status": "in_progress"},
        ])
        assert "updated" in result.lower()
        assert len(tool.tasks) == 2

    def test_replace_all_semantics(self):
        tool = TodoWriteTool()
        tool.execute(tasks=[
            {"content": "Old task 1", "status": "pending"},
            {"content": "Old task 2", "status": "pending"},
        ])
        assert len(tool.tasks) == 2

        # Replace with new list
        tool.execute(tasks=[
            {"content": "New task only", "status": "in_progress"},
        ])
        assert len(tool.tasks) == 1
        assert tool.tasks[0]["content"] == "New task only"

    def test_empty_tasks_clears_list(self):
        tool = TodoWriteTool()
        tool.execute(tasks=[{"content": "Something", "status": "pending"}])
        assert len(tool.tasks) == 1
        tool.execute(tasks=[])
        assert len(tool.tasks) == 0


class TestTodoWriteStatusTracking:
    def test_status_counts_in_result(self):
        tool = TodoWriteTool()
        result = tool.execute(tasks=[
            {"content": "A", "status": "completed"},
            {"content": "B", "status": "completed"},
            {"content": "C", "status": "in_progress"},
            {"content": "D", "status": "pending"},
            {"content": "E", "status": "pending"},
            {"content": "F", "status": "pending"},
        ])
        assert "2 done" in result
        assert "1 in progress" in result
        assert "3 pending" in result

    def test_default_status_is_pending(self):
        tool = TodoWriteTool()
        tool.execute(tasks=[{"content": "No status given"}])
        assert tool.tasks[0]["status"] == "pending"

    def test_all_statuses(self):
        tool = TodoWriteTool()
        tool.execute(tasks=[
            {"content": "A", "status": "pending"},
            {"content": "B", "status": "in_progress"},
            {"content": "C", "status": "completed"},
        ])
        statuses = [t["status"] for t in tool.tasks]
        assert "pending" in statuses
        assert "in_progress" in statuses
        assert "completed" in statuses


class TestTodoWriteContextInjection:
    def test_context_injection_format(self):
        tool = TodoWriteTool()
        tool.execute(tasks=[
            {"content": "Write tests", "status": "pending"},
            {"content": "Run tests", "status": "in_progress"},
            {"content": "Deploy", "status": "completed"},
        ])
        injection = tool.get_context_injection()
        assert "## Current Tasks" in injection
        assert "Write tests" in injection
        assert "Run tests" in injection
        assert "Deploy" in injection

    def test_empty_tasks_no_injection(self):
        tool = TodoWriteTool()
        injection = tool.get_context_injection()
        assert injection == ""

    def test_injection_has_status_icons(self):
        tool = TodoWriteTool()
        tool.execute(tasks=[
            {"content": "Pending task", "status": "pending"},
            {"content": "Active task", "status": "in_progress"},
            {"content": "Done task", "status": "completed"},
        ])
        injection = tool.get_context_injection()
        # Check for unicode status icons
        assert "\u25cb" in injection  # pending circle
        assert "\u25d0" in injection  # in_progress half circle
        assert "\u2713" in injection  # completed check


class TestTodoWriteDefinition:
    def test_definition_name(self):
        tool = TodoWriteTool()
        defn = tool.definition()
        assert defn.name == "todo_write"

    def test_definition_has_tasks_param(self):
        tool = TodoWriteTool()
        defn = tool.definition()
        param_names = [p.name for p in defn.params]
        assert "tasks" in param_names

    def test_tasks_param_is_required(self):
        tool = TodoWriteTool()
        defn = tool.definition()
        tasks_param = [p for p in defn.params if p.name == "tasks"][0]
        assert tasks_param.required is True
        assert tasks_param.type == "array"
