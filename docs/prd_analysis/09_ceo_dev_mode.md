# PRD Analysis: CEO Mode vs Developer Mode

**PRD Section:** Design Philosophy (lines ~558-644 of APP_UX_PRD_FINAL_v0.1.md)
**Analyst:** Backend Claude
**Date:** 2026-03-31

---

## 1. Summary of PRD Requirements

The PRD defines two presentation layers over the same backend data:

**CEO Mode (default):** Human-language descriptions, simple progress (3 of 5 components built), health dots (green/red), chat-first interface, graph-centric view. Hides agent names, models, tokens, PIDs, session IDs.

**Developer/Debug Mode (on demand):** Agent names, models, token counts, file trees, code views, signal timeline with raw events, subprocess info, PIDs, context injection tree, session/task IDs.

The PRD also provides a language translation table mapping developer terms to user terms (e.g., "Santiago CODING claude-opus-4-6" becomes "Your AI is building the Email Parser").

---

## 2. API Strategy: How to Support Both Modes

### Recommendation: Query parameter `?detail=ceo|full` on existing endpoints

Adding separate endpoints (e.g., `/api/agents/ceo` and `/api/agents/dev`) would double the surface area for no real gain. A response-filtering approach is better:

- All endpoints return the **CEO (simplified)** response by default -- CEO mode is the product, not an afterthought.
- Add `?detail=full` query parameter to key endpoints to get the developer/debug view.
- The frontend stores a "Developer Mode" toggle (UserDefaults/localStorage) and passes `?detail=full` when enabled.
- A few endpoints are CEO-only (new) or dev-only (existing, no transformation needed).

### Why not server-side filtering everywhere?

Some transformations are better done on the frontend (hiding/showing fields in the same response). But the key CEO transformations -- turning raw signal events into human-readable activity descriptions -- require semantic understanding that belongs on the backend. The backend has task context, component names, and mission goals needed to produce "Building the Email Parser" from "tool_start: write email_parser.py".

### Endpoints that need CEO/full mode support

| Endpoint | CEO transformation needed |
|----------|--------------------------|
| `GET /api/agents` | Replace agent details with human-readable status; hide model, tokens, sessions, PIDs |
| `GET /api/events/stream` | Transform signal events into human-language activity feed entries |
| `GET /api/workspaces/{id}/tasks` (via missions) | Replace task details with component-level progress summaries |
| `GET /api/workspaces` | Already mostly CEO-friendly (stage, counts). Minor: add `progress_summary` field |
| `GET /api/health` | Already fine for CEO mode -- just needs simpler language in frontend |

### Endpoints that are dev-only (no CEO transformation)

| Endpoint | Why dev-only |
|----------|-------------|
| `GET /api/signals/query` | Raw signal data -- only useful in debug mode |
| `GET /api/signals/stream` | Raw signal stream -- debug mode only |
| `GET /api/workspaces/{id}/prompt-debug` | Context injection tree -- explicitly debug |
| `GET /api/settings` | System config -- dev mode |
| `GET /api/usage` | Token/cost data -- dev mode (stub today) |

---

## 3. CEO-Friendly Data Transformations

These are the core backend transformations needed to turn raw data into CEO-language.

### 3.1 Activity Feed Translation (signal -> human text)

The plugin already emits `label` and `source` fields on `tool_start` signals (added 2026-03-30). The `jb_agent_state.py` already tracks `current_label` and `current_source` per agent. This is the foundation.

**What exists:**
- `tool_start` signals have `label` (e.g., "Writing email_parser.py") and `source` (e.g., "bash", "claude-code")
- `jb_agent_state.py` stores `current_label` per agent
- Agent state already has `_agent_display_name()` mapping ("main" -> "Santiago")

**What's missing -- new translation layer needed:**

| Raw Signal | CEO Translation | Data Needed |
|------------|----------------|-------------|
| `tool_start: write email_parser.py` | "Writing the email parsing logic" | Component name from task -> component mapping |
| `llm_input` with model | "Thinking about next steps" | Nothing extra |
| `tool_start: exec pytest` | "Running tests" | Recognize test commands |
| `tool_start: read config.json` | "Reviewing configuration" | Recognize read patterns |
| `subagent_spawned` | "Starting a new worker" | Nothing extra |
| `tool_end` with error | "Hit an issue, retrying" | Error detection |
| Task status = complete | "Finished building [Component Name]" | Task -> component lookup |
| Task status = failed | "[Component Name] needs attention" | Task -> component lookup |

**New module needed: `jb_ceo_translator.py`**

This module takes raw events/signals and produces CEO-friendly text by:
1. Looking up the task associated with the signal's session
2. Looking up the component associated with the task
3. Applying pattern-matching rules to tool names and parameters
4. Returning a human-readable string and a severity/category

