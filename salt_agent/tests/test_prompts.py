"""Tests for the prompt system — loading, assembling, searching, adapting."""

import pytest

from salt_agent.prompts import (
    SYSTEM_PROMPT,
    PLAN_MODE_PROMPT,
    BUILD_MODE_PROMPT,
    VERIFICATION_PROMPT,
    EXPLORE_PROMPT,
    SUMMARIZATION_PROMPT,
    MEMORY_PROMPT,
    SECURITY_PROMPT,
    WORKER_PROMPT,
    GENERAL_PURPOSE_PROMPT,
    COMMIT_PROMPT,
    PR_CREATION_PROMPT,
    CODE_REVIEW_PROMPT,
    WEBFETCH_PROMPT,
    get_mode_prompt,
    assemble_system_prompt,
    get_all_fragments,
    get_all_agent_prompts,
    get_all_skills,
    get_all_tool_prompts,
    get_all_data,
    list_prompts,
    get_prompt,
    search_prompts,
)
from salt_agent.prompts.provider_adapters import (
    adapt_for_provider,
    get_tool_format_hints,
    get_response_style_hints,
)


# ---------------------------------------------------------------------------
# Curated prompt loading
# ---------------------------------------------------------------------------

class TestCuratedPrompts:
    def test_system_prompt_non_empty(self):
        assert SYSTEM_PROMPT
        assert len(SYSTEM_PROMPT) > 100

    def test_plan_mode_prompt_non_empty(self):
        assert PLAN_MODE_PROMPT
        assert len(PLAN_MODE_PROMPT) > 50

    def test_build_mode_prompt_non_empty(self):
        assert BUILD_MODE_PROMPT
        assert len(BUILD_MODE_PROMPT) > 50

    def test_verification_prompt_non_empty(self):
        assert VERIFICATION_PROMPT
        assert len(VERIFICATION_PROMPT) > 50

    def test_explore_prompt_non_empty(self):
        assert EXPLORE_PROMPT
        assert len(EXPLORE_PROMPT) > 50

    def test_summarization_prompt_non_empty(self):
        assert SUMMARIZATION_PROMPT
        assert len(SUMMARIZATION_PROMPT) > 50

    def test_memory_prompt_non_empty(self):
        assert MEMORY_PROMPT
        assert len(MEMORY_PROMPT) > 50

    def test_security_prompt_non_empty(self):
        assert SECURITY_PROMPT
        assert len(SECURITY_PROMPT) > 50

    def test_all_curated_prompts_are_strings(self):
        for p in [
            SYSTEM_PROMPT, PLAN_MODE_PROMPT, BUILD_MODE_PROMPT,
            VERIFICATION_PROMPT, EXPLORE_PROMPT, SUMMARIZATION_PROMPT,
            MEMORY_PROMPT, SECURITY_PROMPT, WORKER_PROMPT,
            GENERAL_PURPOSE_PROMPT, COMMIT_PROMPT, PR_CREATION_PROMPT,
            CODE_REVIEW_PROMPT, WEBFETCH_PROMPT,
        ]:
            assert isinstance(p, str)


# ---------------------------------------------------------------------------
# get_mode_prompt
# ---------------------------------------------------------------------------

class TestGetModePrompt:
    def test_default_mode(self):
        result = get_mode_prompt("default")
        assert result == SYSTEM_PROMPT

    def test_plan_mode(self):
        result = get_mode_prompt("plan")
        assert result == PLAN_MODE_PROMPT

    def test_build_mode(self):
        result = get_mode_prompt("build")
        assert result == BUILD_MODE_PROMPT

    def test_verify_mode(self):
        result = get_mode_prompt("verify")
        assert result == VERIFICATION_PROMPT

    def test_explore_mode(self):
        result = get_mode_prompt("explore")
        assert result == EXPLORE_PROMPT

    def test_summarize_mode(self):
        result = get_mode_prompt("summarize")
        assert result == SUMMARIZATION_PROMPT

    def test_unknown_mode_falls_back(self):
        result = get_mode_prompt("nonexistent_mode")
        assert result == SYSTEM_PROMPT

    def test_plan_and_build_differ(self):
        plan = get_mode_prompt("plan")
        build = get_mode_prompt("build")
        assert plan != build


# ---------------------------------------------------------------------------
# Catalog system — fragments, agents, skills, tools, data
# ---------------------------------------------------------------------------

class TestCatalogLoaders:
    def test_fragments_load_without_error(self):
        fragments = get_all_fragments()
        assert isinstance(fragments, dict)
        assert len(fragments) > 0

    def test_agent_prompts_load_without_error(self):
        agents = get_all_agent_prompts()
        assert isinstance(agents, dict)
        assert len(agents) > 0

    def test_skills_load_without_error(self):
        skills = get_all_skills()
        assert isinstance(skills, dict)
        # May be empty if no skills defined yet
        assert isinstance(skills, dict)

    def test_tool_prompts_load_without_error(self):
        tools = get_all_tool_prompts()
        assert isinstance(tools, dict)
        assert len(tools) > 0

    def test_data_load_without_error(self):
        data = get_all_data()
        assert isinstance(data, dict)

    def test_all_fragments_are_strings(self):
        for name, content in get_all_fragments().items():
            assert isinstance(name, str)
            assert isinstance(content, str)
            assert len(content) > 0, f"Fragment '{name}' is empty"


