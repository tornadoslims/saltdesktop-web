# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/cso`, `/autoplan`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, `/learn`.

## Work Style

**All coding tasks MUST be delegated to subagents.** When the user asks you to write, edit, or fix code:
1. Plan the work in the main conversation (read files, understand context, decide approach)
2. Delegate the actual code changes to a background Agent — give it a clear prompt with: what files to change, what the changes should be, and verification steps (tests, imports)
3. Continue chatting with the user while the agent works
4. Report the outcome when the agent completes

This keeps the main conversation responsive. Small edits (CLAUDE.md, MESSAGES.md, status files, config) can be done directly.

## Living Documentation

Two docs must be kept up to date. Update them as part of your workflow — not after every tiny change, but after each significant milestone (feature completed, bug fixed, architecture changed, new endpoint added).

### Activity Log (`docs/ACTIVITY_LOG.md`)
- Append a timestamped entry after each significant action
- Format: `### HH:MM — Brief title` followed by 1-3 bullet points
- Group by date
- Include: what was done, what was affected, key numbers (routes, tests)
- This is a running log — only append, never rewrite

### System Spec (`docs/SYSTEM_SPEC.md`)
- Complete specification of the entire system
- After significant architecture changes (new modules, removed modules, API changes, data model changes), delegate a background agent to regenerate it by reading the full codebase
- Trigger: merging entities (plan->mission), adding/removing modules, changing the data model, major refactors
- NOT triggered by: bug fixes, config changes, test additions

## PRD & Spec Documents

All product and technical specs live in `~/Projects/santiago-salt-desktop/claude_plan/prds/`:

| Document | What it covers |
|----------|---------------|
| `APP_UX_PRD.md` | **Salt Desktop PRD** -- the main product spec. Vision, object model, lifecycle, all UX decisions, API gap analysis, four systems (streaming, context, autonomy, routing). START HERE. |
| `PRODUCT_STRATEGY.md` | Product strategy, honest assessment, open questions |
| `JBCP_BUILD_PLAN.md` | Build plan with completed/remaining work tracking |
| `BACKEND_API_SPEC.md` | API endpoint spec for frontend consumption |
| `EVENT_STREAM_SPEC.md` | SSE event stream spec |
| `FRONTEND_SPEC.md` | Frontend architecture spec |
| `PACKAGING_AND_SANDBOX.md` | App packaging and sandboxing |
| `POC_PRD.md` | Proof of concept PRD |

**The app is called Salt Desktop.** JBCP is invisible infrastructure -- never referenced in user-facing UI.

**CRITICAL: The webui-v2 is a TEMPORARY development tool.** It exists to build and test all APIs, UX flows, and real-time features before they are consumed by the proper Swift macOS native app (Salt Desktop). Every API endpoint, every SSE event, every interaction pattern we build in the web UI will be replicated in the native app. The web UI is the proving ground, not the product.

**CRITICAL: Every decision must account for this becoming a fully contained macOS .app.** Salt Desktop will ship as a single macOS application bundle containing the Swift UI, JBCP API server, and all runtime components. All file paths, directory conventions, process management, and architecture decisions must work inside an app sandbox. No hardcoded paths -- use relative paths from a configurable base directory. No assumptions about system-level installs. Everything self-contained.

## Architecture

The system is fully standalone with zero external dependencies on any agent platform.

- **Planning chat:** Direct Anthropic/OpenAI SDK calls (streaming)
- **Building:** Claude Code CLI (`claude --print --output-format json`)
- **Data storage:** SQLite (WAL mode, thread-safe)
- **Credentials:** `~/.missionos/credentials/`
- **Event streaming:** In-memory event bus -> SSE to frontend

### Data Flow Pipeline

```
User -> Chat (direct LLM) -> Mission -> Plan Generation (direct LLM)
  -> Components -> Tasks -> Builder (Claude Code CLI) -> Complete
```

## Credentials & External Service Connections

The companion Swift app (PackagingPOC) handles OAuth flows and API key entry. It saves credentials as JSON files to a shared directory. JBCP reads from here -- never writes (except refreshed OAuth tokens).

### Location: `~/.missionos/credentials/`

Each connected service has a `{service_id}.json` file (OAuth tokens, API keys, connection strings).

**Service IDs:** gmail, google_calendar, google_drive, github, salesforce, notion, linear, jira, discord, telegram, openai, stripe, aws, snowflake, mysql, postgres, oracle, redis, gcp

### Rules
1. **Never write** to `~/.missionos/credentials/` -- only the Swift app writes. ONE exception: writing back refreshed OAuth tokens.
2. **All access through `CredentialStore`** -- single class, single file change when we migrate to secure storage.
3. **Handle missing gracefully** -- if gmail.json doesn't exist, show "Connect Gmail" -- don't crash.
4. **Handle expired OAuth** -- on 401, use refresh_token to get new access_token, write it back.

## Coordination Protocol

**You are the BACKEND Claude.** You work on the JBCP Python runtime, API server, and all backend infrastructure.

There is a **FRONTEND Claude** working on the Swift macOS app at `~/Projects/santiago-salt-desktop/`.

### Session Startup (do BEFORE any work)
1. Read messages: `~/Projects/santiago-salt-desktop/claude_plan/MESSAGES.md` -- check "Unread -- For Backend"
2. Read frontend status: `~/Projects/santiago-salt-desktop/claude_plan/status/frontend.md`
3. If there are unread messages, tell the user and ask if you should address them first
4. Update your status file: `~/Projects/santiago-salt-desktop/claude_plan/status/backend.md`

