# SaltAgent Audit: Comparison to Claude Code Patterns

**Date:** 2026-03-30
**Auditor:** Claude (Opus 4.6)
**Sources:** Claude Code source analysis docs, leaked system prompts (v2.1.50-v2.1.90), Codex static analysis, SaltAgent source code

---

## 1. Agent Loop (`agent.py`)

**Match level: Partial Match (65%)**

### What we got right
- Messages live on the agent instance (`_conversation_messages`). `run()` adds turns, doesn't create new conversations. This is the QueryEngine pattern.
- System prompt reassembled each turn via `_build_system_prompt()` (includes dynamic todo injection).
- Checkpoint saved BEFORE the API call (crash safety).
- Loop detection with warn-then-stop pattern (inject "you're stuck" message, then hard-stop on second warning).
- Tool results are truncated before adding to messages.
- Compaction check happens inside the loop, not outside.
- Hooks fire at correct points: pre_api_call, pre_tool_use, post_tool_use, on_complete, on_error.

### What's different from Claude Code
- **No streaming tool execution.** Claude Code starts executing tools BEFORE the model finishes streaming via `StreamingToolExecutor`. Our loop waits for the full response, then executes tools sequentially. This is a significant latency penalty for multi-tool responses.
- **No error recovery inside the loop.** Claude Code handles prompt-too-long (triggers compaction + retry), max-output-reached (adjusts caps + retry), media overflow (removes content + retry), and fallback model switching. Our loop just yields `AgentError` and returns.
- **Context pressure is checked once, not layered.** Claude Code applies 6+ layers progressively: tool result budgeting, history snip, microcompact, context collapse, autocompact, reactive recovery. We call `manage_pressure()` (one layer of naive summarization) then separately check `needs_compaction()`. The two don't compose well.
- **System prompt is only partially reassembled.** Claude Code reassembles from scratch each turn: memory files, CLAUDE.md, environment info, git status, date, model info, mode injections. We only inject todo state on top of a static base. No per-turn memory surfacing, no environment refresh.
- **No prefetch of relevant memory.** Claude Code does a side-query to surface relevant memory files each turn. We don't.
- **Tool execution is synchronous.** `tool.execute()` is called in sequence. Claude Code batches concurrent-safe tools in parallel.

### What's missing
- Streaming tool execution (tools start during model streaming)
- Prompt-too-long recovery (compact + retry)
- Max-output recovery (adjust caps + retry)
- Fallback model switching
- Concurrent tool execution (parallel read-only tools)
- Per-turn context reassembly (environment, git status, memory)
- Tool result budgeting as a separate pre-turn step
- Microcompact (lightweight intra-turn compression)
- Post-compact file restoration

### Priority: **Critical**

### Recommended fixes
1. Add prompt-too-long error recovery: catch the error, trigger compaction, retry. (2-3 hours)
2. Add concurrent tool execution for read-only tools (Read, Grep, Glob). (4-6 hours)
3. Add streaming tool execution: detect tool_use blocks during streaming, start execution immediately. (6-8 hours)
4. Refactor context pressure into a proper pipeline: budget -> snip -> microcompact -> autocompact -> reactive. (4-6 hours)

---

## 2. Tool System (`tools/`)

**Match level: Partial Match (75%)**

### What we got right
- Typed tool contracts with `ToolDefinition` and `ToolParam` schema objects.
- Read-before-edit enforcement: both `EditTool` and `WriteTool` check `read_tool.files_read`.
- Edit uses string replacement with uniqueness constraint. `old_string` must be unique or `replace_all=True`.
- Bash has configurable timeout and output truncation (30K chars, first/last halves kept).
- `MultiEditTool` for multiple changes to one file in a single call.
- `TodoWriteTool` with replace-all semantics (agent writes full list each time).
- Tool registry with both Anthropic and OpenAI format converters.
- `ReadTool` tracks `files_read` as a set; `WriteTool` tracks `files_written`.
- `GrepTool` falls back from ripgrep to grep.

