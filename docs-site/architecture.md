# Architecture

## High-Level Overview

SaltAgent is a loop-based AI agent that alternates between calling an LLM and executing tools until the task is complete or a turn limit is reached.

```
                        +------------------+
                        |    User Input    |
                        +--------+---------+
                                 |
                                 v
+----------------------------------------------------------------+
|                         SaltAgent                              |
|                                                                |
|  +------------------+    +------------------+                  |
|  |  ContextManager  |    |   MemorySystem   |                  |
|  |  - system prompt |    |  - SALT.md       |                  |
|  |  - file tracking |    |  - memory files  |                  |
|  |  - truncation    |    |  - LLM recall    |                  |
|  +--------+---------+    +--------+---------+                  |
|           |                       |                            |
|           v                       v                            |
|  +------------------------------------------------+           |
|  |              Prompt Assembly                    |           |
|  |  project instructions + user prompt + dynamic   |           |
|  |  context (date, cwd, todo) + system-reminders   |           |
|  +------------------------+-----------------------+           |
|                           |                                    |
|                           v                                    |
|  +------------------------+-----------------------+           |
|  |            Provider Adapter                     |           |
|  |  Anthropic (claude-sonnet-4) / OpenAI (gpt-4o) |           |
|  |  - streaming responses                          |           |
|  |  - prompt caching (Anthropic)                   |           |
|  |  - retry with exponential backoff               |           |
|  |  - model fallback                               |           |
|  +------------------------+-----------------------+           |
|                           |                                    |
|                           v                                    |
|  +------------------------+-----------------------+           |
|  |         StreamingToolExecutor                   |           |
|  |  - safe tools start mid-stream                  |           |
|  |  - unsafe tools queued for after stream          |           |
|  +------------------------+-----------------------+           |
|                           |                                    |
|                           v                                    |
|  +------------------------+-----------------------+           |
|  |           Tool Registry (42 tools)              |           |
|  |  Read, Write, Edit, Bash, Grep, Glob, Git,     |           |
|  |  WebFetch, WebSearch, Agent, Tasks, Skill,      |           |
|  |  REPL, Clipboard, Notebook, MCP tools, ...      |           |
|  +------------------------+-----------------------+           |
|                           |                                    |
|                           v                                    |
|  +------------------------------------------------+           |
|  |                  Hook Engine                    |           |
|  |  pre/post_tool_use, pre/post_api_call,          |           |
|  |  on_error, on_complete, session/turn lifecycle,  |           |
|  |  memory, task, file events (30+ event types)     |           |
|  +------------------------+-----------------------+           |
|                           |                                    |
|  +------------------------+-----------------------+           |
|  |              Compaction Pipeline                 |           |
|  |  L1: Microcompact (truncate old tool results)   |           |
|  |  L2: History snip (trim old assistant text @60%) |           |
|  |  L3: Context collapse (merge tool pairs @70%)   |           |
|  |  L4: LLM summarization (@80%)                   |           |
|  |  L5: Emergency truncation (@95%)                |           |
|  +------------------------------------------------+           |
|                                                                |
+-------------------------------+--------------------------------+
                                |
                                v
                    +---------------------+
                    |   Streaming Events   |
                    |  TextChunk           |
                    |  ToolStart / ToolEnd |
                    |  AgentComplete       |
                    |  AgentError          |
                    |  ContextCompacted    |
                    |  SubagentSpawned     |
                    |  ...                 |
                    +---------------------+
```

## The Agent Loop

The core loop in `SaltAgent.run()` proceeds as follows:

1. **User message** is appended to the persistent conversation history
2. **For each turn** (up to `max_turns`):
    1. **Loop detection** -- check for repeating tool call patterns (length 1-4 patterns repeated 3+ times). Inject a warning message if stuck; hard stop after two warnings.
    2. **Compaction pipeline** -- 5 layers of context management fire at increasing pressure thresholds
    3. **System prompt rebuild** -- project instructions + user prompt + dynamic context (date, cwd, todo state, plan mode)
    4. **System-reminder injection** -- per-turn dynamic context assembled by `AttachmentAssembler` (date, todo, plan mode, skills, git status, task notifications, file mentions, deferred tool lists)
    5. **Memory surfacing** -- LLM side-query ranks memory files by relevance to the current message; relevant memories injected as system-reminders
    6. **Checkpoint** -- save conversation state to JSONL before the API call (crash recovery)
    7. **Budget check** -- stop if `max_budget_usd` exceeded
    8. **LLM call** -- stream response from the provider
    9. **Streaming tool execution** -- safe tools (read, glob, grep, list_files, web_fetch, web_search) start executing as their `tool_use` blocks are detected mid-stream
    10. **Tool execution** -- remaining tools execute after stream completes; hooks fire before/after each tool
    11. **Result assembly** -- tool results appended to conversation history
    12. **Stop hooks** -- post-turn processing (memory extraction every 5 turns, session title generation, stats logging, memory consolidation, suggestion generation)
    13. **If no tool calls** -- agent is done, yield `AgentComplete` and return
    14. **If tool calls** -- loop to next turn

