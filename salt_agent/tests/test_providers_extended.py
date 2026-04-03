"""Extended provider tests — format conversion, message conversion."""

import json

import pytest

from salt_agent.tools.base import ToolDefinition, ToolParam, ToolRegistry, Tool
from salt_agent.providers.openai_provider import OpenAIAdapter


# ---------------------------------------------------------------------------
# Helper tool classes for format tests
# ---------------------------------------------------------------------------

class DummyToolWithOptional(Tool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search",
            description="Search for something.",
            params=[
                ToolParam("query", "string", "Search query.", required=True),
                ToolParam("limit", "integer", "Max results.", required=False),
                ToolParam("case_sensitive", "boolean", "Case sensitive?", required=False),
            ],
        )

    def execute(self, **kwargs) -> str:
        return "ok"


class DummyToolWithEnum(Tool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="format_output",
            description="Format output in given style.",
            params=[
                ToolParam("style", "string", "Output format.", required=True, enum=["json", "yaml", "text"]),
                ToolParam("data", "string", "Data to format.", required=True),
            ],
        )

    def execute(self, **kwargs) -> str:
        return "ok"


# ---------------------------------------------------------------------------
# ToolRegistry format conversion
# ---------------------------------------------------------------------------

class TestToolRegistryAnthropicFormat:
    def test_basic_tool_format(self):
        reg = ToolRegistry()
        reg.register(DummyToolWithOptional())
        tools = reg.to_anthropic_tools()
        assert len(tools) == 1
        t = tools[0]
        assert t["name"] == "search"
        assert t["description"] == "Search for something."
        assert "input_schema" in t
        schema = t["input_schema"]
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "limit" in schema["properties"]
        # Only required params in required list
        assert "query" in schema["required"]
        assert "limit" not in schema["required"]
        assert "case_sensitive" not in schema["required"]

    def test_enum_param(self):
        reg = ToolRegistry()
        reg.register(DummyToolWithEnum())
        tools = reg.to_anthropic_tools()
        style_prop = tools[0]["input_schema"]["properties"]["style"]
        assert style_prop["enum"] == ["json", "yaml", "text"]

    def test_optional_params_not_required(self):
        reg = ToolRegistry()
        reg.register(DummyToolWithOptional())
        tools = reg.to_anthropic_tools()
        required = tools[0]["input_schema"]["required"]
        assert "query" in required
        assert "limit" not in required


class TestToolRegistryOpenAIFormat:
    def test_basic_tool_format(self):
        reg = ToolRegistry()
        reg.register(DummyToolWithOptional())
        tools = reg.to_openai_tools()
        assert len(tools) == 1
        t = tools[0]
        assert t["type"] == "function"
        func = t["function"]
        assert func["name"] == "search"
        assert func["description"] == "Search for something."
        params = func["parameters"]
        assert params["type"] == "object"
        assert "query" in params["properties"]
        assert "query" in params["required"]
        assert "limit" not in params["required"]

    def test_enum_param(self):
        reg = ToolRegistry()
        reg.register(DummyToolWithEnum())
        tools = reg.to_openai_tools()
        style_prop = tools[0]["function"]["parameters"]["properties"]["style"]
        assert style_prop["enum"] == ["json", "yaml", "text"]

    def test_multiple_tools(self):
        reg = ToolRegistry()
        reg.register(DummyToolWithOptional())
        reg.register(DummyToolWithEnum())
        anthropic = reg.to_anthropic_tools()
        openai = reg.to_openai_tools()
        assert len(anthropic) == 2
        assert len(openai) == 2


# ---------------------------------------------------------------------------
# OpenAI message conversion
# ---------------------------------------------------------------------------

class TestOpenAIMessageConversion:
    def test_convert_simple_text_message(self):
        msg = {"role": "user", "content": "hello world"}
        result = OpenAIAdapter._convert_message(msg)
        assert result == {"role": "user", "content": "hello world"}

    def test_convert_assistant_with_tool_use(self):
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me check."},
                {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "read",
                    "input": {"file_path": "/tmp/x.txt"},
                },
            ],
        }
        result = OpenAIAdapter._convert_message(msg)
        assert result["role"] == "assistant"
        assert result["content"] == "Let me check."
        assert len(result["tool_calls"]) == 1
        tc = result["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "read"
        assert json.loads(tc["function"]["arguments"]) == {"file_path": "/tmp/x.txt"}

    def test_convert_single_tool_result(self):
        msg = {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "file contents here"},
            ],
        }
        result = OpenAIAdapter._convert_message(msg)
        assert result["role"] == "tool"
        assert result["tool_call_id"] == "call_1"
        assert result["content"] == "file contents here"

    def test_convert_multiple_tool_results_returns_list(self):
        msg = {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "result1"},
                {"type": "tool_result", "tool_use_id": "call_2", "content": "result2"},
            ],
        }
        result = OpenAIAdapter._convert_message(msg)
        # When multiple tool results, returns a list
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["tool_call_id"] == "call_1"
        assert result[1]["tool_call_id"] == "call_2"

    def test_convert_assistant_text_only_blocks(self):
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Part 1"},
                {"type": "text", "text": "Part 2"},
            ],
        }
        result = OpenAIAdapter._convert_message(msg)
        assert result["role"] == "assistant"
        assert "Part 1" in result["content"]
        assert "Part 2" in result["content"]

    def test_convert_user_text_blocks(self):
        msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": "first part"},
                {"type": "text", "text": "second part"},
            ],
        }
        result = OpenAIAdapter._convert_message(msg)
        assert result["role"] == "user"
        assert "first part" in result["content"]
        assert "second part" in result["content"]

    def test_convert_non_string_content_fallback(self):
        msg = {"role": "user", "content": 12345}
        result = OpenAIAdapter._convert_message(msg)
        assert result["content"] == "12345"

    def test_convert_assistant_with_multiple_tool_uses(self):
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Doing two things."},
                {"type": "tool_use", "id": "c1", "name": "read", "input": {"file_path": "/a"}},
                {"type": "tool_use", "id": "c2", "name": "bash", "input": {"command": "ls"}},
            ],
        }
        result = OpenAIAdapter._convert_message(msg)
        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["function"]["name"] == "read"
        assert result["tool_calls"][1]["function"]["name"] == "bash"

    def test_convert_assistant_tool_use_no_text(self):
        msg = {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "c1", "name": "bash", "input": {"command": "pwd"}},
            ],
        }
        result = OpenAIAdapter._convert_message(msg)
        assert result["role"] == "assistant"
        assert "content" not in result or result.get("content") is None or result.get("content") == ""
        assert len(result["tool_calls"]) == 1
