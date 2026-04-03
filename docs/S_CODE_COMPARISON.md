# s_code vs Claude Code — Complete Feature Comparison

**s_code is a standalone, open-source, multi-provider AI agent engine built in Python.**
**It replicates Claude Code's architecture with key advantages: provider freedom, full extensibility, and embeddability.**

---

## The Numbers

```
┌─────────────────────────┬──────────────┬──────────────────────────┐
│         Metric          │   s_code     │   vs Claude Code         │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ Tools                   │ 42           │ 42/42 (100%)             │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ Slash Commands          │ 72           │ 72/86 (84%)              │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ Hook Events             │ 29           │ 29/30 (97%)              │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ Bundled Skills          │ 17           │ ~20                      │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ System-Reminder Types   │ 15           │ ~30 (rest need IDE)      │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ Compaction Layers       │ 5 + cached   │ 6                        │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ Prompt Fragments        │ 254          │ 254                      │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ Tests                   │ 1,245        │ —                        │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ LLM Providers           │ 2+ (any)     │ 1 (Anthropic only)       │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ Embeddable              │ Yes (Python) │ No (CLI binary)          │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ Language                 │ Python       │ TypeScript               │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ License                  │ MIT          │ Proprietary              │
├─────────────────────────┼──────────────┼──────────────────────────┤
│ Estimated Parity        │ ~92%         │ (standalone CLI basis)    │
└─────────────────────────┴──────────────┴──────────────────────────┘
```

---

## Why s_code Feels "Magic" Like Claude Code

Claude Code feels magical because of what happens BETWEEN the user's message and the response. It's not the model — it's the runtime. s_code replicates every layer of that runtime:

### 1. The Agent Loop (QueryEngine Pattern)
**Claude Code:** Stateful QueryEngine holds the conversation. Each turn adds to it, never starts fresh. System prompt reassembled every turn with fresh context.

**s_code:** Identical pattern. `_conversation_messages` persists across `run()` calls. System prompt rebuilt per-turn with date, git status, todo state, memory, and 15 attachment types.

### 2. Context Assembly (The "Brain" Before Each Call)
**Claude Code:** `utils/attachments.ts` (3,998 lines) assembles ~30 types of dynamic context before every LLM call: memories, file mentions, git status, diagnostics, plan mode, skills, MCP, agent context.

**s_code:** `attachments.py` assembles 15 types per turn: date/time, todo state, plan/auto mode, git status, modified files, file mentions, active tasks, session info, budget warnings, compaction notices, skills, environment, MCP status, recently modified files, memory. The model sees a rich operating context, not a bare prompt.

### 3. Five-Layer Compaction (Long Sessions Don't Die)
**Claude Code:** 6-layer progressive compaction: tool result budgeting → history snip → context collapse → cached microcompact → autocompact → emergency truncate. Sessions last hundreds of turns.

**s_code:** 5 layers + caching: microcompact tool results (every turn) → history snip (60%) → context collapse (70%) → LLM autocompact with `<analysis>` scratchpad (80%) → emergency truncate (95%). Post-compact file restoration reinjects recently-read files. CompactionCache avoids reprocessing.

### 4. Memory That Persists and Surfaces
**Claude Code:** CLAUDE.md discovery (walk up directories), auto-memory with 4 types (user/feedback/project/reference), per-turn LLM-powered relevance ranking, dream consolidation.

**s_code:** Identical. SALT.md/CLAUDE.md discovery, 4 memory types with YAML frontmatter, LLM side-query selects 0-5 relevant memories per turn, stop hooks extract worth-saving info every 5 turns, dream consolidation cleans up every 20 turns.

### 5. Read-Before-Edit Enforcement
**Claude Code:** Edit tool refuses to modify files the model hasn't read. Forces the model to understand context before changing it. String replacement (not line numbers) survives line drift.

**s_code:** Identical enforcement. WriteTool and EditTool track `files_read`. Edit requires unique `old_string`. Multi-edit for batched changes.

### 6. Self-Tracking Task List (TodoWrite)
**Claude Code:** Replace-all semantics — model writes the ENTIRE plan each time. Prevents task amnesia. Injected into context every turn.

**s_code:** Identical. TodoWriteTool with replace-all. Injected as system-reminder. Model always knows what it planned to do.

### 7. Streaming Tool Execution
**Claude Code:** `StreamingToolExecutor` starts executing safe tools (read, glob, grep, web_fetch) WHILE the model is still generating. Major latency win on multi-tool turns.

**s_code:** `StreamingToolExecutor` with `SAFE_STREAMING_TOOLS` frozenset. Safe tools start via `asyncio.create_task()` during streaming. Unsafe tools wait until stream ends. Results collected in order.