## Component Interactions

### Provider Adapters

The `ProviderAdapter` ABC defines the interface:

- `stream_response(system, messages, tools, max_tokens, temperature)` -- stream LLM response as events
- `quick_query(prompt, system, max_tokens)` -- non-streaming side query for memory ranking, extraction, titles

Implementations handle provider-specific concerns:

- **AnthropicAdapter** -- uses `anthropic.Anthropic`, adds `cache_control` to system prompt for prompt caching, exponential backoff retry for rate limits
- **OpenAIAdapter** -- uses `openai.OpenAI`, converts Anthropic message format to OpenAI format, lazy client initialization

### Compaction Pipeline

Context pressure is managed by 5 layers that fire at increasing thresholds:

| Layer | Trigger | Action |
|-------|---------|--------|
| L1: Microcompact | Every turn | Truncate old tool results to 3000 chars (first 2000 + last 1000), skip recent 6 messages |
| L2: History snip | 60% capacity | Snip old assistant text to 200 chars in the first half of messages |
| L3: Context collapse | 70% capacity | Collapse tool call/result pairs into `[Tool calls: read, grep]` summaries |
| L4: Autocompact | 80% capacity | LLM-powered summarization of old conversation into a condensed summary |
| L5: Emergency truncate | 95% capacity | Drop old messages until under 70% capacity, keeping system and recent messages |

### Hook System

The `HookEngine` supports 30+ event types organized into categories:

- **Tool lifecycle**: `pre_tool_use` (can block), `post_tool_use`
- **API lifecycle**: `pre_api_call` (can modify), `post_api_call`
- **Session**: `session_start`, `session_end`, `session_resume`
- **Turn**: `turn_start`, `turn_end`, `turn_cancel`
- **Memory**: `memory_saved`, `memory_deleted`, `memory_surfaced`
- **Subagent**: `subagent_start`, `subagent_end`
- **Task**: `task_created`, `task_completed`, `task_failed`
- **File**: `file_written`, `file_edited`, `file_deleted`, `file_snapshot`
- **Context**: `on_compaction`, `context_compacted`, `context_emergency`

Hooks can be Python callables, shell commands (ShellHook), or HTTP webhooks (HttpHook).

### Permission System

Tool calls pass through a two-stage check:

1. **SecurityClassifier** -- fast rules-based classification of bash commands into safe/needs-review/dangerous
2. **PermissionRule matching** -- glob-based pattern matching against tool names and inputs
3. **Optional AI classifier** -- async LLM side-query for nuanced bash command classification (can escalate but never downgrade)

### Memory System

- **Project instructions** -- `SALT.md` / `CLAUDE.md` loaded from working directory and parents (up to 10 levels)
- **Memory files** -- typed files (user, feedback, project, reference) with YAML frontmatter stored in `~/.s_code/memory/`
- **Memory index** -- `MEMORY.md` provides the catalog
- **Per-turn recall** -- LLM ranks memory files against the current message; relevant ones injected as system-reminders
- **Automatic extraction** -- every 5 turns, an LLM side-query scans recent conversation for things worth saving

## Data Flow Summary

```
User prompt
    |
    +-- append to _conversation_messages
    |
    +-- for each turn:
    |       |
    |       +-- compaction pipeline (L1-L5)
    |       +-- build system prompt (instructions + dynamic context)
    |       +-- inject system-reminders (attachments + memories)
    |       +-- checkpoint (JSONL)
    |       +-- LLM stream → events
    |       +-- streaming tool execution (safe tools start during stream)
    |       +-- remaining tool execution (after stream)
    |       +-- hooks fire (pre/post tool, turn events)
    |       +-- results → _conversation_messages
    |       +-- stop hooks (memory extraction, session title, stats)
    |       |
    |       +-- no tools? → AgentComplete
    |       +-- tools used? → next turn
    |
    v
Streaming AgentEvent iterator
```

## Comparison to Claude Code

SaltAgent is modeled on Claude Code's architecture with the following correspondences:

| Claude Code | SaltAgent |
|-------------|-----------|
| `query/queryLoop.ts` | `agent.py` -- `SaltAgent.run()` |
| `utils/attachments.ts` | `attachments.py` -- `AttachmentAssembler` |
| `query/stopHooks.ts` | `stop_hooks.py` -- `StopHookRunner` |
| `query/compaction.ts` | `compaction.py` -- 5-layer pipeline |
| `query/tokenBudget.ts` | `token_budget.py` -- `BudgetTracker` |
| `permissions/` | `permissions.py` + `security.py` |
| `tools/` | `tools/` -- 42 tool implementations |
| `prompts/` | `prompts/` -- 254 fragments across 5 categories |
| `memory/` | `memory.py` -- `MemorySystem` |
| `hooks/` | `hooks.py` -- `HookEngine` |
| `.claude/instructions.md` | `SALT.md` / `CLAUDE.md` |
| Session persistence | `persistence.py` -- JSONL checkpoints |
| MCP integration | `mcp/` -- server lifecycle, tool bridge |
| Subagents | `subagent.py` -- fresh and fork modes |
