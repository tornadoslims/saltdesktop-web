"""Subagent system -- spawn fresh or forked child agents.

The manager creates child agents; the caller (AgentTool.async_execute) runs
them and yields their events into the parent's stream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from salt_agent.agent import SaltAgent

# Lazy-loaded reference for create_agent (avoids circular import at import time).
# Patching tests should target "salt_agent.subagent._create_agent".
_create_agent = None


def _get_create_agent():
    global _create_agent
    if _create_agent is None:
        from salt_agent import create_agent
        _create_agent = create_agent
    return _create_agent


_FORK_BOILERPLATE = (
    "You are a forked worker process. Execute the task directly and efficiently. "
    "Do NOT spawn sub-agents. Do NOT ask clarifying questions. "
    "When done, report your result in this format:\n"
    "**Scope:** What you were asked to do\n"
    "**Result:** What you did (success/failure)\n"
    "**Key files:** Files you read or examined\n"
    "**Files changed:** Files you created or modified\n"
    "**Issues:** Any problems encountered\n\n"
    "Your task:"
)


class SubagentManager:
    """Manage child agents spawned from a parent agent."""

    def __init__(self, parent_agent: SaltAgent) -> None:
        self.parent = parent_agent
        self.children: list[dict] = []

    # -- Factory methods (create agents, caller runs them) -------------------

    def create_fresh(self, mode: str = "general", max_turns: int = 15) -> SaltAgent:
        """Create a fresh subagent with zero context. Caller runs it.

        Use for exploration, verification, or focused tasks that don't need
        the parent's conversation history.
        """
        factory = _get_create_agent()
        child = factory(
            provider=self.parent.config.provider,
            model=self.parent.config.model,
            api_key=self.parent.config.api_key,
            working_directory=self.parent.config.working_directory,
            system_prompt=_mode_system_prompt(mode),
            max_turns=max_turns,
            persist=False,
        )
        return child

    def create_fork(self, max_turns: int = 15) -> SaltAgent:
        """Create a fork that inherits parent context. Caller runs it.

        Prompt cache prefix sharing: the child uses the EXACT same system
        prompt and tool definitions as the parent, byte-for-byte.  This
        ensures Anthropic's prompt cache gives cache hits on the shared prefix.
        """
        factory = _get_create_agent()
        child = factory(
            provider=self.parent.config.provider,
            model=self.parent.config.model,
            api_key=self.parent.config.api_key,
            working_directory=self.parent.config.working_directory,
            system_prompt=self.parent.context.system_prompt,
            max_turns=max_turns,
            persist=False,
        )
        # Share the SAME tool registry (identical tool definitions for cache prefix)
        child.tools = self.parent.tools
        # Copy parent's conversation messages exactly (deep copy for isolation)
        child._conversation_messages = [
            dict(m) for m in self.parent._conversation_messages
        ]
        return child

    # -- Legacy async helpers (kept for backward compat / direct use) --------

    async def spawn_fresh(
        self,
        prompt: str,
        mode: str = "general",
        max_turns: int = 15,
    ) -> dict:
        """Spawn a fresh subagent and run it to completion.

        Returns a record dict with type, mode, prompt, result.
        This is the legacy API -- new code should use create_fresh() + run().
        """
        child = self.create_fresh(mode=mode, max_turns=max_turns)
        result_text = await _run_agent(child, prompt)

        child_record = {
            "type": "fresh",
            "mode": mode,
            "prompt": prompt[:200],
            "result": result_text[:2000],
        }
        self.children.append(child_record)
        return child_record

    async def fork(
        self,
        prompt: str,
        messages: list[dict] | None = None,
        max_turns: int = 15,
    ) -> dict:
        """Fork: child inherits parent's conversation context.

        Returns a record dict with type, mode, prompt, result.
        This is the legacy API -- new code should use create_fork() + run().
        """
        child = self.create_fork(max_turns=max_turns)
        # Override messages if explicitly provided
        if messages is not None:
            child._conversation_messages = [dict(m) for m in messages]

        result_text = await _run_agent(child, _FORK_BOILERPLATE + "\n\n" + prompt)

        child_record = {
            "type": "fork",
            "mode": "fork",
            "prompt": prompt[:200],
            "result": result_text[:2000],
        }
        self.children.append(child_record)
        return child_record


async def _run_agent(agent, prompt: str) -> str:
    """Run an agent to completion and collect the final text."""
    from salt_agent.events import AgentComplete, TextChunk

    result_text = ""
    async for event in agent.run(prompt):
        if isinstance(event, AgentComplete):
            result_text = event.final_text
        elif isinstance(event, TextChunk):
            result_text += event.text
    return result_text


def _mode_system_prompt(mode: str) -> str:
    """Return a system prompt tailored to the subagent mode."""
    if mode == "verify":
        from salt_agent.prompts.verification import VERIFICATION_PROMPT
        return VERIFICATION_PROMPT

    prompts = {
        "explore": (
            "You are an exploration agent. Your job is to investigate codebases, "
            "read files, search for patterns, and report what you find. "
            "Be thorough but concise in your findings."
        ),
        "worker": (
            "You are a worker agent. Your job is to complete a specific coding task: "
            "write code, edit files, run tests. Focus on the task and report completion."
        ),
        "general": (
            "You are a focused subagent. Complete the given task efficiently "
            "and report the result."
        ),
    }
    return prompts.get(mode, prompts["general"])
