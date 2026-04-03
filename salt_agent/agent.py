"""Core agent loop."""

from __future__ import annotations

import asyncio
import hashlib as _hl
import os
from datetime import datetime, timezone
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
    FileSnapshotted,
    SubagentComplete,
    SubagentSpawned,
    TextChunk,
    ToolEnd,
    ToolStart,
    ToolUse,
)
from salt_agent.file_history import FileHistory
from salt_agent.hooks import HookEngine, HookResult
from salt_agent.memory import MemorySystem
from salt_agent.permissions import PermissionSystem
from salt_agent.persistence import SessionPersistence
from salt_agent.providers.base import ProviderAdapter
from salt_agent.subagent import SubagentManager
from salt_agent.tools.base import ToolRegistry

# Tools that are safe to execute in parallel (no side effects, independent I/O)
PARALLEL_SAFE_TOOLS = frozenset({
    "web_fetch", "web_search", "read", "glob", "grep", "list_files",
})


class SaltAgent:
    """The core agent: iterative LLM + tool execution loop."""

    def __init__(self, config: AgentConfig, tools: ToolRegistry | None = None) -> None:
        self.config = config
        self.provider = self._create_provider()
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

        # Subagent manager (before tools, since AgentTool needs it)
        self.subagent_manager = SubagentManager(self)

        # File history (rewind support)
        session_id = ""
        if self.persistence:
            session_id = self.persistence.session_id
        else:
            import uuid
            session_id = str(uuid.uuid4())
        self.file_history = FileHistory(session_id=session_id)
        self._register_file_history_hook()

        # Tools (after subagent_manager since AgentTool references it)
        self.tools = tools or self._default_tools()

        # Persistent conversation history for interactive mode
        self._conversation_messages: list[dict] = []

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

    @staticmethod
    def _detect_loop(recent_sigs: list[str]) -> bool:
        """Detect repeating patterns in tool call signatures.

        Checks for repeating subsequences of length 1-4 that repeat 3+ times.
        Example: [A,B,A,B,A,B] → pattern [A,B] repeats 3x → True
        """
        if len(recent_sigs) < 6:
            return False

        # Check patterns of length 1 to 4
        for pattern_len in range(1, 5):
            if len(recent_sigs) < pattern_len * 3:
                continue
            # Get the last pattern_len * 3 signatures
            window = recent_sigs[-(pattern_len * 3):]
            pattern = window[:pattern_len]
            repeats = True
            for i in range(pattern_len, len(window)):
                if window[i] != pattern[i % pattern_len]:
                    repeats = False
                    break
            if repeats:
                return True

        return False

    def _default_tools(self) -> ToolRegistry:
        from salt_agent.tools.agent_tool import AgentTool
        from salt_agent.tools.bash import BashTool
        from salt_agent.tools.edit import EditTool
        from salt_agent.tools.glob_tool import GlobTool
        from salt_agent.tools.grep import GrepTool
        from salt_agent.tools.list_files import ListFilesTool
        from salt_agent.tools.multi_edit import MultiEditTool
        from salt_agent.tools.read import ReadTool
        from salt_agent.tools.todo import TodoWriteTool
        from salt_agent.tools.write import WriteTool

        registry = ToolRegistry()

        wd = self.config.working_directory
        read_tool = ReadTool(working_directory=wd)
        registry.register(read_tool)
        registry.register(WriteTool(read_tool=read_tool, working_directory=wd))
        registry.register(EditTool(read_tool=read_tool, working_directory=wd))
        registry.register(MultiEditTool(read_tool=read_tool, working_directory=wd))
        registry.register(BashTool(
            timeout=self.config.bash_timeout,
            working_directory=wd,
        ))
        registry.register(GlobTool(working_directory=wd))
        registry.register(GrepTool(working_directory=wd))
        registry.register(ListFilesTool(working_directory=wd))
        registry.register(TodoWriteTool())
        registry.register(AgentTool(self.subagent_manager))

        # Optional web tools
        if self.config.include_web_tools:
            from salt_agent.tools.web_fetch import WebFetchTool
            from salt_agent.tools.web_search import WebSearchTool

            registry.register(WebFetchTool(extractor=self.config.web_extractor))
            registry.register(WebSearchTool())

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

    def _register_file_history_hook(self) -> None:
        """Register a pre_tool_use hook to snapshot files before writes/edits."""

        def snapshot_hook(data: dict) -> HookResult | None:
            tool_name = data.get("tool_name", "")
            tool_input = data.get("tool_input", {})
            if tool_name in ("write", "edit", "multi_edit"):
                file_path = tool_input.get("file_path", "")
                if file_path:
                    self.file_history.snapshot(file_path)
            return None

        self.hooks.on("pre_tool_use", snapshot_hook)

    def _build_system_prompt(self) -> str:
        """Build the system prompt with dynamic injections each turn.

        Reassembles from scratch: project instructions, user-supplied prompt,
        dynamic context (date, cwd, todo state).
        """
        # Reassemble base from project instructions + user prompt
        parts: list[str] = []
        project_instructions = self.memory.load_project_instructions()
        if project_instructions:
            parts.append(project_instructions)
        if self.config.system_prompt:
            parts.append(self.config.system_prompt)

        # Dynamic per-turn context
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        cwd = os.path.abspath(self.config.working_directory)
        dynamic_parts = [
            f"Current date/time: {now}",
            f"Working directory: {cwd}",
        ]
        todo_injection = self._get_todo_injection()
        if todo_injection:
            dynamic_parts.append(todo_injection)

        parts.append("\n".join(dynamic_parts))

        full_prompt = "\n\n".join(parts)
        # Keep context.system_prompt updated for other consumers
        self.context.set_system(full_prompt)
        return full_prompt

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

        # Restore conversation history so future run() calls continue it
        agent._conversation_messages = list(messages)

        return agent, messages, system

    async def run(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Run the agent loop, yielding events as they occur.

        When conversation persistence is active (_conversation_messages is non-empty
        or accumulating), messages from previous run() calls are preserved so the
        agent maintains context across interactive turns.
        """
        # Append new user message to persistent conversation
        self._conversation_messages.append({"role": "user", "content": prompt})

        # Work with the full conversation history
        messages = self._conversation_messages

        tools_used: list[str] = []
        _recent_tool_sigs: list[str] = []  # tool_name:input_hash for loop detection
        _consecutive_same_result: int = 0
        _last_result_hash: str = ""

        for turn in range(self.config.max_turns):
            # --- Loop detection (inspired by Claude Code's stuck-in-a-loop handling) ---
            if self._detect_loop(_recent_tool_sigs):
                # Inject a "you're stuck" message instead of hard-stopping
                # Give the model ONE chance to course-correct
                messages.append({
                    "role": "user",
                    "content": (
                        "IMPORTANT: You appear to be stuck in a repeating pattern of tool calls. "
                        "Stop and reassess. If you cannot accomplish the task with your available tools, "
                        "explain what you need and what's blocking you. Do NOT repeat the same approach."
                    ),
                })
                _recent_tool_sigs.clear()
                _consecutive_same_result = 0
                # If this is the second time we've injected this warning, hard stop
                if turn > 0 and any(
                    isinstance(m.get("content"), str) and "stuck in a repeating pattern" in m.get("content", "")
                    for m in messages[:-1]
                ):
                    yield AgentError(
                        error="Agent stuck in a loop after two warnings. Stopping.",
                        recoverable=False,
                    )
                    self.hooks.fire("on_error", {"error": "Loop detected — hard stop"})
                    return
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

            # Call LLM (with prompt-too-long recovery)
            tool_uses: list[ToolUse] = []
            full_text = ""
            _prompt_too_long = False

            try:
                async for event in self.provider.stream_response(
                    system=system_prompt,
                    messages=messages,
                    tools=self._get_provider_tools(),
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                ):
                    # Check for prompt-too-long errors in AgentError events
                    if isinstance(event, AgentError):
                        error_lower = event.error.lower()
                        if (
                            ("prompt" in error_lower and "too long" in error_lower)
                            or "too many tokens" in error_lower
                            or "context length" in error_lower
                            or "maximum context length exceeded" in error_lower
                        ):
                            _prompt_too_long = True
                            break
                        if not event.recoverable:
                            yield event
                            self.hooks.fire("on_error", {"error": event.error})
                            return

                    yield event

                    if isinstance(event, TextChunk):
                        full_text += event.text
                    elif isinstance(event, ToolUse):
                        tool_uses.append(event)
            except Exception as e:
                error_str = str(e).lower()
                if (
                    ("prompt" in error_str and "too long" in error_str)
                    or "too many tokens" in error_str
                    or "context length" in error_str
                    or "maximum context length exceeded" in error_str
                ):
                    _prompt_too_long = True
                else:
                    raise

            if _prompt_too_long:
                # Auto-compact and retry this turn
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
                self._conversation_messages[:] = messages
                yield ContextCompacted(old_tokens=old_tokens, new_tokens=new_tokens)
                continue  # retry this turn with compacted context

            # If no tool uses, we are done
            if not tool_uses:
                # Save final assistant message to conversation history
                if full_text:
                    self._conversation_messages.append(
                        {"role": "assistant", "content": full_text}
                    )
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

            # Execute tools -- parallel when safe, sequential otherwise
            tool_results: list[dict] = []
            parallel_safe = (
                len(tool_uses) > 1
                and all(tu.tool_name in PARALLEL_SAFE_TOOLS for tu in tool_uses)
            )

            if parallel_safe:
                # --- Parallel execution path ---
                # Emit all ToolStart events up front
                for tu in tool_uses:
                    yield ToolStart(tool_name=tu.tool_name, tool_input=tu.tool_input)
                    tools_used.append(tu.tool_name)

                # Execute all tools concurrently
                async def _run_one(tu: ToolUse) -> tuple[ToolUse, str, bool]:
                    # Pre-tool hook
                    hook_result = await self.hooks.fire_async("pre_tool_use", {
                        "tool_name": tu.tool_name,
                        "tool_input": tu.tool_input,
                    })
                    if hook_result.action == "block":
                        return (tu, f"Tool blocked: {hook_result.reason}", False)

                    tool = self.tools.get(tu.tool_name)
                    if not tool:
                        available = ", ".join(self.tools.names())
                        return (tu, (
                            f"Error: Tool '{tu.tool_name}' does not exist. "
                            f"Available tools: {available}. "
                            f"Do NOT try to simulate this tool with bash echo or other workarounds. "
                            f"If you cannot accomplish the task with available tools, say so."
                        ), False)

                    try:
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(
                            None, lambda t=tu: tool.execute(**t.tool_input)
                        )
                        return (tu, result, True)
                    except Exception as e:
                        return (tu, f"Error: {str(e)}", False)

                completed = await asyncio.gather(*[_run_one(tu) for tu in tool_uses])

                # Emit all ToolEnd events and build results
                for tu, result, success in completed:
                    yield ToolEnd(
                        tool_name=tu.tool_name,
                        result=result[:200],
                        success=success,
                    )
                    self.hooks.fire("post_tool_use", {
                        "tool_name": tu.tool_name,
                        "result": result[:500],
                        "success": success,
                    })
                    result = self.context.truncate_tool_result(result)

                    # Track for loop detection
                    _sig = f"{tu.tool_name}:{_hl.md5(str(tu.tool_input).encode()).hexdigest()[:8]}"
                    _recent_tool_sigs.append(_sig)
                    _rh = _hl.md5(result.encode()).hexdigest()[:8]
                    if _rh == _last_result_hash:
                        _consecutive_same_result += 1
                    else:
                        _consecutive_same_result = 0
                    _last_result_hash = _rh

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.tool_id,
                        "content": result,
                    })
            else:
                # --- Sequential execution path ---
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
                        available = ", ".join(self.tools.names())
                        result = (
                            f"Error: Tool '{tu.tool_name}' does not exist. "
                            f"Available tools: {available}. "
                            f"Do NOT try to simulate this tool with bash echo or other workarounds. "
                            f"If you cannot accomplish the task with available tools, say so."
                        )
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

                    # Track for loop detection
                    _sig = f"{tu.tool_name}:{_hl.md5(str(tu.tool_input).encode()).hexdigest()[:8]}"
                    _recent_tool_sigs.append(_sig)
                    _rh = _hl.md5(result.encode()).hexdigest()[:8]
                    if _rh == _last_result_hash:
                        _consecutive_same_result += 1
                    else:
                        _consecutive_same_result = 0
                    _last_result_hash = _rh

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

    def clear_conversation(self) -> None:
        """Clear persistent conversation history.

        Call this to reset the agent's memory of previous turns (e.g., /clear).
        """
        self._conversation_messages.clear()
