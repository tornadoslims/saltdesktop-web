# learn-claude-code Repository Analysis

**Repository**: https://github.com/shareAI-lab/learn-claude-code
**Author**: shareAI Lab
**License**: MIT (full commercial use permitted)
**Date of analysis**: 2026-03-30

---

## 1. What Is This Repo?

It is a **teaching repository with working reference implementations**. Not a library. Not a framework. Not something you `pip install`. It is 14 self-contained Python scripts (s01 through s12, plus s_full capstone) that progressively build up every mechanism found in Claude Code's architecture -- from a bare agent loop to multi-agent teams with worktree isolation.

Each script is standalone and runnable. There is no shared library, no importable package, no API surface designed for reuse. The `agents/__init__.py` contains only a comment. The `requirements.txt` has exactly three dependencies: `anthropic`, `python-dotenv`, `pyyaml`.

The web/ directory is a Next.js learning platform (interactive visualizations, step-through diagrams, source viewer) -- purely educational, not functional agent infrastructure.

## 2. Does It Implement an Agent Execution Loop?

**Yes, completely.** The core loop is implemented clearly in `agents/s01_agent_loop.py` and is identical in structure across all 14 files:

```python
def agent_loop(messages: list):
    while True:
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return
        results = []
        for block in response.content:
            if block.type == "tool_use":
                output = TOOL_HANDLERS[block.name](**block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": output})
        messages.append({"role": "user", "content": results})
```

This is the full agentic loop: call LLM, check if it wants tools, execute tools, feed results back, repeat until the model stops.

## 3. Does It Implement Tool Execution?

**Yes.** Every session progressively adds tools. The full tool inventory across all sessions:

### Base Tools (present in every session from s02 onward)
| Tool | Implementation |
|------|---------------|
| `bash` | `subprocess.run()` with 120s timeout, dangerous command blocking |
| `read_file` | Path-safe file read with line limit |
| `write_file` | Path-safe file write with mkdir -p |
| `edit_file` | Exact string replacement (single occurrence) |

### Extended Tools (added progressively)
| Tool | Session | Purpose |
|------|---------|---------|
| `todo` / `TodoWrite` | s03 | In-memory task tracking with nag reminders |
| `task` (subagent) | s04 | Spawn child agent with fresh context, return summary only |
| `load_skill` | s05 | On-demand knowledge loading from SKILL.md files |
| `compact` / `compress` | s06 | Manual and automatic context compression |
| `task_create/get/update/list` | s07 | File-backed persistent task system with dependency graph |
| `background_run` / `check_background` | s08 | Threaded background command execution |
| `spawn_teammate` | s09 | Persistent named agents running in threads |
| `send_message` / `read_inbox` / `broadcast` | s09 | JSONL-based inter-agent messaging |
| `shutdown_request` | s10 | Graceful teammate shutdown protocol |
| `plan_approval` | s10 | Plan review/approval FSM |
| `idle` / `claim_task` | s11 | Autonomous task claiming from a board |
| `worktree_create/enter/close` | s12 | Git worktree isolation for parallel execution |
| `worktree_events` | s12 | Append-only lifecycle event log |

### Safety Mechanisms
- Path sandboxing: all file operations resolve against WORKDIR and reject path traversal
- Dangerous command blocking: blocks `rm -rf /`, `sudo`, `shutdown`, `reboot`, `> /dev/`
- Subprocess timeout: 120s default, 300s for background tasks
- Output truncation: 50KB cap on tool output

## 4. What SDKs Does It Use?

**Anthropic SDK only** (`anthropic>=0.25.0`). All LLM calls use `client.messages.create()` with the Anthropic Messages API. However, the `.env.example` shows it supports any Anthropic-API-compatible provider through `ANTHROPIC_BASE_URL`:

- Anthropic (Claude) -- default
- MiniMax M2.5
- GLM-5 (Zhipu)
- Kimi K2.5 (Moonshot)
- DeepSeek V3.2

There is **no OpenAI SDK usage anywhere**. The entire codebase is Anthropic-native.

## 5. Can It Run Autonomously?

**Yes.** The capstone `s_full.py` and `s11_autonomous_agents.py` demonstrate fully autonomous operation:

- The lead agent receives a prompt and breaks it into tasks
- Teammate agents spawn in threads, each with their own agent loop
- Teammates auto-claim pending tasks when idle (polling every 5 seconds)
- Background commands run in daemon threads with notification delivery
- Context compression keeps sessions running indefinitely
- JSONL mailboxes enable async inter-agent communication

