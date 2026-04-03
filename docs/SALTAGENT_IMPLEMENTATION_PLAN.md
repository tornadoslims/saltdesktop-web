# SaltAgent Implementation Plan

**Date:** 2026-04-02
**Status:** Active
**Based on:** Claude Code source analysis (`CLAUDE_CODE_SOURCE_ANALYSIS.md`), PDF technical report, leaked system prompts, learn-claude-code patterns, KODE SDK architecture

---

## Current State

SaltAgent v0.1 exists at `/Users/jimopenclaw/saltdesktop/salt_agent/` with:
- Core agent loop (async, streaming, multi-turn) ✅
- 7 built-in tools (read, write, edit, bash, glob, grep, list_files) ✅
- 2 provider adapters (Anthropic, OpenAI) ✅
- Event streaming for UI ✅
- Read-before-edit enforcement ✅
- Basic context truncation ✅
- CLI (one-shot + interactive) ✅
- 254 system prompts integrated with assembler ✅
- Provider-specific prompt adapters ✅
- 65 tests passing ✅

---

## Missing Features (10 items, prioritized)

### Phase 1: Build Now (critical for usability)

#### 1. TodoWrite Tool
**What:** Agent self-tracking task list. Prevents task amnesia.
**How Claude Code does it:** Flat array of `{content, status, activeForm}`. Replace-all semantics — the agent writes the ENTIRE list each time (no CRUD). No separate TodoRead tool — the current list is injected into context automatically.
**Implementation:**
- New tool: `salt_agent/tools/todo.py`
- Schema: `TodoWriteTool.execute(tasks=[{content: str, status: "pending"|"in_progress"|"completed"}])`
- Store in agent state (in-memory), inject into context each turn
- On compaction, preserve the task list
**Effort:** Small (1-2 hours)
**Files:** `salt_agent/tools/todo.py`, update `agent.py` to inject todo state

#### 2. Hook Engine
**What:** PreToolUse/PostToolUse callbacks. This is how Salt Desktop tracks what the agent does — update graph nodes, activity feed, permission requests.
**How Claude Code does it:** 27 hook events covering tool/session/agent/compaction/permission lifecycle. Hooks execute as shell commands (JSON stdin/stdout), HTTP webhooks, agent calls, or in-process functions.
**Implementation:**
- New module: `salt_agent/hooks.py`
- Hook types: `pre_tool_use`, `post_tool_use`, `pre_api_call`, `post_api_call`, `on_error`, `on_complete`, `on_permission_request`
- Registration: `agent.hooks.on("pre_tool_use", callback)`
- Callbacks receive event data dict, can return `{"action": "allow"}` or `{"action": "block", "reason": "..."}`
- Salt Desktop registers hooks to update UI in real-time
**Effort:** Small (2-3 hours)
**Files:** `salt_agent/hooks.py`, update `agent.py` to call hooks

#### 3. Context Compaction
**What:** Summarize old turns when the context window fills up. Without this, any task > 20 turns crashes.
**How Claude Code does it:**
- Triggers at `contextWindow - maxOutput - 13K` tokens (~80% full)
- Forks a side-query to the same model with a 9-section summarization prompt
- The `<analysis>` scratchpad block improves summary quality (then stripped from result)
- Post-compact: re-injects up to 5 recently-read files (50K token budget) + the raw transcript path
- The summary replaces all messages except the last user message
**Implementation:**
- New module: `salt_agent/compaction.py`
- Token estimation: `len(text) / 4` (approximate)
- Trigger: check after each turn, if estimated tokens > 80% of context window
- Summarization: side-query using the summarization prompt from `prompts/summarization.py`
- Post-compact restoration: re-inject files from `read_tool.files_read` (most recent N)
- Preserve: todo list, working directory, files modified list
**Effort:** Medium (4-6 hours)
**Files:** `salt_agent/compaction.py`, update `agent.py` and `context.py`

---

### Phase 2: Build Next (makes it reliable)

