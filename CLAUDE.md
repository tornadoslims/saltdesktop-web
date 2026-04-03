# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/cso`, `/autoplan`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, `/learn`.

## Work Style

**All coding tasks MUST be delegated to subagents.** When the user asks you to write, edit, or fix code:
1. Plan the work in the main conversation (read files, understand context, decide approach)
2. Delegate the actual code changes to a background Agent -- give it a clear prompt with: what files to change, what the changes should be, and verification steps (tests, imports)
3. Continue chatting with the user while the agent works
4. Report the outcome when the agent completes

This keeps the main conversation responsive. Small edits (CLAUDE.md, config) can be done directly.

## Living Documentation

Two docs must be kept up to date. Update them as part of your workflow -- not after every tiny change, but after each significant milestone (feature completed, bug fixed, architecture changed).

### Activity Log (`docs/ACTIVITY_LOG.md`)
- Append a timestamped entry after each significant action
- Format: `### HH:MM -- Brief title` followed by 1-3 bullet points
- Group by date
- Include: what was done, what was affected, key numbers (tests)
- This is a running log -- only append, never rewrite

### System Spec (`docs/SYSTEM_SPEC.md`)
- Complete specification of the entire system
- After significant architecture changes (new modules, removed modules, API changes, data model changes), delegate a background agent to regenerate it by reading the full codebase
- Trigger: adding/removing modules, changing the data model, major refactors
- NOT triggered by: bug fixes, config changes, test additions

## What SaltAgent Is

**SaltAgent is a standalone CLI agent for autonomous coding tasks.** It is a Python implementation inspired by Claude Code's architecture. It is NOT part of any desktop app, web UI, or orchestration platform. It IS the product -- a self-contained agent execution engine.

Think of it as: `claude` CLI reimplemented in Python, with the same tool-use loop, compaction, memory, hooks, permissions, subagents, and MCP support.

## SaltAgent Implementation Rules

**Always implement SaltAgent features the way Claude Code does it.** Reference `docs/CLAUDE_CODE_ALIGNMENT.md` for the gap analysis, and `docs/CLAUDE_CODE_SOURCE_ANALYSIS.md` / `docs/CLAUDE_CODE_INTERNALS.md` for deep-dive details.

Key patterns to always follow:
- **The agent IS the conversation.** Messages live on the agent instance. `run()` adds turns, doesn't create new conversations. The QueryEngine model, not request/response.
- **System prompt is reassembled every turn.** Memory, context, and attachments may change between turns.
- **Compaction replaces old messages** with a summary inside the same conversation. Not a new conversation.
- **Transcripts are JSONL, append-only, written BEFORE the API call.** Crash safety.
- **Tools are typed platform entities** with hooks, permissions, and structured results.
- **Edit uses string replacement, requires prior Read.** Non-negotiable.
- **TodoWrite uses replace-all semantics.** Agent writes the ENTIRE list each time.
- **Context pressure is multi-layered.** Not just truncation -- budget, summarize, compact, restore.
- **Subagents are cheap forks.** Fresh subagents get zero context. Forks share the prompt cache.
- **Loop detection warns first, stops second.** Inject a "you're stuck" message before hard-stopping.

## Project Structure

### Agent Core (`salt_agent/`)

| File | Purpose |
|------|---------|
| `agent.py` | Core agent loop: iterative LLM + tool execution, compaction, loop detection |
| `config.py` | AgentConfig dataclass: provider, model, context window, permissions, etc. |
| `context.py` | Context assembly and pressure management |
| `compaction.py` | LLM-based conversation compaction with file restoration |
| `hooks.py` | Hook engine: pre/post tool use, errors, completion, compaction |
| `memory.py` | Memory system: project instructions (SALT.md/CLAUDE.md), persistent memory |
| `permissions.py` | Rule-based tool call authorization with security classifier |
| `persistence.py` | JSONL session storage for crash recovery and resume |
| `subagent.py` | Subagent manager: fresh spawn and fork modes |
| `file_history.py` | Content-addressed file snapshots for rewind |
| `security.py` | Bash command security classifier |
| `plugins.py` | Plugin discovery and loading |
| `events.py` | Event types for streaming output |
| `cli.py` | Terminal interface with slash commands |

