# PRD Analysis: Mission → Agent Lifecycle

**PRD Section:** Lines ~50-107 of APP_UX_PRD_FINAL_v0.1.md

---

## Phase-by-Phase Analysis

### Phase 1: Planning
**PRD Vision:** Chat interface, AI as solution architect, context scoped to mission + workspace.
**Current State:** ✅ Mostly working. Mission creation with `planning` status exists. Plugin injects planning mode prompt and blocks exec/write/edit/subagents tools. Context injection scopes to focused mission.
**Gaps:** None critical for v1.

### Phase 2: Spec'd (Ready to Build)
**PRD Vision:** Component graph showing planned architecture, spec document, "Build It" button.
**Current State:** ✅ Working. `/mission generate` dispatches to jbcp-worker, produces components/connections/tasks stored on mission. `/mission approve` transitions to `active`, creates component/connection/task records.
**Gaps:** No "spec document" generation (PRD mentions PRD + tech spec). Graph shows planned components but may lack edge labels from contracts.

### Phase 3: Building
**PRD Vision:** Graph nodes light up, progress per component, activity feed, answer agent questions (feedback loop).
**Current State:** ⚠️ Partially working. Orchestrator dispatches tasks, signals flow, component statuses update. Real-time signal push works (<50ms).
**Gaps:**
- No feedback loop — agents are fully autonomous, no mechanism to surface questions to user
- Progress is coarse (task status, not per-file)
- Component status updates depend on reactor interpreting signals correctly

### Phase 4: Complete
**PRD Vision:** All green nodes, "Ready to deploy", "Try It" runs once, "Deploy as Agent" when ready.
**Current State:** ❌ Missing critical pieces.
**Gaps:**
- No "Try It" (run-once) capability — requires pipeline runner (jb_pipeline.py, NOT BUILT)
- Mission auto-completes when all tasks done, but no explicit "complete" → "deploy" transition
- No deploy endpoint

### Phase 5: Running (Agent)
**PRD Vision:** Mission graduates to Agents section in sidebar. Green dot, health stats, last run, uptime. Pause/restart/undeploy.
**Current State:** ❌ Major gaps.
**Gaps:**
- Services have no `mission_id` field — can't link back to missions
- No `deployed` mission status
- No deploy endpoint (`POST /api/missions/{id}/deploy`)
- No undeploy endpoint
- `start_service()` just flips a status flag — no actual process management
- No health monitoring beyond static flags

---

## Concrete Coding Tasks

### Must-Have (v1)

| # | Task | File(s) | Effort |
|---|------|---------|--------|
| 1 | Add `mission_id` to service data model | `jb_services.py` | Small |
| 2 | Add `deployed` to valid mission statuses | `jb_missions.py` | Small |
| 3 | Create `POST /api/missions/{id}/deploy` — creates service, sets mission status to deployed | `jb_api.py`, `jb_missions.py`, `jb_services.py` | Medium |
| 4 | Create `POST /api/services/{id}/undeploy` — stops service, returns mission to complete | `jb_api.py`, `jb_services.py`, `jb_missions.py` | Medium |
| 5 | Add `POST /api/services/{id}/start` endpoint | `jb_api.py` | Small |
| 6 | Make mission cancel actually stop pending/running tasks | `jb_api.py`, `jb_queue.py` | Small |

### Should-Have (v1)

| # | Task | File(s) | Effort |
|---|------|---------|--------|
| 7 | Mission progress endpoint — `GET /api/missions/{id}/progress` returning component-level status | `jb_api.py` | Small |
| 8 | Mission-scoped graph — `GET /api/workspaces/{id}/graph?mission_id=X` | `jb_components.py`, `jb_api.py` | Small |
| 9 | Component status change SSE events | `jb_reactor.py`, `jb_event_bus.py` | Medium |
| 10 | Sidebar data endpoint — workspace with categorized missions (agents vs active vs planning) | `jb_api.py` | Small |
| 11 | Enriched live services endpoint with last_run, run_count, uptime | `jb_services.py`, `jb_api.py` | Medium |

### Explicitly v2

- Pipeline runner (jb_pipeline.py) — generates executable code from component graph
- "Try It" run-once capability — depends on pipeline runner
- Actual process management (cron, daemon, webhook scheduling)
- Health monitoring with real checks
- Agent feedback loop (questions surfaced to user chat)
- Live code streaming
- Token/cost tracking per mission
