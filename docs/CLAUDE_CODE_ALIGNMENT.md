# Claude Code Alignment Report

Gap analysis between SaltAgent and Claude Code's actual implementation,
based on reading the Claude Code source tree at `~/Desktop/claude-code-info/`.

---

## 1. Query Loop (Claude Code `src/query/` -> SaltAgent `agent.py`)

**Claude Code has:**
- `query/config.ts` -- QueryConfig: immutable config snapshotted once at query() entry (session ID, feature gates for streaming tool execution, fast mode, etc.)
- `query/deps.ts` -- QueryDeps: injectable I/O dependencies (callModel, microcompact, autocompact, uuid). Tests inject fakes.
- `query/tokenBudget.ts` -- BudgetTracker: tracks token budget per turn with diminishing-returns detection. Nudges the model to continue if under 90% budget, stops if >3 continuations with <500 delta tokens.
- `query/stopHooks.ts` -- handleStopHooks: runs after each assistant turn. Fires Stop hooks, TeammateIdle hooks, TaskCompleted hooks. Also triggers memory extraction, auto-dream, prompt suggestion, and computer-use cleanup.

**SaltAgent has:**
- `agent.py` -- SaltAgent.run(): monolithic loop with inline config, no dependency injection, basic token estimation, no stop hooks, no turn-level budget tracking, no diminishing-returns detection.

**Gaps:**
1. **No dependency injection.** Claude Code separates deps (callModel, autocompact) so tests can inject fakes. SaltAgent's provider is the only injectable; tools, compaction, UUID generation are all inline.
2. **No token budget tracking.** Claude Code tracks per-turn token budgets and nudges the model to continue when under budget. SaltAgent only checks compaction threshold.
3. **No stop hooks.** Claude Code runs extensive post-turn hooks (memory extraction, dream consolidation, prompt suggestion). SaltAgent fires `on_complete` but nothing in between turns.
4. **No streaming tool execution.** Claude Code can execute tools while streaming the next response. SaltAgent waits for full response then executes tools.

**Changes needed:**
- Add `QueryConfig` equivalent (session gates, feature flags)
- Add `BudgetTracker` to nudge model on long tasks
- Add stop hooks that run between turns (memory extraction, at minimum)
- Consider dependency injection for testability

---

## 2. Tools (Claude Code `src/tools/` -> SaltAgent `tools/`)

**Claude Code tools (42 tool types):**
- Core: Bash, FileRead, FileWrite, FileEdit, Glob, Grep, NotebookEdit
- Agent/Team: AgentTool, SendMessage, TeamCreate, TeamDelete
- Planning: EnterPlanMode, ExitPlanMode, EnterWorktree, ExitWorktree
- Tasks: TaskCreate, TaskGet, TaskList, TaskOutput, TaskStop, TaskUpdate
- Config: ConfigTool, BriefTool, SkillTool, ToolSearchTool, SleepTool
- Web: WebFetch, WebSearch
- MCP: MCPTool, McpAuth, ListMcpResources, ReadMcpResource
- Special: AskUserQuestion, TodoWrite, RemoteTrigger, ScheduleCron, REPLTool, LSPTool, PowerShell, SyntheticOutput

**SaltAgent tools (14 tool types):**
- Core: Bash, Read, Write, Edit, MultiEdit, Glob, Grep, ListFiles
- Agent: AgentTool
- Git: GitStatus, GitDiff, GitCommit
- Web: WebFetch, WebSearch
- Other: TodoWrite

**Missing tools:**
1. **TaskCreate/TaskGet/TaskList/TaskUpdate/TaskStop/TaskOutput** -- Background task management. Claude Code can spawn tasks that run in parallel (shell, agent, remote agent, workflow, dream). Critical for multi-agent coordination.
2. **TeamCreate/TeamDelete/SendMessage** -- Team/swarm coordination. Allows the main agent to create teams of agents that communicate via messages.
3. **EnterPlanMode/ExitPlanMode** -- Structured plan mode as tool calls (not just config flags).
4. **EnterWorktree/ExitWorktree** -- Git worktree isolation for parallel work.
5. **ConfigTool** -- Runtime config changes from within the agent.
6. **SkillTool** -- Invoke skills (markdown-based prompt injection commands).
7. **ToolSearchTool** -- Deferred tool loading. Show tool summaries, fetch full schemas on demand. Reduces prompt size.
8. **SleepTool** -- Wait for background tasks.
9. **NotebookEdit** -- Jupyter notebook editing.
10. **LSPTool** -- Language Server Protocol diagnostics.
11. **ScheduleCronTool** -- Schedule recurring remote agents.
12. **AskUserQuestion** -- Structured question with preview/suggestions.
13. **RemoteTriggerTool** -- Trigger remote agents.