# ---------------------------------------------------------------------------
# assemble_system_prompt
# ---------------------------------------------------------------------------

class TestAssembleSystemPrompt:
    def test_default_mode_returns_non_empty(self):
        result = assemble_system_prompt("default")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_plan_mode_differs_from_build(self):
        plan = assemble_system_prompt("plan")
        build = assemble_system_prompt("build")
        assert plan != build

    def test_with_extra_context(self):
        result = assemble_system_prompt("default", extra_context="CUSTOM_CONTEXT_MARKER")
        assert "CUSTOM_CONTEXT_MARKER" in result

    def test_with_specific_fragments(self):
        fragments = get_all_fragments()
        if fragments:
            first_key = list(fragments.keys())[0]
            result = assemble_system_prompt("default", include_fragments=[first_key])
            assert len(result) > 0

    def test_with_skills(self):
        skills = get_all_skills()
        if skills:
            first_key = list(skills.keys())[0]
            result = assemble_system_prompt("default", include_skills=[first_key])
            assert len(result) > 0


# ---------------------------------------------------------------------------
# list_prompts / search_prompts / get_prompt
# ---------------------------------------------------------------------------

class TestPromptRegistry:
    def test_list_prompts_returns_entries(self):
        entries = list_prompts()
        assert isinstance(entries, list)
        assert len(entries) > 0

    def test_list_prompts_has_metadata(self):
        entries = list_prompts()
        for entry in entries[:5]:  # Check first 5
            assert "name" in entry
            assert "category" in entry
            assert "package" in entry
            assert "module" in entry

    def test_list_prompts_by_category(self):
        fragment_entries = list_prompts(category="fragment")
        assert isinstance(fragment_entries, list)
        if fragment_entries:
            assert all(e["package"] == "fragments" for e in fragment_entries)

    def test_list_prompts_unknown_category_empty(self):
        result = list_prompts(category="nonexistent")
        assert result == []

    def test_search_prompts_finds_results(self):
        results = search_prompts("security")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_search_prompts_no_results(self):
        results = search_prompts("xyzzy_nonexistent_unique_string_12345")
        assert results == []

    def test_get_prompt_fragments(self):
        fragments = get_all_fragments()
        if fragments:
            first_name = list(fragments.keys())[0]
            content = get_prompt("fragments", first_name)
            assert isinstance(content, str)
            assert len(content) > 0

    def test_get_prompt_unknown_raises(self):
        with pytest.raises(KeyError):
            get_prompt("fragments", "nonexistent_module_xyz_12345")

    def test_get_prompt_unknown_category_raises(self):
        with pytest.raises(KeyError):
            get_prompt("bogus_category", "anything")


# ---------------------------------------------------------------------------
# Provider adapters
# ---------------------------------------------------------------------------

class TestProviderAdapters:
    def test_adapt_for_anthropic(self):
        base = "You are a helpful assistant."
        result = adapt_for_provider(base, "anthropic")
        assert "You are a helpful assistant." in result
        assert "Provider Notes (Anthropic)" in result

    def test_adapt_for_openai(self):
        base = "You are a helpful assistant."
        result = adapt_for_provider(base, "openai")
        assert "You are a helpful assistant." in result
        assert "Provider Notes (OpenAI)" in result

    def test_adapt_for_gemini(self):
        base = "You are a helpful assistant."
        result = adapt_for_provider(base, "gemini")
        assert "You are a helpful assistant." in result
        assert "project_context" in result

    def test_adapt_for_xai(self):
        base = "You are a helpful assistant."
        result = adapt_for_provider(base, "xai")
        assert "You are a helpful assistant." in result
        assert "Provider Notes (xAI)" in result

    def test_adapt_unknown_provider_unchanged(self):
        base = "You are a helpful assistant."
        result = adapt_for_provider(base, "unknown_provider")
        assert result == base

    def test_openai_agent_mode_suffix(self):
        base = "Base prompt"
        result = adapt_for_provider(base, "openai", model="codex-mini")
        assert "Agent Mode Notes" in result

    def test_tool_format_hints(self):
        hints = get_tool_format_hints("anthropic")
        assert hints["format"] == "json_schema"
        assert hints["edit_style"] == "string_replacement"

    def test_tool_format_hints_openai(self):
        hints = get_tool_format_hints("openai")
        assert hints["format"] == "typescript"

    def test_tool_format_hints_default(self):
        hints = get_tool_format_hints("unknown_provider_xyz")
        assert "format" in hints

    def test_response_style_hints(self):
        hints = get_response_style_hints("anthropic")
        assert hints["emojis"] == "never"
        assert hints["preamble_before_tools"] is False

    def test_response_style_hints_openai(self):
        hints = get_response_style_hints("openai")
        assert hints["preamble_before_tools"] is True