### 8. Subagents That Share Cache
**Claude Code:** Fresh subagents get zero context. Forks inherit full conversation with byte-identical prompt prefix for cache hits. Verification specialist with self-awareness prompt.

**s_code:** `SubagentManager.create_fresh()` (zero context) and `create_fork()` (inherits conversation + shares tool registry for cache). Async execution via `async_execute()` yields events through parent's generator. Verification mode with the "You are bad at verification" prompt.

### 9. Background Tasks (Parallel Agents)
**Claude Code:** Task system runs agents in parallel threads. 6 CRUD tools. Main agent continues while tasks execute.

**s_code:** `TaskManager` runs each task in a daemon thread with its own event loop and SaltAgent instance. 6 tools: task_create, task_list, task_get, task_output, task_stop, task_update. Completion callbacks notify CLI.

### 10. Loop Detection (Stuck Agent Recovery)
**Claude Code:** Detects repeating tool call patterns. Injects "you're stuck" message. Hard stops on second warning.

**s_code:** Tracks tool call signatures (name + input hash). Detects patterns of length 1-4 repeating 3+ times. First: injects warning. Second: hard stop. Unknown tools return available tool list with explicit "do NOT simulate with bash echo."

### 11. Cancel Cleanup (Conversation Stays Valid)
**Claude Code:** When cancelled mid-tool, adds dummy results so every tool_call has a matching tool response. Conversation is always API-valid.

**s_code:** Identical. Ctrl+C during tool execution adds "Tool call cancelled by user." for unprocessed calls. Both sequential and parallel paths handle cancel.

### 12. Session Persistence (Crash Recovery)
**Claude Code:** JSONL append-only per session. Write BEFORE API call. Resume hydrates from last checkpoint. Search across sessions.

**s_code:** Identical pattern. `SessionPersistence` writes JSONL checkpoints before every API call. `resume(session_id)` hydrates. `SessionSearchIndex` with inverted index for fast search. Concurrent session detection via PID lock files.

### 13. AI Permission Classifier
**Claude Code:** Races an AI side-query against the user prompt for bash commands. Classifier can escalate (allow→ask) but never downgrade (deny→allow).

**s_code:** `ai_classify_bash()` uses `quick_query()` on a cheap model. Rules-based check runs first (fast path). AI can escalate but never downgrade a hard deny. Full `BashSandbox` with 12 config options (blocked commands, patterns, sudo, network, paths, env filtering).

### 14. Hook Engine (Lifecycle Observability)
**Claude Code:** 30+ hook events. Shell command, HTTP webhook, agent call, and in-process function hooks. PreToolUse can block.

**s_code:** 29 events across session/turn/tool/memory/subagent/task/context/file lifecycle. In-process callbacks, shell commands (`ShellHook`), and HTTP webhooks (`HttpHook`). Pre-tool hooks can block or modify input.

### 15. Prompt Caching (Cost Reduction)
**Claude Code:** Prompt cache with `cache_control: ephemeral` on system prompt. Forks share byte-identical prefix.

**s_code:** Anthropic adapter sends system prompt with `cache_control: {"type": "ephemeral"}`. Fork subagents share identical system prompt + tool registry. 50-90% cost reduction on long sessions.

---

## Where s_code Goes BEYOND Claude Code

### Multi-Provider Support
Claude Code only works with Anthropic models. s_code works with:
- **Anthropic** (Claude Opus, Sonnet, Haiku)
- **OpenAI** (GPT-5.4, GPT-4o, o3, o4-mini)
- Any provider via custom `ProviderAdapter`

Switch models at runtime: `/model gpt-5.4` → `/model claude-sonnet-4-6`

### Provider-Specific Prompt Adaptation
s_code automatically adapts prompts for each provider. GPT models get channel architecture hints. Claude gets anti-sycophancy instructions. Gemini gets context hierarchy tags. The same agent works optimally across all models.

### Embeddable as a Python Library
Claude Code is a CLI binary. s_code is a Python library:

```python
from salt_agent import create_agent

agent = create_agent(provider="openai", model="gpt-4o")
async for event in agent.run("Fix the bug"):
    handle(event)
```

Embed in FastAPI, Flask, Django, Celery, desktop apps, Jupyter — anywhere Python runs.

### Custom Tools in 10 Lines
```python
from salt_agent import Tool, ToolDefinition, ToolParam

class MyTool(Tool):
    def definition(self):
        return ToolDefinition(name="my_tool", description="Does something", params=[])
    def execute(self, **kwargs):
        return "result"
```