**Changes needed (priority order):**
1. TaskCreate/TaskList/TaskGet/TaskUpdate -- enables background agents
2. SkillTool + ToolSearchTool -- enables skills and deferred tools
3. EnterPlanMode/ExitPlanMode as tools (not just config)
4. AskUserQuestion -- structured interaction
5. SleepTool -- background task coordination
6. ConfigTool -- runtime config

---

## 3. Context Assembly (Claude Code `src/context/` -> SaltAgent `context.py`)

**Claude Code `src/context/`:**
This directory is actually React UI context providers (stats, voice, notifications, modals, mailbox, FPS metrics, prompt overlay, queued messages). NOT the context assembly system.

The actual context assembly in Claude Code lives in:
- `utils/attachments.ts` (3998 lines!) -- Manages system-reminder injections: TODO state, plan mode state, auto mode denials, relevant memories, MCP instructions, file modified warnings, skill invocations, git status, diagnostics, token usage, hook results, etc.
- `utils/systemPrompt.ts` -- Assembles the full system prompt each turn
- `utils/context.ts` -- Miscellaneous context helpers

**SaltAgent has:**
- `context.py` -- ContextManager: basic token estimation, file tracking, tool result truncation. 66 lines.
- `prompts/assembler.py` -- Static prompt composition from fragments.

**Gaps:**
1. **No dynamic per-turn attachments.** Claude Code injects system-reminders each turn with current state (todo, plan mode, memories, diagnostics, file changes, git status). SaltAgent only injects date/time/cwd.
2. **No attachment types.** Claude Code has ~30 attachment types (todo_reminder, plan_mode, relevant_memories, mcp_instructions, file_modified, git_status, new_diagnostics, hook_results, etc.).
3. **No system-reminder mechanism.** Claude Code uses `<system-reminder>` tags in user messages to inject dynamic context without counting against the conversation.
4. **No memory surfacing.** Claude Code finds relevant memories per-turn using an LLM side-query and injects them.

**Changes needed:**
1. Add system-reminder injection system (per-turn dynamic context)
2. Add memory surfacing (find relevant memories for current query)
3. Add git status injection
4. Add todo state injection (partially exists but basic)
5. Add file-modified-since-read detection and notification

---

## 4. Memory (Claude Code `src/memdir/` -> SaltAgent `memory.py`)

**Claude Code has:**
- `memdir/memdir.ts` (508 lines) -- MEMORY.md entrypoint (max 200 lines / 25KB), memory directory with typed files, search guidance
- `memdir/paths.ts` (279 lines) -- Auto memory paths, daily log paths, configurable override
- `memdir/memoryTypes.ts` (272 lines) -- 4 memory types: user, feedback, project, reference. Detailed prompts for what to save and what not to save.
- `memdir/findRelevantMemories.ts` (142 lines) -- LLM-powered memory relevance ranking per query
- `memdir/memoryScan.ts` (95 lines) -- Scan memory files, extract frontmatter headers
- `memdir/memoryAge.ts` (54 lines) -- Memory freshness tracking and drift caveats
- `memdir/teamMemPaths.ts` (293 lines) -- Team memory (shared across agents)
- `memdir/teamMemPrompts.ts` (101 lines) -- Combined memory prompts for teams
- `services/extractMemories/` -- Auto-extract memories from conversations
- `services/SessionMemory/` -- Session-level memory (compaction summaries)
- `services/autoDream/` -- Consolidate memories during idle time

**SaltAgent has:**
- `memory.py` -- MemorySystem: 73 lines. Loads SALT.md/CLAUDE.md, basic MEMORY.md index, save/load memory files. No types, no relevance ranking, no extraction, no consolidation.

