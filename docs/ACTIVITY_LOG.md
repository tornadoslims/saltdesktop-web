# Activity Log

Real-time log of everything done in this workspace. Updated automatically by the Backend Claude after each significant action.

---

## 2026-03-29

### Initial Build Session
- Built entire JBCP control plane from scratch: 24 runtime modules, all importing clean
- 373 tests passing across 17 test files
- 36 API endpoints on FastAPI server (port 8718)
- Fixed company naming bugs (CLI fallback names, plugin rename logic, Discord API User-Agent)
- Added rename-sweep CLI command and `POST /api/workspaces/sync-names` endpoint
- Added company- prefix gate to plugin (`JBCP_CHANNEL_PREFIX`)
- Set up coordination system with frontend Claude (MESSAGES.md, prds/, status/, locks/)
- Reworked `GET /api/agents` for rich agent state (status, model, workspace, tokens, subagents)
- Built TUI dashboard with 7 views
- Built React + Express web dashboard (dashboard/) for visual monitoring
- Created full documentation: CLAUDE.md, BACKEND_API_SPEC.md, EVENT_STREAM_SPEC.md, FRONTEND_SPEC.md

---

## 2026-03-30

### MVP Completion
- **End-to-end pipeline working:** generate → approve → dispatch → worker completes all tasks
- Tested full flow through API: workspace creation → mission → plan generation → approval → task dispatch → worker execution → completion

### Data Model Simplification
- **Merged Plan into Mission** — deleted jb_plans.py (~200 lines removed)
- Mission now has `items`, `components`, `connections` fields directly
- Mission statuses: planning, planned, active, complete, failed, cancelled
- Removed all Plan-related API endpoints, simplified sidebar/inspector/state

### Signal System Enhancements
- Added new signal types: `llm_input` (model, provider, prompt size, history count) and `llm_output` (model, text preview, text size, token usage)
- Enhanced `tool_start`/`tool_end` with `source` (bash/http/web/browser/subprocess/claude-code) and `label` (human-readable descriptions)
- Added `result_preview` (first 500 chars) to `tool_end` signals
- **Built real-time signal push system:** HTTP POST from plugin → API event bus, <50ms latency
- New endpoint: `POST /api/signals/push`

### Web UI Dashboard (webui/)
- Built lightweight web UI served directly by FastAPI at http://localhost:8718/
- 5 pages: workspaces, workspace detail, activity feed, agents, debug
- Chat with SSE streaming, command autocomplete (`/` triggers command palette)
- Typing indicator driven by real-time signals (llm_input, tool_start)
- **SSE drop recovery:** when gateway drops connection during tool use, signals keep typing indicator alive, `agent_turn` triggers history fetch
- 15-second targeted refresh (doesn't rebuild chat or component graph)

### Plugin Fixes
- Fixed Discord token parsing (was reading wrong config path)
- Fixed slash command resolver (was using stale `slash:` routing IDs instead of real channel IDs)
- Fixed planning mode tool blocking — now blocks `subagents` tool (Santiago was spawning coding agents during planning)
- Fixed context injection for frontend sessions (direct company ID lookup)
- Renamed `/debug` to `/jbdebug` to avoid conflict with OpenClaw built-in

### API Additions
- `GET /api/commands` — all slash commands with descriptions and workflow
- `GET /api/workspaces/{id}/prompt-debug` — full prompt injection tree for debugging
- `POST /api/signals/push` — real-time signal delivery from plugin
- Fixed event stream keepalives (15s interval)
- Fixed agent workspace association (session reuse detection)

### Testing
- Added API flow test suite (`test_api_flow.py` — 33 integration tests)
- Added end-to-end test suite (`test_end_to_end.py`)
- Tested Approach 1 for tool deny list — doesn't work, OpenClaw subagent spawning loops
- Configured ACP/Claude Code test agent (santiago-cc) — ready to test

### Documentation
- Generated SYSTEM_SPEC.md (~800 lines, full system reference)
- **Current totals: 44 API routes, 358 unit tests, 33 integration tests, 25+ modules**

### Product Strategy Discussion
- Defined object model: User → Workspace → Mission → Service (1:1)
- Components shared globally (single user, no governance needed)
- Coding agent feedback loop: agent question → Santiago relays → user answers → re-dispatch
- Decided: web UI is v1 product, native app builds against locked API spec
- Documented honest assessment: strengths, concerns, next steps
- Created PRODUCT_STRATEGY.md PRD

### Live Build View
- Built real-time build view in webui: progress bar, task cards with signal feed, elapsed timers
- Active tasks show live signal events (thinking, searching, writing, running tests)
- Failed tasks show errors with retry buttons
- Completed tasks show summary and duration

### Product Strategy — Component Graph as Executable Source of Truth
- Decided: component graph should be auto-generated pipeline runner (like N8N but AI-generated)
- Graph defines execution order based on data flow connections
- Users see and understand how their system works via the graph
- Components have typed contracts (input/output types, config, schemas)
- Two working examples exist: email_digest_runner.py, cryptodash_runner.py
- Phase 9 (jb_pipeline.py) will auto-generate runner code from component graph
- Discussed gmail→telegram alert example as test case for component decomposition

---

## 2026-03-31

### Salt Desktop PRD Session
- Created comprehensive Salt Desktop PRD (APP_UX_PRD.md) with full product vision
- Decided all 7 UX experiences: chat, graph interaction, "Build It", error states, navigation, creating things, "Go Live"
- Defined 4 separate systems: real-time streaming, context injection, agent autonomy, multi-mission routing
- Mission→Agent lifecycle: missions are the build process, agents are the deployed result
- Component summary chain: invisible Layer 2 that flows summaries through the graph for status reporting
- "The Swarm": anonymous workers by role (Coder/Researcher/Analyst/Writer) building in parallel
- Living dashboard replaces portfolio kanban
- All 7 open questions resolved (Santiago as single agent, component library trophy case, macOS notifications, single user, no mobile)
- API gap analysis: 80% covered, 7 gaps identified (Gap 6 feedback loop eliminated)
- PRD frozen as FINAL v0.1
- Full web UI rebuild launched against PRD