### Plugin System
Discover and load plugins from directories or pip entry_points. Plugins can add tools, hooks, and prompts.

### Configurable Web Content Extraction
Three extraction backends: trafilatura (best), readability, regex. Configurable per-agent.

### Full Bash Sandbox
12 configurable options: blocked commands, patterns, sudo control, network control, path restrictions, environment filtering. Claude Code has basic sandbox flags.

### Token Budget with Auto-Continue
Tracks real token counts per turn. When the model hits 90% of output budget, automatically nudges it to continue (with diminishing returns detection). Budget limit enforcement stops the agent when `--max-budget-usd` is exceeded.

### Reactive State Store
`StateStore` with subscriber notifications. External systems observe agent state changes in real-time. Claude Code's AppStateStore is internal to the UI.

### Coordinator Mode
`--coordinator` strips write/execute tools. The agent can only delegate via tasks, teams, and messages. Perfect for orchestration-only agents.

### Team Management
`team_create` and `team_delete` tools for multi-agent coordination. Teams are named groups of background tasks that can be managed as a unit.

### Cron Scheduling
`cron_create`, `cron_delete`, `cron_list` tools for scheduling recurring tasks within a session.

---

## Feature-by-Feature Comparison

### Core Architecture

| Feature | Claude Code | s_code | Parity |
|---------|------------|--------|--------|
| Stateful query loop | ✅ | ✅ | 100% |
| Per-turn system prompt assembly | ✅ | ✅ | 100% |
| Streaming model responses | ✅ | ✅ | 100% |
| Streaming tool execution | ✅ | ✅ | 95% |
| Conversation persistence across turns | ✅ | ✅ | 100% |
| Error recovery (prompt-too-long) | ✅ | ✅ | 100% |
| Loop detection + recovery | ✅ | ✅ | 100% |
| Cancel cleanup | ✅ | ✅ | 100% |

### Tools (42/42)

| Tool | Claude Code | s_code | Notes |
|------|------------|--------|-------|
| File read (with offset/limit) | ✅ | ✅ | + image/PDF support |
| File write (read-before-write) | ✅ | ✅ | |
| File edit (string replacement) | ✅ | ✅ | + multi_edit |
| Bash (timeout, sandbox) | ✅ | ✅ | + 12-option sandbox |
| Glob (pattern matching) | ✅ | ✅ | + mtime sort |
| Grep (ripgrep, rich params) | ✅ | ✅ | 8 parameters |
| List files | ✅ | ✅ | |
| TodoWrite | ✅ | ✅ | Replace-all semantics |
| Agent (subagent spawn) | ✅ | ✅ | Async with event streaming |
| Task CRUD (6 tools) | ✅ | ✅ | Background threads |
| Web fetch | ✅ | ✅ | + trafilatura extraction |
| Web search | ✅ | ✅ | DuckDuckGo |
| Skill invoke | ✅ | ✅ | |
| Tool search (deferred) | ✅ | ✅ | |
| Notebook edit | ✅ | ✅ | |
| Git tools | Via bash | ✅ Native | status, diff, commit |
| Teams | ✅ | ✅ | create, delete |
| Send message | ✅ | ✅ | Inter-task |
| Plan mode tools | ✅ | ✅ | enter/exit |
| Worktree tools | ✅ | ✅ | enter/exit |
| Cron tools | ✅ | ✅ | create, delete, list |
| Config tool | ✅ | ✅ | Runtime get/set |
| Sleep tool | ✅ | ✅ | Duration or task wait |
| Ask user | ✅ | ✅ | Structured with suggestions |
| MCP resources | ✅ | ✅ | List from servers |
| Brief | ✅ | ✅ | Synthetic output |
| Python REPL | ❌ | ✅ | s_code exclusive |
| Clipboard | ❌ | ✅ | s_code exclusive |
| Open | ❌ | ✅ | s_code exclusive |

### Context & Memory

| Feature | Claude Code | s_code | Parity |
|---------|------------|--------|--------|
| 5+ compaction layers | ✅ (6) | ✅ (5+cache) | 95% |
| Post-compact file restoration | ✅ | ✅ | 100% |
| `<analysis>` scratchpad in compaction | ✅ | ✅ | 100% |
| CLAUDE.md/SALT.md discovery | ✅ | ✅ | 100% |
| 4 memory types with frontmatter | ✅ | ✅ | 100% |
| LLM-powered memory relevance | ✅ | ✅ | 100% |
| Memory extraction (stop hooks) | ✅ | ✅ | 100% |
| Dream consolidation | ✅ | ✅ | 100% |
| System-reminder injection | ✅ (~30 types) | ✅ (15 types) | 75% |
| Token budget tracking | ✅ | ✅ | 100% |
| Auto-continue on truncation | ✅ | ✅ | 100% |