### 3.2 Progress Summarization

**What exists:**
- `_compute_stage()` in `jb_api.py` derives workspace stage (idle/planning/building/ready/failed/production)
- Task counts per workspace (active, complete, total)
- Component counts per workspace

**What's missing:**
- Per-mission progress: "3 of 5 components built" -- need to count components by status
- Estimated completion: "almost done" vs "just started" -- can derive from component status ratios
- Time-based: "started 12 minutes ago" -- tasks have timestamps

**New field on workspace/mission responses (CEO mode default, always included):**

```json
{
  "progress": {
    "summary": "3 of 5 components built",
    "percent": 60,
    "phase": "building",
    "started_ago": "12 minutes ago",
    "current_activity": "Writing the email parsing logic"
  }
}
```

### 3.3 Health Dots

**What exists:**
- Service status (running/paused/stopped)
- Task status (complete/failed/running)
- Agent status (coding/thinking/idle/offline)
- `_compute_stage()` gives workspace-level stage

**What's missing:**
- Unified health dot per workspace/mission: green/yellow/red/gray
- Rules:
  - **Green:** all tasks complete OR service running healthy
  - **Yellow:** tasks in progress (building), or service starting
  - **Red:** any task failed, service unhealthy, agent offline during active work
  - **Gray:** idle, no active work

**New field:** `health: "green" | "yellow" | "red" | "gray"` on workspace and mission responses.

---

## 4. Developer/Debug Mode: What Exists vs What's New

### Already exists (dev mode data sources)

| Feature | Current Endpoint | Status |
|---------|-----------------|--------|
| Agent names + models | `GET /api/agents` -> `current_model`, `agent_id` | Working |
| Token counts (per agent session) | `GET /api/agents` -> `total_tokens_used` | Working |
| Signal timeline | `GET /api/signals/query` + `GET /api/signals/stream` | Working |
| Session IDs, task IDs | `GET /api/agents` -> `sessions`, `linked_tasks` | Working |
| Subagent tree | `GET /api/agents` -> `subagents` list | Working |
| Context injection tree | `GET /api/workspaces/{id}/prompt-debug` | Working |
| Tools used per agent | `GET /api/agents` -> `tools_used` list | Working |
| Task details (goal, status, retries) | `GET /api/missions/{id}/tasks` | Working |

### Missing for dev mode

| Feature | What's needed | Priority |
|---------|--------------|----------|
| **File trees** | List files created/modified by a task/agent session. Signals have file paths in `tool_start` params but no aggregation endpoint. | v1 |
| **Code views** | Read file contents for components. Need `GET /api/components/{id}/files` that reads from workspace directory. | v2 |
| **PID/subprocess info** | Signals contain some subprocess data via `subagent_spawned`. No explicit PID tracking. OpenClaw manages processes. | v2 (low value) |
| **Token/cost tracking** | `GET /api/usage` is a stub returning zeros. Need to aggregate from `llm_output` signals. | v1 |
| **Per-task signal timeline** | Filter signals by task. Need session_id -> task_id mapping (exists in reactor) exposed as `GET /api/tasks/{id}/signals`. | v1 |

---

## 5. Technical Mapping Verification

The PRD provides a mapping table (lines 628-643). Verifying each against current API:

| PRD Mapping | Current Endpoint | Status | Gap |
|-------------|-----------------|--------|-----|
| Create a Company -> `POST /api/workspaces` | `POST /api/workspaces` | **WORKS** | None |
| Create a Mission -> `POST /api/workspaces/{id}/missions` | `POST /api/workspaces/{id}/missions` | **WORKS** | None |
| Chat (planning) -> `POST /api/chat` | `POST /api/chat` with workspace_id, session_key, context injection | **WORKS** | None |
| Generate Spec -> `/mission generate` | `POST /api/missions/{id}/generate` | **WORKS** | Also available as `/mission generate` slash command in chat |
| Build It -> `/mission approve` | `POST /api/missions/{id}/approve` | **WORKS** | Also available as `/mission approve` slash command |
| Component progress -> `GET /api/workspaces/{id}/tasks` + signals | Tasks via `GET /api/missions/{id}/tasks`, signals via SSE stream | **PARTIAL** | No `GET /api/workspaces/{id}/tasks` endpoint -- tasks are accessed per-mission. Need workspace-level task aggregation or keep per-mission. |
| Go Live -> `POST /api/services` | `POST /api/workspaces/{id}/promote` | **WORKS** | Endpoint path differs from PRD (`/promote` vs `/services`), but functionally equivalent |
| Health/status -> `GET /api/services/{id}` + signals | `GET /api/services/{id}` exists. Signal-derived health not integrated into service response. | **PARTIAL** | Service health is static (from service record). Need signal-derived health enrichment. |
| Component graph -> `GET /api/workspaces/{id}/graph` | `GET /api/workspaces/{id}/graph` | **WORKS** | Graph is workspace-level, not mission-filtered. PRD says "filtered by mission components" -- need `?mission_id=X` param. |
| Agent decisions -> decision log in task result | Task result stored on completion. No dedicated "decisions" view. | **GAP** | Need to capture agent reasoning/decisions during execution and expose via `GET /api/tasks/{id}/decisions` or include in task response. |

