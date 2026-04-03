"""
Prompt assembler — composes fragments, agent prompts, skills, and tool descriptions
into complete system prompts for SaltAgent.
"""

from pathlib import Path
import importlib
import pkgutil


def _load_all_from_package(package_name: str) -> dict[str, str]:
    """Load all PROMPT constants from a prompts subpackage."""
    results = {}
    package = importlib.import_module(f"salt_agent.prompts.{package_name}")
    pkg_path = Path(package.__file__).parent

    for _, module_name, _ in pkgutil.iter_modules([str(pkg_path)]):
        mod = importlib.import_module(f"salt_agent.prompts.{package_name}.{module_name}")
        if hasattr(mod, 'PROMPT'):
            results[module_name] = mod.PROMPT

    return results


def get_all_fragments() -> dict[str, str]:
    """Load all behavioral instruction fragments."""
    return _load_all_from_package("fragments")


def get_all_agent_prompts() -> dict[str, str]:
    """Load all subagent role prompts."""
    return _load_all_from_package("agents")


def get_all_skills() -> dict[str, str]:
    """Load all skill prompts."""
    return _load_all_from_package("skills")


def get_all_tool_prompts() -> dict[str, str]:
    """Load all tool description prompts."""
    return _load_all_from_package("tools")


def get_all_data() -> dict[str, str]:
    """Load all reference data prompts."""
    return _load_all_from_package("data")


def assemble_system_prompt(
    mode: str = "default",
    include_fragments: list[str] | None = None,
    include_tools: list[str] | None = None,
    include_skills: list[str] | None = None,
    extra_context: str = "",
) -> str:
    """
    Assemble a complete system prompt from components.

    Args:
        mode: Agent mode — "default", "plan", "build", "verify", "explore", "worker"
        include_fragments: Specific fragments to include (None = all core fragments)
        include_tools: Tool descriptions to include (None = based on registered tools)
        include_skills: Skills to include (None = none)
        extra_context: Additional context (mission info, company info, etc.)
    """
    parts = []

    # 1. Core behavioral fragments (always included)
    fragments = get_all_fragments()
    if include_fragments:
        for name in include_fragments:
            if name in fragments:
                parts.append(fragments[name])
    else:
        # Include all core behavioral fragments by default
        core_fragment_names = [
            "doing_tasks_software_engineering_focus",
            "doing_tasks_read_before_modifying",
            "doing_tasks_no_unnecessary_additions",
            "doing_tasks_no_premature_abstractions",
            "doing_tasks_no_unnecessary_error_handling",
            "doing_tasks_no_compatibility_hacks",
            "doing_tasks_minimize_file_creation",
            "doing_tasks_security",
            "doing_tasks_no_time_estimates",
            "doing_tasks_ambitious_tasks",
            "doing_tasks_help_and_feedback",
            "executing_actions_with_care",
            "censoring_assistance_with_malicious_activities",
        ]
        for name in core_fragment_names:
            if name in fragments:
                parts.append(fragments[name])

    # 2. Mode-specific agent prompt
    agent_prompts = get_all_agent_prompts()
    mode_map = {
        "plan": "plan_mode_enhanced",
        "build": "worker_fork_execution",
        "verify": "verification_specialist",
        "explore": "explore",
        "worker": "general_purpose",
        "default": "general_purpose",
    }
    agent_key = mode_map.get(mode, "general_purpose")
    if agent_key in agent_prompts:
        parts.append(agent_prompts[agent_key])

    # 3. Tool descriptions
    if include_tools:
        tool_prompts = get_all_tool_prompts()
        for name in include_tools:
            if name in tool_prompts:
                parts.append(tool_prompts[name])

    # 4. Skills
    if include_skills:
        skills = get_all_skills()
        for name in include_skills:
            if name in skills:
                parts.append(skills[name])

    # 5. Extra context
    if extra_context:
        parts.append(extra_context)

    return "\n\n---\n\n".join(parts)