### Permissions & Security

| Feature | Claude Code | s_code | Parity |
|---------|------------|--------|--------|
| Rule-based permission system | ✅ | ✅ | 100% |
| AI bash command classifier | ✅ | ✅ | 90% |
| Bash sandbox config | ✅ (14 fragments) | ✅ (12 options) | 85% |
| Auto mode (skip prompts) | ✅ | ✅ | 100% |
| File history / rewind | ✅ | ✅ | 100% |
| Content-addressed snapshots | ✅ | ✅ | 100% |

### CLI Experience

| Feature | Claude Code | s_code | Parity |
|---------|------------|--------|--------|
| Interactive REPL | ✅ | ✅ | 100% |
| One-shot mode | ✅ | ✅ | 100% |
| Slash commands | 86 | 72 | 84% |
| Tab completion | ✅ | ✅ | 90% |
| Persistent history | ✅ | ✅ | 100% |
| Markdown rendering | ✅ | ✅ | 90% |
| Syntax highlighting | ✅ | ✅ | 80% |
| Status bar | ✅ | ✅ | 80% |
| Spinner/thinking indicator | ✅ | ✅ | 100% |
| Git branch in prompt | ✅ | ✅ | 100% |
| Session resume | ✅ | ✅ | 100% |
| Token/cost tracking | ✅ | ✅ | 100% |
| Prompt suggestions | ✅ | ✅ | 80% |
| Model switching at runtime | ✅ | ✅ | 100% |
| Budget limit enforcement | ❌ | ✅ | s_code exclusive |

### Extensibility

| Feature | Claude Code | s_code | Parity |
|---------|------------|--------|--------|
| MCP server support | ✅ | ✅ | 85% |
| MCP resources + prompts | ✅ | ✅ | 80% |
| Skill system | ✅ | ✅ | 85% |
| Plugin system | ✅ | ✅ | 75% |
| Custom tools | Via MCP only | ✅ Native Python | Better |
| Custom providers | ❌ (Anthropic only) | ✅ | s_code exclusive |
| Hook engine | ✅ | ✅ | 95% |
| Embeddable as library | ❌ | ✅ | s_code exclusive |
| HTTP webhook hooks | ❌ | ✅ | s_code exclusive |
| Config file persistence | ✅ | ✅ | 100% |

### What Claude Code Has That s_code Doesn't

| Feature | Why it's missing | Impact |
|---------|-----------------|--------|
| IDE extensions (VS Code, JetBrains) | Requires editor integration | Low for CLI users |
| Chrome browser integration | Requires browser extension | Low |
| Ink-based terminal UI | Different rendering paradigm (React for terminals) | Cosmetic |
| Full vim keybindings | 10+ hours of work | Niche |
| LSP integration | 10+ hours, complex protocol | Medium |
| Voice input | Requires audio stack | Low |
| Login/OAuth accounts | Requires cloud backend | Not applicable |
| Remote/bridge sessions | Requires server infrastructure | Future |
| Auto-update | Requires distribution infrastructure | Future |

---

## The Magic Is in the Integration

What makes both Claude Code and s_code feel "magic" isn't any single feature. It's how they all work together:

1. **You type a prompt** → context assembly gathers memories, git status, file mentions, todo state, skills, MCP tools
2. **The model thinks** → with 15 types of dynamic context it knows exactly what's going on
3. **It uses tools** → read-before-edit enforced, streaming execution starts immediately, hooks fire
4. **Between turns** → stop hooks extract memories, generate suggestions, track tokens, update state
5. **If context fills** → 5-layer compaction fires progressively, restoring recently-read files
6. **If it gets stuck** → loop detection warns, then stops. Unknown tools get clear error messages
7. **If you cancel** → conversation stays valid with cancel results. Resume anytime
8. **If it crashes** → JSONL checkpoint was written BEFORE the API call. Resume from exactly where it stopped

Every interaction is wrapped in this invisible machinery. The user just sees: "it works."

---

## Summary

**s_code is ~92% feature parity with Claude Code for standalone CLI use.**

The remaining ~8% is IDE integration, Ink rendering, vim mode, and LSP — features that require platform-specific infrastructure and don't apply to a standalone agent.

For everything that matters — the agent loop, tools, memory, compaction, permissions, skills, MCP, hooks, streaming, persistence, and extensibility — s_code matches or exceeds Claude Code.

And it does things Claude Code can't: run on any LLM provider, embed in Python projects, extend with native tools, and deploy anywhere Python runs.