#### 4. Session Persistence
**What:** Save conversation state before every API call. Resume from crashes. Search past sessions.
**How Claude Code does it:**
- JSONL files at `~/.claude/projects/<sanitized-cwd>/<session-id>.jsonl`
- Append-only, one JSON object per line
- Messages carry `parentUuid` for ordering
- Write BEFORE the API call (so a killed process can still resume)
- Subagent transcripts nested under session directory
**Implementation:**
- New module: `salt_agent/persistence.py`
- Save location: `~/.saltdesktop/sessions/<session-id>.jsonl`
- Save: append message to JSONL before each API call
- Resume: `agent.resume(session_id)` — hydrates messages from JSONL
- Search: grep through JSONL files for content
**Effort:** Medium (3-4 hours)
**Files:** `salt_agent/persistence.py`, update `agent.py`

#### 5. Memory System
**What:** Project-level instructions (like CLAUDE.md), cross-session memory, per-turn relevant memory surfacing.
**How Claude Code does it:**
- Two layers: CLAUDE.md (hierarchical, always loaded) + auto-memory (`memory/` dir with MEMORY.md index)
- Per-turn: side-query to Sonnet selects up to 5 relevant memory files from frontmatter headers
- Memory files have `name`, `description`, `type` frontmatter
**Implementation:**
- New module: `salt_agent/memory.py`
- Project instructions: look for `CLAUDE.md` or `SALT.md` in working directory and parents
- Memory dir: `~/.saltdesktop/memory/` with `MEMORY.md` index
- Per-turn surfacing: lightweight side-query listing memory file descriptions, model picks relevant ones
- Inject selected memories into context assembly
**Effort:** Medium (4-5 hours)
**Files:** `salt_agent/memory.py`, update `context.py`

#### 6. Permission System
**What:** Ask before dangerous operations. Bash commands need approval, file writes outside working dir need approval.
**How Claude Code does it:**
- Multi-layered: tool-level checks → rule matching (from settings) → hooks → bash classifier (AI side-query) → user prompt
- Rules from policy > user > project > local settings
- Classifier races the user prompt — whichever responds first wins
**Implementation (simplified for v1):**
- New module: `salt_agent/permissions.py`
- Rules: `{"bash": "ask", "write_outside_cwd": "deny", "write_inside_cwd": "allow"}`
- In CLI: prompt user for approval. In Salt Desktop: emit permission event, wait for UI response.
- Hook integration: `pre_tool_use` hook can block tools
**Effort:** Small-Medium (2-3 hours)
**Files:** `salt_agent/permissions.py`, update `agent.py`

---

### Phase 3: Build Later (makes it powerful)

#### 7. Subagent/Fork System
**What:** Spawn child agents for exploration, verification, parallel work.
**How Claude Code does it:**
- Fresh subagents: zero context + prompt (for explore, verify)
- Forks: inherit parent's full conversation, share prompt cache (byte-identical prefix)
- Fork children get strict boilerplate with output format rules
- Subagent results are collected and injected back into parent
**Implementation:**
- New module: `salt_agent/subagent.py`
- `agent.spawn_subagent(prompt, mode="explore")` — creates new SaltAgent with its own context
- `agent.fork(prompt)` — creates new SaltAgent with parent's messages
- Results returned as tool_result to parent
- Salt Desktop integration: subagent events feed into the "swarm" visualization
**Effort:** Medium (4-6 hours)
**Files:** `salt_agent/subagent.py`, new Agent tool in `tools/`

#### 8. File History / Rewind
**What:** Snapshot files before modification. Rewind to restore.
**How Claude Code does it:**
- Content-addressed backups: SHA-256 hash as filename, stored via hard links
- Max 100 snapshots per session
- Rewind restores files from backups; files created during session are deleted
**Implementation:**
- New module: `salt_agent/file_history.py`
- Before each write/edit: snapshot the original file content
- Storage: `~/.saltdesktop/snapshots/<session-id>/<sha256>.bak`
- Rewind: restore all modified files, delete created files
- Hook into WriteTool and EditTool via the hook engine
**Effort:** Small (2-3 hours)
**Files:** `salt_agent/file_history.py`, hook into write/edit tools

#### 9. Streaming Tool Execution
**What:** Execute tools while the model is still streaming its response.
**How Claude Code does it:**
- `StreamingToolExecutor` queues tools as `tool_use` blocks arrive during streaming
- Concurrent-safe tools run in parallel
- Buffers results in order for the next API call
- Significant latency reduction
**Implementation:**
- Modify the agent loop to detect tool_use blocks during streaming (not after)
- Start execution immediately while continuing to read the stream
- Buffer results, assemble tool_result messages in order
- Requires careful async handling
**Effort:** Hard (6-8 hours)
**Files:** Major refactor of `agent.py`

