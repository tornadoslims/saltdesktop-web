# SaltAgent vs Claude Code — Feature Gap Analysis

**Date:** 2026-04-02
**SaltAgent version:** v0.6 (575 tests, ~75-80% match)
**Based on:** Claude Code source analysis, PDF report, leaked prompts, audit

---

## What SaltAgent HAS (parity achieved)

- Core agent loop (async, streaming, multi-turn, conversation persistence)
- 12 tools: read, write, edit, multi_edit, bash, glob, grep, list_files, todo_write, agent, web_fetch, web_search
- 2 provider adapters (Anthropic with prompt caching, OpenAI) with retry/backoff
- Hook engine (9 events, pre/post tool use, blocking)
- Context compaction (80% threshold, LLM summarization, analysis scratchpad, post-compact file restoration)
- Session persistence (JSONL, save before API call, resume)
- Memory system (SALT.md/CLAUDE.md discovery, memory index)
- Permission system (rule-based, deny/ask/allow)
- Subagent spawning (fresh + fork with boilerplate)
- File history / rewind (SHA-256 snapshots)
- Web tools with trafilatura/readability extraction
- Parallel tool execution (independent tools run concurrently)
- Loop detection (warn first, stop second)
- Read-before-edit enforcement
- Per-turn system prompt reassembly
- Prompt-too-long error recovery (auto-compact + retry)
- 254 system prompts integrated with assembler
- Provider-specific prompt adapters
- Polished CLI (spinner, markdown rendering, syntax highlighting, slash commands, token tracking)
- Conversation memory across interactive turns
- TodoWrite for agent self-tracking

---

## What Claude Code HAS that SaltAgent DOES NOT

### High Impact — Users Would Notice

| # | Feature | What it does | Effort | Priority |
|---|---------|-------------|--------|----------|
| 1 | **Auto-mode** | Fully autonomous execution — skips permission prompts for all tool calls. User trusts the agent to make decisions. Toggle with `/auto` command. | 1 hour | Build now |
| 2 | **Image/PDF reading** | Read tool handles images (sends as base64 to multimodal models) and PDFs (extracts text). Enables "read this screenshot" or "analyze this PDF." | 2 hours | Build now |
| 3 | **Model fallback** | When primary model is overloaded or rate-limited, auto-switch to a backup model (e.g., Sonnet → Haiku, GPT-5.4 → GPT-4o-mini). Configurable fallback chain. | 1 hour | Build now |
| 4 | **Plan mode with approval** | Structured planning: `/plan` command → agent writes a TodoWrite plan → user reviews → `/approve` to execute. Prevents "just start building" without thinking. | 2 hours | Build now |
| 5 | **Session search** | Search across all past sessions by content. `agent.search_sessions("gmail connector")` returns matching sessions with context. CLI: `/search <query>`. | 1 hour | Build now |
| 6 | **Diff preview before apply** | Before editing a file, show a colored diff of what will change and ask for confirmation. In auto-mode, skip the confirmation. | 1 hour | Build now |
| 7 | **MCP support** | Connect to Model Context Protocol servers for additional tools. Databases, APIs, browser automation, custom tools — all pluggable via MCP. The extensibility layer. | 1-2 days | Build next |

### Medium Impact — Power Users Would Notice

| # | Feature | What it does | Effort | Priority |
|---|---------|-------------|--------|----------|
| 8 | **Streaming tool execution** | Start executing tools WHILE the model is still generating its response. Detects tool_use blocks mid-stream and begins execution immediately. 2-4x latency reduction on multi-tool turns. | 6-8 hours | Build later |
| 9 | **Security classifier** | AI side-query (cheap model like Haiku) classifies bash commands as safe/needs-review/dangerous. Races the user permission prompt — whichever responds first wins. | 3-4 hours | Build later |
| 10 | **Verification specialist** | Dedicated adversarial subagent spawned after building to verify code works. Uses the self-awareness prompt: "You are bad at verification. You read code and write PASS instead of running it." Forces actual test execution. | 2 hours | Build next |
| 11 | **Git-aware tools** | Native git tools: current branch awareness, create commits with proper messages, show diffs, stage files. Currently we use bash for all git operations — works but not optimized. | 3-4 hours | Build later |
| 12 | **Plugin system** | Discover and load plugins from directories and entry_points. Plugins can add tools, hooks, and prompt fragments. How Salt Desktop extends SaltAgent with custom capabilities. | 4-6 hours | Build later |
| 13 | **Prompt cache prefix sharing** | When forking subagents, ensure the system prompt + conversation prefix is byte-identical so Anthropic's prompt cache gives cache hits. Claude Code makes all forks share identical placeholder tool_results. | 3-4 hours | Build later |

### Lower Impact — Nice-to-Have

