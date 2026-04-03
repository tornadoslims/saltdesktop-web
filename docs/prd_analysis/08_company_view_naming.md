# PRD Analysis: Company View + Naming & Language

**PRD Section:** Lines ~267-415 of APP_UX_PRD_FINAL_v0.1.md

---

## 1. Current Company Data Model vs PRD Needs

### What Exists (`jb_companies.py`)
- Company fields: `id`, `name`, `discord_channel_id`, `focused_mission_id`, `mission_ids`, `archived`, `created_at`, `updated_at`, `context_file_path`
- `_company_to_workspace()` in `jb_api.py` enriches with: mission count, task count, component count, service count, stage

### What's Missing
- **No `description` field** — PRD requires auto-generated, editable description
- **No categorized mission breakdown** — PRD shows Agents (deployed), Missions (in-progress), Completed separately
- **No service/agent info in workspace response** — just a count, not names/statuses
- **No `last_activity` field** — sidebar pulse needs this

---

## 2. API Response Changes Needed

### `GET /api/workspaces` (list)
Current returns: id, name, stage, mission_count, task_count, component_count, service_count, archived

Needs to add:
- `description: string | null`
- `running_agents: [{name, status, last_run}]` — deployed services
- `active_missions: [{name, status, phase_label}]` — non-complete missions
- `completed_missions_count: int`
- `last_activity: string` — human-readable last event
- `last_activity_at: string` — ISO timestamp

### `GET /api/workspaces/{id}` (detail)
Needs a richer response or new detail endpoint:
- Full agent list with health
- Full mission list categorized by status
- Completed missions (collapsed)
- `+ New Mission` action context

---

## 3. Naming & Language Translation

The PRD has a clear translation table. Recommend a `jb_labels.py` module:

```python
MISSION_PHASE_LABELS = {
    "planning": "Planning",
    "planned": "Ready to Build", 
    "active": "Building",
    "complete": "Ready to Deploy",
    "deployed": "Running",
    "failed": "Failed",
    "cancelled": "Cancelled",
}

SERVICE_STATUS_LABELS = {
    "running": "Healthy",
    "paused": "Paused",
    "stopped": "Stopped",
    "error": "Problem",
}
```

API returns both raw status AND `phase_label`/`status_label` so frontend doesn't duplicate translation logic.

**Hidden concepts:** Tasks, orchestrator, signals, dispatch, queue — none of these appear in Company View API responses.

---

## 4. Concrete Coding Tasks

### v1

| # | Task | File(s) | Effort |
|---|------|---------|--------|
| 1 | Add `description` field to company model + CRUD | `jb_companies.py` | Small |
| 2 | `PATCH /api/workspaces/{id}/description` endpoint | `jb_api.py` | Small |
| 3 | Enrich workspace list response with agent/mission breakdown | `jb_api.py` | Medium |
| 4 | Create `GET /api/workspaces/{id}/detail` with full categorized view | `jb_api.py` | Medium |
| 5 | Create `jb_labels.py` with all translation maps | New file | Small |
| 6 | Add `phase_label` and `status_label` to all mission/service responses | `jb_api.py` | Small |
| 7 | Add `last_activity` / `last_activity_at` to workspace responses | `jb_api.py` | Small |
| 8 | Tests for enriched responses and labels | `tests/` | Medium |

### v2

| # | Task | Notes |
|---|------|-------|
| 9 | Auto-generate company descriptions via LLM | After mission completion, summarize what the company does |
| 10 | Remove raw task counts from public API | Only expose component-level progress |
| 11 | Real uptime/alert metrics on agents | Blocked on service deployment (Phase 10) |
| 12 | Copy-quality formatted strings ("Gmail Checker is running" not "status: running") | Polish pass |

---

## 5. Key Risk

**N+1 query pattern** — `_company_to_workspace` already hits 4 data stores per company. Adding categorized views makes it heavier. Fine for <20 companies but may need caching later.
