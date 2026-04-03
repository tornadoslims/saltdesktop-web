"""SaltAgent prompt library.

Two systems coexist here:

1. **Curated prompts** — 14 directly-usable system prompts adapted from Claude Code's
   254 system prompts. Import the constants or use get_mode_prompt().

       from salt_agent.prompts import SYSTEM_PROMPT, get_mode_prompt
       agent = create_agent(system_prompt=SYSTEM_PROMPT)
       agent = create_agent(system_prompt=get_mode_prompt("verify"))

2. **Prompt catalog** — The full set of 254 prompts organized into subpackages
   (fragments, agents, skills, tools, data). Use assemble_system_prompt() to
   compose them, or search/list with the registry.

       from salt_agent.prompts import assemble_system_prompt, search_prompts
       prompt = assemble_system_prompt(mode="plan", include_skills=["debugging"])
"""

# --- Curated mode prompts (directly usable) ---
from salt_agent.prompts.system_prompt import SYSTEM_PROMPT
from salt_agent.prompts.plan_mode import PLAN_MODE_PROMPT
from salt_agent.prompts.build_mode import BUILD_MODE_PROMPT
from salt_agent.prompts.verification import VERIFICATION_PROMPT
from salt_agent.prompts.explore import EXPLORE_PROMPT
from salt_agent.prompts.summarization import SUMMARIZATION_PROMPT
from salt_agent.prompts.memory import MEMORY_PROMPT
from salt_agent.prompts.security import SECURITY_PROMPT
from salt_agent.prompts.worker import WORKER_PROMPT
from salt_agent.prompts.general_purpose import GENERAL_PURPOSE_PROMPT
from salt_agent.prompts.commit import COMMIT_PROMPT
from salt_agent.prompts.pr_creation import PR_CREATION_PROMPT
from salt_agent.prompts.code_review import CODE_REVIEW_PROMPT
from salt_agent.prompts.webfetch import WEBFETCH_PROMPT

# --- Prompt catalog (composable system) ---
from salt_agent.prompts.assembler import (
    assemble_system_prompt,
    get_all_fragments,
    get_all_agent_prompts,
    get_all_skills,
    get_all_tool_prompts,
    get_all_data,
)
from salt_agent.prompts.registry import list_prompts, get_prompt, search_prompts

__all__ = [
    # Curated prompts
    "SYSTEM_PROMPT",
    "PLAN_MODE_PROMPT",
    "BUILD_MODE_PROMPT",
    "VERIFICATION_PROMPT",
    "EXPLORE_PROMPT",
    "SUMMARIZATION_PROMPT",
    "MEMORY_PROMPT",
    "SECURITY_PROMPT",
    "WORKER_PROMPT",
    "GENERAL_PURPOSE_PROMPT",
    "COMMIT_PROMPT",
    "PR_CREATION_PROMPT",
    "CODE_REVIEW_PROMPT",
    "WEBFETCH_PROMPT",
    "get_mode_prompt",
    # Catalog system
    "assemble_system_prompt",
    "get_all_fragments",
    "get_all_agent_prompts",
    "get_all_skills",
    "get_all_tool_prompts",
    "get_all_data",
    "list_prompts",
    "get_prompt",
    "search_prompts",
]


def get_mode_prompt(mode: str) -> str:
    """Get the curated system prompt for a given agent mode.

    Args:
        mode: One of "default", "plan", "build", "verify", "explore",
              "summarize", "memory", "security", "worker", "general",
              "commit", "pr", "review", "webfetch".

    Returns:
        The system prompt string. Falls back to SYSTEM_PROMPT for unknown modes.
    """
    prompts = {
        "default": SYSTEM_PROMPT,
        "plan": PLAN_MODE_PROMPT,
        "build": BUILD_MODE_PROMPT,
        "verify": VERIFICATION_PROMPT,
        "explore": EXPLORE_PROMPT,
        "summarize": SUMMARIZATION_PROMPT,
        "memory": MEMORY_PROMPT,
        "security": SECURITY_PROMPT,
        "worker": WORKER_PROMPT,
        "general": GENERAL_PURPOSE_PROMPT,
        "commit": COMMIT_PROMPT,
        "pr": PR_CREATION_PROMPT,
        "review": CODE_REVIEW_PROMPT,
        "webfetch": WEBFETCH_PROMPT,
    }
    return prompts.get(mode, SYSTEM_PROMPT)
