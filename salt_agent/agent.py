"""Core agent loop."""

from __future__ import annotations

import asyncio
import hashlib as _hl
import os
from datetime import datetime, timezone
from typing import AsyncIterator

from salt_agent.attachments import AttachmentAssembler
from salt_agent.compaction import (
    compact_context,
    emergency_truncate,
    estimate_messages_tokens,
    microcompact_tool_results,
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
from salt_agent.memory import MemorySystem, find_relevant_memories
from salt_agent.permissions import PermissionSystem
from salt_agent.persistence import SessionPersistence
from salt_agent.providers.base import ProviderAdapter
from salt_agent.skills.manager import SkillManager
from salt_agent.stop_hooks import StopHookRunner
from salt_agent.subagent import SubagentManager
from salt_agent.tasks.manager import TaskManager
from salt_agent.token_budget import BudgetTracker
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
            auto_mode=config.auto_mode,
            plan_mode=config.plan_mode,
        )
        # Register permission hook
        self._register_permission_hook()

        # Subagent manager (before tools, since AgentTool needs it)
        self.subagent_manager = SubagentManager(self)

        # Task manager (background tasks in separate threads)
        self.task_manager = TaskManager(self)

        # File history (rewind support)
        session_id = ""
        if self.persistence:
            session_id = self.persistence.session_id
        else:
            import uuid
            session_id = str(uuid.uuid4())
        self.file_history = FileHistory(session_id=session_id)
        self._register_file_history_hook()

        # Skills system (before tools, since SkillTool needs it)
        self.skill_manager = SkillManager(extra_dirs=config.skill_dirs)

        # Token budget tracker (real API usage, not estimates)
        self.budget = BudgetTracker(
            context_window=config.context_window,
            max_output=config.max_tokens,
            model=config.model,
        )

        # Tools (after subagent_manager since AgentTool references it)
        self.tools = tools or self._default_tools()

        # Coordinator mode: strip write/execute tools, keep delegation-only tools
        if config.coordinator_mode:
            from salt_agent.coordinator import apply_coordinator_mode
            apply_coordinator_mode(self.tools)

        # Plugin system
        self.plugin_manager = None
        if config.plugin_dirs:
            from salt_agent.plugins import PluginManager
            self.plugin_manager = PluginManager(plugin_dirs=config.plugin_dirs)
            self.plugin_manager.discover()
            # Register plugin tools
            for tool in self.plugin_manager.get_tools():
                self.tools.register(tool)
            # Register plugin hooks
            for event_name, callback in self.plugin_manager.get_hooks():
                self.hooks.on(event_name, callback)

        # MCP manager (lazy-started on first run)
        self.mcp_manager = None
        self._mcp_started = False
        if config.enable_mcp:
            try:
                from salt_agent.mcp import MCPManager
                mcp_dir = config.mcp_config_path or config.working_directory
                self.mcp_manager = MCPManager(working_directory=mcp_dir)
            except ImportError:
                pass  # mcp package not installed

        # Stop hooks (post-turn processing: memory extraction, session title, stats)
        self.stop_hooks = StopHookRunner(self)

        # Attachment assembler (per-turn system-reminder injection)
        self.attachments = AttachmentAssembler(self)

        # Persistent conversation history for interactive mode
        self._conversation_messages: list[dict] = []

        # Build system prompt: project instructions first, then user-supplied prompt
        self._assemble_system_prompt()

    def _create_provider(self) -> ProviderAdapter:
        if self.config.provider == "anthropic":
            from salt_agent.providers.anthropic import AnthropicAdapter
            return AnthropicAdapter(
                api_key=self.config.api_key,
                model=self.config.model,
                fallback_model=self.config.fallback_model,
            )
        elif self.config.provider == "openai":
            from salt_agent.providers.openai_provider import OpenAIAdapter
            return OpenAIAdapter(
                api_key=self.config.api_key,
                model=self.config.model,
                fallback_model=self.config.fallback_model,
            )
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

        # Task tools (background task management)
        from salt_agent.tools.tasks import (
            TaskCreateTool,
            TaskGetTool,
            TaskListTool,
            TaskOutputTool,
            TaskStopTool,
            TaskUpdateTool,
        )
        registry.register(TaskCreateTool(self.task_manager))
        registry.register(TaskListTool(self.task_manager))
        registry.register(TaskGetTool(self.task_manager))
        registry.register(TaskOutputTool(self.task_manager))
        registry.register(TaskStopTool(self.task_manager))
        registry.register(TaskUpdateTool(self.task_manager))

        # Optional web tools
        if self.config.include_web_tools:
            from salt_agent.tools.web_fetch import WebFetchTool
            from salt_agent.tools.web_search import WebSearchTool

            registry.register(WebFetchTool(extractor=self.config.web_extractor))
            registry.register(WebSearchTool())

        # Optional git tools
        if self.config.include_git_tools:
            from salt_agent.tools.git import GitCommitTool, GitDiffTool, GitStatusTool

            registry.register(GitStatusTool(working_directory=wd))
            registry.register(GitDiffTool(working_directory=wd))
            registry.register(GitCommitTool(working_directory=wd))

        # Skill tool (invoke skills by name)
        from salt_agent.tools.skill_tool import SkillTool
        registry.register(SkillTool(self.skill_manager))

        # ToolSearch (deferred tool loading infrastructure)
        from salt_agent.tools.tool_search import ToolSearchTool
        registry.register(ToolSearchTool(registry))

        # AskUser tool
        from salt_agent.tools.ask_user import AskUserQuestionTool
        registry.register(AskUserQuestionTool())

        # Plan mode tools
        from salt_agent.tools.plan_mode_tool import EnterPlanModeTool, ExitPlanModeTool
        registry.register(EnterPlanModeTool(self.config))
        registry.register(ExitPlanModeTool(self.config))

        # Sleep tool
        from salt_agent.tools.sleep_tool import SleepTool
        registry.register(SleepTool(task_manager=self.task_manager))

        # Config tool
        from salt_agent.tools.config_tool import ConfigTool
        registry.register(ConfigTool(agent_config=self.config))

        # SendMessage tool
        from salt_agent.tools.message_tool import SendMessageTool
        registry.register(SendMessageTool(task_manager=self.task_manager))

        # Worktree tools
        from salt_agent.tools.worktree_tool import EnterWorktreeTool, ExitWorktreeTool
        enter_wt = EnterWorktreeTool(agent_config=self.config)
        registry.register(enter_wt)
        registry.register(ExitWorktreeTool(enter_tool=enter_wt))

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

        # Plan mode injection
        if self.config.plan_mode:
            dynamic_parts.append(
                "You MUST create a plan using todo_write before taking any action. "
                "List all steps you will take. Do NOT execute any tools other than "
                "todo_write until the user types /approve."
            )

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
        # Lazy-start MCP servers on first run
        if self.mcp_manager and not self._mcp_started:
            try:
                mcp_tools = await self.mcp_manager.start_servers()
                for tool in mcp_tools:
                    self.tools.register(tool)
                self._mcp_started = True
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("MCP startup failed: %s", e)
                self._mcp_started = True  # Don't retry on every run()

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

            # Microcompaction: truncate old tool results before checking full compaction
            messages = microcompact_tool_results(messages)

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

                # Emergency truncation if compaction wasn't enough
                if new_tokens > int(self.config.context_window * 0.95):
                    messages = emergency_truncate(
                        messages, int(self.config.context_window * 0.7)
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

            # --- Per-turn system-reminder injection (into a COPY of messages) ---
            reminders = self.attachments.assemble()

            # Inject relevant memories via LLM side-query
            last_content = messages[-1].get("content", "") if messages else ""
            if isinstance(last_content, str):
                query_text = last_content
            elif isinstance(last_content, list):
                query_text = " ".join(
                    b.get("text", "") for b in last_content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                query_text = str(last_content)

            if query_text and len(query_text) > 10:
                try:
                    memory_files = await find_relevant_memories(
                        query=query_text,
                        memory_index=self.memory.scan_memory_files(),
                        provider=self.provider,
                    )
                    for filename in memory_files:
                        content = self.memory.load_memory_file(filename)
                        if content:
                            reminders.append(
                                f"<system-reminder>\nRelevant memory ({filename}):\n"
                                f"{content[:2000]}\n</system-reminder>"
                            )
                except Exception:
                    pass  # Memory recall must never crash the agent

            # Build turn_messages: inject reminders into a copy (NOT saved to _conversation_messages)
            turn_messages = list(messages)
            if reminders:
                reminder_block = "\n".join(reminders)
                last_msg = turn_messages[-1]
                if isinstance(last_msg.get("content"), str):
                    turn_messages[-1] = dict(last_msg)  # shallow copy
                    turn_messages[-1]["content"] = last_msg["content"] + "\n\n" + reminder_block

            # Save checkpoint BEFORE the API call (crash recovery)
            if self.persistence:
                self.persistence.save_checkpoint(messages, system_prompt)

            # Budget limit check
            if self.budget and self.config.max_budget_usd:
                if self.budget.total_cost_estimate >= self.config.max_budget_usd:
                    yield AgentError(
                        error=f"Budget limit reached (${self.config.max_budget_usd})",
                        recoverable=False,
                    )
                    return

            # Fire pre_api_call hook
            self.hooks.fire("pre_api_call", {
                "messages": turn_messages,
                "system": system_prompt,
            })

            # Start turn budget tracking
            self.budget.start_turn()

            # Call LLM (with prompt-too-long recovery)
            tool_uses: list[ToolUse] = []
            full_text = ""
            _prompt_too_long = False

            try:
                async for event in self.provider.stream_response(
                    system=system_prompt,
                    messages=turn_messages,
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

            # Record real token usage from provider
            if hasattr(self.provider, "last_usage") and self.provider.last_usage:
                self.budget.record_usage(
                    self.provider.last_usage.get("input_tokens", 0),
                    self.provider.last_usage.get("output_tokens", 0),
                )

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

            # If no tool uses, check if model should continue or we are done
            if not tool_uses:
                # Check if model hit output limit and should be nudged to continue
                if self.budget.should_continue():
                    if full_text:
                        self._conversation_messages.append(
                            {"role": "assistant", "content": full_text}
                        )
                    self._conversation_messages.append({
                        "role": "user",
                        "content": (
                            "<system-reminder>Your response was cut off. "
                            "Please continue where you left off.</system-reminder>"
                        ),
                    })
                    continue  # run another turn

                # Save final assistant message to conversation history
                if full_text:
                    self._conversation_messages.append(
                        {"role": "assistant", "content": full_text}
                    )
                # Run stop hooks (memory extraction, session title, stats)
                try:
                    await self.stop_hooks.run_after_turn(
                        self._conversation_messages, turn + 1
                    )
                except Exception:
                    pass  # Stop hooks must never crash the agent
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

            # Execute tools -- async tools yield events, parallel when safe, sequential otherwise
            tool_results: list[dict] = []

            # Check if any tool in this batch is async (e.g. agent tool)
            has_async_tool = any(
                (t := self.tools.get(tu.tool_name)) and t.is_async()
                for tu in tool_uses
            )

            # Async tools force sequential execution (they yield events)
            parallel_safe = (
                len(tool_uses) > 1
                and not has_async_tool
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

                try:
                    completed = await asyncio.gather(*[_run_one(tu) for tu in tool_uses])
                except (KeyboardInterrupt, asyncio.CancelledError):
                    # Cancel cleanup: add cancel results for all tool calls
                    for tu in tool_uses:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.tool_id,
                            "content": "Tool call cancelled by user.",
                        })
                    if tool_results:
                        self._conversation_messages.append({"role": "user", "content": tool_results})
                    yield AgentError(error="Cancelled by user.", recoverable=False)
                    return

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
                # --- Sequential execution path (handles both sync and async tools) ---
                try:
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
                        if tool and tool.is_async():
                            # --- Async tool path: yield events from the generator ---
                            result = ""
                            success = True
                            try:
                                async for item in tool.async_execute(**tu.tool_input):
                                    if item["type"] == "event":
                                        # Forward subagent/child events to the parent's stream
                                        yield item["event"]
                                    elif item["type"] == "result":
                                        result = item["content"]
                            except Exception as e:
                                result = f"Error: {str(e)}"
                                success = False

                            if not result.startswith("Error"):
                                success = True
                            else:
                                success = False

                            yield ToolEnd(
                                tool_name=tu.tool_name,
                                result=result[:200],
                                success=success,
                            )

                        elif tool:
                            # --- Sync tool path: existing behavior ---
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
                except (KeyboardInterrupt, asyncio.CancelledError):
                    # Cancel cleanup: add cancel results for unprocessed tool calls
                    processed_ids = {r["tool_use_id"] for r in tool_results}
                    for tu in tool_uses:
                        if tu.tool_id not in processed_ids:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tu.tool_id,
                                "content": "Tool call cancelled by user.",
                            })
                    if tool_results:
                        self._conversation_messages.append({"role": "user", "content": tool_results})
                    yield AgentError(error="Cancelled by user.", recoverable=False)
                    return

            # Inject pending images from ReadTool as multimodal content
            read_tool = self.tools.get("read")
            if read_tool and hasattr(read_tool, "_pending_images") and read_tool._pending_images:
                for img in read_tool._pending_images:
                    tool_results.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img["media_type"],
                            "data": img["base64_data"],
                        },
                    })
                read_tool._pending_images.clear()

            messages.append({"role": "user", "content": tool_results})

            # Run stop hooks between turns (after tool results appended)
            try:
                await self.stop_hooks.run_after_turn(
                    self._conversation_messages, turn + 1
                )
            except Exception:
                pass  # Stop hooks must never crash the agent

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