**Gaps:**
1. **No memory types.** Claude Code has user/feedback/project/reference types with specific save/don't-save guidelines. SaltAgent has flat files.
2. **No memory relevance ranking.** Claude Code uses an LLM side-query to select which memories to surface. SaltAgent loads everything or nothing.
3. **No auto memory extraction.** Claude Code auto-extracts memories after each turn. SaltAgent requires explicit save.
4. **No memory consolidation (auto-dream).** Claude Code consolidates memories during idle time.
5. **No daily log.** Claude Code maintains a daily activity log in memory.
6. **No memory freshness/drift tracking.** Claude Code warns about stale memories.
7. **No frontmatter parsing.** Claude Code uses YAML frontmatter for memory metadata.

**Changes needed (priority order):**
1. Add memory types (user, feedback, project, reference) with frontmatter
2. Add memory relevance ranking (LLM side-query)
3. Add auto memory extraction (post-turn hook)
4. Add daily activity log
5. Add memory freshness tracking

---

## 5. Commands/Slash Commands (Claude Code `src/commands/` -> SaltAgent `cli.py`)

**Claude Code has 86+ slash commands organized in directories**, including:
- Session: /clear, /compact, /resume, /session, /export, /share
- Code: /commit, /diff, /branch, /review, /pr_comments
- Planning: /plan, /ultraplan
- Config: /config, /model, /effort, /fast, /permissions, /sandbox-toggle
- Memory: /memory
- Tools: /mcp, /hooks, /skills, /plugin, /reload-plugins
- Agents: /agents, /tasks
- Debug: /doctor, /stats, /cost, /usage, /status, /debug-tool-call
- Navigation: /add-dir, /files, /context
- Special: /init, /help, /version, /upgrade, /feedback, /login, /logout

**SaltAgent has ~15 slash commands** (inline in cli.py):
- /help, /clear, /compact, /status, /model, /auto, /plan, /approve, /tools, /sessions, /resume, /search, /rewind, /export, /quit

**Missing commands:**
1. /commit, /diff, /review -- Git workflow
2. /memory -- Memory management
3. /skills -- Skill management
4. /mcp -- MCP server management
5. /hooks -- Hook management
6. /config -- Runtime config
7. /context -- View current context
8. /doctor -- Diagnostic checks
9. /cost, /usage, /stats -- Usage tracking
10. /init -- Initialize project (create CLAUDE.md)
11. /add-dir -- Add directories to context

**Changes needed:**
1. Add /commit, /diff (leverage existing git tools)
2. Add /memory (manage memory files)
3. Add /init (create SALT.md/CLAUDE.md)
4. Add /context (show current context window state)
5. Add /cost (track API usage)

---

## 6. Hooks (Claude Code `utils/hooks.ts` -> SaltAgent `hooks.py`)

**Claude Code hook events (5023 lines, 51 exports!):**
- PreToolUse, PostToolUse, PostToolUseFailure, PermissionDenied
- Stop, SubagentStop, StopFailure
- TeammateIdle, TaskCreated, TaskCompleted
- UserPromptSubmit
- SessionStart, SessionEnd, Setup
- SubagentStart
- PreCompact, PostCompact
- PermissionRequest
- ConfigChange, CwdChanged, FileChanged
- InstructionsLoaded
- Elicitation, ElicitationResult
- StatusLine, FileSuggestion
- WorktreeCreate, WorktreeRemove
- Notification

Hook types: command (shell), prompt (LLM), http (webhook), agent (spawn agent), function (callback)

**SaltAgent hook events (78 lines, 9 events):**
- pre_tool_use, post_tool_use, pre_api_call, post_api_call
- on_text_chunk, on_error, on_complete, on_compaction, on_permission_request

**Gaps:**
1. **Missing lifecycle hooks:** SessionStart, SessionEnd, Setup, SubagentStart
2. **Missing compaction hooks:** PreCompact, PostCompact
3. **Missing file hooks:** FileChanged, CwdChanged
4. **Missing config hooks:** ConfigChange, InstructionsLoaded
5. **Missing team hooks:** TeammateIdle, TaskCreated, TaskCompleted
6. **No hook types.** Claude Code supports shell command hooks, LLM prompt hooks, HTTP webhook hooks, agent hooks, and function callbacks. SaltAgent only has function callbacks.
7. **No hook configuration.** Claude Code loads hooks from settings.json. SaltAgent only supports programmatic registration.
8. **No blocking error aggregation.** Claude Code hooks can return blocking errors, modify inputs, prevent continuation.

