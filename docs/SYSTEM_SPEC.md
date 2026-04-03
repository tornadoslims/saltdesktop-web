# JBCP System Specification

**Version:** 0.4.0
**Date:** 2026-03-30
**Status:** Complete reference for developers and AI agents

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Runtime Modules](#3-runtime-modules)
4. [Data Model](#4-data-model)
5. [API Endpoints](#5-api-endpoints)
6. [Plugin — jbcp-observer](#6-plugin--jbcp-observer)
7. [Web Dashboard](#7-web-dashboard)
8. [Signal System](#8-signal-system)
9. [Mission Lifecycle](#9-mission-lifecycle)
10. [Configuration](#10-configuration)
11. [Testing](#11-testing)
12. [File Locations](#12-file-locations)

---

## 1. System Overview

### What JBCP Is

**JBCP (JB Command Processor)** is the mission-driven control plane for OpenClaw. It turns a single user prompt into a fully planned, built, tested, and deployed software system. Users describe what they want (e.g., "build a bot that checks my work email every 15 minutes and alerts me") and JBCP orchestrates AI agents to plan, build, and deploy it.

JBCP is the backend brain of an autonomous agent named **Santiago**. It manages:
- **Workspaces** (companies) mapped to Discord channels or frontend sessions
- **Missions** with structured planning workflows
- **Components** representing logical software pieces with typed contracts
- **Tasks** dispatched to OpenClaw AI agents (jbcp-worker) for execution
- **Services** for deployed, production-running workloads

### Product Vision

A user opens a Discord channel (or the desktop app), describes what they want to build, and JBCP:

1. Creates a workspace and enters **planning mode**
2. Facilitates an architecture conversation between the user and Santiago
3. Generates a structured plan: components, connections, and tasks
4. On approval, enqueues tasks and dispatches them to AI worker agents
5. Tracks progress, retries failures, compacts context, and auto-completes missions
6. Optionally promotes the result to a running service

### Key Design Principles

- **Python CLI as single source of truth for mutations.** All writes to JSON data files go through runtime modules. The plugin never writes JSON directly.
- **File-backed persistence.** All state lives in JSON files under `data/`. No database. `JsonStore` handles atomic reads/writes.
- **Graph is derived, not stored.** `build_graph()` reads components and connections on demand.
- **Context injection is scoped.** Only mapped channels receive JBCP context in prompts.
- **Tool blocking during planning mode.** The plugin blocks exec/write/edit tools to prevent building before the plan is approved.

---

## 2. Architecture

### Data Flow Pipeline

```
Company -> Mission -> Plan (items/components/connections) -> Approve -> Tasks -> Dispatch -> Worker -> Complete -> Compact
```

### Detailed Flow

```
1. COMPANY (workspace) is created when:
   - A Discord channel is first mapped (auto-created by plugin)
   - The frontend creates a new workspace via POST /api/workspaces
   - The CLI calls `company get-or-create`

2. MISSION is created for a long-running goal within a workspace.
   Starts in "planning" status.

3. PLANNING MODE: User chats about requirements. Santiago acts as
   solution architect (exec/write tools are BLOCKED). The plugin
   injects a planning prompt into the LLM context.

4. PLAN GENERATION: /mission generate dispatches to jbcp-worker
   agent which produces structured JSON: components, connections,
   and task items. Stored on the mission object.

5. APPROVAL: /mission approve transitions mission to "active":
   - Creates Component records in jb_components.json
   - Creates Connection records in jb_connections.json
   - Enqueues Task records in jb_queue.json (priority-ordered)
   - Each task references its component and mission

6. DISPATCH: The orchestrator picks up pending tasks and sends
   them to OpenClaw agents via the bridge:
   - Builds a rich prompt with company context + mission context
   - Calls `openclaw agent --agent jbcp-worker --json --message ...`
   - Maps outcomes: complete, running (timeout), or failed

7. RECONCILIATION: The orchestrator checks running/dispatched tasks
   by querying OpenClaw sessions for status updates.

8. RETRY: Failed tasks with remaining retries are moved back to pending.

9. LIFECYCLE: When all tasks reach terminal states:
   - All complete -> mission "complete"
   - Any failed (retries exhausted) -> mission "failed"

10. COMPACTION: After tasks complete, the compaction agent updates
    mission_context.md with a summary of progress, so subsequent
    tasks get richer context.
```

### Component Architecture

```
+-------------------+     +-------------------+     +-------------------+
|  OpenClaw Plugin  |     |   FastAPI Server   |     |   Web Dashboard   |
|  (jbcp-observer)  |     |   (jb_api.py)      |     |   (dashboard/)    |
|  - Signal capture |     |   - REST endpoints |     |   - React SPA     |
|  - Context inject |     |   - Chat proxy     |     |   - Express BFF   |
|  - Tool blocking  |     |   - SSE streaming  |     |   - File reader   |
|  - /mission cmds  |     |   - Event bus      |     |   - WS to gateway |
+--------+----------+     +--------+-----------+     +--------+----------+
         |                          |                          |
         v                          v                          v
+--------+----------+     +--------+-----------+     +--------+----------+
|   Python CLI      |     |   Runtime Modules   |     |   JSON Data Files |
|  (jb_cli.py)      +---->|   jb_queue.py       +---->|   data/*.json     |
|  - All mutations  |     |   jb_missions.py    |     |   data/signals/   |
|  - JSON output    |     |   jb_companies.py   |     |   data/companies/ |
+-------------------+     |   jb_components.py  |     |   logs/           |
                          |   jb_services.py    |     +-------------------+
                          |   jb_orchestrator.py|
                          |   jb_bridge.py      |
                          +---------------------+
                                    |
                                    v
                          +---------------------+
                          |   OpenClaw Gateway   |
                          |   (port 18789)       |
                          |   - Agent execution  |
                          |   - Chat sessions    |
                          +---------------------+
```

---

## 3. Runtime Modules

All modules live in `~/.openclaw/workspace/runtime/`. Every module uses `BASE_DIR = Path(__file__).resolve().parent.parent` to resolve the workspace root.

### Core Data Modules

| Module | File | Purpose |
|--------|------|---------|
| **jb_common.py** | Shared utilities | `JsonStore` class, `utc_now_iso()`, `age_seconds()`, `parse_iso()`, `DATA_DIR`, `BASE_DIR`, `LOG_DIR` paths |
| **jb_queue.py** | Task CRUD | Full task lifecycle: `enqueue()`, `get_pending()`, `mark_dispatched()`, `mark_running()`, `mark_complete()`, `mark_failed()`, `mark_suspect()`, `mark_needs_review()`, `retry_task()`, `get_retryable()`, `attach_openclaw_session()`, `attach_subagent_session()`, `attach_external_process()`, `touch_external_process()` |
| **jb_missions.py** | Mission CRUD | `create_mission()`, `approve_mission()`, `mark_planned()`, `reopen_planning()`, `add_item()`, `remove_item()`, `update_item()`, `attach_task()`, `mark_mission_status()`, `_compute_dep_depth()` for priority ordering |
| **jb_companies.py** | Company/workspace CRUD | `create_company()`, `update_company_name()`, `archive_company()`, `attach_mission()`, `set_focused_mission()`, `get_focused_mission_id()`, `get_company_context_path()`, `get_mission_context_path()`, `ensure_mission_context()` |
| **jb_company_mapping.py** | External ID mapping | Maps Discord channels (or other sources) to company IDs. `create_mapping()`, `get_company_id_by_external()`, `get_external_id_by_company()`, `delete_mapping()` |
| **jb_components.py** | Component registry | `create_component()`, `update_component()`, `mark_component_status()`, `attach_task()`, `add_file()`, `list_connections()`, `create_connection()`, `delete_connection()`, `build_graph()`, `check_component_lifecycle()` |
| **jb_services.py** | Service registry | `create_service()`, `update_service()`, `start_service()`, `stop_service()`, `pause_service()`, `resume_service()`, `allocate_port()`, `release_port()`, `record_run()`, `list_runs()` |
| ~~jb_plans.py~~ | **REMOVED** | Plan entity merged into Mission. Plans are now embedded as `items`, `components`, `connections` fields on the Mission object. |

### Orchestration Modules

| Module | File | Purpose |
|--------|------|---------|
| **jb_orchestrator.py** | 5-phase orchestration loop | `run_once()` executes: (1) `retry_failed()` -- requeue retryable tasks, (2) `dispatch_pending()` -- send tasks to OpenClaw, (3) `reconcile_running()` -- check running task sessions, (4) `check_lifecycles()` -- auto-complete/fail missions, (5) `compact_completed()` -- update mission context. Runs as `--once` or continuous loop with `--interval` seconds. |
| **jb_openclaw_bridge.py** | OpenClaw dispatch | `dispatch_task()` -- builds prompt, calls `openclaw agent` CLI, handles outcomes. `invoke_openclaw()` -- raw subprocess call. `build_task_prompt()` -- assembles company/mission/task context. `check_session_status()` -- queries existing sessions for reconciliation. `build_context_summary()` -- for /contextmem display. Also manages wake request handling. |
| **jb_compaction.py** | Context updates | `compact_mission()` -- builds a summary prompt from completed/pending/failed tasks and dispatches to jbcp-worker to rewrite `mission_context.md`. `check_mission_lifecycle()` -- auto-marks missions complete/failed based on task states. `run_compaction_sweep()` -- sweeps all active missions. |
| **jb_plan_generate.py** | AI plan generation | `generate_mission_plan()` -- fetches chat history from OpenClaw, builds a structured prompt, calls jbcp-worker, parses the JSON response (components, connections, tasks), normalizes items, saves to mission. `parse_items_from_response()` -- robust JSON extraction from worker text (handles markdown fences, nested objects, arrays). |

### Event and Signal Modules

| Module | File | Purpose |
|--------|------|---------|
| **jb_events.py** | Append-only JSONL log | `emit_event()` writes structured events to `logs/jbcp_events.jsonl`. `read_events()`, `filter_events()` for querying. Events carry: `ts`, `event_type`, `mission_id`, `task_id`, `openclaw_session_id`, `parent_session_id`, `subagent_session_id`, `payload`. |
| **jb_event_bus.py** | In-memory pub/sub | Real-time event distribution for SSE. `emit()` pushes to all connected async queues AND writes to JSONL. `subscribe()` returns an `asyncio.Queue`. `unsubscribe()` removes it. `health_check()` returns subscriber count. |
| **jb_signals.py** | Signal file reader | `read_signals()` reads `data/signals/jbcp_signals.jsonl` (written by the plugin). `get_active_sessions()` derives session state from signal history. Handles rotated files for continuity. Also receives real-time signals via `POST /api/signals/push` (HTTP push from plugin, <50ms latency). |
| **jb_signal_rotate.py** | Daily signal rotation | `rotate_signals()` renames the signal file to `jbcp_signals.YYYY-MM-DD.jsonl`, creates a fresh empty file, and deletes rotated files older than `keep_days` (default 7). Called by orchestrator. |
| **jb_agent_state.py** | Agent state tracker | `get_agent_states()` parses signals to build real-time view of agents: status (coding/thinking/idle/offline), current model, workspace, file, activity label, source type, token usage, subagents, linked tasks. `get_active_tool_calls()` finds in-flight tool calls. |

### Monitoring and Recovery

| Module | File | Purpose |
|--------|------|---------|
| **jb_watchdog.py** | Stale task detection | `inspect_task()` checks tasks in active states for staleness. Marks stale tasks as "suspect", stale external processes as "needs_review". Optionally emits wake requests. Configurable thresholds: `--stale-task-seconds` (default 300), `--stale-process-seconds` (default 180). |
| **jb_wake.py** | Wake request system | `emit_wake_request()` creates intervention triggers. `request_from_task()` creates wake from a task with enriched details. `read_wake_requests()`, `filter_wake_requests()` for querying. Wake requests stored in `data/jb_wake_requests.jsonl`. |

### CLI and Interface Modules

| Module | File | Purpose |
|--------|------|---------|
| **jb_cli.py** | CLI entry point | Single entry point for all mutations, called by the plugin via `execFileSync`. Subcommands: `company create/get-or-create/rename/rename-sweep`, `mission new/list/switch/status/generate/approve/cancel/set-items`, `contextmem`. All output is JSON. |
| **jb_commands.py** | API command handler | Handles slash commands from the API chat endpoint: `/mission`, `/contextmem`, `/jbdebug`, `/status`. Returns formatted text responses. Mirrors plugin commands but in Python. |
| **jb_api.py** | FastAPI server | HTTP API on port 8718 with 44 endpoints. Chat proxy to OpenClaw gateway. SSE streams for events and signals. Signal push receiver (`POST /api/signals/push`). Serves web UI from `webui/` directory. Pydantic models for request validation. CORS configured for local development and LAN access. |
| **jb_dashboard.py** | TUI dashboard | Terminal-based dashboard with 7 views: Companies, Tasks, Missions, Plans, Events, Activity, Wakes. |
| **jb_status.py** | Quick status CLI | Formatted terminal output of missions, tasks, events, and wake requests. Supports `--all`, `--events N`, `--json`, `--tasks-only` flags. |
| **jb_validate_queue.py** | Queue integrity check | Loads and validates all tasks, printing status. Exits non-zero if the queue file is corrupt. |
| **jb_enqueue.py** | Task creation CLI | `build_task()` helper and CLI for creating tasks with origin/delivery metadata. |
| **jb_discord.py** | Discord API helpers | `get_channel_name()` queries Discord REST API for channel names. `resolve_all_channel_names()` batch-resolves for rename sweeps. Reads bot token from OpenClaw config or environment. |

### Auxiliary Modules (Non-JBCP)

| Module | Purpose |
|--------|---------|
| `email_digest_*.py` | Email digest worker (Gmail fetch, summarize, Slack post) |
| `cryptodash_*.py` | Crypto dashboard worker (BTC fetcher, history, renderer, alerts) |

---

## 4. Data Model

All data is persisted as JSON files in `~/.openclaw/workspace/data/`.

### Company (Workspace)

**File:** `data/jb_companies.json`

| Field | Type | Description |
|-------|------|-------------|
| `company_id` | string (UUID) | Primary key |
| `name` | string | Display name (from Discord channel name or user input) |
| `status` | enum | `active`, `archived` |
| `focused_mission_id` | string or null | Currently active mission |
| `mission_ids` | string[] | All attached mission IDs |
| `company_context_path` | string | Path to `company_context.md` |
| `created_at` | ISO-8601 | Creation timestamp |
| `updated_at` | ISO-8601 | Last update timestamp |

**Directory structure per company:**
```
data/companies/{company_id}/
  company_context.md          # Company-level persistent context
  missions/{mission_id}/
    mission_context.md        # Mission-level persistent context (updated by compaction)
```

### Mission

**File:** `data/jb_missions.json`

| Field | Type | Description |
|-------|------|-------------|
| `mission_id` | string (UUID) | Primary key |
| `company_id` | string or null | Parent workspace |
| `goal` | string | User's stated goal (required, non-empty) |
| `summary` | string or null | Generated summary |
| `status` | enum | See lifecycle below |
| `constraints` | string[] | User-specified constraints |
| `source_artifacts` | object[] | `{type, path, description}` |
| `task_ids` | string[] | Linked task IDs |
| `items` | object[] | Plan items (task blueprints) -- see below |
| `components` | object[] | Architecture components (raw from plan generation) |
| `connections` | object[] | Data flow connections (raw from plan generation) |
| `origin` | object or null | Where the mission request came from |
| `delivery` | object or null | How to return results |
| `context_path` | string or null | Path to mission_context.md |
| `created_at` | ISO-8601 | Creation timestamp |
| `updated_at` | ISO-8601 | Last update timestamp |

**Valid mission statuses:** `planning`, `planned`, `active`, `blocked`, `complete`, `failed`, `cancelled`

**Plan Item (embedded in mission):**

| Field | Type | Description |
|-------|------|-------------|
| `item_id` | string (UUID) | Unique item identifier |
| `title` | string | Short title (defaults to first 60 chars of goal) |
| `goal` | string | Actionable task goal (required, non-empty) |
| `type` | enum | `coding`, `research`, `document`, `analysis`, `unknown` |
| `component` | string | Component name this task targets |
| `constraints` | string[] | Task-level constraints |
| `dependencies` | string[] | Item IDs this depends on |
| `priority` | int | 1-10, higher runs first |

### Task

**File:** `data/jb_queue.json`

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Primary key |
| `company_id` | string or null | Parent workspace |
| `mission_id` | string or null | Parent mission |
| `type` | string | `coding`, `research`, `document`, `analysis`, `unknown` |
| `status` | enum | See below |
| `priority` | int | Higher = runs first (adjusted by dependency depth) |
| `assigned_to` | string or null | Agent assignment (e.g., `openclaw:jbcp-worker`) |
| `retry_count` | int | Current retry count |
| `max_retries` | int | Maximum retries (default 3) |
| `error` | string or null | Last error message |
| `origin` | object | `{surface, session_id, thread_id}` |
| `delivery` | object | `{mode}` (default: `reply_to_origin`) |
| `openclaw_session_id` | string or null | OpenClaw session handling this task |
| `parent_session_id` | string or null | Parent session if subagent |
| `subagent_session_id` | string or null | Subagent session if spawned |
| `external_process` | object or null | `{type, pid, status, started_at, last_seen}` |
| `payload` | object | `{goal, item_id, constraints, component, ...}` |
| `created_at` | ISO-8601 | Creation timestamp |
| `updated_at` | ISO-8601 | Last update timestamp |

**Valid task statuses:** `pending`, `dispatched`, `running`, `in_progress`, `complete`, `failed`, `suspect`, `needs_review`

**Task status transitions:**
```
pending -> dispatched -> running -> complete
                      \-> complete (immediate)
                      \-> failed
running -> complete (via reconciliation)
running -> failed (aborted session)
failed -> pending (retry)
dispatched/running/in_progress -> suspect (watchdog: stale)
* -> needs_review (watchdog: stale external process)
```

### Component

**File:** `data/jb_components.json`

| Field | Type | Description |
|-------|------|-------------|
| `component_id` | string (UUID) | Primary key |
| `workspace_id` | string | Parent workspace (required) |
| `name` | string | Component name (required, non-empty) |
| `type` | enum | `connector`, `processor`, `ai`, `output`, `scheduler`, `storage`, `config` |
| `description` | string | What this component does |
| `status` | enum | `planned`, `building`, `built`, `testing`, `passing`, `failing`, `deployed` |
| `contract` | object | Typed interface -- see below |
| `directory` | string | Filesystem directory for this component |
| `files` | string[] | Files belonging to this component |
| `dependencies` | string[] | Component IDs this depends on |
| `task_ids` | string[] | Tasks linked to this component |
| `created_at` | ISO-8601 | Creation timestamp |
| `updated_at` | ISO-8601 | Last update timestamp |

**Component Contract:**

| Field | Type | Description |
|-------|------|-------------|
| `input_type` | string or null | Input data type (e.g., `List[Email]`) |
| `output_type` | string | Output data type (default: `Any`) |
| `config_fields` | object | Configuration parameters `{key: type}` |
| `input_schema` | object | JSON schema for input |
| `output_schema` | object | JSON schema for output |

**Build progress heuristic:**
```
planned: 0%  ->  building: 25%  ->  built: 50%  ->  testing: 65%
passing: 85%  ->  deployed: 100%     failing: 60%
```

### Connection

**File:** `data/jb_connections.json`

| Field | Type | Description |
|-------|------|-------------|
| `connection_id` | string (UUID) | Primary key |
| `workspace_id` | string | Parent workspace (required) |
| `from_component_id` | string | Source component (required) |
| `to_component_id` | string | Target component (required) |
| `from_output` | string | Named output port |
| `to_input` | string | Named input port |
| `type` | enum | `data_flow`, `control_flow` |
| `label` | string or null | Human-readable description |

### Service

**File:** `data/jb_services.json`

| Field | Type | Description |
|-------|------|-------------|
| `service_id` | string (UUID) | Primary key |
| `workspace_id` | string | Parent workspace (required) |
| `name` | string | Service name (required, non-empty) |
| `description` | string | What this service does |
| `status` | enum | `stopped`, `starting`, `running`, `error`, `paused` |
| `type` | enum | `scheduled`, `daemon`, `webhook`, `manual` |
| `schedule` | string or null | Cron schedule (for scheduled type) |
| `directory` | string | Service directory |
| `entry_point` | string | Entry point script/module |
| `has_frontend` | boolean | Whether the service has a web frontend |
| `frontend_path` | string or null | Path to frontend assets |
| `port` | int or null | Allocated port (from range starting at 9000) |
| `pid` | int or null | Process ID when running |
| `last_run` | ISO-8601 or null | Timestamp of last run |
| `last_run_status` | string or null | Status of last run |
| `last_run_duration_ms` | int or null | Duration of last run |
| `next_run` | ISO-8601 or null | Scheduled next run |
| `health` | string | `unknown`, `healthy`, etc. |
| `run_count` | int | Total runs |
| `error_count` | int | Total errors |
| `created_at` | ISO-8601 | Creation timestamp |
| `updated_at` | ISO-8601 | Last update timestamp |

**Service Run (file: `data/jb_service_runs.json`):**

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | string (UUID) | Primary key |
| `service_id` | string | Parent service |
| `started_at` | ISO-8601 | When the run started |
| `completed_at` | ISO-8601 or null | When the run finished |
| `status` | enum | `running`, `success`, `error` |
| `duration_ms` | int or null | Run duration |
| `output_preview` | string or null | First 500 chars of output |
| `error` | string or null | Error message |
| `tokens_used` | int | Tokens consumed |

### Company Mapping

**File:** `data/jb_company_mappings.json`

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Source system (e.g., `discord`) |
| `external_id` | string | External identifier (e.g., `channel:1234567890`) |
| `company_id` | string | JBCP company ID |
| `created_at` | ISO-8601 | Creation timestamp |

### Event

**File:** `logs/jbcp_events.jsonl` (append-only JSONL)

| Field | Type | Description |
|-------|------|-------------|
| `ts` | ISO-8601 | Event timestamp |
| `event_type` | string | Event type (see event types below) |
| `mission_id` | string or null | Related mission |
| `task_id` | string or null | Related task |
| `openclaw_session_id` | string or null | Related OpenClaw session |
| `parent_session_id` | string or null | Parent session |
| `subagent_session_id` | string or null | Subagent session |
| `payload` | object | Event-specific data |

**Event types emitted by the system:**
- `task_dispatched` -- task sent to OpenClaw
- `task_completed` -- task finished successfully
- `task_failed` -- task failed
- `task_running` -- task still executing (dispatch timeout)
- `task_retried` -- failed task requeued
- `task_dispatch_error` -- error during dispatch
- `task_marked_suspect` -- watchdog flagged stale task
- `external_process_stale` -- watchdog flagged stale process
- `mission_completed` -- all tasks complete
- `mission_failed` -- tasks failed beyond retry
- `mission_compacted` -- context file updated
- `mission.created` -- new mission created
- `mission.generated` -- plan items generated
- `mission.approved` -- mission approved, tasks enqueued
- `mission.cancelled` -- mission cancelled
- `mission.switched` -- focused mission changed
- `jbcp_wake_requested` -- wake request created
- `jbcp_bridge_wake_seen` -- bridge processed wake request
- `workspaces_synced` -- workspace names synced with Discord

### Wake Request

**File:** `data/jb_wake_requests.jsonl` (append-only JSONL)

| Field | Type | Description |
|-------|------|-------------|
| `ts` | ISO-8601 | Request timestamp |
| `type` | string | Always `jbcp_wake` |
| `reason` | string | Why intervention is needed |
| `task_id` | string or null | Related task |
| `mission_id` | string or null | Related mission |
| `requested_action` | string | `inspect`, `retry`, `summarize` |
| `details` | object | Context-specific details |
| `status` | enum | `pending`, `handled`, `ignored`, `error` |

---

## 5. API Endpoints

FastAPI server running on **port 8718**. Base URL: `http://localhost:8718`.

### Health and System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | System health: uptime, gateway connectivity, workspace/mission/task/agent counts, event bus status, version |
| `GET` | `/api/settings` | System settings: gateway config, JBCP paths/version, agent list |
| `GET` | `/api/agents` | Agent states derived from signals: status (coding/thinking/idle/offline), model, workspace, file, tokens, subagents |
| `GET` | `/api/live` | Running/starting services |
| `GET` | `/api/usage` | Token/cost usage (stub -- returns zeroed counters) |
| `GET` | `/api/commands` | List all slash commands with descriptions and workflow |
| `GET` | `/api/reference` | Full API documentation with request/response schemas |

### Workspaces (Companies)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/workspaces` | List all workspaces with derived stage (idle/planning/building/ready/failed/production) |
| `POST` | `/api/workspaces` | Create workspace + first mission in planning state. Body: `{prompt, name?}` |
| `PATCH` | `/api/workspaces/{id}` | Rename workspace. Body: `{name}` |
| `POST` | `/api/workspaces/sync-names` | Query Discord for real channel names and rename workspaces |
| `GET` | `/api/workspaces/{id}/missions` | List missions for workspace |
| `POST` | `/api/workspaces/{id}/missions` | Create mission in workspace. Body: `{goal}` |
| `GET` | `/api/workspaces/{id}/components` | List components for workspace |
| `GET` | `/api/workspaces/{id}/graph` | Component dependency graph (nodes + edges) |
| `GET` | `/api/workspaces/{id}/memory` | Read company + focused mission context files |
| `PATCH` | `/api/workspaces/{id}/memory` | Overwrite company context file. Body: `{content}` |
| `GET` | `/api/workspaces/{id}/prompt-debug` | Full prompt injection tree showing what JBCP sends to the LLM |
| `POST` | `/api/workspaces/{id}/promote` | Promote workspace to deployed service. Body: `{name?, type?, schedule?, entry_point?, has_frontend?}` |

### Missions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/missions/{id}/tasks` | List tasks for mission |
| `POST` | `/api/missions/{id}/generate` | Generate plan via jbcp-worker agent (blocks 10-30s) |
| `POST` | `/api/missions/{id}/approve` | Approve plan, create components, enqueue tasks |
| `POST` | `/api/missions/{id}/cancel` | Cancel mission |
| `GET` | `/api/missions/{id}/context` | Context summary for mission |

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/tasks/{id}/retry` | Retry a failed task |

### Components and Services

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/components/{id}` | Component detail |
| `GET` | `/api/services` | List all services |
| `GET` | `/api/services/{id}` | Service detail |
| `POST` | `/api/services/{id}/pause` | Pause running service |
| `POST` | `/api/services/{id}/resume` | Resume paused service |
| `POST` | `/api/services/{id}/stop` | Stop service |
| `GET` | `/api/services/{id}/runs` | Run history for service |

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Proxy chat to OpenClaw gateway. Returns SSE stream. Intercepts slash commands first. Body: `{workspace_id, mission_id?, message, history?}` |
| `GET` | `/api/workspaces/{id}/chat/history` | Fetch conversation history from OpenClaw |
| `DELETE` | `/api/workspaces/{id}/chat/history` | Clear/reset chat session |

### Streaming (SSE)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/events/stream` | Unified SSE stream: JBCP state changes + agent activity + system health keepalives (every 15s). Tails both the in-memory event bus and the signals JSONL file. |
| `GET` | `/api/signals/stream` | Raw signal SSE stream. Tails `jbcp_signals.jsonl` and emits each new line. Keepalive every 15s. |
| `POST` | `/api/signals/push` | Real-time signal push from plugin. Receives signal JSON, writes to signal file, and pushes to event bus (<50ms latency). |

### Pydantic Request Models

```python
class CreateWorkspaceRequest:
    prompt: str              # Initial goal/prompt
    name: str | None = None  # Workspace name (defaults to first 60 chars of prompt)

class PatchWorkspaceRequest:
    name: str                # New workspace name

class CreateMissionRequest:
    goal: str                # Mission goal

class ChatRequest:
    workspace_id: str        # Workspace ID
    mission_id: str | None   # Optional mission ID
    message: str             # User message
    history: list[dict] | None  # Optional conversation history

class PatchMemoryRequest:
    content: str             # Full text to write to company context file

class PromoteWorkspaceRequest:
    name: str | None = None
    description: str = ""
    type: str = "manual"     # manual, scheduled, daemon, webhook
    schedule: str | None = None
    entry_point: str = ""
    has_frontend: bool = False
```

---

## 6. Plugin -- jbcp-observer

**Location:** `~/.openclaw/plugins/jbcp-observer/index.js`
**Deployed:** `~/.openclaw/extensions/jbcp-observer/index.js`
**ID:** `jbcp-observer`

The plugin is the bridge between OpenClaw's agent runtime and JBCP's Python backend.

### Plugin Architecture

All data mutations go through the Python CLI (`python -m runtime.jb_cli`) via `execFileSync`. The plugin never writes JSON data files directly. This ensures all validation and normalization happens in one place.

```javascript
function jbcpCli(...args) {
  execFileSync(VENV_PYTHON, ["-m", "runtime.jb_cli", ...args], {
    cwd: WORKSPACE, encoding: "utf-8", timeout: 15000
  });
}
```

### Registered Commands

| Command | Description |
|---------|-------------|
| `/mission` | Mission management (new, list, generate, approve, cancel, switch, status, help) |
| `/plan` | Deprecated -- redirects to `/mission` commands |
| `/contextmem` | Show context injection stats for current channel |
| `/jbdebug` | Toggle debug settings (debug_footer, debug_signals, debug_tool_blocks) |

### Event Hooks

| Hook | Purpose |
|------|---------|
| `message_received` | Auto-creates company for channel (only `company-*` channels). Updates company name from Discord. Writes `message_received` signal. |
| `message_sending` | When `debug_footer` is ON, appends a status footer to outgoing messages showing company, mission, mode, and context sizes. |
| `before_prompt_build` | **Context injection.** Reads company context + mission context from files and appends to system prompt. If mission is in planning mode, injects the full planning prompt with architecture guidelines, blocked tool instructions, component/connection/task lists. |
| `before_tool_call` (handler 1) | **Tool blocking in planning mode.** Blocks tools `exec`, `write`, `edit`, `process`, `subagents`, `cron`, `web_fetch`, `web_search` when the focused mission is in "planning" status. Returns a `block` response with a reason explaining planning mode. |
| `before_tool_call` (handler 2) | **Signal capture.** Writes `tool_start` signal with enriched metadata: derives `source` (bash/http/web/browser/subprocess/claude-code) and `label` (human-readable description like "write: parser.py" or "python: pytest tests/"). |
| `after_tool_call` | Writes `tool_end` signal with success/error, duration, result preview (first 500 chars). |
| `session_start` | Writes `session_start` signal. |
| `session_end` | Writes `session_end` signal with message count and duration. |
| `agent_end` | Writes `agent_turn` signal with model, trigger, success, duration. |
| `llm_input` | Writes `llm_input` signal with model, provider, prompt size, history count. |
| `llm_output` | Writes `llm_output` signal with model, text preview, text size, token usage. |
| `subagent_spawned` | Writes `subagent_spawned` signal. |
| `subagent_ended` | Writes `subagent_ended` signal with outcome. |

### Channel Filtering

Currently limited to Discord channels prefixed with `company-` (controlled by `JBCP_CHANNEL_PREFIX`). The `shouldProcessChannel()` function:
1. Always processes already-mapped channels
2. For unmapped channels, queries Discord API for the channel name
3. Only proceeds if the name starts with `company-`

### Context Injection Detail

The `before_prompt_build` hook:
1. Extracts conversation ID from session key (format: `agent:main:{source}:{channel|company}:{id}`)
2. Resolves company via direct ID lookup or mapping table
3. Reads `company_context.md` (skips files that are headers-only)
4. Reads `mission_context.md` for the focused mission
5. Builds injection block: `--- JBCP Context Injection ---` + company context + mission context + `--- End JBCP Context ---`
6. If mission is in planning state, appends a planning mode block with:
   - Role instructions (solution architect, no code)
   - Current architecture (components, connections)
   - Current tasks
   - Tool blocking notice

---

## 7. Web Dashboard

### Web UI (Primary)

**Location:** `~/.openclaw/workspace/webui/`
**URL:** `http://localhost:8718/` (served by FastAPI)
**Stack:** Vanilla HTML/CSS/JS (no build step)

5 pages:
- **Workspaces** -- list all workspaces with stage badges, mission counts
- **Workspace Detail** -- missions, components, tasks, chat with SSE streaming
- **Activity Feed** -- real-time event/signal stream with color-coded entries
- **Agents** -- live agent states (coding/thinking/idle/offline) with token usage
- **Debug** -- prompt injection tree, signal inspector, system health

Chat features:
- SSE streaming from OpenClaw gateway (proxied through API)
- Command autocomplete: typing `/` shows command palette from `GET /api/commands`
- Typing indicator driven by real-time signals (`llm_input`, `tool_start`)
- SSE drop recovery: when gateway drops connection during tool use, signals keep typing indicator alive, `agent_turn` signal triggers chat history fetch to recover missed content
- 15-second targeted refresh (updates status badges and counts without rebuilding chat or component graph)

### Legacy Dashboard (React + Express)

**Location:** `~/.openclaw/workspace/dashboard/`
**Port:** 3456 (Express server)
**Stack:** React (Vite) + Express + TypeScript

### Architecture

```
dashboard/
  package.json              # Monorepo with workspaces: server, client
  client/                   # React SPA (Vite)
    src/
      App.tsx               # Main layout: StatusBar + Sidebar + MainArea + EventTimeline
      api/hooks.ts          # usePolling() hook for data fetching
      components/
        Sidebar.tsx         # Tree navigation: workspaces -> missions -> tasks
        MainArea.tsx        # Detail panel router
        StatusBar.tsx       # Top bar: health, tasks, OpenClaw status
        detail/
          OverviewPanel.tsx  # System overview with counts and status
          CompanyDetail.tsx  # Workspace detail view
          MissionDetail.tsx  # Mission detail with items/components
          TaskDetail.tsx     # Task detail with status, error, sessions
          PlanDetail.tsx     # Plan detail (legacy)
        openclaw/
          OpenClawPanel.tsx  # OpenClaw gateway status and config
        timeline/
          EventTimeline.tsx  # Real-time event feed
  server/                   # Express BFF (Backend-for-Frontend)
    src/
      index.ts              # Express app with CORS, routes, static serving
      config.ts             # Paths to all data files, ports
      jbcp/
        routes.ts           # JBCP data endpoints (read JSON files directly)
        file-reader.ts      # JSON/JSONL file readers, hierarchy builder
      openclaw/
        routes.ts           # OpenClaw proxy endpoints
        ws-client.ts        # WebSocket client to OpenClaw gateway
```

### Dashboard Server Endpoints

| Path | Description |
|------|-------------|
| `GET /api/jbcp/companies` | List companies |
| `GET /api/jbcp/companies/:id` | Company detail with context |
| `GET /api/jbcp/missions` | List missions |
| `GET /api/jbcp/missions/:id` | Mission detail with context |
| `GET /api/jbcp/plans` | List plans |
| `GET /api/jbcp/tasks` | List tasks |
| `GET /api/jbcp/tasks/:id` | Task detail |
| `GET /api/jbcp/events?limit=N` | Recent events |
| `GET /api/jbcp/signals?limit=N` | Recent signals |
| `GET /api/jbcp/wake-requests` | Wake requests |
| `GET /api/jbcp/mappings` | Company mappings |
| `GET /api/jbcp/hierarchy` | Full company -> mission -> task tree |
| `GET /api/jbcp/stats` | File-level statistics |
| `PATCH /api/jbcp/tasks/:id/cancel` | Cancel a pending/suspect task |
| `PATCH /api/jbcp/tasks/:id/ignore` | Ignore a non-running task |
| `DELETE /api/jbcp/tasks/clear?statuses=complete` | Archive and remove completed tasks |
| `GET /api/openclaw/status` | OpenClaw gateway status |
| `GET /api/health` | Dashboard health check |

### UI Components

- **StatusBar:** Shows system health, active task count, OpenClaw connectivity
- **Sidebar:** Hierarchical tree of workspaces -> missions -> tasks. Expandable nodes with status icons. Refresh button. OpenClaw section link.
- **MainArea:** Routes to detail panels based on selection type
- **OverviewPanel:** System-wide overview with workspace count, mission count, task breakdown by status, recent events
- **CompanyDetail:** Workspace info, missions list, task summary, context file preview
- **MissionDetail:** Goal, status, plan items, components, connections, linked tasks
- **TaskDetail:** Full task info, status history, error messages, OpenClaw session links, retry button
- **PlanDetail:** Plan items with status, component references (legacy)
- **OpenClawPanel:** Gateway connection status, agent list, configuration
- **EventTimeline:** Scrolling feed of recent events and signals

---

## 8. Signal System

Signals are the real-time telemetry stream from the OpenClaw plugin to JBCP. Written to `data/signals/jbcp_signals.jsonl` as JSONL (one JSON object per line). Signals arrive via two paths: (1) file write by the plugin, tailed by the API server, and (2) HTTP push via `POST /api/signals/push` for <50ms latency delivery to the event bus and connected SSE clients.

### Signal Types

| Signal | Trigger | Key Fields |
|--------|---------|------------|
| `message_received` | User sends a message | `channel`, `conversation_id`, `from` |
| `session_start` | Agent session begins | `session_id`, `session_key`, `agent_id`, `trigger` |
| `session_end` | Agent session ends | `session_id`, `session_key`, `agent_id`, `message_count`, `duration_ms` |
| `agent_turn` | Agent completes a turn | `session_id`, `session_key`, `agent_id`, `model`, `trigger`, `success`, `error`, `duration_ms` |
| `llm_input` | Request sent to LLM | `session_id`, `agent_id`, `run_id`, `model`, `provider`, `prompt_chars`, `history_count`, `images_count` |
| `llm_output` | LLM response received | `session_id`, `agent_id`, `run_id`, `model`, `provider`, `text_preview`, `text_chars`, `usage` |
| `tool_start` | Tool call begins | `session_id`, `agent_id`, `run_id`, `tool`, `source`, `label`, `params` |
| `tool_end` | Tool call completes | `session_id`, `agent_id`, `run_id`, `tool`, `ok`, `error`, `duration_ms`, `result_preview`, `result_chars` |
| `subagent_spawned` | Subagent created | `child_session_key`, `agent_id`, `label`, `mode`, `run_id` |
| `subagent_ended` | Subagent finished | `target_session_key`, `target_kind`, `reason`, `outcome`, `error`, `run_id` |

All signals carry a `ts` (ISO-8601 timestamp) field added by the `writeSignal()` function.

### Signal-Derived State

The `jb_agent_state.py` module processes signals to derive:

- **Agent status:** `coding` (write/edit/exec within 60s), `thinking` (llm_input/agent_turn within 60s), `idle` (>60s, <300s), `offline` (>300s)
- **Source classification:** `bash`, `http`, `web`, `browser`, `subprocess`, `claude-code`, `llm`
- **Activity label:** Human-readable like "write: parser.py", "python: pytest tests/", "thinking (claude-opus-4-6)"
- **Token usage:** Aggregated from `llm_output` signals per agent
- **Subagent tracking:** Parent-child relationships from spawn/end signals
- **Workspace attribution:** Extracted from session keys via company mapping

### Signal Rotation

Daily rotation managed by `jb_signal_rotate.py`:
- Renames `jbcp_signals.jsonl` to `jbcp_signals.YYYY-MM-DD.jsonl`
- Creates fresh empty file
- Deletes rotated files older than 7 days (configurable)
- Called automatically by the orchestrator at the start of each run

---

## 9. Mission Lifecycle

### State Machine

```
                    +----------+
                    |  draft   |  (legacy/initial)
                    +----+-----+
                         |
                    +----v-----+
           +------->| planning |<------+
           |        +----+-----+       |
           |             |             |
           |     /mission generate     |
           |             |             |
           |        +----v-----+       |
           |        | planned  |  reopen_planning()
           |        +----+-----+-------+
           |             |
           |     /mission approve
           |             |
           |        +----v-----+
           |        |  active  |
           |        +--+--+--+-+
           |           |  |  |
           |   all     |  |  |  any failed
           |  complete |  |  |  (retries
           |           |  |  |   exhausted)
           |     +-----+  |  +------+
           |     |         |         |
           | +---v---+ +---v---+ +---v----+
           | |complete| |blocked| | failed |
           | +--------+ +---+---+ +--------+
           |                 |
           |                 | (unblock)
           |                 v
           +---------+  active
                     |
                +----v------+
                | cancelled |
                +-----------+
```

### Workflow Steps

1. **Create Mission:** `POST /api/workspaces/{id}/missions` or `/mission new <goal>`. Creates mission in `planning` status. Sets as focused mission.

2. **Planning Phase:** User chats with Santiago about requirements. Tools are blocked. Plugin injects planning prompt.

3. **Generate Plan:** `/mission generate` or `POST /api/missions/{id}/generate`.
   - Fetches chat history from OpenClaw gateway
   - Builds a structured prompt asking for components, connections, and tasks
   - Dispatches to jbcp-worker agent
   - Parses JSON response (handles markdown fences, nested objects)
   - Normalizes items and saves to mission
   - Can be run multiple times to refine

4. **Review:** User reviews generated plan. Can chat more and regenerate.

5. **Approve Mission:** `/mission approve` or `POST /api/missions/{id}/approve`.
   - Creates Component records in `jb_components.json`
   - Creates Connection records in `jb_connections.json`
   - Enqueues Task records with dependency-adjusted priorities
   - Links tasks to components
   - Transitions mission to `active`

6. **Execution:** Orchestrator dispatches tasks to OpenClaw agents.

7. **Monitoring:** Orchestrator reconciles running tasks, retries failures.

8. **Compaction:** After tasks complete, updates `mission_context.md`.

9. **Completion:** When all tasks reach terminal states:
   - All complete -> mission `complete`
   - Any failed (retries exhausted) -> mission `failed`

10. **Promotion (optional):** `POST /api/workspaces/{id}/promote` creates a Service record for production deployment.

---

## 10. Configuration

### OpenClaw Configuration

**File:** `~/.openclaw/openclaw.json`

Used by the API server and plugin for:
- Gateway URL and auth token
- Discord bot token (for channel name resolution)
- Agent list and default model

```json
{
  "gateway": {
    "port": 18789,
    "auth": {
      "token": "<gateway-auth-token>"
    }
  },
  "channels": {
    "discord": {
      "token": "<discord-bot-token>"
    }
  },
  "agents": {
    "list": [
      {"id": "main", "name": "Santiago"},
      {"id": "jbcp-worker", "name": "JBCP Worker"}
    ],
    "defaults": {
      "model": {
        "primary": "claude-sonnet-4-6"
      }
    }
  }
}
```

### JBCP Settings

**File:** `data/jbcp_settings.json`

Debug toggles managed by `/jbdebug` command:
```json
{
  "debug_footer": false,
  "debug_signals": false,
  "debug_tool_blocks": false
}
```

### Plugin Configuration

**File:** `~/.openclaw/plugins/jbcp-observer/openclaw.plugin.json`

Standard OpenClaw plugin manifest:
```json
{
  "id": "jbcp-observer",
  "name": "JBCP Observer",
  "description": "JBCP control plane: signals, context, /mission, /plan commands",
  "version": "1.0.0"
}
```

### Key Constants

| Constant | Value | Location |
|----------|-------|----------|
| API Port | 8718 | `jb_api.py` |
| Dashboard Port | 3456 | `dashboard/server/src/config.ts` |
| Gateway URL | `http://10.0.0.137:18789` | `jb_api.py` |
| Gateway WS | `ws://127.0.0.1:18789` | `dashboard/server/src/config.ts` |
| Service Port Range | 9000+ | `jb_services.py` |
| Default Agent | `jbcp-worker` | `jb_openclaw_bridge.py` |
| Dispatch Timeout | 600s | `jb_openclaw_bridge.py` |
| Stale Task Threshold | 300s | `jb_watchdog.py` |
| Stale Process Threshold | 180s | `jb_watchdog.py` |
| Signal Keep Days | 7 | `jb_signal_rotate.py` |
| Channel Prefix | `company-` | Plugin `JBCP_CHANNEL_PREFIX` |

---

## 11. Testing

### Test Files

| File | Lines | Coverage |
|------|-------|----------|
| `test_queue.py` | 242 | Task CRUD, status transitions, retries, session attachment, external process |
| `test_missions.py` | 150 | Mission CRUD, item management, planning workflow |
| `test_companies.py` | 435 | Company CRUD, mission attachment, focused mission, context paths |
| `test_components.py` | 416 | Component CRUD, connections, graph generation, lifecycle |
| `test_services.py` | 403 | Service CRUD, lifecycle, port allocation, run tracking |
| `test_events.py` | 72 | Event emission and filtering |
| `test_signals.py` | 80 | Signal reading, active session derivation |
| `test_wake.py` | 114 | Wake request creation, filtering, task-based wakes |
| `test_watchdog.py` | 103 | Stale task detection, suspect marking |
| `test_enqueue.py` | 50 | Task creation via build_task() |
| `test_bridge.py` | 210 | Task prompt building, context summary, agent resolution |
| `test_context_injection.py` | 210 | Context file reading, injection block assembly |
| `test_orchestrator.py` | 155 | Dispatch, reconcile, retry, lifecycle phases |
| `test_retry.py` | 97 | Retry logic, retry count, max retries |
| `test_lifecycle.py` | 131 | Mission auto-completion, failure detection |
| `test_agent_state.py` | 107 | Agent state derivation, status classification |
| `test_api_flow.py` | 555 | Full API endpoint testing |
| `test_end_to_end.py` | 256 | End-to-end flows: workspace -> mission -> approve -> tasks |
| `conftest.py` | -- | Shared fixtures, temp data directories |
| **Total** | **~3800** | **358 unit + 33 integration = 391 tests** |

### Running Tests

```bash
# Setup
cd ~/.openclaw/workspace
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_queue.py -v

# Run with coverage
python -m pytest tests/ --cov=runtime --cov-report=term-missing

# Quick run (quiet output)
python -m pytest tests/ -q
```

### Test Architecture

Tests use temporary data directories created by `conftest.py` fixtures. Each test gets isolated JSON files, preventing cross-test contamination. External dependencies (OpenClaw gateway, Discord API) are mocked.

---

## 12. File Locations

### Workspace Root

| Path | Description |
|------|-------------|
| `~/.openclaw/workspace/` | Workspace root (`BASE_DIR`) |
| `~/.openclaw/workspace/runtime/` | All Python runtime modules |
| `~/.openclaw/workspace/data/` | JSON persistence (`DATA_DIR`) |
| `~/.openclaw/workspace/logs/` | Orchestrator logs, event JSONL (`LOG_DIR`) |
| `~/.openclaw/workspace/tests/` | Test suite |
| `~/.openclaw/workspace/webui/` | Web UI dashboard (vanilla HTML/CSS/JS, served by FastAPI) |
| `~/.openclaw/workspace/dashboard/` | Legacy web dashboard (React + Express) |
| `~/.openclaw/workspace/workers/` | Worker agent configurations |
| `~/.openclaw/workspace/memory/` | Daily memory files |
| `~/.openclaw/workspace/docs/` | Documentation |

### Data Files

| Path | Description |
|------|-------------|
| `data/jb_companies.json` | Company records |
| `data/jb_missions.json` | Mission records |
| `data/jb_queue.json` | Task queue |
| `data/jb_queue_archive.json` | Archived tasks (from dashboard clear) |
| `data/jb_components.json` | Component records |
| `data/jb_connections.json` | Connection records |
| `data/jb_services.json` | Service records |
| `data/jb_service_runs.json` | Service run history |
| `data/jb_company_mappings.json` | External ID -> company mappings |
| ~~data/jb_plans.json~~ | **REMOVED** -- plan data now embedded in missions |
| `data/jb_wake_requests.jsonl` | Wake request log (JSONL) |
| `data/jbcp_settings.json` | Debug settings |
| `data/signals/jbcp_signals.jsonl` | Current signal file (written by plugin) |
| `data/signals/jbcp_signals.YYYY-MM-DD.jsonl` | Rotated signal files |
| `data/companies/{id}/company_context.md` | Company-level persistent context |
| `data/companies/{id}/missions/{mid}/mission_context.md` | Mission-level persistent context |

### Log Files

| Path | Description |
|------|-------------|
| `logs/orchestrator.log` | Orchestrator run log |
| `logs/jbcp_events.jsonl` | System event log (JSONL) |

### Plugin Files

| Path | Description |
|------|-------------|
| `~/.openclaw/plugins/jbcp-observer/index.js` | Plugin source |
| `~/.openclaw/plugins/jbcp-observer/openclaw.plugin.json` | Plugin manifest |
| `~/.openclaw/plugins/jbcp-observer/package.json` | Plugin package |
| `~/.openclaw/extensions/jbcp-observer/index.js` | Deployed plugin |

### Configuration Files

| Path | Description |
|------|-------------|
| `~/.openclaw/openclaw.json` | OpenClaw gateway and agent configuration |
| `~/.openclaw/workspace/requirements.txt` | Python dependencies |
| `~/.openclaw/workspace/CLAUDE.md` | AI agent instructions |

### Identity Files (Agent Personality)

| Path | Description |
|------|-------------|
| `~/.openclaw/workspace/SOUL.md` | Agent personality definition |
| `~/.openclaw/workspace/IDENTITY.md` | Agent identity |
| `~/.openclaw/workspace/USER.md` | User profile |
| `~/.openclaw/workspace/MEMORY.md` | Curated long-term memory index |
| `~/.openclaw/workspace/TOOLS.md` | Available tools reference |

---

## How to Run Everything

```bash
# Activate the virtual environment
cd ~/.openclaw/workspace
source .venv/bin/activate

# Start the API server (port 8718)
python -m runtime.jb_api

# Start the web dashboard (port 3456)
cd dashboard && npm start

# Run the orchestrator (single pass)
python -m runtime.jb_orchestrator --once

# Run the orchestrator (continuous, 60s interval)
python -m runtime.jb_orchestrator --interval 60

# Quick status check
python -m runtime.jb_status

# TUI dashboard
python -m runtime.jb_dashboard

# Run compaction sweep
python -m runtime.jb_compaction --sweep

# Check lifecycle only
python -m runtime.jb_compaction --sweep --lifecycle-only

# Run watchdog
python -m runtime.jb_watchdog --apply --emit-wakes

# Rotate signals
python -m runtime.jb_signal_rotate

# Validate queue integrity
python -m runtime.jb_validate_queue

# View agent states
python -m runtime.jb_agent_state

# Enqueue a task manually
python -m runtime.jb_enqueue --type coding --goal "Build the parser"

# Run tests
python -m pytest tests/ -v
```
