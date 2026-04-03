# PRD Analysis: Home — Living Dashboard + Always Alive Layer

**PRD Section:** Lines ~110-205 of APP_UX_PRD_FINAL_v0.1.md

---

## Element-by-Element Analysis

### 1. "What's Running" Section
**PRD Vision:** Live services with health status, stats (emails checked, alerts sent), uptime.
**What Exists:**
- `GET /api/services` returns service list with status, type, schedule, run counts
- `GET /api/services/{id}` returns individual service detail
- Service model has `run_count`, `last_run_at`, `total_duration_ms`
**What's Missing:**
- No aggregate "dashboard" endpoint that returns all running services across all workspaces
- Service stats are basic counters — no domain-specific stats ("142 emails checked")
- Health is a static flag, not signal-derived
- No cross-workspace service summary

**v1 Tasks:**
1. `GET /api/dashboard/running` — aggregate all services with status=running across workspaces, include workspace name, service name, run stats
2. Add `health_status` computed field (healthy/degraded/down based on last_run recency + error rate)

**v2:** Domain-specific stats require pipeline runner output parsing. Defer.

### 2. "In Progress" Section
**PRD Vision:** Active builds with real progress bars, component-level status, what's happening right now.
**What Exists:**
- `GET /api/workspaces/{id}/missions` returns missions with status
- Task statuses available per mission
- Signal stream shows real-time activity
**What's Missing:**
- No aggregate "in progress" endpoint across all workspaces
- No progress percentage per mission (need completed_tasks/total_tasks)
- No "what's happening right now" summary from signals

**v1 Tasks:**
3. `GET /api/dashboard/building` — all missions with status=active, include progress (completed/total tasks), current activity from latest signals
4. Add `progress` computed field to mission responses (tasks completed / total)

### 3. "Recent" Section
**PRD Vision:** Activity feed showing what happened since last visit, continuously updating.
**What Exists:**
- `GET /api/events/stream` SSE endpoint tails JSONL events + signals
- Event log has timestamped entries
**What's Missing:**
- No "recent activity" REST endpoint (only SSE stream)
- No human-readable event formatting (raw signal data)
- No "since last visit" tracking

**v1 Tasks:**
5. `GET /api/dashboard/recent?since=TIMESTAMP&limit=20` — recent events formatted for human consumption
6. Signal-to-human translator function (shared with CEO mode translator)

### 4. Sidebar Activity Pulse
**PRD Vision:** Every agent/mission shows last activity and timestamp, updating live.
**What Exists:**
- `GET /api/workspaces` returns workspace list with mission/task/component counts
- Agent state has `last_seen` timestamps
**What's Missing:**
- No `last_activity` or `last_activity_text` on workspace/mission/service responses
- No SSE events scoped to sidebar updates

**v1 Tasks:**
7. Add `last_activity` and `last_activity_text` fields to workspace list response
8. Add same to mission list items and service list items

### 5. Bottom Status Ticker
**PRD Vision:** Scrolling recent events across bottom of every page.
**What Exists:** SSE event stream
**What's Missing:** This is purely frontend — backend just needs the formatted event stream (covered by task 6).
**v1:** No additional backend work. Frontend consumes SSE stream.

### 6. Heartbeat on Every Page
**PRD Vision:** Compact "4 working now" indicator with expandable detail.
**What Exists:**
- `GET /api/agents` returns agent states with status
- `GET /api/status` returns aggregate counts
**What's Missing:**
- No single "heartbeat" endpoint returning: active worker count, last activity per running service

**v1 Tasks:**
9. `GET /api/dashboard/heartbeat` — { active_workers: N, running_services: N, latest_events: [...] }

### 7. Breathing Graph Nodes
**PRD Vision:** Subtle pulse animation on live graph nodes, data flow wave animation.
**What's Missing:** Purely frontend animation. Backend provides component status + connection data. No backend work.

---

## Summary: All v1 Backend Tasks

| # | Task | Endpoint/File | Effort |
|---|------|---------------|--------|
| 1 | Dashboard running services aggregate | `GET /api/dashboard/running` | Small |
| 2 | Health status computation on services | `jb_services.py` | Small |
| 3 | Dashboard building missions aggregate | `GET /api/dashboard/building` | Small |
| 4 | Mission progress computation | `jb_missions.py` | Small |
| 5 | Dashboard recent activity (REST) | `GET /api/dashboard/recent` | Medium |
| 6 | Signal-to-human translator | `jb_ceo_translator.py` (new) | Medium |
| 7 | Last activity on workspace responses | `jb_api.py` | Small |
| 8 | Last activity on mission/service responses | `jb_api.py` | Small |
| 9 | Dashboard heartbeat endpoint | `GET /api/dashboard/heartbeat` | Small |

**v2:** Domain-specific service stats, "since last visit" tracking, graph animation data events.