#### 10. Security Classifier
**What:** AI side-query to classify bash commands as safe/dangerous for autonomous mode.
**How Claude Code does it:**
- Two classifiers: bash command safety + transcript-based auto-mode classifier
- Both run as cheap side-queries (Haiku) racing the user permission prompt
- Denial tracking with circuit breakers
**Implementation:**
- New module: `salt_agent/security.py`
- Lightweight LLM call with the security prompt from `prompts/security.py`
- Classify bash commands: safe (allow), needs-review (ask), dangerous (block)
- Integrate with permission system
**Effort:** Medium (3-4 hours)
**Files:** `salt_agent/security.py`, integrate with `permissions.py`

---

## Additional Tools to Add

Based on Claude Code's tool set, these tools are NOT yet in SaltAgent:

| Tool | Priority | Effort | Notes |
|------|----------|--------|-------|
| TodoWrite | Phase 1 | Small | See #1 above |
| WebFetch | Phase 2 | Small | Fetch URL content, return as text |
| WebSearch | Phase 2 | Small | Search via API (Brave, DuckDuckGo, etc.) |
| MultiEdit | Phase 2 | Small | Multiple edits to same file in one call |
| Agent (subagent) | Phase 3 | Medium | Spawn child agent as a tool |
| NotebookEdit | Skip | Medium | Jupyter notebooks — not needed |
| LSP | Skip | Hard | Language server — overkill for v1 |

---

## Implementation Order

```
Week 1:
  ├── TodoWrite tool
  ├── Hook engine
  ├── Context compaction
  └── Basic permission system

Week 2:
  ├── Session persistence
  ├── Memory system (CLAUDE.md loading)
  ├── WebFetch + WebSearch tools
  └── MultiEdit tool

Week 3:
  ├── Subagent/fork system
  ├── File history/rewind
  ├── Security classifier
  └── Per-turn memory surfacing

Week 4:
  ├── Streaming tool execution
  ├── Integration testing with Salt Desktop
  ├── Performance optimization
  └── Documentation
```

---

## Key Architecture Decisions

1. **Hooks are the integration layer.** Salt Desktop doesn't poll SaltAgent — it registers hooks that fire on every tool call, error, completion. This is how the graph updates in real-time.

2. **Compaction uses the same model.** Don't switch to a cheaper model for summarization — the quality drop is too high. Use the same model with the summarization prompt.

3. **Persistence is append-only JSONL.** Simple, crash-safe, grep-able. No database for sessions.

4. **Permissions default to "ask" in CLI, "allow" in Salt Desktop.** The UI handles permission differently (emit event, wait for UI response). The CLI prompts the user.

5. **Subagents are cheap.** Fresh subagents get zero context — they're disposable. Forks are expensive but share the prompt cache.

6. **File history uses content-addressing.** Hard links save disk space. SHA-256 prevents duplicates.

---

## Success Criteria

SaltAgent reaches feature parity with Claude Code when:
- [ ] Can plan work before acting (TodoWrite)
- [ ] Can handle sessions > 50 turns without crashing (compaction)
- [ ] Can resume from a crashed session (persistence)
- [ ] Can read project instructions (memory/CLAUDE.md)
- [ ] Can spawn focused sub-tasks (subagents)
- [ ] Asks before dangerous operations (permissions)
- [ ] Salt Desktop can track every action in real-time (hooks)
- [ ] Can undo mistakes (file history/rewind)
- [ ] Autonomous mode with safety guardrails (security classifier)

---

## References

- `docs/CLAUDE_CODE_SOURCE_ANALYSIS.md` — Detailed analysis of each feature from actual source code
- `docs/CLAUDE_CODE_INTERNALS.md` — Architecture overview from PDF + leaked prompts
- `docs/LEARN_CLAUDE_CODE_ANALYSIS.md` — Python implementation patterns
- `docs/KODE_AGENT_SDK_ANALYSIS.md` — TypeScript reference architecture
- `docs/SALTAGENT_PRD.md` — Product requirements
- `docs/PROVIDER_PROMPT_ANALYSIS.md` — Per-provider prompt adaptations
- `docs/PROMPT_ANALYSIS.md` — Analysis of all 254 system prompts