### Gaps Summary

1. **Workspace-level tasks endpoint** -- `GET /api/workspaces/{id}/tasks` is missing. Tasks are accessed per-mission via `GET /api/missions/{id}/tasks`. Add a workspace-level convenience endpoint.
2. **Mission-filtered graph** -- `GET /api/workspaces/{id}/graph?mission_id=X` param needed.
3. **Signal-derived service health** -- Service response should include health from recent signals (last heartbeat, error rate).
4. **Agent decision log** -- Tasks need a `decisions` field or separate endpoint showing what the AI decided and why during execution.
5. **Service report endpoint** -- PRD specifies `POST /api/services/{id}/report` for the summary chain from agent runs (e.g., "checked 47 emails, sent 3 alerts"). Does not exist. Required for the dashboard's running services display.
6. **SSE mission_id filter** -- PRD explicitly calls out `GET /api/events/stream?mission_id=X` for mission-scoped streaming. Current SSE stream has no filter parameter. The reactor already does session-to-mission lookup, so adding the filter is straightforward. This is separate from the `?detail` param.

---

## 6. Concrete Coding Tasks

### v1 Tasks (needed for MVP)

#### T1: CEO Translation Module (`runtime/jb_ceo_translator.py`)
- New module with `translate_signal(signal, context) -> CeoActivity` function
- Looks up signal's session -> task -> component chain
- Maps tool operations to human-readable strings
- Pattern library: write -> "Writing...", exec pytest -> "Running tests", read -> "Reviewing...", llm_input -> "Thinking..."
- Returns: `{"text": "Building the Email Parser", "category": "building", "component_name": "Email Parser", "icon": "hammer"}`
- **Estimate:** ~150 lines, moderate complexity (needs task/component lookups)

#### T2: `?detail=ceo|full` Query Parameter on Key Endpoints
- Add optional `detail` query param (default `ceo`) to `GET /api/agents`, `GET /api/workspaces`, `GET /api/workspaces/{id}/missions`
- Default (`detail=ceo`):
  - `/api/agents`: return simplified agent list -- `[{"status": "building", "activity": "Writing the email parsing logic", "workspace_name": "Email Bot"}]` -- hide model, tokens, sessions, subagents, tools
  - `/api/workspaces`: add `progress`, `health`, `current_activity` fields
  - `/api/workspaces/{id}/missions`: add `progress` summary, hide task IDs
- When `detail=full`: return everything as endpoints do today (backward compatible for dev tools)
- **Estimate:** ~100 lines of response transformation logic in `jb_api.py`

#### T3: CEO-Mode Event Stream Transformation
- Modify `GET /api/events/stream` to accept `?detail=ceo|full` (default `ceo`)
- When CEO mode (default): pass each signal through `jb_ceo_translator.translate_signal()` before emitting
- Only emit user-relevant events: skip raw `llm_input`, `llm_output`, `before_model_resolve`, etc.
- Emit simplified events: `{"type": "activity", "text": "Writing the email parsing logic", "component": "Email Parser", "timestamp": "..."}`
- **Estimate:** ~50 lines in event stream handler

#### T4: Workspace-Level Tasks Endpoint
- Add `GET /api/workspaces/{id}/tasks` that returns all tasks across all missions in the workspace
- Optional `?status=running` filter
- **Estimate:** ~20 lines

#### T5: Mission-Filtered Graph
- Add `?mission_id=X` query param to `GET /api/workspaces/{id}/graph`
- Filter nodes/edges to only those components belonging to the specified mission
- **Estimate:** ~15 lines

#### T6: Health Dot Computation
- Add `_compute_health(workspace_id) -> "green" | "yellow" | "red" | "gray"` helper
- Include in workspace response as `health` field
- Rules: green = all done or running; yellow = building; red = failed; gray = idle
- **Estimate:** ~30 lines

#### T7: Usage Endpoint (De-stub)
- Replace `GET /api/usage` stub with real token aggregation from `llm_output` signals in the database
- Aggregate by model, agent, workspace
- **Estimate:** ~60 lines