### What's different from Claude Code
- **No `description` parameter enforcement on Bash.** Claude Code requires a `description` param on every Bash call for user-facing clarity. We accept it but don't require it. The description is used in the UI to explain what a command does.
- **No `run_in_background` support for Bash.** Claude Code allows background execution with later notification. We don't support this.
- **No `dangerouslyDisableSandbox` flag.** Claude Code has a sandboxing system for Bash. We have no sandbox at all.
- **Bash timeout is in seconds, not milliseconds.** Claude Code uses milliseconds (max 600,000 = 10 min). We use seconds (default 30). This is a minor difference but could cause confusion for model prompts expecting ms.
- **No `pages` parameter on Read.** Claude Code supports reading specific page ranges from PDFs. We don't.
- **No image/PDF reading.** Claude Code's Read tool handles images (multimodal) and PDFs.
- **TodoWrite is missing `activeForm` field.** Claude Code has three fields: `content`, `status`, and `activeForm` (present continuous form like "Running tests"). The `activeForm` is displayed in the UI during execution. We only have `content` and `status`.
- **No concurrency metadata on tools.** Claude Code tools declare `isConcurrencySafe()` and `read-only`/`destructive` metadata. We have no such metadata.
- **Grep is missing many Claude Code parameters.** Claude Code's Grep has: `output_mode` (content/files_with_matches/count), `-A/-B/-C` context lines, `head_limit`, `offset`, `multiline`, `type` (file type). We have: `pattern`, `path`, `glob`, `case_insensitive`.
- **Glob doesn't sort by modification time.** Claude Code sorts results by mtime. We sort alphabetically.
- **ListFiles tool doesn't exist in Claude Code.** Claude Code uses Bash `ls` instead. Having it isn't wrong, but it's extra.
- **AgentTool doesn't support fork, background, or model selection.** Claude Code's Task tool has: `subagent_type`, `model`, `resume`, `run_in_background`, `max_turns`, `isolation`. Our AgentTool only has `prompt` and `mode`.

### What's missing
- Bash background execution (`run_in_background`)
- Bash sandbox system
- PDF/image reading in Read tool
- `activeForm` field on TodoWrite
- Tool concurrency metadata (`isConcurrencySafe`)
- Rich Grep parameters (output_mode, context lines, multiline, type, head_limit)
- Agent tool: fork mode, background execution, model selection, resume
- `NotebookEdit` tool (low priority)

### Priority: **Important**

### Recommended fixes
1. Add `activeForm` to TodoWrite schema. (30 min)
2. Add `run_in_background` to BashTool. (2-3 hours)
3. Enrich GrepTool parameters to match Claude Code's schema (output_mode, context lines, head_limit at minimum). (2-3 hours)
4. Add concurrency metadata to tools (`is_concurrent_safe` property on Tool base class). (1 hour)
5. Expand AgentTool with `run_in_background`, `model`, `max_turns`. (2-3 hours)

---

## 3. Context Management (`context.py`, `compaction.py`)

**Match level: Partial Match (40%)**

