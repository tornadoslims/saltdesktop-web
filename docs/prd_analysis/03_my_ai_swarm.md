# PRD Analysis: My AI Page + The Swarm

**PRD Section:** Lines ~205-265 of APP_UX_PRD_FINAL_v0.1.md

---

## Current State → Swarm Mapping

### How Agent State Works Today
- `jb_agent_state.py` reads `jbcp_signals.jsonl` and derives agent state
- `get_agent_states()` returns agents with: name, type, status (coding/thinking/idle/offline), active_sessions, total_turns, tools_used, linked_tasks, last_seen, subagents
- Status derived from signal recency: coding if tool signals recent, thinking if llm signals recent, idle if >5min, offline if >30min
- Agents identified by session keys like `agent:jbcp-worker:main`

### Mapping to Swarm Abstraction

| PRD Concept | Current Data Source | Gap |
|-------------|-------------------|-----|
| Worker role (Coder/Researcher/etc) | Task `type` field on linked task | Task types exist but aren't mapped to role icons |
| "writing auth logic" | `tool_start` signal with `label` field | Labels exist but are tool-level, not component-level |
| Component being worked on | Task → `component_id` → component name | Join path exists but `get_agent_states()` doesn't resolve it |
| Progress per worker | Task status (pending/running/complete) | Binary, not granular |
| Worker count per mission | Tasks with status=running, grouped by mission | Query exists but no endpoint |
| Anonymous workers | Agent names are internal (jbcp-worker) | Already anonymous by accident |

### Key Insight
The "swarm" is really just a view transformation of existing data: running tasks + their linked components + active signals. No new data collection needed — just new aggregation and formatting.

---

## Concrete Coding Tasks

### v1 (MVP)

| # | Task | File(s) | Effort |
|---|------|---------|--------|
| 1 | **Swarm endpoint** — `GET /api/dashboard/swarm` returns workers grouped by mission. Each worker: role (from task type), component name, current activity (from latest signal), status | `jb_api.py`, new `jb_swarm.py` | Medium |
| 2 | **Role mapping** — map task types to PRD roles: `coding`→Coder, `research`→Researcher, `document`→Writer, `analysis`→Analyst. Fallback: "Worker" | `jb_swarm.py` | Small |
| 3 | **Activity text from signals** — for each running task, find latest signal for that session and translate to human text. Reuse CEO translator. "tool_start write email_parser.py" → "writing email parser" | `jb_ceo_translator.py` | Covered by dashboard task |
| 4 | **Queued workers** — include pending tasks as "queued" entries in swarm view, showing component name | `jb_swarm.py` | Small |
| 5 | **Completed workers** — include recently completed tasks (last 30min) with result summary, lines of code | `jb_swarm.py` | Small |
| 6 | **Mission-scoped swarm** — `GET /api/missions/{id}/swarm` for mission-specific build view | `jb_api.py` | Small |
| 7 | **SSE swarm events** — publish `swarm.worker.started`, `swarm.worker.progress`, `swarm.worker.completed` events | `jb_event_bus.py`, `jb_reactor.py` | Medium |

### v2

| # | Task | Notes |
|---|------|-------|
| 8 | Per-worker signal timeline (debug mode) | Stream of raw signals for a specific worker |
| 9 | Worker model/token info (debug mode) | Requires signal enrichment |
| 10 | Worker file tree (what files were created/modified) | Parse file_write signals |
| 11 | Parallel worker coordination | Workers don't coordinate today — they might conflict |

---

## Running Section (Services)

The "Running" section of My AI page maps directly to the service registry:

| PRD Field | Current Data | Gap |
|-----------|-------------|-----|
| Service name | ✅ service.name | None |
| Health status | ⚠️ service.status (static flag) | Need signal-derived health |
| Schedule | ✅ service.schedule | None |
| Run count | ✅ service.run_count | None |
| "3 alerts today" | ❌ No domain stats | Requires pipeline runner output |

**v1 Task:**
8. Add `GET /api/dashboard/services` with computed health and human-friendly schedule labels ("every 15 minutes" not "*/15 * * * *")

---

## Architecture Decision

The swarm is a **read-only view layer** — no new state to manage. It's a join across:
- `jb_queue.py` (running/pending tasks)
- `jb_components.py` (component names for tasks)
- `jb_signals.py` (latest signals per session)
- `jb_services.py` (running services)

Recommend a dedicated `jb_swarm.py` module (~150 lines) that composes these queries, rather than adding complexity to existing modules.
