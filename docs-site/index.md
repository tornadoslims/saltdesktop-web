# SaltAgent

**A standalone AI agent execution engine in Python.** SaltAgent is a fully-featured Claude Code replica that you can run from the CLI, embed in your own Python projects, or extend with custom tools and providers.

## Key Stats

| Metric | Count |
|--------|-------|
| Built-in tools | 42 |
| CLI slash commands | 72 |
| Prompt fragments | 254 |
| Test files | 57 |
| LLM providers | 2 (Anthropic, OpenAI) |

## Quick Example

```python
from salt_agent import create_agent

agent = create_agent(
    provider="openai",
    model="gpt-4o",
    working_directory="/path/to/project",
    system_prompt="You are a code assistant.",
)

import asyncio

async def main():
    async for event in agent.run("Fix the failing tests"):
        if event.type == "text_chunk":
            print(event.text, end="")
        elif event.type == "tool_start":
            print(f"\n[Using {event.tool_name}]")
        elif event.type == "complete":
            print(f"\nDone in {event.turns} turns")

asyncio.run(main())
```

## Feature Highlights

- **42 built-in tools** -- file I/O, bash, grep, glob, git, web fetch/search, tasks, subagents, MCP, notebooks, clipboard, REPL, and more
- **Multi-provider** -- Anthropic and OpenAI with streaming, retry, fallback, and prompt caching
- **5-layer compaction** -- microcompact, history snip, context collapse, LLM summarization, emergency truncation
- **Memory system** -- project instructions (SALT.md/CLAUDE.md), typed cross-session memory with LLM-powered recall
- **Hook engine** -- 30+ lifecycle events with shell, HTTP, and Python callbacks that can block, modify, or observe tool calls
- **Permission system** -- rule-based + AI-powered bash command classification
- **Session persistence** -- JSONL crash recovery and session resume
- **Subagents** -- fresh or forked child agents that share prompt cache prefixes
- **Background tasks** -- independent agent runs in daemon threads
- **Skills** -- markdown-based prompt injection with frontmatter metadata, requirements checking, and priority resolution
- **MCP integration** -- auto-discover and connect to Model Context Protocol servers via `.mcp.json`
- **Plugin system** -- extend with custom tools, hooks, and prompt fragments via `SaltPlugin` subclasses or pip entry points
- **Streaming tool execution** -- safe read-only tools start executing during the model stream, before it finishes generating
- **Coordinator mode** -- delegation-only agent that strips write/execute tools
- **Plan mode** -- agent must create a plan before taking any action
- **Token budget tracking** -- per-turn cost tracking with diminishing-returns detection
- **File history** -- content-addressed snapshots for full session rewind via `/undo`
- **254 prompt fragments** -- behavioral instructions, tool descriptions, agent roles, skills, and reference data

## Architecture at a Glance

```
User Input
    |
    v
+-------------------+
|    SaltAgent       |  <-- Core agent loop
|  +--------------+  |
|  |  Providers   |  |  <-- Anthropic / OpenAI adapters
|  +--------------+  |
|  |  Tools (42)  |  |  <-- Read, Write, Edit, Bash, Grep, Glob, Git, Web, Tasks, ...
|  +--------------+  |
|  |  Hooks       |  |  <-- pre/post tool, API, session, turn, memory, task events
|  +--------------+  |
|  |  Compaction   | |  <-- 5-layer context management
|  +--------------+  |
|  |  Memory      |  |  <-- Project instructions + cross-session recall
|  +--------------+  |
|  |  Persistence |  |  <-- JSONL checkpoints for crash recovery
|  +--------------+  |
+-------------------+
    |
    v
Streaming Events (TextChunk, ToolStart, ToolEnd, AgentComplete, ...)
```

## Getting Started

See the [Getting Started guide](getting-started.md) to install and run SaltAgent in 5 minutes.

## Embedding in Your Project

See the [Embedding guide](embedding.md) to learn how to use SaltAgent as a library in your Python applications -- web servers, CLI tools, background workers, desktop apps, and more.