**Changes needed:**
1. Add SessionStart, SessionEnd hooks (fire at session boundaries)
2. Add PreCompact, PostCompact hooks
3. Add shell command hook type (run arbitrary commands on events)
4. Add hook configuration from settings file
5. Add SubagentStart hook

---

## 7. Session Storage (Claude Code `utils/sessionStorage.ts` -> SaltAgent `persistence.py`)

**Claude Code has (5106 lines!):**
- JSONL transcript files per session
- Project-scoped session directories
- Agent metadata (per-subagent)
- Remote agent metadata
- Session title generation
- Cross-project resume
- Concurrent session detection
- Session search
- Internal event reader/writer
- File history tracking
- Tool result storage (separate from transcript)
- Transcript sanitization

**SaltAgent has (119 lines):**
- JSONL session files with checkpoints
- Session listing
- Last checkpoint loading
- Basic search

**Gaps:**
1. **No project-scoped sessions.** Claude Code stores sessions per project. SaltAgent uses a flat directory.
2. **No transcript vs checkpoint separation.** Claude Code writes BEFORE the API call (crash safety) with full message transcript. SaltAgent writes checkpoints.
3. **No concurrent session detection.** Claude Code detects and warns about multiple sessions.
4. **No tool result storage.** Claude Code stores large tool results separately to keep transcripts small.
5. **No session title generation.** Claude Code auto-generates meaningful session titles.

**Changes needed:**
1. Project-scoped session directories
2. Write transcript BEFORE API calls (already partially done)
3. Session title generation
4. Tool result storage (offload large results)

---

## 8. Compaction (Claude Code `services/compact/` -> SaltAgent `compaction.py`)

**Claude Code has (11 files, 3971 lines):**
- `compact.ts` (1706 lines) -- Full compaction: strip images, build post-compact messages, file restoration, skill restoration, plan restoration, async agent attachments
- `autoCompact.ts` -- Auto-compact thresholds, warning states, buffer tokens
- `microCompact.ts` -- Micro-compaction: time-based triggers, cache-friendly edits
- `sessionMemoryCompact.ts` -- Session memory compaction variant
- `prompt.ts` -- Compaction prompts: partial and full
- `grouping.ts` -- Group messages by API round
- `apiMicrocompact.ts` -- API-level context management
- `postCompactCleanup.ts` -- Post-compact cleanup

**SaltAgent has (215 lines):**
- Basic compaction: keep last 2 messages, summarize rest with LLM
- Post-compact file restoration (up to 5 files, 50K budget)
- Analysis scratchpad stripping

**Gaps:**
1. **No micro-compaction.** Claude Code has time-based micro-compaction that removes stale cache entries between turns.
2. **No partial compaction.** Claude Code can compact just the oldest messages, keeping recent ones intact.
3. **No session memory compaction.** Claude Code has a separate compaction mode that preserves session memory.
4. **No plan/skill/async-agent restoration.** Claude Code restores plan state, active skills, and async agent state after compaction.
5. **No API-round grouping.** Claude Code groups messages by API round for smarter compaction.
6. **No post-compact hooks.** Claude Code fires PreCompact/PostCompact hooks.

**Changes needed:**
1. Add partial compaction (compact oldest messages, keep recent)
2. Add post-compact restoration of plan state, todo state, skill state
3. Add PreCompact/PostCompact hook firing
4. Add micro-compaction (optional, for long sessions)

---

## 9. Coordinator Mode (Claude Code `src/coordinator/`)

**Claude Code has:**
- `coordinatorMode.ts` -- Special mode where the main agent becomes a coordinator that only delegates to workers. Strips write tools, keeps only team/task/message tools. Custom system prompt focused on delegation.

**SaltAgent:** No equivalent. The agent always has all tools.

**Changes needed:** Consider adding a coordinator mode where the main agent delegates all coding to subagents (like the existing subagent system but formalized).

---

## 10. Services (Claude Code `src/services/`)