The s_full capstone has **24 tools** and combines all 11 harness mechanisms into a single runnable script. Given a prompt like "build a REST API with tests," it would plan the work, spawn teammate agents, have them write code and run tests, and coordinate through message passing.

**Limitation**: There is no built-in retry-on-test-failure loop. If a test fails, the agent sees the output and may choose to fix it, but there is no harness-level guarantee of a fix-and-retry cycle. That logic lives in the model's reasoning, not the code.

## 6. License

**MIT License**, copyright 2024 shareAI Lab. Full permissions:
- Commercial use
- Modification
- Distribution
- Sublicensing
- Private use

Only requirement: include the copyright notice. **Can absolutely be bundled in a commercial app.**

## 7. How Does It Compare to Claude Code CLI?

It is a **pedagogical reimplementation of Claude Code's architecture**. The README explicitly states this: "this repository reverse-engineers one harness mechanism from Claude Code's architecture."

| Aspect | Claude Code CLI | learn-claude-code |
|--------|----------------|-------------------|
| Purpose | Production tool | Teaching / reference |
| Language | TypeScript/Node | Python |
| Installation | `npm i -g @anthropic-ai/claude-code` | Clone + pip install |
| Tool count | 20+ production tools | 24 tools (s_full) |
| Sandboxing | Full OS-level sandbox | Basic path checks + command blocklist |
| Permission system | Interactive approval, trust levels | None |
| MCP support | Full | None |
| Streaming | Yes | No (blocking calls) |
| Context window management | Production-grade | Teaching implementation |
| Hook system | Pre/post tool, session lifecycle | Minimal event bus in s12 |
| Error recovery | Production retry logic | Model-dependent |
| Session persistence | Resume, fork, worktree | Fresh per run (tasks persist to disk) |

**Key difference**: Claude Code is a polished product with security, UX, streaming, and error handling. learn-claude-code strips all that away to expose the architectural patterns in the simplest possible code.

## 8. Could Salt Desktop Use This Instead of Claude Code CLI?

### The Direct Answer: Yes, with significant work.

The code demonstrates that building a standalone agent execution engine in Python is entirely feasible. The core loop is ~20 lines. The full harness (s_full.py) is ~700 lines. Here is what makes it viable and what is missing:

### What Is Already There (can be extracted)
1. **The agent loop** -- works, tested, clean
2. **Tool dispatch** -- extensible handler map pattern
3. **File operations** -- bash, read, write, edit with path safety
4. **Subagent spawning** -- fresh context per child, summary-only return
5. **Context compression** -- 3-layer strategy (micro, auto, manual)
6. **Task persistence** -- JSON file-backed task graph with dependencies
7. **Background execution** -- threaded commands with notification queue
8. **Multi-agent coordination** -- JSONL mailboxes, team management

### What Is Missing (must be built for Salt Desktop)
1. **No library API surface** -- every file is a standalone script with `if __name__ == "__main__"`. Must be refactored into importable classes/functions.
2. **No streaming** -- all LLM calls are blocking. For a desktop app, you need streaming to show progress.
3. **No callback/event system** -- no way to hook into tool execution, progress updates, or errors from outside the loop.
4. **No proper error handling** -- exceptions are caught and returned as strings. No structured error types.
5. **No cancellation** -- once the loop starts, there is no way to abort it from outside.
6. **No token counting** -- uses `len(str(messages)) // 4` as a rough estimate. Production needs actual token counting.
7. **No permission governance** -- no approval workflow for dangerous operations.
8. **No model flexibility** -- hardcoded to Anthropic SDK. If Salt Desktop wants to support OpenAI or Gemini models, the SDK layer needs abstraction.
9. **No test coverage of agent behavior** -- the tests only check that files compile and that BackgroundManager works. Zero tests of the actual agent loop.

### Recommended Approach for Salt Desktop

**Do not use this repository as a dependency.** Instead, use it as a **blueprint** to build Salt Desktop's own agent engine. Specifically:

1. **Extract the patterns, not the code.** The agent loop, tool dispatch map, subagent isolation, and context compression patterns are the valuable parts. Reimplement them in a clean library with proper typing, error handling, and an event system.

2. **Build a `SaltAgent` class** with this interface:
   ```python
   class SaltAgent:
       def __init__(self, model: str, tools: list[Tool], system: str, workdir: Path)
       async def run(self, prompt: str, on_tool_call: Callback, on_progress: Callback) -> AgentResult
       def cancel(self)
       def spawn_subagent(self, prompt: str, tools: list[Tool]) -> AgentResult
   ```

