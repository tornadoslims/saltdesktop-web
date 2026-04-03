# SaltAgent Parity Progress Tracker

**Target: 90%+ parity with Claude Code**
**Current: 64% (as of final audit)**
**Last updated: 2026-04-02**

---

## Score by Area

| Area | Current | Target | Status | Agent |
|------|---------|--------|--------|-------|
| Query loop | 75% | 90% | 🔨 Streaming tools deferred | — |
| Error recovery | 75% | 85% | ✅ Cancel cleanup done | — |
| Subagents | 75% | 85% | ✅ Async refactor done | — |
| Context assembly | 70% | 85% | 🔨 More attachment types | Building |
| Memory | 70% | 85% | ✅ Ranking + consolidation done | — |
| Persistence | 70% | 80% | ✅ Concurrent detection done | — |
| Provider | 70% | 80% | ✅ Budget tracking done | — |
| Tools | 65% | 85% | 🔨 Rich Grep, glob sort | Building |
| Permissions | 65% | 75% | ✅ Security classifier done | — |
| Tasks | 65% | 75% | ✅ 6 CRUD tools done | — |
| Compaction | 60% | 80% | 🔨 History snip, context collapse | Building |
| Hooks | 55% | 75% | 🔨 More event types needed | Queued |
| Skills | 55% | 75% | 🔨 More bundled skills, conditional activation | Building |
| MCP | 50% | 70% | 🔨 Resources + prompts | Building |
| Plugin | 50% | 65% | 🔲 entry_points discovery | Queued |
| State | 40% | 60% | 🔲 Reactive state store | Queued |
| Commands | 29% | 60% | 🔨 37→50+ commands | Queued |
| **CLI UX** | **30%** | **80%** | 🔨 Major overhaul | Building |

---

## Currently Building (active agents)

1. **CLI UX overhaul + Rich Grep + Glob sort** — banner fix, tool display cleanup, response indicator, suggestions off by default
2. **Compaction layers + more skills + MCP resources** — history snip, context collapse, 5 new skills, MCP resource/prompt discovery

## Queued (launch after current agents finish)

### Batch 1: CLI Polish
- [ ] Slash command typeahead/autocomplete (Tab completion)
- [ ] Richer tool output (file sizes, line counts, previews)
- [ ] Better text streaming (word wrap at terminal width)
- [ ] Progress indicator between turns (not just spinner)
- [ ] Session title in prompt after first turn
- [ ] Multiline input without backslash (detect incomplete statements)
- [ ] Input history across sessions (persistent readline history)
- [ ] Color themes (not just on/off)

### Batch 2: Hooks + State + Plugin
- [ ] Expand to 20+ hook event types (match Claude Code's lifecycle)
- [ ] Centralized reactive state store (AppStateStore pattern)
- [ ] Plugin entry_points discovery (pip-installed plugins)
- [ ] Skill conditional activation (os, bins, env requirements)

### Batch 3: Commands
- [ ] Remaining slash commands to reach 50+
- [ ] Command typeahead/autocomplete
- [ ] Command history

### Batch 4: Advanced
- [ ] Streaming tool execution
- [ ] AI permission classifier (race user prompt)
- [ ] Relevance caching for memory surfacing
- [ ] Inter-task messaging depth

---

## Completed Features

### v1.3 (current)
- ✅ Core agent loop with conversation persistence
- ✅ 31 tools (read, write, edit, multi_edit, bash, glob, grep, list_files, todo_write, agent, web_fetch, web_search, git_status, git_diff, git_commit, task_create/get/list/output/stop/update, ask_user, enter/exit_plan_mode, sleep, config, send_message, enter/exit_worktree, skill, tool_search)
- ✅ Anthropic + OpenAI providers (caching, retry, fallback, usage tracking)
- ✅ Hook engine (9 events, shell + HTTP hooks)
- ✅ Context compaction (microcompact + autocompact + emergency)
- ✅ Session persistence + resume + search
- ✅ Memory system (types, ranking, extraction, consolidation)
- ✅ Permission system (rules + security classifier)
- ✅ Subagent spawning (async, fork + fresh, cache sharing)
- ✅ File history / rewind
- ✅ Web tools (trafilatura/readability, parallel execution)
- ✅ MCP integration (.mcp.json, tool bridge)
- ✅ Task system (background agents, 6 tools)
- ✅ Skills system (discovery, bundled, invocation)
- ✅ ToolSearch (deferred loading)
- ✅ Token budget tracking
- ✅ Stop hooks (memory extraction, titles, consolidation, suggestions)
- ✅ System-reminder injection (7 attachment types)
- ✅ Coordinator mode
- ✅ Auto/plan mode
- ✅ Cancel cleanup (dummy tool results)
- ✅ 37 slash commands
- ✅ Polished CLI (syntax highlight, markdown, spinner, token tracking)
- ✅ 975 tests
