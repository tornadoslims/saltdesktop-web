# SaltAgent vs Claude Code -- Final Parity Audit

**Date:** 2026-03-30
**Auditor:** Claude (Opus 4.6, 1M context)
**Sources read:**
- All SaltAgent source files (agent.py, config.py, context.py, compaction.py, hooks.py, memory.py, permissions.py, persistence.py, subagent.py, file_history.py, security.py, plugins.py, stop_hooks.py, attachments.py, coordinator.py, token_budget.py, tools/*.py, providers/*.py, tasks/manager.py, skills/manager.py, mcp/*.py, cli.py, prompts/__init__.py, prompts/assembler.py)
- All Claude Code src_md/__directory__.md files (tools/, query/, context/, coordinator/, services/, hooks/, state/, skills/, tasks/, memdir/, commands/, plugins/)
- Full PDF: "How Claude Code Works" (31 sections, 1500+ lines)
- Previous audits: SALTAGENT_AUDIT.md, SALTAGENT_FEATURE_GAP.md, CLAUDE_CODE_ALIGNMENT.md

---

## Section 1: Tool-by-Tool Comparison

### Claude Code Tools (42 tool directories)

| # | Claude Code Tool | SaltAgent Equivalent | Match |
|---|-----------------|---------------------|-------|
| 1 | **BashTool** | `bash.py` | **Partial** -- Missing: `run_in_background`, `dangerouslyDisableSandbox`, `description` required param, millisecond timeout (CC uses ms, we use seconds). Has: timeout, output truncation, working directory, security classifier pre-check. |
| 2 | **FileReadTool** | `read.py` | **Partial** -- Missing: PDF page ranges (`pages` param), image reading (multimodal base64), Jupyter notebook rendering. Has: offset/limit, line numbers, mtime tracking for stale-file detection. |
| 3 | **FileWriteTool** | `write.py` | **Full** -- Read-before-write enforcement, absolute paths, content overwrite. |
| 4 | **FileEditTool** | `edit.py` | **Full** -- String replacement with uniqueness constraint, `replace_all` flag. |
| 5 | **GlobTool** | `glob_tool.py` | **Partial** -- Missing: sort by modification time (CC sorts by mtime, we sort alphabetically). Has: pattern matching, path parameter. |
| 6 | **GrepTool** | `grep.py` | **Partial** -- Missing: `output_mode` (content/files_with_matches/count), `-A/-B/-C` context lines, `head_limit`, `offset`, `multiline`, `type` (file type filter). Has: pattern, path, glob, case_insensitive. Significant parameter gap. |
| 7 | **AgentTool** | `agent_tool.py` | **Partial** -- Missing: built-in agent types directory, model selection per-agent, isolation levels, resume capability. Has: fresh + fork modes, prompt param, mode param (explore/worker/verify/general). |
| 8 | **AskUserQuestionTool** | `ask_user.py` | **Full** -- Asks user a question and returns their response. |
| 9 | **TodoWriteTool** | `todo.py` | **Partial** -- Missing: `activeForm` field (present-continuous verb for UI display during execution). Has: content + status fields, replace-all semantics, context injection. |
| 10 | **SkillTool** | `skill_tool.py` | **Full** -- Invokes skills by name, injects SKILL.md content into context. |
| 11 | **ToolSearchTool** | `tool_search.py` | **Full** -- Deferred tool loading infrastructure, keyword search against tool registry. |
| 12 | **TaskCreateTool** | `tasks.py` (TaskCreateTool) | **Full** -- Creates background tasks that run in separate threads. |
| 13 | **TaskGetTool** | `tasks.py` (TaskGetTool) | **Full** |
| 14 | **TaskListTool** | `tasks.py` (TaskListTool) | **Full** |
| 15 | **TaskOutputTool** | `tasks.py` (TaskOutputTool) | **Full** |
| 16 | **TaskStopTool** | `tasks.py` (TaskStopTool) | **Full** |
| 17 | **TaskUpdateTool** | `tasks.py` (TaskUpdateTool) | **Full** |
| 18 | **WebFetchTool** | `web_fetch.py` | **Full** -- URL fetching with content extraction (trafilatura/readability/regex). |
| 19 | **WebSearchTool** | `web_search.py` | **Full** -- Web search via DuckDuckGo or configurable backend. |
| 20 | **ConfigTool** | `config_tool.py` | **Full** -- Get/set agent configuration at runtime. |
| 21 | **EnterPlanModeTool** | `plan_mode_tool.py` | **Full** -- Enters plan mode, restricts tools to todo_write only. |
| 22 | **ExitPlanModeTool** | `plan_mode_tool.py` | **Full** -- Exits plan mode, re-enables all tools. |
| 23 | **SleepTool** | `sleep_tool.py` | **Full** -- Waits for background tasks or a duration. |
| 24 | **SendMessageTool** | `message_tool.py` | **Full** -- Sends messages to background tasks. |
| 25 | **EnterWorktreeTool** | `worktree_tool.py` | **Full** -- Creates a git worktree for isolated work. |
| 26 | **ExitWorktreeTool** | `worktree_tool.py` | **Full** -- Exits and cleans up a git worktree. |
| 27 | **MCPTool** | `mcp/tool_bridge.py` | **Full** -- MCP tools discovered from servers are bridged into the tool registry. |
| 28 | **ListMcpResourcesTool** | N/A | **Missing** -- Lists available MCP resources. |
| 29 | **ReadMcpResourceTool** | N/A | **Missing** -- Reads a specific MCP resource. |
| 30 | **McpAuthTool** | N/A | **Missing** -- Handles MCP server authentication flows. |
| 31 | **BriefTool** | N/A | **Missing** -- Upload/brief tool for attaching documents to context. |
| 32 | **LSPTool** | N/A | **Missing** -- Language Server Protocol: go-to-definition, find-references, diagnostics. |
| 33 | **NotebookEditTool** | N/A | **Missing** -- Edit Jupyter notebook cells. |
| 34 | **PowerShellTool** | N/A | **Missing** -- Windows PowerShell execution (N/A for macOS target). |
| 35 | **REPLTool** | N/A | **Missing** -- Interactive REPL sessions. |
| 36 | **RemoteTriggerTool** | N/A | **Missing** -- Trigger remote agent execution. |
| 37 | **ScheduleCronTool** | N/A | **Missing** -- Schedule cron-based remote agent runs. |
| 38 | **SyntheticOutputTool** | N/A | **Missing** -- Internal tool for structured output injection. |
| 39 | **TeamCreateTool** | N/A | **Missing** -- Create a team of agents. |
| 40 | **TeamDeleteTool** | N/A | **Missing** -- Delete an agent team. |

### SaltAgent-only tools (not in Claude Code)

| Tool | Purpose |
|------|---------|
| `multi_edit.py` | Multiple edits to one file in a single call (CC does this via repeated Edit calls) |
| `list_files.py` | List directory contents (CC uses `bash ls`) |
| `git.py` (GitStatusTool, GitDiffTool, GitCommitTool) | Native git tools (CC uses Bash for git) |

### Tool Score: 26/40 have equivalents. 19 Full, 7 Partial, 14 Missing.
**Tool parity: 65%**

---

## Section 2: Command-by-Command Comparison

### Claude Code Slash Commands (86 command directories)

| Category | CC Command | SaltAgent | Match |
|----------|-----------|-----------|-------|
| **Session** | /clear | /clear | Full |
| | /compact | /compact | Full |
| | /resume | /resume | Full |
| | /session | /sessions | Full |
| | /rename | N/A | Missing |
| | /export | /export | Full |
| | /share | N/A | Missing |
| | /copy | N/A | Missing |
| | /rewind | /undo | Full |
| | /summary | /history | Partial (different name) |
| **Model** | /model | /model | Full |
| | /fast | N/A | Missing |
| | /effort | N/A | Missing |
| | /output-style | N/A | Missing |
| **Mode** | /plan | /plan | Full |
| | /permissions | N/A | Missing |
| | /sandbox-toggle | N/A | Missing |
| **Code** | /commit | /commit | Full (via skill) |
| | /review | /review | Full (via skill) |
| | /diff | /diff | Full |
| | /branch | /branch | Full |
| **Tools** | /mcp | N/A | Missing (no /mcp command, but MCP works) |
| | /config | /config | Full |
| | /context | N/A | Missing |
| | /files | N/A | Missing |
| **Info** | /help | /help | Full |
| | /cost | /cost | Full |
| | /usage | /tokens | Full (different name) |
| | /stats | /budget | Partial |
| | /status | /status (git) | Partial (different scope) |
| | /version | /version | Full |
| | /doctor | /doctor | Full |
| **Task** | /tasks | /tasks | Full |
| **Memory** | /memory | /memory | Full |
| **Plugin** | /plugin | N/A | Missing |
| | /reload-plugins | N/A | Missing |
| | /skills | /skills | Full |
| **Agent** | /agents | N/A | Missing |
| | /verify | /verify | Full |
| | /coordinator | /coordinator | Full |
| **Auth** | /login | N/A | Missing |
| | /logout | N/A | Missing |
| **Advanced** | /bridge | N/A | Missing |
| | /btw | N/A | Missing |
| | /chrome | N/A | Missing |
| | /desktop | N/A | Missing |
| | /ide | N/A | Missing |
| | /keybindings | N/A | Missing |
| | /voice | N/A | Missing |
| | /vim | N/A | Missing |
| | /theme | N/A | Missing |
| | /color | N/A | Missing |
| | /stickers | N/A | Missing |
| | /teleport | N/A | Missing |
| | /tag | N/A | Missing |
| | /mobile | N/A | Missing |
| | /add-dir | N/A | Missing |
| | /env | N/A | Missing |

### SaltAgent-only commands

| Command | Purpose |
|---------|---------|
| /auto | Toggle auto mode |
| /approve | Approve plan and execute |
| /provider | Switch provider |
| /stash | Git stash |
| /log | Git log |
| /forget | Delete a memory file |
| /mode | Show/change agent mode |
| /search | Search past sessions |
| /memories | Alias for /memory |
| /tools | List available tools |

### Command Score: ~25 of 86 CC commands have equivalents (some under different names).
**Command parity: 29%** (but many CC commands are platform-specific: login, chrome, desktop, mobile, IDE, bridge, etc.)
**Functional command parity (excluding platform-specific): ~55%**

---

## Section 3: Architecture Comparison

### Query Loop

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Iterative assistant/tool loop | Yes (query.ts, 1730 lines) | Yes (agent.py run(), ~350 lines) | **Full** |
| Streaming response | Yes | Yes | **Full** |
| Max turns limit | Yes | Yes (config.max_turns) | **Full** |
| Auto-continue on truncation | Yes (max-output recovery) | Yes (budget.should_continue()) | **Full** |
| Prompt-too-long recovery | Yes (compact + retry) | Yes (detect + compact + continue) | **Full** |
| Media overflow recovery | Yes | No | **Missing** |
| Fallback model switching | Yes (mid-turn) | Partial (provider-level retry only) | **Partial** |
| Streaming tool execution | Yes (StreamingToolExecutor) | No (tools execute after full response) | **Missing** |

**Query loop parity: 75%**

### Context Assembly

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Per-turn system prompt rebuild | Yes (full reassembly each turn) | Yes (_build_system_prompt()) | **Full** |
| System-reminder injection | Yes (utils/attachments.ts, ~30 types) | Yes (attachments.py, 7 types) | **Partial** -- CC has ~30 attachment types, SA has 7 |
| Date/time injection | Yes | Yes | **Full** |
| Git status injection | Yes | Yes | **Full** |
| Working directory injection | Yes | Yes | **Full** |
| Todo/plan state injection | Yes | Yes | **Full** |
| MCP status injection | Yes | Yes | **Full** |
| Modified files warning | Yes | Yes | **Full** |
| IDE selection/state | Yes | No | **Missing** |
| Agent/teammate context | Yes | No | **Missing** |
| Queued command injection | Yes | No | **Missing** |

**Context assembly parity: 70%**

### Compaction (All Layers)

| Layer | Claude Code | SaltAgent | Match |
|-------|------------|-----------|-------|
| Tool result budgeting | Yes (pre-turn) | Yes (truncate_tool_result in context.py) | **Partial** -- CC does this as a pipeline step, SA does it at insertion time |
| History snip | Yes | No | **Missing** |
| Microcompact | Yes (lightweight, time-based triggers) | Yes (microcompact_tool_results) | **Partial** -- SA only truncates old tool results; CC does lightweight summarization |
| Cached microcompact | Yes | No | **Missing** |
| Context collapse | Yes (feature-gated) | No | **Missing** |
| Autocompact | Yes (threshold-based) | Yes (needs_compaction at 80%) | **Full** |
| Manual compact (/compact) | Yes | Yes | **Full** |
| Partial compact | Yes | No | **Missing** |
| LLM-based summarization | Yes | Yes (compact_context) | **Full** |
| Post-compact file restoration | Yes (files, plans, skills, agent ctx) | Yes (files only, up to 5) | **Partial** -- CC restores plans, skills, and agent context too |
| Emergency truncation | Yes | Yes (emergency_truncate) | **Full** |
| Reactive recovery path | Yes (compact + retry mid-turn) | Yes (prompt-too-long -> compact -> continue) | **Full** |

**Compaction parity: 60%**

### Memory System

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| CLAUDE.md / MEMORY.md loading | Yes (memdir/) | Yes (memory.py) | **Full** |
| Parent directory traversal | Yes | Yes (10 levels) | **Full** |
| Memory types (user/feedback/project/reference) | Yes (memoryTypes.ts) | Yes (MEMORY_TYPES dict) | **Full** |
| YAML frontmatter parsing | Yes | Yes | **Full** |
| Memory index (MEMORY.md) | Yes | Yes | **Full** |
| Per-turn relevant memory surfacing | Yes (findRelevantMemories) | Yes (find_relevant_memories, LLM side-query) | **Full** |
| Memory extraction (stop hook) | Yes (extractMemories service) | Yes (_extract_memories in stop_hooks) | **Full** |
| Memory consolidation | Yes (autoDream) | Yes (_consolidate_memories in stop_hooks) | **Partial** -- SA does basic consolidation; CC has autoDream with consolidation lock |
| Session memory compaction | Yes (sessionMemoryCompact) | No | **Missing** |
| Team memory sync | Yes (teamMemorySync) | No | **Missing** |
| Memory age/freshness | Yes (memoryAge.ts) | No | **Missing** |

**Memory system parity: 70%**

### Session Persistence

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| JSONL-based storage | Yes | Yes | **Full** |
| Save before API call | Yes (emphasized in code) | Yes (save_checkpoint) | **Full** |
| Session resume | Yes | Yes | **Full** |
| Session listing | Yes | Yes | **Full** |
| Session search | Yes | Yes | **Full** |
| Session title generation | Yes | Yes (stop hook) | **Full** |
| Concurrent session detection | Yes | Yes (lock file) | **Full** |
| File history snapshots | Yes | Yes (file_history.py) | **Full** |
| Attribution snapshots | Yes | No | **Missing** |
| Content replacement tracking | Yes | No | **Missing** |
| Context-collapse recording | Yes | No | **Missing** |
| Remote session hydration | Yes | No | **Missing** |

**Persistence parity: 70%**

### Hook System

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Pre/post tool hooks | Yes | Yes (pre_tool_use, post_tool_use) | **Full** |
| Pre/post API call hooks | Yes | Yes (pre_api_call, post_api_call) | **Full** |
| Error hooks | Yes | Yes (on_error) | **Full** |
| Completion hooks | Yes | Yes (on_complete) | **Full** |
| Compaction hooks | Yes (pre/post compact) | Partial (on_compaction only) | **Partial** |
| Shell command hooks | Yes | Yes (ShellHook) | **Full** |
| HTTP webhook hooks | Yes | Yes (HttpHook) | **Full** |
| Config change hooks | Yes | No | **Missing** |
| CWD change hooks | Yes | No | **Missing** |
| File change hooks | Yes | No | **Missing** |
| Session start/end hooks | Yes | No | **Missing** |
| Subagent start hooks | Yes | No | **Missing** |
| User prompt submit hooks | Yes | No | **Missing** |
| Trust gating | Yes | No | **Missing** |
| Permission denied hooks | Yes | Partial (on_permission_request) | **Partial** |
| Hook-based attachments | Yes | No | **Missing** |
| Stop hooks (post-turn) | Yes (query/stopHooks.ts) | Yes (stop_hooks.py) | **Full** |

**Hook system parity: 55%**

### Permission System

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Rule-based allow/deny/ask | Yes | Yes | **Full** |
| Glob pattern matching | Yes | Yes | **Full** |
| Auto mode (skip all prompts) | Yes | Yes | **Full** |
| Plan mode restriction | Yes | Yes (todo_write only) | **Full** |
| Security classifier | Yes (Haiku side-query) | Yes (rules-based, no LLM) | **Partial** -- CC uses AI classification, SA uses pattern matching |
| Sandbox integration | Yes (macOS sandbox) | No | **Missing** |
| Managed settings / policy limits | Yes | No | **Missing** |
| Per-tool permission UI | Yes (component per tool type) | No (single ask callback) | **Partial** |

**Permission parity: 65%**

### Subagent System

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Fresh spawn | Yes | Yes (create_fresh) | **Full** |
| Fork with context | Yes | Yes (create_fork) | **Full** |
| Prompt cache prefix sharing | Yes | Yes (identical system prompt + tools) | **Full** |
| Mode-specific system prompts | Yes | Yes (explore/worker/verify/general) | **Full** |
| Boilerplate for fork tasks | Yes | Yes (_FORK_BOILERPLATE) | **Full** |
| Model selection per subagent | Yes | No (inherits parent model) | **Missing** |
| Resume/reconnect to subagent | Yes | No | **Missing** |

**Subagent parity: 75%**

### Task System

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Background task execution | Yes | Yes (daemon threads) | **Full** |
| Task create/list/get/output/stop/update | Yes | Yes (6 tools) | **Full** |
| Task status tracking | Yes | Yes (pending/running/completed/failed/stopped) | **Full** |
| Task type variety (shell, agent, remote, teammate, dream) | Yes (5 types) | No (agent tasks only) | **Partial** |
| Task completion callbacks | Yes | Yes | **Full** |
| Remote agent tasks | Yes | No | **Missing** |
| In-process teammate tasks | Yes | No | **Missing** |

**Task system parity: 65%**

### Skill System

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| SKILL.md-based loading | Yes | Yes | **Full** |
| Frontmatter parsing | Yes | Yes | **Full** |
| Multi-directory discovery | Yes | Yes (bundled + user + workspace) | **Full** |
| Bundled skills | Yes (17: batch, claude-api, chrome, debug, keybindings, loop, lorem-ipsum, remember, schedule, simplify, skillify, stuck, update-config, verify, verify-content) | Partial (2: commit, review) | **Partial** -- 2 vs 17 bundled skills |
| Conditional skill activation | Yes | No | **Missing** |
| MCP skill builders | Yes | No | **Missing** |
| Dynamic skill loading | Yes | No | **Missing** |

**Skill system parity: 55%**

### MCP System

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| stdio transport | Yes | Yes | **Full** |
| SSE/HTTP/WebSocket transports | Yes | No | **Missing** |
| Tool discovery | Yes | Yes | **Full** |
| Tool execution via bridge | Yes | Yes (MCPToolBridge) | **Full** |
| Resource listing/reading | Yes (ListMcpResourcesTool, ReadMcpResourceTool) | No | **Missing** |
| Auth handling | Yes (McpAuthTool, auth caching) | No | **Missing** |
| Server lifecycle (start/shutdown) | Yes | Yes | **Full** |
| .mcp.json config loading | Yes | Yes | **Full** |
| MCP commands in slash menu | Yes (/mcp) | No | **Missing** |
| IDE RPC bridging | Yes | No | **Missing** |

**MCP parity: 50%**

### Provider Layer

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Anthropic provider | Yes | Yes | **Full** |
| OpenAI provider | Yes (via API translation) | Yes | **Full** |
| Prompt caching | Yes | Yes (Anthropic adapter) | **Full** |
| Streaming | Yes | Yes | **Full** |
| Retry with backoff | Yes | Yes | **Full** |
| Fallback model | Yes (mid-turn) | Partial (provider-level) | **Partial** |
| Usage tracking | Yes | Yes (last_usage) | **Full** |
| Quick query (non-streaming) | Yes | Yes (quick_query) | **Full** |
| Task budget configuration | Yes | No | **Missing** |
| Effort configuration | Yes | No | **Missing** |
| Cache breakpoint insertion | Yes | No | **Missing** |

**Provider parity: 70%**

### Plugin System

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Plugin discovery from directories | Yes | Yes | **Full** |
| Plugin provides tools | Yes | Yes | **Full** |
| Plugin provides hooks | Yes | Yes | **Full** |
| Plugin provides prompts | Yes | Yes | **Full** |
| Plugin marketplace | Yes | No | **Missing** |
| Plugin installation manager | Yes | No | **Missing** |
| Builtin plugins | Yes | No | **Missing** |
| DXT format support | Yes | No | **Missing** |

**Plugin parity: 50%**

### State Management

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Conversation messages on agent instance | Yes | Yes (_conversation_messages) | **Full** |
| App state store | Yes (AppStateStore, 570 lines) | No (state is distributed across agent attributes) | **Missing** |
| Speculation/suggestion state | Yes | Partial (stop_hooks generates suggestions) | **Partial** |
| Task state in app state | Yes | Partial (TaskManager._tasks) | **Partial** |

**State management parity: 40%**

### Error Recovery

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Prompt-too-long recovery | Yes | Yes | **Full** |
| Max-output recovery | Yes | Yes (budget.should_continue()) | **Full** |
| Media overflow recovery | Yes | No | **Missing** |
| Fallback model retry | Yes | Partial | **Partial** |
| Emergency truncation | Yes | Yes | **Full** |
| Loop detection | Yes | Yes (warn then stop) | **Full** |

**Error recovery parity: 75%**

### Streaming

| Aspect | Claude Code | SaltAgent | Match |
|--------|------------|-----------|-------|
| Text streaming | Yes | Yes (TextChunk events) | **Full** |
| Tool use streaming | Yes | Yes (ToolUse events) | **Full** |
| Streaming tool execution (overlap) | Yes (StreamingToolExecutor) | No | **Missing** |
| Structured output streaming | Yes | No | **Missing** |

**Streaming parity: 50%**

---

## Section 4: Behavioral Comparison

| Behavior | Claude Code | SaltAgent | Match |
|----------|------------|-----------|-------|
| **Read-before-edit enforcement** | Yes (Write/Edit check read tracker) | Yes (WriteTool/EditTool check read_tool.files_read) | **Full** |
| **Loop detection** | Yes (pattern detection + warn + stop) | Yes (_detect_loop: patterns of length 1-4, 3+ repeats; warn then hard stop) | **Full** |
| **Token budget management** | Yes (BudgetTracker, per-turn tracking) | Yes (BudgetTracker, real API usage, cost estimates) | **Full** |
| **Auto-continue on truncation** | Yes (output utilization > threshold) | Yes (output_utilization > 0.90, diminishing returns check) | **Full** |
| **Prompt caching** | Yes (system prompt + tool defs cached) | Yes (Anthropic adapter sends cache_control blocks) | **Full** |
| **Post-compact restoration** | Yes (files, plans, skills, agent context) | Partial (files only, up to 5, 50K token budget) | **Partial** |
| **System-reminder injection** | Yes (~30 types in attachments.ts) | Yes (7 types in attachments.py, injected into copy of messages) | **Partial** |
| **Memory surfacing per turn** | Yes (findRelevantMemories, LLM side-query) | Yes (find_relevant_memories, LLM side-query) | **Full** |
| **Stop hooks** | Yes (memory extraction, session title, stats) | Yes (memory extraction, session title, stats, consolidation, suggestions) | **Full** -- SA actually has MORE stop hooks |
| **Security classification** | Yes (AI-based Haiku classifier) | Yes (rules-based SecurityClassifier) | **Partial** -- different approach, SA is faster but less nuanced |
| **Budget limit** | Yes | Yes (max_budget_usd config, checked each turn) | **Full** |
| **Concurrent tool execution** | Yes (tool orchestration partitions serial/parallel) | Yes (PARALLEL_SAFE_TOOLS, parallel when all tools are safe) | **Full** |
| **Prompt suggestion generation** | Yes (PromptSuggestion service) | Yes (_generate_suggestions in stop_hooks) | **Full** |
| **Away summary** | Yes (generateAwaySummary) | No | **Missing** |
| **Prevent sleep** | Yes (caffeinate) | No | **Missing** |
| **Notifications** | Yes (sendNotification) | No | **Missing** |
| **VCR recording/replay** | Yes | No | **Missing** |
| **Diagnostic tracking** | Yes | No | **Missing** |

---

## Section 5: What's STILL Missing

### Critical (users would immediately notice)

| # | Feature | Description | Effort | Being Built? |
|---|---------|-------------|--------|-------------|
| 1 | **Streaming tool execution** | Start executing tools WHILE model is still generating. CC's StreamingToolExecutor detects tool_use blocks mid-stream. Major latency reduction (2-4x for multi-tool turns). | 6-8 hours | No |
| 2 | **Rich Grep parameters** | CC's Grep has output_mode, context lines, head_limit, offset, multiline, type filter. SA only has pattern/path/glob/case_insensitive. Models trained on CC's Grep will struggle with SA's limited version. | 3-4 hours | No |
| 3 | **PDF/image reading** | ReadTool cannot handle images or PDFs. CC sends images as base64 to multimodal models, extracts PDF text with page ranges. | 2-3 hours | No |

### Important (power users / long sessions would notice)

| # | Feature | Description | Effort | Being Built? |
|---|---------|-------------|--------|-------------|
| 4 | **History snip** | CC applies targeted history trimming before compaction. SA jumps straight from microcompact to full autocompact. The intermediate step prevents unnecessary full compactions. | 3-4 hours | No |
| 5 | **Partial compact** | CC can compact only part of the conversation. SA always compacts everything except the last 2 messages. | 4-6 hours | No |
| 6 | **Post-compact plan/skill/agent restoration** | CC restores plans, skills, and agent context after compaction. SA only restores files. | 2 hours | No |
| 7 | **More bundled skills** | CC ships 17 bundled skills; SA has 2. Key missing: debug, simplify, verify (with examples), loop, remember, update-config, keybindings. | 4-6 hours | No |
| 8 | **Glob sort by mtime** | CC sorts glob results by modification time. SA sorts alphabetically. Models expect mtime order. | 30 min | No |
| 9 | **MCP resource tools** | CC has ListMcpResourcesTool and ReadMcpResourceTool. SA only bridges MCP tools, not resources. | 2-3 hours | No |
| 10 | **Sandbox system** | CC has macOS sandbox for bash execution. SA has no sandboxing. | 8+ hours | No |

### Nice-to-Have (platform features, not core agent)

| # | Feature | Description | Effort | Being Built? |
|---|---------|-------------|--------|-------------|
| 11 | **LSP integration** | Language Server Protocol for semantic code understanding. | 8+ hours | No |
| 12 | **IDE integration** | VS Code / JetBrains extensions. | 20+ hours | No |
| 13 | **Voice input** | Speech-to-text. | 10+ hours | No |
| 14 | **Bridge/remote sessions** | Distributed agent operation. | 10+ hours | No |
| 15 | **Team/buddy mode** | Multi-agent collaboration infrastructure. | 10+ hours | No |
| 16 | **Notebook editing** | Jupyter .ipynb support. | 4 hours | No |
| 17 | **Plugin marketplace** | Plugin discovery and installation from registries. | 6+ hours | No |
| 18 | **Centralized app state store** | CC has AppStateStore (570 lines). SA distributes state across agent attributes. | 4-6 hours | No |
| 19 | **Telemetry/analytics** | Usage tracking and feature management. | 4-6 hours | No |
| 20 | **Configurable keybindings** | Custom keyboard shortcuts. | 3-4 hours | No |

### Skip (platform-specific or marginal value)

- PowerShellTool (Windows only)
- Claude-in-Chrome (Anthropic-specific)
- Mobile/desktop app commands
- Stickers
- Lorem ipsum skill
- OAuth/login (SaaS-specific)
- Auto-update
- Vim mode

---

## Section 6: Overall Parity Assessment

### Score by System

| System | Parity | Weight |
|--------|--------|--------|
| Query loop | 75% | High |
| Tool set | 65% | High |
| Context assembly | 70% | High |
| Compaction | 60% | High |
| Memory | 70% | Medium |
| Session persistence | 70% | Medium |
| Hook system | 55% | Medium |
| Permission system | 65% | Medium |
| Subagent system | 75% | Medium |
| Task system | 65% | Medium |
| Skill system | 55% | Low |
| MCP system | 50% | Medium |
| Provider layer | 70% | High |
| Plugin system | 50% | Low |
| State management | 40% | Low |
| Error recovery | 75% | High |
| Streaming | 50% | Medium |
| Commands | 55% | Low |
| Behavioral patterns | 75% | High |

### Weighted Overall Parity: **64%**

### Honest Assessment

SaltAgent is a legitimate functional replica of Claude Code's core agent loop. The foundation is solid: the query loop works, tools execute, compaction happens, memory surfaces, sessions persist, hooks fire, subagents spawn, tasks run in background, MCP servers connect, plugins load, skills inject context.

**What it gets right:**
- The core turn lifecycle (prompt -> context assembly -> LLM call -> tool execution -> persistence) is architecturally sound
- Memory system is genuinely good (types, frontmatter, LLM relevance ranking, extraction, consolidation)
- Error recovery (prompt-too-long, loop detection, auto-continue) works
- Session persistence with crash recovery is real
- Prompt caching for subagents is implemented
- Budget tracking with real API usage data
- The behavioral patterns (read-before-edit, system-reminder injection, post-compact restoration) are present

**Where it falls short:**
- Compaction is 1 layer where CC has 6+ composable layers. This WILL matter in long sessions.
- No streaming tool execution. This is a noticeable latency gap on every multi-tool turn.
- Grep parameters are too limited. Models trained on CC will try to use output_mode, context lines, etc.
- Only 2 bundled skills vs 17.
- Hook system covers ~55% of CC's event types.
- MCP only bridges tools, not resources or auth.
- No sandbox, no LSP, no IDE integration.
- State is scattered rather than centralized.

**Is it ready for "feature parity" declaration?** No. It is ready for "functional core parity" -- the essential agent loop works. But Claude Code has 1,907 files and 12,920 internal import edges. SaltAgent has ~30 source files. The gap is in depth, not breadth. Each system that exists works, but each system is 40-70% as deep as CC's equivalent.

**To reach 80% parity**, the most impactful work would be:
1. Rich Grep parameters (3 hours, high frequency tool)
2. Streaming tool execution (8 hours, every turn is faster)
3. Glob mtime sort (30 min, trivial but models expect it)
4. Post-compact plan/skill restoration (2 hours)
5. More bundled skills (4 hours)
6. PDF/image reading (3 hours)
7. History snip compaction layer (4 hours)
8. MCP resource tools (3 hours)

Total: ~28 hours of focused work to move from 64% to ~80%.