### What we got right
- Token estimation via `len(text) // 4` (same approximation Claude Code uses).
- Tool result truncation with first/last halves preserved.
- Compaction triggers at 80% of context window (Claude Code uses `contextWindow - maxOutput - 13K`, which is roughly 80-85%).
- Compaction uses the same model (not a cheaper one).
- 9-section summarization prompt structure (matches Claude Code's sections almost exactly).
- Compaction produces a summary that replaces old messages.
- Files read list is passed to compaction for preservation.
- Todo state is preserved through compaction.

### What's different from Claude Code
- **Only 2 context pressure layers, not 6.** We have: (1) `manage_pressure()` which does naive turn summarization at 75%, and (2) `compact_context()` which does full LLM summarization at 80%. Claude Code has 6 layers that compose progressively.
- **No `<analysis>` scratchpad in compaction.** Claude Code instructs the summarizer to produce an `<analysis>` block first (improves quality), then strips it. We don't.
- **No "CRITICAL: Do NOT call any tools" guardrail.** Claude Code's compaction prompt explicitly prevents the summarizer from calling tools. Ours doesn't include this.
- **No post-compact file restoration.** Claude Code reinjects up to 5 recently-read files (50K token budget) after compaction. We don't restore anything -- the model loses access to all file content after compaction.
- **No circuit breaker.** Claude Code stops retrying after 3 consecutive compaction failures (`MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES`). We have no failure tracking.
- **Conversation text is truncated to 500 chars per message in compaction input.** Claude Code sends full content. Our truncation means the summarizer is working with incomplete information.
- **Summary max tokens is 2000.** Claude Code uses 20,000. Our summaries are too short to capture complex sessions.
- **No compaction boundary marker.** Claude Code inserts a `SystemCompactBoundaryMessage` sentinel. We use a plain user message with "[Context Summary]" prefix. The model can't distinguish compaction boundaries from user messages.
- **`manage_pressure()` is destructive and lossy.** It replaces middle messages with role + first 200 chars. This is not summarization -- it's information destruction. Claude Code never does this; it either summarizes properly or doesn't touch the messages.
- **Compaction summary system prompt is too generic.** We use "You are a context summarizer. Produce a concise summary." Claude Code uses a detailed summarization system prompt with explicit sections and rules.

### What's missing
- Proper 6-layer context pressure pipeline
- `<analysis>` scratchpad block in summarization
- "Do NOT call any tools" guardrail in summarization prompt
- Post-compact file restoration (reinject 5 recently-read files, 50K budget)
- Compaction failure circuit breaker (3 strikes)
- Compaction boundary markers
- Adequate summary max tokens (20K, not 2K)
- Microcompact (lightweight intra-turn compression)
- History snip (targeted removal of low-value older turns)
- Tool result budgeting as a separate pre-turn step
- Reactive compaction (retry on prompt-too-long)

### Priority: **Critical**

### Recommended fixes
1. **Increase summary max tokens to 10,000-20,000.** Current 2000 is far too low. (5 min)
2. **Add post-compact file restoration.** After compaction, reinject the 5 most recently read files. (2-3 hours)
3. **Add `<analysis>` scratchpad and "no tools" guardrail to compaction prompt.** (30 min)
4. **Remove `manage_pressure()` or replace with proper microcompact.** The current implementation is destructive. Better to just let compaction handle it. (1-2 hours)
5. **Add compaction failure circuit breaker.** Track failures, stop after 3. (30 min)
6. **Don't truncate conversation text in compaction input.** Pass full content (up to 10K per message). (30 min)

---

## 4. Session Persistence (`persistence.py`)

**Match level: Partial Match (60%)**

### What we got right
- JSONL append-only format.
- Checkpoint saved BEFORE each API call (crash safety).
- Session ID as filename.
- Resume loads the most recent checkpoint.
- Events and checkpoints are separate entry types.
- Session listing with metadata (size, modified time).
- `~/.saltdesktop/sessions/` as the default location.

### What's different from Claude Code
- **Checkpoints contain the full message array.** Claude Code appends individual messages (one per line). We write the entire `messages` list as a single JSONL entry on every checkpoint. This means (a) the file grows quadratically (N messages * N turns), and (b) we can't reconstruct the conversation incrementally.
- **No `parentUuid` chain.** Claude Code messages carry `parentUuid` for ordering and branching. We have no message identity.
- **No separate entry types for different message kinds.** Claude Code has: `user`, `assistant`, `attachment`, `system`, `file_history_snapshot`, `attribution_snapshot`, `content_replacement`. We have: `checkpoint` and generic `event`.
- **No file history snapshots in the JSONL.** Claude Code serializes file history state to the transcript for resume. We don't persist file history.
- **No content replacement for large payloads.** Claude Code stores large tool outputs separately and references them by ID. We store everything inline, which bloats the JSONL.
- **Resume doesn't restore file history, todo state, or tool tracking.** Claude Code's resume restores: file history, attribution state, context-collapse state, todos, agent settings, worktree state. We only restore messages.

### What's missing
- Individual message appending (instead of full checkpoint each time)
- Message identity (`parentUuid` or sequence number)
- File history persistence in JSONL
- Content replacement for large tool outputs
- Resume restoration of todo state, file history, tool tracking state
- Session metadata entries (start/end, agent settings)
- Subagent transcript storage (nested under session)

### Priority: **Important**

### Recommended fixes
1. **Switch to per-message appending.** Append each message individually instead of the full array. Keep a checkpoint entry periodically for fast resume. (3-4 hours)
2. **Add message IDs.** UUID per message with parent reference. (1 hour)
3. **Persist and restore todo state on resume.** Scan transcript backwards for last todo_write. (1-2 hours)
4. **Add content replacement for large tool outputs.** Store outputs > 10KB in separate files, reference by hash. (2-3 hours)

---

## 5. Memory System (`memory.py`)

**Match level: Partial Match (50%)**

### What we got right
- Hierarchical CLAUDE.md/SALT.md discovery: walks up directories (up to 10 levels).
- Searches for `SALT.md`, `CLAUDE.md`, and `.claude/instructions.md`.
- Memory directory at `~/.saltdesktop/memory/` with MEMORY.md as index.
- Memory files can be loaded individually.
- Project instructions loaded at startup and injected into system prompt.
- Closer-to-cwd files loaded first.

### What's different from Claude Code
- **No per-turn memory surfacing.** Claude Code does a side-query to Sonnet each turn, passing memory file descriptions and the current user query, to select up to 5 relevant memory files. We load MEMORY.md at startup and never dynamically select memories.
- **No YAML frontmatter parsing.** Claude Code memory files have `name`, `description`, `type` frontmatter. We parse MEMORY.md lines as raw text without structure.
- **No memory type taxonomy.** Claude Code has 4 types: user preferences, feedback, project context, reference. We have no type system.
- **Project instructions are truncated to 5000 chars.** Claude Code allows up to 40,000 chars per file. 5K is very limiting for rich project instructions.
- **No `@path` include directives.** Claude Code supports `@path` in CLAUDE.md to reference other files. We don't.
- **No `.claude/rules/*.md` loading.** Claude Code loads all `.md` files from `.claude/rules/` directory. We don't.
- **No user-level CLAUDE.md.** Claude Code loads `~/.claude/CLAUDE.md` as global user instructions. We only look in the working directory tree.
- **No `alreadySurfaced` tracking.** Claude Code tracks which memory files have been surfaced in prior turns to avoid re-picking. We don't surface at all.
- **Memory index parsing is fragile.** We look for lines starting with `- [`, which is a specific markdown format. Claude Code scans `.md` files in the directory and reads frontmatter.

### What's missing
- Per-turn relevant memory surfacing via side-query
- YAML frontmatter parsing for memory files
- Memory type taxonomy (user/feedback/project/reference)
- `@path` include directives in instruction files
- `.claude/rules/*.md` loading
- User-level global instructions (`~/.saltagent/SALT.md` or similar)
- `alreadySurfaced` tracking
- Adequate character limits (40K not 5K)

### Priority: **Important**

### Recommended fixes
1. **Increase instruction file character limit from 5K to 40K.** (5 min)
2. **Add user-level global instructions** at `~/.saltdesktop/SALT.md`. (30 min)
3. **Load `.claude/rules/*.md` (or `.salt/rules/*.md`) files.** (30 min)
4. **Add per-turn memory surfacing.** Side-query to a cheap model with memory file descriptions. (4-6 hours)
5. **Parse YAML frontmatter from memory files.** (1-2 hours)

---

## 6. Permission System (`permissions.py`)

**Match level: Partial Match (35%)**

### What we got right
- Rule-based system with tool name, pattern, and action (allow/ask/deny).
- Glob matching for bash commands and file paths.
- Default rules for dangerous operations (rm -rf, sudo, git push, etc.).
- Ask callback mechanism for user prompts.
- Integrated as a pre_tool_use hook.
- Fallback to allow when no ask callback is available.

### What's different from Claude Code
- **No rule source hierarchy.** Claude Code has 5 rule sources in priority order: policy (enterprise) > user settings > project settings > local settings > CLI flags. We have a single flat list.
- **No settings persistence.** Claude Code's "Allow always" persists rules to settings.json. Our rules only live in memory.
- **No AI-based classifier.** Claude Code has a bash classifier that evaluates command safety via a cheap model call, racing against the user prompt. We have no AI classification.
- **No denial tracking or circuit breakers.** Claude Code tracks denial counts and stops after repeated denials to prevent infinite loops. We have no tracking.
- **Pattern matching is too simple.** Our glob matching works for basic patterns but doesn't handle edge cases well. `rm -rf *` won't match `rm -rf /important/path` because fnmatch requires the full string to match.
- **No per-tool permission handlers.** Claude Code has dedicated permission handlers per tool type. We use the same glob matching for everything.
- **Ask callback is synchronous.** In an async agent loop, the ask callback blocks the entire loop. Claude Code races the classifier against the user prompt.
- **No session-scoped permissions.** Claude Code allows "Allow for this session" vs "Allow always". We only have permanent rules.
- **Multi_edit tool is not checked.** The permission system only matches `write` and `edit`, but `multi_edit` writes to files too and isn't matched.

### What's missing
- Rule source hierarchy (user > project > local)
- Settings persistence ("Allow always" writes to config file)
- AI-based bash classifier (cheap model evaluates safety)
- Denial tracking with circuit breakers
- Session-scoped vs permanent permissions
- Per-tool permission handlers
- Classifier racing (auto-approve before user responds)
- Multi_edit permission matching
- Subagent permission bubbling

### Priority: **Important**

### Recommended fixes
1. **Add multi_edit to permission matching.** (15 min)
2. **Add settings persistence.** Save rules to `~/.saltdesktop/settings.json`. (1-2 hours)
3. **Add rule source hierarchy.** Load from user config + project config. (2-3 hours)
4. **Add denial tracking.** Count consecutive denials, warn after 3. (1 hour)
5. **Session-scoped permissions.** "Allow for this session" option. (1-2 hours)

---

## 7. Hook Engine (`hooks.py`)

**Match level: Partial Match (45%)**

### What we got right
- Event-based callback system with registration and firing.
- `HookResult` with `action` (allow/block/modify) and `reason`.
- First non-allow result wins (short-circuit evaluation).
- Both sync and async hook support (`fire` and `fire_async`).
- `modified_input` field on HookResult (hooks can modify tool input).
- Silent exception handling (hooks don't crash the agent).
- 9 defined event types covering tool, API, error, and completion lifecycle.

### What's different from Claude Code
- **Only 9 events vs 27.** Claude Code has: PreToolUse, PostToolUse, PostToolUseFailure, SessionStart, SessionEnd, Setup, SubagentStart, SubagentStop, PreCompact, PostCompact, PermissionRequest, PermissionDenied, TaskCreated, TaskCompleted, UserPromptSubmit, Notification, Stop, StopFailure, ConfigChange, InstructionsLoaded, CwdChanged, FileChanged, WorktreeCreate, WorktreeRemove, TeammateIdle, Elicitation, ElicitationResult. We have 9 basics.
- **Only in-process function hooks.** Claude Code supports 5 hook types: shell commands, agent hooks, HTTP webhooks, prompt hooks, in-process functions. We only support in-process callbacks.
- **No hook configuration from files.** Claude Code loads hooks from `settings.json` keyed by event name with matchers. We only register programmatically.
- **No matcher/filter system.** Claude Code hooks have `matcher` fields (glob patterns, regex) to select which tools/events trigger the hook. Our hooks fire for all events of a type.
- **No timeout on hooks.** Claude Code has per-hook timeouts (10 min default for tool hooks, 1.5s for SessionEnd). Our hooks can hang forever.
- **`modified_input` is defined but never used.** The HookResult has a `modified_input` field, but `agent.py` never checks it. PreToolUse hooks can't actually modify tool input.
- **No async hook execution with concurrency.** Claude Code can run hooks in background. Our async support just handles coroutine callbacks.

### What's missing
- 18 additional event types (session, subagent, compaction, permission, config lifecycle)
- Shell command hooks (JSON stdin/stdout)
- HTTP webhook hooks
- Agent hooks (model call as hook)
- Prompt injection hooks
- Hook configuration from settings files
- Matcher/filter system for selective hook firing
- Hook timeouts
- Actually using `modified_input` from HookResult
- Background/async hooks with notifications

### Priority: **Nice-to-have** (for SaltAgent standalone; **Important** if Salt Desktop integration needs more events)

### Recommended fixes
1. **Wire up `modified_input`.** In `agent.py`, apply modified input from pre_tool_use hooks. (30 min)
2. **Add shell command hooks.** Execute external commands with JSON stdin/stdout. (2-3 hours)
3. **Add hook timeouts.** Wrap hook execution in asyncio.wait_for. (30 min)
4. **Add SessionStart and SessionEnd events.** Fire at agent init and completion. (30 min)
5. **Add SubagentStart/SubagentStop events.** Fire from SubagentManager. (30 min)

---

## 8. Subagent System (`subagent.py`)

**Match level: Partial Match (40%)**

### What we got right
- Two modes: fresh subagent (zero context) and fork (inherits parent context).
- Fresh subagents get mode-specific system prompts (explore, verify, worker, general).
- Subagent results collected and returned as text.
- SubagentManager tracks children.
- AgentTool exposes subagent spawning as a tool within the agent loop.

### What's different from Claude Code
- **Fork doesn't actually share conversation context correctly.** Our `fork()` sets `child.context._messages` but the agent loop uses `_conversation_messages`. The fork implementation is broken -- it writes to a field that `run()` never reads from.
- **No prompt cache sharing.** Claude Code forks are designed for byte-identical API prefixes to share the prompt cache. Our forks create entirely new conversations with no cache optimization.
- **No fork boilerplate.** Claude Code injects strict rules: "You are a forked worker process. Do NOT spawn sub-agents. Execute directly." With enforced output format: Scope, Result, Key files, Files changed, Issues. We have generic mode prompts.
- **No fork detection.** Claude Code has `isInForkChild()` to prevent recursive forks. We have no protection against a subagent spawning another subagent.
- **No background execution.** Claude Code supports `run_in_background: true` on the Task tool. Our AgentTool blocks until the subagent completes.
- **No verification specialist.** Claude Code has a dedicated verification agent with the remarkable self-awareness prompt: "You are Claude, and you are bad at verification. You read code and write PASS instead of running it." We have a generic "verify" mode.
- **No agent definitions from files.** Claude Code loads agent definitions from `.claude/agents/*.md` with YAML frontmatter. We hardcode modes.
- **No tool filtering for subagents.** Claude Code agents declare `tools`/`disallowedTools`. Our subagents get the full tool set.
- **No worktree isolation.** Claude Code can spawn subagents in isolated git worktrees.
- **AgentTool runs subagent in a thread pool.** This works but is fragile. The `asyncio.run()` inside a `ThreadPoolExecutor` creates a new event loop per subagent, which can cause issues with shared state.

### What's missing
- Prompt cache sharing for forks (byte-identical prefix)
- Fork boilerplate with strict output format
- Recursive fork prevention
- Background subagent execution with notifications
- Verification specialist with self-awareness prompt
- Agent definitions from `.salt/agents/*.md` files
- Tool filtering per subagent (allow/disallow lists)
- Worktree isolation
- Proper async subagent execution (not thread pool hack)

### Priority: **Important**

### Recommended fixes
1. **Fix fork implementation.** Set `_conversation_messages` instead of `context._messages`. (30 min)
2. **Add fork boilerplate with output format rules.** (30 min)
3. **Add recursive fork prevention.** Check if already in a subagent before spawning. (30 min)
4. **Add background execution.** Run subagent in asyncio.create_task, return a task ID. (2-3 hours)
5. **Add verification specialist prompt.** The self-awareness prompt is critical for reliable verification. (30 min)
6. **Add tool filtering.** Allow subagents to specify which tools they can use. (1-2 hours)

---

## 9. Provider Adapters (`providers/`)

**Match level: Partial Match (60%)**

### What we got right
- Abstract `ProviderAdapter` base class with streaming interface.
- Anthropic adapter handles streaming correctly: content_block_start, content_block_delta, content_block_stop events.
- OpenAI adapter handles streaming with delta accumulation.
- OpenAI message format conversion (Anthropic format to OpenAI format) covers: tool_result blocks, assistant tool_use blocks, text blocks.
- Both adapters parse partial tool_use JSON from streaming deltas.
- Error handling yields recoverable `AgentError` events.

### What's different from Claude Code
- **No prompt caching support.** Claude Code uses Anthropic's prompt caching (`cache_control` on system prompt blocks). This is a major cost optimization. We don't set any cache hints.
- **No retry/backoff on rate limits.** Claude Code has retry logic at the API layer. Our adapters let exceptions propagate.
- **No fallback model switching.** Claude Code can switch to a backup model if the primary fails. We have no fallback.
- **Anthropic client is created per-call.** `client = anthropic.Anthropic(api_key=...)` is called every turn. Should be created once and reused.
- **OpenAI client is also created per-call.** Same issue.
- **No token usage tracking from API responses.** Claude Code extracts input/output token counts from API responses. We don't track them (the CLI estimates from text length, which is very rough).
- **No max-output recovery.** When the model hits the output token limit, Claude Code adjusts caps and retries. We don't detect this.
- **No handling of overloaded/unavailable responses.** Anthropic returns `overloaded_error` or `api_error` that should trigger retries with backoff.
- **OpenAI message conversion doesn't handle all edge cases.** For example, `_convert_message` returns either a dict or a list of dicts. The caller must check `isinstance(converted, list)` -- this pattern is fragile.

### What's missing
- Prompt caching (set `cache_control` on system prompt blocks)
- Retry with backoff on rate limits and overloaded errors
- Fallback model switching
- Client reuse (create once, not per-call)
- Token usage extraction from API responses
- Max-output detection and recovery
- Streaming error recovery (discard partial response, retry)

### Priority: **Critical** (prompt caching alone can cut costs 50-90%)

### Recommended fixes
1. **Create clients once in `__init__`, not per-call.** (15 min)
2. **Add prompt caching.** Set `cache_control: {"type": "ephemeral"}` on system prompt. (1-2 hours)
3. **Extract token usage from API responses.** Return input/output token counts. (1-2 hours)
4. **Add retry with backoff.** Retry on 429, 529, 503 errors. (2-3 hours)
5. **Add max-output detection.** Check stop_reason == "max_tokens", signal to caller. (1 hour)

---

## 10. CLI (`cli.py`)

**Match level: Partial Match (70%)**

### What we got right
- Terminal-native interface with ANSI color support.
- Animated braille spinner during thinking with elapsed time.
- Heartbeat messages that change based on silence duration.
- Markdown rendering with syntax highlighting (Python).
- Inline formatting: bold, code spans.
- Code blocks with language detection and highlighting.
- Tool call display: lightning bolt icon + brief description.
- Tool result display: check/cross icons + one-line summaries.
- Slash commands: /help, /clear, /compact, /mode, /tools, /cost, /quit.
- Startup banner with provider, directory, tools info.
- Multi-line input support (backslash continuation).
- JSON output mode for piping.
- Token/cost tracking with model-specific rates.
- Completion summary line (elapsed time, tool calls, tokens, cost).
- Context-aware tool result summaries (pytest output detection, file count, etc.).
- API key resolution from multiple sources (env vars, config files).
- NO_COLOR support.

### What's different from Claude Code
- **No session resume from CLI.** Claude Code has `--resume` flag to continue a previous session. We don't expose resume in the CLI.
- **No session history search.** Claude Code can list and search past sessions.
- **No permission prompts inline.** When a tool needs permission, Claude Code shows the prompt inline in the terminal. We default to allow when no callback is set.
- **Slash commands are incomplete.** `/compact` and `/history` say "not yet implemented". Claude Code has full implementations.
- **No `--continue` / `--resume` flag.** Claude Code supports `--resume <session-id>` and `--continue` (resume last session).
- **No `--print` mode.** Claude Code has `--print` for non-interactive single-shot output without tool use display.
- **No pipe detection.** Claude Code detects when stdin is piped and adjusts behavior. Our CLI checks `sys.stdout.isatty()` for color but doesn't handle piped input.
- **Markdown rendering is basic.** No list handling, no table rendering, no horizontal rules. Claude Code renders full GitHub-flavored markdown.
- **Token tracking is estimated, not real.** We estimate tokens from text length. Claude Code extracts actual token counts from API responses.
- **No edit diff display.** Claude Code shows colored before/after for edits. We have `_edit_colored_summary` but it only shows first 30 chars.
- **No configuration file support.** No `~/.saltdesktop/settings.json` for persisting preferences.

### What's missing
- Session resume (`--resume`, `--continue`)
- Session history/search
- Inline permission prompts
- Working `/compact` and `/history` commands
- `--print` mode for scripting
- Pipe input detection
- Full markdown rendering (lists, tables)
- Real token counts from API
- Configuration file (`~/.saltdesktop/settings.json`)

### Priority: **Nice-to-have** (CLI is already quite polished)

### Recommended fixes
1. **Implement `/compact` command.** Call `compact_context()` on the current conversation. (1-2 hours)
2. **Add `--resume` flag.** List sessions, select one, hydrate. (2-3 hours)
3. **Add inline permission prompts.** When ask_callback is needed, prompt in the terminal. (1-2 hours)
4. **Wire up real token counts from API responses.** (1-2 hours after provider fix)

---

## 11. Prompt System (`prompts/`)

**Match level: Full Match (85%)**

### What we got right
- 14 curated mode prompts adapted from Claude Code's system prompts.
- 254-prompt catalog organized into subpackages (fragments, agents, skills, tools, data).
- Composable prompt assembly via `assemble_system_prompt()`.
- Mode-specific prompt selection.
- Prompt registry with search/list capabilities.
- Core behavioral fragments: read-before-modifying, no unnecessary additions, no premature abstractions, security, etc.
- 9-section summarization prompt.
- Verification specialist prompt, worker fork prompt, explore prompt.

### What's different from Claude Code
- **System prompt isn't reassembled every turn.** The prompts exist but `agent.py` only calls `_assemble_system_prompt()` once in `__init__`. Claude Code rebuilds from scratch each turn, incorporating fresh memory, environment info, date, model info, etc.
- **No environment/date/model injection.** Claude Code injects current date, platform info, git status, model name into the system prompt each turn. We don't.
- **No `<system-reminder>` injection mechanism.** Claude Code injects system reminders into tool results and user messages. We have no equivalent.

### What's missing
- Per-turn system prompt reassembly with dynamic context
- Environment info injection (date, platform, git status, model)
- System reminder injection mechanism

### Priority: **Important**

### Recommended fixes
1. **Reassemble system prompt each turn** in the agent loop (not just at init). Inject date, platform, working directory. (1-2 hours)
2. **Add system reminder injection.** Append reminders to tool results for context updates. (1-2 hours)

---

## Overall Assessment

### Match Percentage by Component

| Component | Match | Score |
|-----------|-------|-------|
| Agent Loop | Partial | 65% |
| Tool System | Partial | 75% |
| Context Management | Partial | 40% |
| Session Persistence | Partial | 60% |
| Memory System | Partial | 50% |
| Permission System | Partial | 35% |
| Hook Engine | Partial | 45% |
| Subagent System | Partial | 40% |
| Provider Adapters | Partial | 60% |
| CLI | Partial | 70% |
| Prompt System | Full | 85% |

**Overall weighted match: ~55%**

The architecture is sound. The patterns are correct. What's missing is depth -- each component implements the happy path but lacks the error recovery, optimization, and edge case handling that makes Claude Code robust.

---

## Top 10 Fixes Ranked by Impact

| # | Fix | Impact | Effort | Component |
|---|-----|--------|--------|-----------|
| 1 | **Add prompt caching to Anthropic adapter** | 50-90% cost reduction | 1-2 hours | Providers |
| 2 | **Fix compaction: increase max tokens to 20K, add `<analysis>` scratchpad, add "no tools" guardrail** | Prevents information loss on long sessions | 1-2 hours | Compaction |
| 3 | **Add post-compact file restoration** (reinject 5 recently-read files) | Prevents agent losing working context after compaction | 2-3 hours | Compaction |
| 4 | **Add prompt-too-long error recovery** (catch error, compact, retry) | Prevents hard crashes on long sessions | 2-3 hours | Agent Loop |
| 5 | **Remove/replace `manage_pressure()`** with proper layered pipeline | Current implementation destroys context instead of preserving it | 2-3 hours | Context |
| 6 | **Create API clients once, not per-call** + extract real token counts | Eliminates object creation overhead + enables accurate cost tracking | 1-2 hours | Providers |
| 7 | **Add retry with backoff on rate limits** | Prevents failures on busy APIs | 2-3 hours | Providers |
| 8 | **Fix fork implementation** (write to `_conversation_messages`, add boilerplate) | Fork subagents are currently broken | 1 hour | Subagents |
| 9 | **Per-turn system prompt reassembly** (inject date, env, dynamic memory) | Model gets stale context without this | 1-2 hours | Prompts |
| 10 | **Add concurrent tool execution for read-only tools** | 2-4x speedup on multi-tool responses | 4-6 hours | Agent Loop |

### Total estimated effort for all 10 fixes: ~20-30 hours (3-4 focused days)

### What NOT to prioritize
- Full 27-event hook system (not needed until Salt Desktop integration demands it)
- AI-based bash classifier (rules-based is fine for now)
- Worktree isolation (nice but not essential)
- Agent definitions from files (hardcoded modes work fine)
- Full markdown rendering in CLI (current rendering is adequate)
- HTTP/shell hook types (in-process callbacks are sufficient)

---

## Conclusion

SaltAgent has the right bones. The architecture mirrors Claude Code's patterns correctly: agent-owns-conversation, string-replacement edits, read-before-edit enforcement, hook-based extensibility, JSONL persistence, subagent spawning. The prompt library is genuinely strong with 254 prompts.

The gaps are almost entirely in **resilience and optimization**: error recovery, context pressure management, prompt caching, concurrent execution, and post-compaction restoration. These are the details that make Claude Code work across millions of sessions without degrading. Fixing the top 10 items above would bring the overall match from ~55% to ~75%, with the most impactful changes (prompt caching, compaction fixes, error recovery) being relatively small in effort.