#### T7b: Service Report Endpoint (`POST /api/services/{id}/report`)
- Accepts `{ summary_chain: string[], final_summary: string, run_metrics: {} }`
- Stores on the service record and latest run record
- `GET /api/services/{id}` returns `last_report` field in response
- Enables dashboard display: "Gmail Checker -- checked 47 emails, sent 3 alerts"
- Also add `summary` as required field on base component output contract in `jb_components.py`
- **Estimate:** ~50 lines in `jb_api.py` + `jb_services.py`

#### T7c: SSE Mission Filter (`GET /api/events/stream?mission_id=X`)
- Add `mission_id` query parameter to the SSE stream endpoint
- When set, filter events: lookup signal.session_id -> task (via openclaw_session_id) -> task.mission_id
- Only emit events matching the filter (plus keepalives)
- Unfiltered stream remains the default for dashboard view
- **Estimate:** ~30 lines in the `events_stream` handler

### v2 Tasks (post-MVP)

#### T8: Per-Task Signal Timeline
- `GET /api/tasks/{id}/signals` -- filter signals by the task's `openclaw_session_id`
- Include CEO-translated versions by default; raw data when `?detail=full`
- **Estimate:** ~40 lines

#### T9: Agent File Tree
- `GET /api/agents/{id}/files` or `GET /api/tasks/{id}/files`
- Aggregate file paths from `tool_start` signals (write, edit, read operations)
- Group by directory, sort by recency
- **Estimate:** ~60 lines

#### T10: Decision Log
- Capture agent "decisions" during task execution (from compaction summaries, tool choices, or explicit decision signals)
- `GET /api/tasks/{id}/decisions` endpoint
- **Estimate:** ~80 lines (requires signal/compaction integration)

#### T11: Code View
- `GET /api/components/{id}/files` -- list files associated with a component
- `GET /api/files?path=X` -- read file contents (with safety restrictions)
- **Estimate:** ~50 lines

#### T12: Service Health from Signals
- Enrich `GET /api/services/{id}` with signal-derived health data
- Last heartbeat, error count in last hour, uptime duration
- **Estimate:** ~40 lines

---

## 7. Architecture Decision: Where Does Mode Live?

The UI toggle for CEO vs Dev mode is a **frontend concern**. The backend should not store user preferences about which mode to show. The frontend:

1. Stores the mode preference locally (UserDefaults on macOS, localStorage on web)
2. Passes `?detail=full` on API requests when Developer Mode is on (omits for CEO default)
3. Additionally hides/shows UI elements client-side (IDs, raw data panels, etc.)

The backend's job is to provide two levels of response richness. The frontend decides which to request and how to render it.

---

## 8. v1 vs v2 Boundary

**v1 (MVP -- web UI):**
- T1 (CEO translator), T2 (query param), T3 (CEO event stream), T4 (workspace tasks), T5 (mission graph filter), T6 (health dots), T7 (usage de-stub), T7b (service report), T7c (SSE mission filter)
- Frontend can ship with a toggle that switches between CEO and dev views
- CEO mode is the default; dev mode shows the full data via `?detail=full`

**v2 (native app):**
- T8-T12 (per-task signals, file trees, decision logs, code views, service health)
- These are inspector/slideout panel features that benefit from native app polish
- The API endpoints should exist before the native app ships, but are not needed for web UI MVP

---

## 9. Risk Assessment

**Low risk:**
- T4, T5, T6 are trivial additions to existing endpoints
- Health dots are simple state derivation from data that already exists

**Medium risk:**
- T1 (CEO translator) needs careful design. The quality of human-readable text is the entire CEO mode experience. Bad translations ("Executing subprocess bash -c pytest tests/") destroy the illusion. Needs a curated pattern library and fallback ("Working on [Component Name]").
- T3 (CEO event stream) must handle the case where a signal has no task/component association (e.g., main agent activity not tied to a specific build task). Fallback: "AI is active" or suppress the event.

**High risk:**
- T7 (usage de-stub) depends on signal data quality. If `llm_output` signals don't consistently include token usage, the numbers will be wrong. Need to audit signal completeness first.
- T10 (decision log) is conceptually undefined. What counts as a "decision"? This needs product thinking before engineering.

---

## 10. Dependencies

- T2 and T3 depend on T1 (CEO translator must exist before endpoints can use it)
- T6 depends on nothing -- standalone helper
- T4 and T5 are independent
- T7 depends on signal database having `llm_output` records with usage data
- T7b (service report) is independent -- new endpoint + schema change
- T7c (SSE mission filter) is independent -- modification to existing stream handler
- All v2 tasks are independent of each other