### During Work
- When you finish something that affects the frontend, write to "Unread -- For Frontend" in MESSAGES.md
- When you start/finish significant work, update `status/backend.md`
- Only move a message to Archive after the work is DONE -- reading is not addressing

### Key Locations

| What | Where |
|------|-------|
| Messages | `~/Projects/santiago-salt-desktop/claude_plan/MESSAGES.md` |
| PRDs & specs | `~/Projects/santiago-salt-desktop/claude_plan/prds/` |
| Your status | `~/Projects/santiago-salt-desktop/claude_plan/status/backend.md` |
| Frontend status | `~/Projects/santiago-salt-desktop/claude_plan/status/frontend.md` |
| Shared context | `~/Projects/santiago-salt-desktop/claude_plan/status/SHARED_CONTEXT.md` |

### Rules
1. **Check messages first** -- every session, before doing anything
2. **Don't modify frontend files** -- that's the other Claude's territory
3. **Document API changes** -- write to MESSAGES.md + update the PRD in `prds/`
4. **Lock before editing shared files** -- check `locks/` before touching `prds/` or `MESSAGES.md`
5. **Test before announcing** -- run `python -m pytest tests/ -q` before claiming something works
6. **Keep the API server importable** -- verify `python -c "from runtime.jb_api import app"` after changes

---

## What This Is

**JBCP (JB Command Processor)** is the mission-driven control plane for Salt Desktop. It turns a single user prompt into a fully built, tested, and deployed system. Users describe what they want ("build a bot that checks my work email every 15 minutes and alerts me...") and JBCP orchestrates AI agents to plan, build, and deploy it.

## Project Structure

### Runtime Modules (`runtime/`)

| File | Purpose |
|------|---------|
| `jb_queue.py` | Task CRUD: pending -> dispatched -> running -> complete/failed, priority-sorted |
| `jb_missions.py` | Mission CRUD with company linkage, constraints, task linking |
| `jb_companies.py` | Company/workspace CRUD, focused mission, context file paths |
| `jb_company_mapping.py` | Maps external sources to companies (extensible) |
| `jb_components.py` | Component registry: CRUD, typed contracts, connections, graph generation |
| `jb_services.py` | Service registry: lifecycle, run tracking, port allocation |
| `jb_builder.py` | Claude Code CLI builder: spawns claude --print to build components |
| `jb_orchestrator.py` | Orchestrator loop: retry -> dispatch -> reconcile -> lifecycle -> compact |
| `jb_compaction.py` | Updates mission_context.md after task completion |
| `jb_plan_generate.py` | Direct LLM calls to generate structured plan items from chat |
| `jb_events.py` | Append-only JSONL event log |
| `jb_event_bus.py` | In-memory pub/sub event bus for real-time SSE |
| `jb_commands.py` | Slash command handling for the API chat endpoint |
| `jb_api.py` | FastAPI backend server on port 8718 |
| `jb_database.py` | SQLite database layer (WAL mode, thread-safe) |
| `jb_credentials.py` | Credential store for external services |
| `jb_pipeline.py` | Pipeline runner for component chains |
| `jb_common.py` | Shared utilities: JsonStore, utc_now_iso, DATA_DIR, BASE_DIR |
| `jb_labels.py` | Human-readable status labels |
| `jb_ceo_translator.py` | CEO-mode signal translation for simplified UI |
| `jb_mock_data.py` | Mock data for UI development |
| `jb_swarm.py` | Multi-agent swarm building |

### Other Directories

- `data/` -- SQLite database and JSON persistence
- `logs/` -- Orchestrator logs and JSONL event streams
- `memory/` -- Daily memory files
- `components/` -- Built component code
- `pipelines/` -- Pipeline definitions
- `tests/` -- Test suite
- `webui-v2/` -- Temporary web UI for development

## How to Run Things

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -q

# API server (port 8718)
python -m runtime.jb_api

# Orchestrator (single pass)
python -m runtime.jb_orchestrator --once

# Compaction sweep
python -m runtime.jb_compaction --sweep

# Plan generation
python -m runtime.jb_plan_generate --mission-id X
```

## Key Design Decisions

- **Direct LLM calls for planning.** Chat and plan generation call Anthropic/OpenAI APIs directly via their SDKs. No intermediate gateway.
- **Claude Code CLI for building.** Components are built by spawning `claude --print --output-format json` with structured prompts. Fully local.
- **SQLite for persistence.** All state lives in a SQLite database with WAL mode for concurrent reads/writes. Legacy JSON files kept for backward compat.
- **Components have typed contracts.** Each component declares input_type, output_type, config_fields, input_schema, and output_schema. Connections validate compatibility.
- **Services are deployed workspaces with lifecycle management.** Types: scheduled, daemon, webhook, manual. Each gets port allocation, run tracking, and health monitoring.
- **Graph is derived, not stored.** `build_graph()` reads components and connections to produce nodes and edges on demand.
- **In-memory event bus for real-time updates.** All mutations emit events that SSE subscribers receive instantly.

## Key Conventions

- All timestamps are UTC ISO format
- Task IDs, mission IDs, component IDs, and service IDs are UUIDs
- Every module uses `BASE_DIR = Path(__file__).resolve().parent.parent` to find workspace root
- Tasks carry `origin` (where the request came from) and `delivery` (how to return results)
