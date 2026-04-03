# Claude Code Source Analysis for SaltAgent

Analysis of the Claude Code TypeScript source at `/Users/jimopenclaw/Desktop/claude-code-info/src/` to understand implementation details of features missing from SaltAgent.

---

## 1. TodoWrite/TodoRead (Task Tracking)

### Files
- `src/tools/TodoWriteTool/TodoWriteTool.ts` -- main tool implementation
- `src/tools/TodoWriteTool/prompt.ts` -- prompt/description with usage guidance
- `src/tools/TodoWriteTool/constants.ts` -- tool name constant
- `src/utils/todo/types.ts` -- Zod schemas for todo items

### How It Works

**Schema**: Each todo item has three fields:
```
{
  content: string       // imperative form: "Run tests"
  status: "pending" | "in_progress" | "completed"
  activeForm: string    // present continuous: "Running tests"
}
```

The todo list is simply `TodoItem[]` -- a flat array, no nesting, no IDs.

**Storage**: Todos live in `AppState.todos`, a `Record<string, TodoList>` keyed by either `agentId` (for subagents) or `sessionId` (for the main thread). This is purely in-memory state -- no file persistence for v1. On session resume, todos are reconstructed by scanning the transcript backwards for the last `TodoWrite` tool_use block.

**Tool behavior**:
1. Agent calls `TodoWrite({ todos: [...] })` with the ENTIRE updated list
2. Tool captures `oldTodos`, sets `newTodos` in AppState
3. If ALL todos are `completed`, the list is cleared (set to `[]`)
4. Returns a success message telling the agent to continue working
5. A verification nudge fires when 3+ tasks are closed and none had "verif" in the name

**Key design decisions**:
- The agent sends the FULL list every time (replace semantics, not patch)
- No separate TodoRead tool -- the agent reads from the tool result which includes oldTodos/newTodos
- The prompt is extensive (~180 lines) with examples of when TO and when NOT TO use todos
- Rule: exactly ONE task should be `in_progress` at any time
- The `activeForm` is displayed in the UI during execution

