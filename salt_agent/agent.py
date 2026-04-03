"""Core agent loop."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from salt_agent.compaction import (
    compact_context,
    estimate_messages_tokens,
    needs_compaction,
)
from salt_agent.config import AgentConfig
from salt_agent.context import ContextManager
from salt_agent.events import (
    AgentComplete,
    AgentError,
    AgentEvent,
    ContextCompacted,
    TextChunk,
    ToolEnd,
    ToolStart,
    ToolUse,
)
from salt_agent.hooks import HookEngine, HookResult
from salt_agent.memory import MemorySystem
from salt_agent.permissions import PermissionSystem
from salt_agent.persistence import SessionPersistence
from salt_agent.providers.base import ProviderAdapter
from salt_agent.tools.base import ToolRegistry


class SaltAgent:
    """The core agent: iterative LLM + tool execution loop."""

    def __init__(self, config: AgentConfig, tools: ToolRegistry | None = None) -> None:
        self.config = config
        self.provider = self._create_provider()
        self.tools = tools or self._default_tools()
        self.context = ContextManager(
            context_window=config.context_window,
            max_tool_result_chars=config.max_tool_result_chars,
        )
        self.hooks = HookEngine()

        # Memory system
        self.memory = MemorySystem(
            working_directory=config.working_directory,
            memory_dir=config.memory_dir or None,
        )

        # Session persistence (optional)
        self.persistence: SessionPersistence | None = None
        if config.persist:
            self.persistence = SessionPersistence(
                session_id=config.session_id or None,
                sessions_dir=config.sessions_dir or None,
            )

        # Permission system
        self.permissions = PermissionSystem(
            rules=config.permission_rules,
            ask_callback=config.permission_ask_callback,
        )
        # Register permission hook
        self._register_permission_hook()

        # Build system prompt: project instructions first, then user-supplied prompt
        self._assemble_system_prompt()

    def _create_provider(self) -> ProviderAdapter:
        if self.config.provider == "anthropic":
            from salt_agent.providers.anthropic import AnthropicAdapter
            return AnthropicAdapter(api_key=self.config.api_key, model=self.config.model)
        elif self.config.provider == "openai":
            from salt_agent.providers.openai_provider import OpenAIAdapter
            return OpenAIAdapter(api_key=self.config.api_key, model=self.config.model)
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")

    def _default_tools(self) -> ToolRegistry:
        from salt_agent.tools.bash import BashTool
        from salt_agent.tools.edit import EditTool
        from salt_agent.tools.glob_tool import GlobTool
        from salt_agent.tools.grep import GrepTool
        from salt_agent.tools.list_files import ListFilesTool
        from salt_agent.tools.read import ReadTool
        from salt_agent.tools.todo import TodoWriteTool
        from salt_agent.tools.write import WriteTool

        registry = ToolRegistry()

        wd = self.config.working_directory
        read_tool = ReadTool(working_directory=wd)
        registry.register(read_tool)
        registry.register(WriteTool(read_tool=read_tool, working_directory=wd))
        registry.register(EditTool(read_tool=read_tool, working_directory=wd))
        registry.register(BashTool(
            timeout=self.config.bash_timeout,
            working_directory=wd,
        ))
        registry.register(GlobTool(working_directory=wd))
        registry.register(GrepTool(working_directory=wd))
        registry.register(ListFilesTool(working_directory=wd))
        registry.register(TodoWriteTool())

        return registry

    def _get_provider_tools(self) -> list[dict]:
        if self.config.provider == "openai":
            return self.tools.to_openai_tools()
        return self.tools.to_anthropic_tools()

    def _get_todo_injection(self) -> str:
        """Get todo context injection if the todo tool has tasks."""
        todo_tool = self.tools.get("todo_write")
        if todo_tool and hasattr(todo_tool, "get_context_injection"):
            return todo_tool.get_context_injection()
        return ""

    def _assemble_system_prompt(self) -> None:
        """Assemble the system prompt: project instructions + user-supplied prompt."""
        parts: list[str] = []
        # Project instructions (highest priority -- at the top)
        project_instructions = self.memory.load_project_instructions()
        if project_instructions:
            parts.append(project_instructions)
        # User-supplied system prompt
        if self.config.system_prompt:
            parts.append(self.config.system_prompt)
        self.context.set_system("\n\n".join(parts))

    def _register_permission_hook(self) -> None:
        """Register the permission system as a pre_tool_use hook."""

        def permission_hook(data: dict) -> HookResult | None:
            tool_name = data.get("tool_name", "")
            tool_input = data.get("tool_input", {})
            action, reason = self.permissions.check(tool_name, tool_input)
            if action == "deny":
                return HookResult(action="block", reason=reason)
            return None

        self.hooks.on("pre_tool_use", permission_hook)

    def _build_system_prompt(self) -> str:
        """Build the system prompt with any dynamic injections (e.g., todo state)."""
        base = self.context.system_prompt
        todo_injection = self._get_todo_injection()
        if todo_injection:
            return base + "\n\n" + todo_injection if base else todo_injection
        return base

    @classmethod
    def resume(
        cls,
        session_id: str,
        config: AgentConfig | None = None,
        tools: ToolRegistry | None = None,
    ) -> tuple[SaltAgent, list[dict], str]:
        """Resume a session from a persisted checkpoint.

        Returns (agent, messages, system_prompt) so the caller can continue
        the conversation.
        """
        if config is None:
            config = AgentConfig()
        config.session_id = session_id
        config.persist = True

        agent = cls(config, tools=tools)
        assert agent.persistence is not None

        checkpoint = agent.persistence.load_last_checkpoint()
        if checkpoint is None:
            raise ValueError(f"No checkpoint found for session {session_id}")

        messages = checkpoint.get("messages", [])
        system = checkpoint.get("system", "")
        if system:
            agent.context.set_system(system)

        return agent, messages, system

    async def run(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Run the agent loop, yielding events as they occur."""
        messages: list[dict] = [{"role": "user", "content": prompt}]
        tools_used: list[str] = []

        for turn in range(self.config.max_turns):
            # Context pressure check
            messages = self.context.manage_pressure(messages)

            # Check if compaction is needed
            if needs_compaction(messages, self.config):
                old_tokens = estimate_messages_tokens(messages)
                todo_state = self._get_todo_injection()
                files_read = self.context._files_read
                messages = await compact_context(
                    messages,
                    self.context.system_prompt,
                    self.config,
                    self.provider,
                    todo_state=todo_state,
                    files_read=files_read,
                )
                new_tokens = estimate_messages_tokens(messages)
                self.hooks.fire("on_compaction", {
                    "old_tokens": old_tokens,
                    "new_tokens": new_tokens,
                })
                yield ContextCompacted(
                    old_tokens=old_tokens,
                    new_tokens=new_tokens,
                )

            # Build system prompt with todo injection
            system_prompt = self._build_system_prompt()

            # Save checkpoint BEFORE the API call (crash recovery)
            if self.persistence:
                self.persistence.save_checkpoint(messages, system_prompt)

            # Fire pre_api_call hook
            self.hooks.fire("pre_api_call", {
                "messages": messages,
                "system": system_prompt,
            })

            # Call LLM
            tool_uses: list[ToolUse] = []
            full_text = ""

            async for event in self.provider.stream_response(
                system=system_prompt,
                messages=messages,
                tools=self._get_provider_tools(),
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            ):
                yield event

                if isinstance(event, TextChunk):
                    full_text += event.text
                elif isinstance(event, ToolUse):
                    tool_uses.append(event)
                elif isinstance(event, AgentError) and not event.recoverable:
                    self.hooks.fire("on_error", {"error": event.error})
                    return

            # If no tool uses, we are done
            if not tool_uses:
                self.hooks.fire("on_complete", {
                    "turns": turn + 1,
                    "tools_used": tools_used,
                })
                yield AgentComplete(
                    final_text=full_text,
                    turns=turn + 1,
                    tools_used=tools_used,
                )
                return

            # Build assistant message
            assistant_content: list[dict] = []
            if full_text:
                assistant_content.append({"type": "text", "text": full_text})
            for tu in tool_uses:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tu.tool_id,
                    "name": tu.tool_name,
                    "input": tu.tool_input,
                })
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute tools
            tool_results: list[dict] = []
            for tu in tool_uses:
                # Fire pre_tool_use hook -- can block
                hook_result = await self.hooks.fire_async("pre_tool_use", {
                    "tool_name": tu.tool_name,
                    "tool_input": tu.tool_input,
                })

                if hook_result.action == "block":
                    result = f"Tool blocked: {hook_result.reason}"
                    yield ToolStart(tool_name=tu.tool_name, tool_input=tu.tool_input)
                    yield ToolEnd(
                        tool_name=tu.tool_name,
                        result=result,
                        success=False,
                    )
                    tools_used.append(tu.tool_name)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.tool_id,
                        "content": result,
                    })
                    continue

                yield ToolStart(tool_name=tu.tool_name, tool_input=tu.tool_input)
                tools_used.append(tu.tool_name)

                tool = self.tools.get(tu.tool_name)
                if tool:
                    try:
                        result = tool.execute(**tu.tool_input)
                        success = True
                        yield ToolEnd(
                            tool_name=tu.tool_name,
                            result=result[:200],
                            success=True,
                        )
                    except Exception as e:
                        result = f"Error: {str(e)}"
                        success = False
                        yield ToolEnd(
                            tool_name=tu.tool_name,
                            result=result,
                            success=False,
                        )
                else:
                    result = f"Unknown tool: {tu.tool_name}"
                    success = False
                    yield ToolEnd(
                        tool_name=tu.tool_name,
                        result=result,
                        success=False,
                    )

                # Fire post_tool_use hook
                self.hooks.fire("post_tool_use", {
                    "tool_name": tu.tool_name,
                    "result": result[:500],
                    "success": success,
                })

                result = self.context.truncate_tool_result(result)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.tool_id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

        self.hooks.fire("on_error", {
            "error": f"Max turns ({self.config.max_turns}) reached",
        })
        yield AgentError(
            error=f"Max turns ({self.config.max_turns}) reached",
            recoverable=False,
        )