### Tools (`salt_agent/tools/`)

| File | Purpose |
|------|---------|
| `base.py` | Tool, ToolDefinition, ToolParam, ToolRegistry base classes |
| `bash.py` | Shell command execution with timeout and sandbox support |
| `read.py` | File reading with offset/limit, image support, PDF support |
| `write.py` | File writing (requires prior read) |
| `edit.py` | String replacement editing (requires prior read) |
| `multi_edit.py` | Batch file editing |
| `glob_tool.py` | Fast file pattern matching |
| `grep.py` | Content search via ripgrep |
| `list_files.py` | Directory listing |
| `agent_tool.py` | Spawn subagents (fresh or fork) |
| `todo.py` | Todo list with replace-all semantics |
| `git.py` | Git status, diff, commit |
| `web_fetch.py` | Web page fetching and extraction |
| `web_search.py` | Web search |

### Prompts (`salt_agent/prompts/`)

254 prompt constants organized into:
- `fragments/` -- Behavioral instructions (doing tasks, security, tool usage)
- `agents/` -- Subagent role prompts (verification, exploration, worker)
- `skills/` -- Skill prompts (debugging, API reference, simplify)
- `tools/` -- Tool description prompts
- `data/` -- Reference data (API docs, SDK patterns)
- `assembler.py` -- Compose fragments into complete system prompts
- `registry.py` -- Search and list prompts

### MCP (`salt_agent/mcp/`)

| File | Purpose |
|------|---------|
| `config.py` | Parse .mcp.json server configuration |
| `manager.py` | MCP server lifecycle (start, tool discovery, shutdown) |
| `tool_bridge.py` | Bridge MCP tools into SaltAgent's ToolRegistry |

### Providers (`salt_agent/providers/`)

| File | Purpose |
|------|---------|
| `base.py` | ProviderAdapter abstract base |
| `anthropic.py` | Anthropic Claude adapter (streaming) |
| `openai_provider.py` | OpenAI adapter (streaming) |

### Other

- `tests/` -- Test suite
- `docs/` -- Documentation and analysis

## How to Run Things

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest salt_agent/tests/ -q

# CLI (interactive)
python -m salt_agent -i

# CLI (one-shot)
python -m salt_agent "Create a hello world script"

# CLI (with options)
python -m salt_agent -p anthropic -m claude-sonnet-4-20250514 --auto "Fix the failing tests"
```

## Key Design Decisions

- **Standalone CLI agent.** SaltAgent is a self-contained product, not a component of any larger system. No dependencies on external orchestration, desktop apps, or web UIs.
- **Claude Code architecture.** The design mirrors Claude Code's actual source: query loop, tool execution, compaction, memory, hooks, permissions, subagents, MCP.
- **Provider-agnostic.** Supports Anthropic and OpenAI via adapter pattern. Provider swap is a config change.
- **File-based persistence.** Sessions are JSONL files. Memory is markdown files. Config is JSON. No database.
- **Plugin system.** Extend with additional tools, hooks, and prompts via SaltPlugin subclasses.
- **MCP support.** Auto-discovers and connects to MCP servers from .mcp.json.

## Key Conventions

- Default data directory: `~/.salt-agent/`
- Sessions: `~/.salt-agent/sessions/`
- Memory: `~/.salt-agent/memory/`
- Snapshots: `~/.salt-agent/snapshots/`
- Project instructions: SALT.md or CLAUDE.md in working directory (searched up to 10 levels)
- All timestamps are UTC ISO format
- Session IDs and tool IDs are UUIDs