### Prompt (condensed key rules)
- Use for 3+ step tasks, multi-file changes, user-provided lists
- Don't use for single trivial tasks or informational questions
- Mark tasks complete IMMEDIATELY after finishing (don't batch)
- Never mark completed if tests failing or errors unresolved
- Always provide both `content` and `activeForm`

### Implementation Recommendations for SaltAgent
- **Data model**: Simple -- `List[dict]` with `content`, `status`, `activeForm` fields
- **Storage**: Keep in session state dict, keyed by agent/session ID
- **Tool**: Single `todo_write` tool that takes the full list as input
- **Resume**: Scan transcript for last todo_write call to restore state
- **No separate read tool needed** -- the model tracks state from tool results

### Estimated Effort: **Small** (1-2 hours)

---

## 2. Context Compaction

### Files
- `src/services/compact/autoCompact.ts` -- auto-compaction trigger logic
- `src/services/compact/compact.ts` -- core compaction engine (~700 lines)
- `src/services/compact/prompt.ts` -- summarization prompts (full + partial)
- `src/services/compact/postCompactCleanup.ts` -- cache/state cleanup after compaction
- `src/services/compact/microCompact.ts` -- lightweight intra-turn compression
- `src/services/compact/grouping.ts` -- message grouping for partial compact

### How It Works

**Trigger**: Auto-compaction triggers when token usage exceeds `contextWindow - maxOutputTokens - 13,000` (the 13K is `AUTOCOMPACT_BUFFER_TOKENS`). Checked after each model response. Manual `/compact` command also available.

**Compaction process**:
1. Pre-compact hooks fire (external consumers can inject instructions)
2. Messages are stripped of images (replaced with `[image]` markers)
3. The full conversation (or partial slice) is sent to a forked model call with a summarization system prompt
4. The model produces an `<analysis>` scratchpad (stripped later) and a `<summary>` with 9 sections
5. The `<analysis>` block is stripped from the final summary
6. A `SystemCompactBoundaryMessage` is inserted into the message array
7. The summary becomes a new user message: "This session is being continued from a previous conversation..."
8. Post-compact cleanup clears caches, classifier approvals, etc.

**The summarization prompt** instructs the model to produce these 9 sections:
1. Primary Request and Intent
2. Key Technical Concepts
3. Files and Code Sections (with full code snippets)
4. Errors and fixes
5. Problem Solving
6. All user messages (verbatim, non-tool-result)
7. Pending Tasks
8. Current Work (what was happening right before compaction)
9. Optional Next Step

**Partial compaction**: Can compact only older messages while preserving recent ones ("from" direction) or compact a prefix while keeping newer messages intact ("up_to" direction).

**Post-compact restoration**: After compaction, up to 5 recently-read files are re-injected (up to 5K tokens each, 50K total budget). Active skill content is also re-injected. The transcript path is included so the model can read the raw JSONL if it needs exact details.

**Key constants**:
- `AUTOCOMPACT_BUFFER_TOKENS = 13,000`
- `MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20,000`
- `POST_COMPACT_MAX_FILES_TO_RESTORE = 5`
- `POST_COMPACT_TOKEN_BUDGET = 50,000`
- `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3` (circuit breaker)

**Critical design detail**: The compaction prompt starts with `CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.` and ends with a reminder. This prevents the summarization model from trying to use tools.

### Implementation Recommendations for SaltAgent
- **Token counting**: Use `tiktoken` or Anthropic's token counting API to track context usage
- **Trigger**: Check after each model response; compact when usage > 80% of context window
- **Prompt**: Use the 9-section summarization prompt structure (it's well-tested)
- **Boundary marker**: Insert a sentinel message so you know where compaction happened
- **Post-compact**: Re-inject key files and the transcript path
- **Circuit breaker**: Stop retrying after 3 consecutive failures

### Estimated Effort: **Large** (1-2 days)

---

## 3. Session Persistence / Resume

### Files
- `src/utils/sessionStorage.ts` -- JSONL transcript read/write, session metadata
- `src/utils/sessionRestore.ts` -- resume logic: state restoration, agent re-linking
- `src/history.ts` -- session listing and navigation

### How It Works

**Storage format**: Each session is a JSONL file at `~/.claude/projects/<sanitized-cwd>/<session-id>.jsonl`. Each line is a JSON entry with a `type` field.

**Entry types in the JSONL**:
- `user`, `assistant`, `attachment`, `system` -- transcript messages (the conversation)
- `file_history_snapshot` -- file backup state for rewind
- `attribution_snapshot` -- commit attribution tracking
- `content_replacement` -- large tool outputs replaced with references
- `context_collapse_commit/snapshot` -- context collapse state

**Session metadata** is appended to the JSONL as entries with fields like `sessionId`, `agentName`, `agentColor`, `agentSetting`, `customTitle`, `mode`, `worktreeSession`, etc. Metadata is re-appended on session exit.

**Resume process** (`sessionRestore.ts`):
1. Load the JSONL transcript file
2. Parse entries into typed messages (user/assistant/system/attachment)
3. Restore file history snapshots
4. Restore attribution state
5. Restore context-collapse state
6. Extract todos from transcript (scan backwards for last TodoWrite block)
7. Restore agent settings (model override, agent type)
8. Restore worktree state (cd back into worktree if session crashed inside one)
9. Re-append session metadata to the JSONL

**Key design decisions**:
- JSONL format: append-only, one JSON object per line, easy to parse
- `parentUuid` chain: each message references its parent for ordering
- Subagent transcripts stored in `<session-id>/subagents/agent-<agentId>.jsonl`
- `--fork-session` creates a new session ID but copies messages
- Content replacement: large tool outputs are stored separately and referenced by ID

### Implementation Recommendations for SaltAgent
- **Format**: Use JSONL -- simple, append-only, easy to parse
- **Location**: `~/.saltagent/projects/<sanitized-cwd>/<session-id>.jsonl`
- **Append on each message**: Don't batch writes; append immediately
- **Resume**: Parse JSONL, rebuild message array, restore state
- **Metadata**: Append a metadata entry at session start and end
- **Content replacement**: For large tool outputs, store separately and reference by hash

### Estimated Effort: **Medium** (4-6 hours)

---

## 4. Memory System

### Files
- `src/memdir/memdir.ts` -- memory prompt generation, MEMORY.md handling
- `src/memdir/findRelevantMemories.ts` -- per-turn memory selection via Sonnet
- `src/memdir/memoryScan.ts` -- filesystem scanning of memory files
- `src/memdir/paths.ts` -- memory directory path resolution
- `src/memdir/memoryTypes.ts` -- 4-type taxonomy (user/feedback/project/reference)
- `src/utils/claudemd.ts` -- CLAUDE.md file discovery and loading

### How It Works

**Two separate systems**:

**A. CLAUDE.md (instruction files)** -- loaded in priority order:
1. Managed (`/etc/claude-code/CLAUDE.md`) -- global for all users
2. User (`~/.claude/CLAUDE.md`) -- private global
3. Project (`CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/*.md`) -- checked into repo
4. Local (`CLAUDE.local.md`) -- private per-project

Files closer to cwd have higher priority (loaded later in context). Supports `@path` include directives for referencing other files. Max character count per file: 40,000.

**B. Auto Memory (memdir)** -- persistent file-based memory at `~/.claude/projects/<sanitized-git-root>/memory/`:
- `MEMORY.md` is the index file (loaded into every conversation, max 200 lines / 25KB)
- Individual memory files with YAML frontmatter (name, description, type)
- 4-type taxonomy: user preferences, feedback, project context, reference
- Model writes memories as markdown files with frontmatter
- Model updates MEMORY.md index with one-line pointers

**Per-turn memory recall** (`findRelevantMemories.ts`):
1. Scan memory directory for `.md` files (max 200, sorted by mtime)
2. Read frontmatter headers (description, type) -- first 30 lines only
3. Format as a manifest and send to Sonnet via `sideQuery`
4. Sonnet selects up to 5 relevant memories based on the user's query
5. Selected memory files are injected into context

**The selection prompt**: "You are selecting memories that will be useful to Claude Code as it processes a user's query. Return a list of filenames (up to 5). Only include memories you are certain will be helpful. If unsure, do not include."

**Key design decisions**:
- Memory files use frontmatter for metadata (name, description, type)
- MEMORY.md is always in context; topic files are selectively injected
- Selection uses a cheap Sonnet call with structured JSON output
- Recently-used tools are passed to the selector to avoid re-surfacing tool docs the model is already using
- `alreadySurfaced` set prevents re-picking files shown in prior turns

### Implementation Recommendations for SaltAgent
- **CLAUDE.md**: Implement hierarchical loading (user > project > local) with priority ordering
- **Memory directory**: Use `~/.saltagent/projects/<git-root>/memory/` with MEMORY.md as index
- **Frontmatter**: Parse YAML frontmatter from memory files for metadata
- **Per-turn recall**: Use a cheap model call (Haiku/Sonnet) to select relevant memories
- **Skip for v1**: The per-turn recall via side query is expensive -- start with just always loading MEMORY.md

### Estimated Effort: **Medium** (CLAUDE.md loading: 2-3 hours; full memdir with recall: 1 day)

---

## 5. Subagent/Fork System

### Files
- `src/tools/AgentTool/AgentTool.tsx` -- main Agent tool (400+ lines)
- `src/tools/AgentTool/prompt.ts` -- agent tool prompt with examples
- `src/tools/AgentTool/forkSubagent.ts` -- fork semantics (inherits parent context)
- `src/tools/AgentTool/runAgent.ts` -- agent execution engine
- `src/tools/AgentTool/loadAgentsDir.ts` -- agent definition loading from markdown files
- `src/tools/AgentTool/agentMemory.ts` -- agent-specific memory
- `src/tasks/LocalAgentTask/` -- async/background agent task management

### How It Works

**Two modes of spawning**:

**A. Fresh subagent** (with `subagent_type`): Starts with zero context. Gets a clean system prompt, its own tool pool, and the user's prompt as its first message. Used for specialized tasks (test-runner, code-reviewer, etc.).

**B. Fork** (without `subagent_type`): Inherits the parent's FULL conversation context and system prompt. The fork child gets the parent's message history plus a directive. Designed for prompt cache sharing -- all forks from the same parent share the same API request prefix.

**Agent definitions**: Loaded from `.claude/agents/*.md` files with YAML frontmatter specifying:
- `agentType` -- name
- `whenToUse` -- description
- `tools` / `disallowedTools` -- tool allowlist/denylist
- `maxTurns` -- turn limit
- `model` -- model override or "inherit"
- `permissionMode` -- "bubble" (surface to parent) or others

**Execution flow** (`runAgent.ts`):
1. Create a unique `agentId` (UUID)
2. Resolve tool pool (filter by agent's tools/disallowedTools)
3. Build system prompt (agent's custom or default)
4. Create a child abort controller
5. Call `query()` in a loop with the agent's messages and tools
6. Agent runs autonomously up to `maxTurns`
7. Result is returned as a tool result to the parent

**Fork-specific behavior**:
- `buildForkedMessages()` creates the child's message history:
  - Full parent assistant message (all tool_use blocks)
  - Single user message with placeholder tool_results + the directive
  - All forks get identical placeholders so API prefix is byte-identical (cache sharing)
- Fork child gets a strict boilerplate: "You are a forked worker process. Do NOT spawn sub-agents. Execute directly."
- Output format enforced: Scope, Result, Key files, Files changed, Issues
- `isInForkChild()` detects recursive fork attempts by checking for the boilerplate tag in history

**Background/async**: Agents can run in background (`run_in_background: true`). The parent continues working and gets a notification when the agent completes.

**Isolation**: `isolation: "worktree"` creates a temporary git worktree so the agent works on an isolated copy.

### Implementation Recommendations for SaltAgent
- **Start simple**: Implement fresh subagents first (no fork/context inheritance)
- **Agent definitions**: Load from `.saltagent/agents/*.md` with YAML frontmatter
- **Execution**: Spawn a new model conversation with the agent's system prompt + user prompt
- **Tool filtering**: Allow agents to declare allowed/disallowed tools
- **Communication**: Agent returns a single result string to the parent
- **Background**: Run in a thread/process, notify parent on completion
- **Skip for v1**: Fork semantics (context inheritance, cache sharing), worktree isolation, remote agents

### Estimated Effort: **Large** (basic subagents: 1 day; full fork system: 3-4 days)

---

## 6. Permission System

### Files
- `src/hooks/toolPermission/PermissionContext.ts` -- permission evaluation context
- `src/hooks/toolPermission/handlers/` -- per-tool permission handlers
- `src/utils/permissions/permissions.ts` -- core permission matching logic
- `src/utils/permissions/PermissionRule.ts` -- rule data structures
- `src/utils/permissions/PermissionUpdate.ts` -- rule persistence
- `src/utils/classifierApprovals.ts` -- AI-based auto-approval tracking

### How It Works

**Permission flow for each tool use**:
1. Tool's `checkPermissions()` method runs first (tool-level validation)
2. Permission rules are checked against a priority-ordered rule set
3. If no rule matches, hooks run (`PermissionRequest` hook event)
4. If no hook decides, the bash classifier may auto-approve (AI-based)
5. If still undecided, the user is prompted in the UI

**Permission rules** have:
- `tool` -- which tool (e.g., "Bash", "FileWrite")
- `value` -- pattern to match (e.g., command regex, file path glob)
- `behavior` -- "allow" | "deny" | "ask"
- `source` -- where the rule came from (user settings, project settings, CLI)

**Rule sources** (priority order):
1. Policy settings (managed/enterprise)
2. User settings (`~/.claude/settings.json`)
3. Project settings (`.claude/settings.json`)
4. Local settings (`.claude/settings.local.json`)
5. CLI flags

**Classifier auto-approval** (`classifierApprovals.ts`):
- Two classifiers: `bash` (command safety) and `auto-mode` (transcript-based)
- Bash classifier evaluates if a command is safe to auto-approve
- Auto-mode classifier uses conversation transcript to assess safety
- Approvals are tracked per tool_use_id

**Permission persistence**: Users can choose "Allow always" which persists the rule to settings.json. Rules support both session-scoped and permanent storage.

**Subagent permissions**: `permissionMode: "bubble"` surfaces permission prompts to the parent terminal. Subagents can also run with pre-approved permissions.

### Implementation Recommendations for SaltAgent
- **Rule format**: JSON rules with tool name, pattern, and behavior
- **Rule sources**: Start with user config file + project config
- **Flow**: Check rules first, fall back to user prompt
- **Persistence**: "Allow always" writes to user config
- **Skip for v1**: Classifier auto-approval, managed/enterprise policies

### Estimated Effort: **Medium** (basic allow/deny rules: 4-6 hours; full system with classifiers: 2 days)

---

## 7. Hook Engine

### Files
- `src/utils/hooks.ts` -- core hook execution engine (~700+ lines)
- `src/utils/hooks/hookEvents.ts` -- event broadcasting system
- `src/utils/hooks/hooksConfigManager.ts` -- configuration management
- `src/utils/hooks/sessionHooks.ts` -- per-session hook registration
- `src/utils/hooks/execAgentHook.ts` -- agent-type hook execution
- `src/utils/hooks/execPromptHook.ts` -- prompt-injection hooks
- `src/utils/hooks/execHttpHook.ts` -- HTTP webhook hooks
- `src/entrypoints/sdk/coreTypes.ts` -- hook event type definitions

### How It Works

**27 hook events** defined:
- **Tool lifecycle**: `PreToolUse`, `PostToolUse`, `PostToolUseFailure`
- **Session lifecycle**: `SessionStart`, `SessionEnd`, `Setup`
- **Agent lifecycle**: `SubagentStart`, `SubagentStop`
- **Compaction**: `PreCompact`, `PostCompact`
- **Permission**: `PermissionRequest`, `PermissionDenied`
- **Task**: `TaskCreated`, `TaskCompleted`
- **User interaction**: `UserPromptSubmit`, `Notification`
- **Stop**: `Stop`, `StopFailure`
- **Config**: `ConfigChange`, `InstructionsLoaded`, `CwdChanged`, `FileChanged`
- **Worktree**: `WorktreeCreate`, `WorktreeRemove`
- **Other**: `TeammateIdle`, `Elicitation`, `ElicitationResult`

**Hook types**:
1. **Shell hooks**: Execute shell commands with JSON on stdin, parse JSON from stdout
2. **Agent hooks**: Spawn an agent (model call) with the hook input
3. **HTTP hooks**: POST to a URL with the hook input as JSON body
4. **Prompt hooks**: Inject text into the system prompt
5. **Function hooks**: In-process callbacks (SDK/programmatic)

**Hook configuration**: Defined in `settings.json` under a `hooks` key, keyed by event name. Each hook has:
- `matcher` -- which tools/events to match (glob patterns, regex)
- `command` -- shell command to execute
- `timeout` -- execution timeout (default: 10 minutes for tool hooks, 1.5s for SessionEnd)

**Hook input/output**: Hooks receive JSON on stdin with event-specific fields (tool name, input, session ID, transcript path, etc.). They return JSON on stdout with fields like `decision` (allow/deny), `reason`, `updatedInput`.

**Async hooks**: Can run in background. Some hooks (like `asyncRewake`) fire and forget, notifying via task-notification on completion.

**Key design**: Hooks are the extension mechanism for external consumers. The SDK uses hooks for programmatic control. Plugins register hooks via frontmatter. Skills register hooks for their lifecycle events.

### Implementation Recommendations for SaltAgent
- **Start with**: `PreToolUse` (permission checks), `PostToolUse` (logging), `SessionStart`, `SessionEnd`
- **Format**: Shell commands that receive JSON on stdin and return JSON on stdout
- **Config**: Define in a config file, keyed by event name
- **Skip for v1**: Agent hooks, HTTP hooks, prompt hooks, async hooks

### Estimated Effort: **Medium** (basic shell hooks for 4 events: 4-6 hours; full 27-event system: 2-3 days)

---

## 8. Streaming Tool Execution

### Files
- `src/services/tools/StreamingToolExecutor.ts` -- core executor class
- `src/query.ts` -- integration in the main query loop
- `src/query/config.ts` -- feature gate (`streamingToolExecution`)

### How It Works

**Yes, Claude Code starts executing tools BEFORE the model finishes streaming.**

**StreamingToolExecutor class**:
1. As the model streams its response, each `tool_use` block is detected and added to the executor via `addTool(block, assistantMessage)`
2. The executor immediately starts executing tools that are safe to run concurrently
3. Results are buffered and emitted in the order tools were received (preserving ordering)

**Concurrency model**:
- Each tool declares `isConcurrencySafe(input)` -- whether it can run in parallel
- Concurrent-safe tools execute in parallel with other concurrent-safe tools
- Non-concurrent tools get exclusive access (must execute alone)
- A child abort controller fires when a Bash tool errors, killing sibling subprocesses

**Tool tracking states**: `queued` -> `executing` -> `completed` -> `yielded`

**Integration with query loop** (`query.ts`):
```
const useStreamingToolExecution = config.gates.streamingToolExecution
let streamingToolExecutor = useStreamingToolExecution
  ? new StreamingToolExecutor(tools, canUseTool, toolUseContext, ...)
  : null
```
When streaming, as each tool_use block arrives: `streamingToolExecutor.addTool(toolBlock, message)`. After streaming completes, `getRemainingResults()` yields any still-pending results.

**Fallback**: If streaming fails, the executor is discarded (`discard()`) and tools are re-executed sequentially.

### Implementation Recommendations for SaltAgent
- **Worth implementing**: Significant speedup for multi-tool responses
- **Design**: As the stream yields tool_use blocks, queue them for immediate execution
- **Concurrency**: Mark read-only tools (Read, Grep, Glob) as concurrent-safe
- **Ordering**: Buffer results and yield in original order
- **Error handling**: If one tool fails, optionally cancel siblings

### Estimated Effort: **Medium** (basic streaming execution: 4-6 hours; full concurrency model: 1 day)

---

## 9. File History / Rewind

### Files
- `src/utils/fileHistory.ts` -- complete implementation (~500 lines)
- `src/hooks/useFileHistorySnapshotInit.ts` -- initialization hook

### How It Works

**Snapshot system**:
- Before any file edit, `fileHistoryTrackEdit()` creates a backup of the original file
- After each model turn, `fileHistoryMakeSnapshot()` creates a snapshot of all tracked files
- Snapshots are stored in `~/.claude/.file_history/` as content-addressed files (SHA-256 hash)

**Backup storage**: Files are backed up using hard links (fast, no extra disk space if content hasn't changed). Backup filename format: `<sha256-of-content>@v<version>`. New files get `backupFileName: null` to indicate they didn't exist.

**State tracking** (`FileHistoryState`):
```
{
  snapshots: FileHistorySnapshot[]  // max 100
  trackedFiles: Set<string>         // all files ever modified
  snapshotSequence: number          // monotonic counter
}
```

Each `FileHistorySnapshot`:
```
{
  messageId: UUID                   // associated with which model message
  trackedFileBackups: Record<string, FileHistoryBackup>
  timestamp: Date
}
```

**Rewind** (`fileHistoryRewind()`):
1. Find the target snapshot by `messageId`
2. Call `applySnapshot()` which restores each tracked file from its backup
3. If the backup is `null` (file was created during the session), the file is deleted
4. If the backup file exists, copy it back to the original location

**Diff stats**: `fileHistoryGetDiffStats()` compares current file state against a snapshot to show what would change on rewind (files changed, insertions, deletions).

**Resume support**: Snapshots are serialized to the session JSONL transcript. On resume, `fileHistoryRestoreStateFromLog()` rebuilds the state from persisted snapshot entries.

### Implementation Recommendations for SaltAgent
- **Backup directory**: `~/.saltagent/.file_history/`
- **Before each edit**: Copy original file to backup dir with content hash
- **Snapshot per turn**: Record which files have which backup versions
- **Rewind**: Copy backup files back to original locations
- **Skip for v1**: Diff stats, hard links (just use file copies), resume support

### Estimated Effort: **Medium** (basic backup/rewind: 4-6 hours; full with resume: 1 day)

---

## 10. Security Monitor / Classifier

### Files
- `src/utils/classifierApprovals.ts` -- approval tracking store
- `src/utils/permissions/permissions.ts` -- classifier integration in permission flow
- `src/tools/BashTool/bashPermissions.ts` -- bash command classifier
- `src/utils/permissions/classifierDecision.ts` -- classifier decision types (gated)
- `src/utils/permissions/autoModeState.ts` -- auto-mode (YOLO) state (gated)

### How It Works

**Two classifier systems** (both behind feature flags):

**A. Bash Classifier** (`BASH_CLASSIFIER` feature flag):
- Evaluates bash commands for safety before execution
- Runs as a side query (cheap model call) in parallel with the permission prompt
- If the classifier approves before the user responds, the command runs automatically
- Tracks approvals per `tool_use_id` for UI display ("auto-approved by classifier: <rule>")
- Uses `awaitClassifierAutoApproval()` which races the classifier against user input

**B. Transcript Classifier** (`TRANSCRIPT_CLASSIFIER` feature flag):
- Auto-mode / "YOLO mode" safety monitor
- Evaluates the full conversation transcript context to assess whether an action is safe
- Uses `setYoloClassifierApproval()` / `getYoloClassifierApproval()`
- Tracks denial counts with circuit breaker: after repeated denials, falls back to prompting
- `DenialTrackingState` with `DENIAL_LIMITS` for windowed denial counting

**Classifier checking state**:
- `setClassifierChecking(toolUseID)` -- marks a tool as being evaluated
- `clearClassifierChecking(toolUseID)` -- evaluation complete
- UI subscribes to `subscribeClassifierChecking` signal to show "evaluating..." indicator

**The classifier decision flow** (in auto/YOLO mode):
1. Tool use arrives, permission check starts
2. If auto-mode is active, the transcript classifier evaluates safety
3. If approved, the tool runs without user prompt
4. If denied, the user is prompted (or the action is auto-rejected with a message)
5. Denial tracking prevents infinite loops of denied actions

### Implementation Recommendations for SaltAgent
- **Start simple**: Rules-based allowlist for safe bash commands (ls, cat, git status, etc.)
- **Phase 2**: Add a cheap model call to evaluate commands not on the allowlist
- **Auto-mode**: Track denial counts; if the model keeps trying denied actions, abort
- **Skip for v1**: Full transcript-based classifier, real-time classifier racing

### Estimated Effort: **Small** for basic rules; **Large** for AI classifiers (2-3 days)

---

## Prioritized Implementation Plan for SaltAgent

### Phase 1: Build First (High Impact, Lower Effort)

1. **TodoWrite/TodoRead** -- Small effort, high UX impact. The model naturally wants to track progress; giving it this tool makes complex tasks more reliable.

2. **Session Persistence (JSONL transcripts)** -- Medium effort, foundational. Every other feature depends on having persistent sessions. Implement append-only JSONL with resume.

3. **CLAUDE.md Loading** -- Small-medium effort, high impact. Load instruction files from user home + project directory. This is the primary configuration mechanism.

4. **File History / Rewind** -- Medium effort, high safety value. Backup files before edits; provide rewind. Users need this escape hatch.

### Phase 2: Build Second (High Impact, Higher Effort)

5. **Context Compaction** -- Large effort, essential for long sessions. Use the 9-section summarization prompt. Trigger at 80% context usage.

6. **Basic Permission System** -- Medium effort. Rules-based allow/deny for tools. "Allow always" persistence. No classifier needed yet.

7. **Basic Subagent System** -- Large effort, but unlocks parallel work. Start with fresh subagents only (no fork/context sharing).

8. **Streaming Tool Execution** -- Medium effort, significant perf improvement. Start executing tools as they stream in.

### Phase 3: Build Later (Nice to Have)

9. **Hook Engine** -- Build when external integrations are needed. Start with PreToolUse + SessionStart/End.

10. **Memory System with Recall** -- The per-turn Sonnet call for memory selection is expensive. Start with always-loaded MEMORY.md; add selective recall later.

11. **Security Classifier** -- Only needed for auto-mode / YOLO. Start with rules-based safety.

### Skip for v1

- Fork subagent semantics (context inheritance, cache sharing)
- Worktree isolation for agents
- Remote agent execution
- Team memory
- AI-based bash classifier
- Transcript-based auto-mode classifier
- Agent-type hooks and HTTP hooks
- Partial compaction (just do full compaction)
- Prompt hooks
- Context collapse (UI optimization, not core functionality)