**Claude Code services (20 subdirectories):**
- `api/` -- Claude API client with retry, streaming, error handling
- `compact/` -- Compaction (covered above)
- `mcp/` -- MCP server management (23 files)
- `analytics/` -- Telemetry, feature gates
- `plugins/` -- Plugin installation, management
- `tools/` -- Tool execution service, streaming executor, hooks
- `lsp/` -- Language Server Protocol integration
- `extractMemories/` -- Auto memory extraction
- `autoDream/` -- Memory consolidation
- `SessionMemory/` -- Session-level memory
- `tips/` -- User tips system
- `PromptSuggestion/` -- Suggest next prompts
- `oauth/` -- OAuth flows
- `MagicDocs/` -- Documentation generation
- `AgentSummary/` -- Agent summary generation
- `toolUseSummary/` -- Tool use summarization
- `remoteManagedSettings/` -- Remote settings sync
- `teamMemorySync/` -- Team memory synchronization

**SaltAgent:** Services are inlined into the agent loop. No separate service layer.

**Changes needed (priority order):**
1. Extract tool execution into a service (enables streaming execution)
2. Add memory extraction service
3. Add prompt suggestion service (optional)

---

## 11. Skills (Claude Code `src/skills/`)

**Claude Code has:**
- Skills are markdown files with YAML frontmatter that define: name, description, trigger conditions, and prompt content
- Skills are loaded from: user skills dir, project skills dir, managed skills, plugins, bundled, MCP
- Conditional activation based on file paths
- SkillTool invokes skills by name
- Bundled skills: commit, review-pr, update-config, keybindings, simplify, loop, schedule, etc.
- Skills have token budgets and frontmatter estimation

**SaltAgent:** No skill system. Prompts are hardcoded Python constants.

**Changes needed:**
1. Add skill file format (markdown with frontmatter)
2. Add skill loading from directories
3. Add SkillTool to invoke skills
4. Port bundled skills (commit, review-pr, simplify)

---

## 12. Tasks (Claude Code `src/tasks/`)

**Claude Code task types:**
- LocalShellTask -- Background shell command
- LocalAgentTask -- Background agent (subagent)
- RemoteAgentTask -- Remote agent (runs on server)
- InProcessTeammateTask -- In-process teammate agent
- DreamTask -- Memory consolidation background task
- LocalWorkflowTask -- Multi-step workflow
- MonitorMcpTask -- Monitor MCP server
- LocalMainSessionTask -- The main interactive session

**SaltAgent:** No task system. Subagents are fire-and-forget, no tracking.

**Changes needed:**
1. Add task types (shell, agent, at minimum)
2. Add TaskCreate/TaskList/TaskGet tools
3. Add task status tracking
4. Add main session task registration

---

## 13. State (Claude Code `src/state/`)

**Claude Code has:**
- `AppState` -- Central state store with: messages, tool permission context, completion boundary, speculation state, footer items, focused agent, plan mode state
- `AppStateStore` -- Typed store with getState/setState
- `selectors.ts` -- Derived state (active agent, viewed teammate)
- `store.ts` -- Generic reactive store
- `onChangeAppState.ts` -- State change handlers
- `teammateViewHelpers.ts` -- Teammate view state management

**SaltAgent:** State is scattered across agent instance attributes. No centralized state store.

**Changes needed:**
1. Consider a centralized state object (not critical for CLI, more important for UI integration)
2. At minimum, formalize the agent's current state (mode, permissions, active tasks, etc.)

---

## Priority Order for Closing Gaps

### P0 -- Critical (fundamentally different from Claude Code)
1. **Memory types + relevance ranking** -- Claude Code's memory system is vastly more sophisticated
2. **Stop hooks / post-turn hooks** -- Memory extraction, cleanup
3. **Skills system** -- Markdown-based extensible prompts
4. **Dynamic per-turn context injection** -- system-reminders

### P1 -- Important (significant feature gaps)
5. **Task system** -- Background task management
6. **Token budget tracking** -- Diminishing returns detection
7. **Partial compaction** -- Smarter compaction
8. **SkillTool + ToolSearchTool** -- Deferred tool loading
9. **More slash commands** -- /commit, /memory, /init, /context

### P2 -- Nice to have (polish)
10. **Shell command hooks** -- Configurable hooks from settings
11. **Project-scoped sessions** -- Better session organization
12. **Session title generation** -- Auto-naming sessions
13. **Micro-compaction** -- Time-based cache management
14. **Coordinator mode** -- Delegation-only mode