| # | Feature | What it does | Effort | Priority |
|---|---------|-------------|--------|----------|
| 14 | **LSP integration** | Language Server Protocol: go to definition, find references, diagnostics, symbol search. Gives the agent semantic understanding of code, not just text. | 8+ hours | Skip for v1 |
| 15 | **Notebook editing** | Edit Jupyter notebook cells. NotebookEdit tool that reads/writes .ipynb files. | 4 hours | Skip for v1 |
| 16 | **IDE extensions** | VS Code and JetBrains extensions that embed SaltAgent. Open files, get cursor position, show diagnostics. | 20+ hours | Skip for v1 |
| 17 | **Voice input** | macOS voice overlay — speak instead of type. Speech-to-text → prompt. | 10+ hours | Skip for v1 |
| 18 | **Vim keybindings** | Full vim mode in the terminal (normal, insert, visual, operators, motions). | 6-8 hours | Skip for v1 |
| 19 | **Rich terminal UI** | Ink/React-based terminal rendering with layout components. Currently we use raw ANSI codes. | 10+ hours | Skip for v1 |
| 20 | **Bridge/remote sessions** | Distributed operation: run the agent on a remote server, interact from local terminal. Session bridging across machines. | 10+ hours | Skip for v1 |
| 21 | **Team/buddy mode** | Multi-user collaboration: multiple people interacting with the same agent session. Buddy mode for pair programming. | 10+ hours | Skip for v1 |
| 22 | **Auto-update** | Self-updating binary. Check for new versions, download, replace. | 4-6 hours | Skip for v1 |
| 23 | **Telemetry** | Usage analytics: tool call frequency, model usage, session length, error rates. Opt-in. | 3-4 hours | Skip for v1 |
| 24 | **Configurable keybindings** | Custom keyboard shortcuts for the CLI. | 3-4 hours | Skip for v1 |

---

## Implementation Plan

### Phase 5: Quick Wins (1 day)

Build items 1-6 — each is 1-2 hours:

1. **Auto-mode toggle**
   - Add `auto_mode: bool = False` to AgentConfig
   - `/auto` slash command toggles it
   - When auto, permission system allows everything
   - CLI shows "AUTO MODE" indicator in prompt

2. **Image/PDF reading**
   - Update ReadTool to detect image files (.png, .jpg, .gif, .webp, .svg)
   - For images: read as base64, return as content block `{"type": "image", "source": {"type": "base64", ...}}`
   - For PDFs: use `pdftotext` via bash or Python `PyPDF2` to extract text
   - Requires multimodal message format in providers

3. **Model fallback**
   - Add `fallback_model: str = ""` to AgentConfig
   - In providers: if primary model fails with overload/rate-limit after all retries, switch to fallback
   - CLI: `--fallback-model gpt-4o-mini`

4. **Plan mode with approval**
   - `/plan` command sets a flag: agent must write a TodoWrite plan before executing
   - System prompt injection: "You MUST create a plan using todo_write before taking any action. Wait for the user to say /approve."
   - `/approve` command removes the restriction, agent proceeds with the plan

5. **Session search**
   - Add `search_sessions(query: str)` to SessionPersistence
   - Grep through JSONL files for matching content
   - Returns: session_id, matching line, context
   - CLI: `/search <query>`

6. **Diff preview**
   - Before EditTool.execute(), show the diff and ask for confirmation
   - In auto-mode: skip confirmation
   - Use the permission hook to intercept edit calls and show the diff

### Phase 6: MCP Support (2-3 days)

The big extensibility win. MCP allows connecting any tool server:
- Database tools (query Postgres, MongoDB)
- Browser automation (Playwright, Puppeteer)
- API tools (Slack, Gmail, GitHub)
- Custom tools (anything you build)

Implementation:
- MCP client that connects to stdio or HTTP servers
- Tools from MCP servers are dynamically registered in the ToolRegistry
- Config: list of MCP server commands in a JSON file
- Matches how Claude Code does it: `--mcp-config mcp.json`

### Phase 7: Verification + Security (1 day)

10. Verification specialist subagent
9. Security classifier for bash

### Phase 8: Performance (2 days)

8. Streaming tool execution
13. Prompt cache prefix sharing

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Claude Code feature match | ~75-80% | 90%+ |
| Tests passing | 575 | 650+ |
| Average tool execution time | Sequential | Parallel for read-only |
| Web content extraction | 17K chars | 50K+ chars (trafilatura) |
| Cost per session (Anthropic) | No caching | 50-90% reduction with caching |
| Session resilience | Resume from crash | + auto-compact on overflow |

---

## What We're NOT Building (intentional gaps)

- **IDE extensions** — Salt Desktop IS the IDE. Web UI + native app.
- **Vim mode** — Nice but not essential. Readline is enough.
- **Rich terminal UI (Ink)** — Our ANSI rendering is adequate. The real UI is the web app.
- **Voice** — Future feature, not core to agent capability.
- **Multi-user** — Salt Desktop is single-user for v1.
- **Auto-update** — Handled by the macOS app's update mechanism, not the agent.

These are conscious decisions, not gaps. SaltAgent is embedded in Salt Desktop — the desktop app handles UI, distribution, and collaboration. SaltAgent handles intelligence.