3. **Use the Anthropic SDK directly** (as this repo does). The SDK is the only dependency needed. The loop is trivial. There is no value in an intermediary framework.

4. **Port the tool implementations** from s02 (bash, read, write, edit). These are solid and simple. Add: glob, grep, git operations.

5. **Port the context compression** from s06. The 3-layer strategy is sound: micro-compact old tool results, auto-compact when tokens exceed threshold, manual compact on demand.

6. **Port the task system** from s07 if Salt Desktop needs persistent task tracking across agent invocations.

### Estimated Effort

Building a production-quality `SaltAgent` engine based on these patterns: **2-3 days of focused work**. The patterns are proven. The Anthropic SDK does the heavy lifting. The main work is:
- Wrapping the loop with async/streaming support
- Adding an event/callback system for the desktop UI
- Proper error types and cancellation
- Tests

## 9. Complete Tool/Capability Inventory

### s_full.py Capstone (24 tools)

| # | Tool | Category |
|---|------|----------|
| 1 | `bash` | Execution |
| 2 | `read_file` | Filesystem |
| 3 | `write_file` | Filesystem |
| 4 | `edit_file` | Filesystem |
| 5 | `TodoWrite` | Planning |
| 6 | `task` (subagent) | Delegation |
| 7 | `load_skill` | Knowledge |
| 8 | `compress` | Context management |
| 9 | `background_run` | Async execution |
| 10 | `check_background` | Async execution |
| 11 | `task_create` | Task persistence |
| 12 | `task_get` | Task persistence |
| 13 | `task_update` | Task persistence |
| 14 | `task_list` | Task persistence |
| 15 | `spawn_teammate` | Multi-agent |
| 16 | `list_teammates` | Multi-agent |
| 17 | `send_message` | Communication |
| 18 | `read_inbox` | Communication |
| 19 | `broadcast` | Communication |
| 20 | `shutdown_request` | Lifecycle |
| 21 | `plan_approval` | Governance |
| 22 | `idle` | Lifecycle |
| 23 | `claim_task` | Autonomous |
| 24 | (s12 adds) `worktree_create/enter/close/events` | Isolation |

### s12 Additional Tools (4 more)
| # | Tool | Category |
|---|------|----------|
| 25 | `worktree_create` | Git isolation |
| 26 | `worktree_enter` | Git isolation |
| 27 | `worktree_close` | Git isolation |
| 28 | `worktree_events` | Observability |

## 10. Web UI Component

The `web/` directory is a **Next.js 16 learning platform**, not an agent UI. It contains:

- Interactive step-through diagrams of each session's mechanism
- Source code viewer with syntax highlighting
- Diff viewer to see what changed between sessions
- i18n support (English, Chinese, Japanese)
- Timeline and comparison views
- Deployed via Vercel

**Not relevant to Salt Desktop's needs.** This is purely educational visualization.

## 11. Related Projects (Mentioned in README)

### Kode Agent CLI (`@shareai-lab/kode`)
An open-source coding agent CLI with skill/LSP support, Windows-ready, pluggable with multiple model providers. This is the "productionized" version of what learn-claude-code teaches.

### Kode Agent SDK (`shareAI-lab/Kode-agent-sdk`)
Described as "a standalone library with no per-user process overhead, embeddable in backends, browser extensions, embedded devices." **This might be more directly relevant to Salt Desktop than learn-claude-code itself**, but was not analyzed here (separate repository).

### claw0 (`shareAI-lab/claw0`)
Companion repo adding heartbeat, cron, IM routing, memory, and soul personality to the agent core. Relevant if Salt Desktop ever wants always-on agent behavior.

---

## Bottom Line

**learn-claude-code proves that building your own agent execution engine is straightforward.** The core loop is trivial. The Anthropic SDK handles the hard part (the LLM). Everything else -- tool dispatch, subagents, context compression, task persistence, multi-agent coordination -- is well-demonstrated in clean, readable Python.

**For Salt Desktop**: Do not depend on this repo. Do not depend on Claude Code CLI, Codex, or Gemini CLI. Instead, build a `SaltAgent` engine using the patterns demonstrated here. The Anthropic SDK + a 20-line loop + tool handlers + context compression is all that is needed. Own the engine. It is simple enough to own.

The only external dependency should be the model provider SDK (`anthropic` for Claude, `openai` for GPT if needed). Everything else is application code that Salt Desktop should control directly.
