# Consolidated v1 Task List

**Generated:** 2026-03-31
**Source:** PRD analysis files 01-09

---

## Decisions

- **Platform:** Web app (vanilla HTML/CSS/JS in `webui/`). Updating the existing v2 web UI to match the PRD.
- **OpenClaw dependency:** Accepted as-is. Fix issues as they surface.
- **Component interface:** Hard contract. Coding agents MUST produce `contract.py` / `main.py` / `test_main.py`. Task prompts are prescriptive (like ComfyUI/N8N/Salt.ai node specs). F3 is P0.
- **Frontend:** Built alongside backend in `webui/`. Each workstream includes its frontend implementation.
- **Testing:** Continuous. Write tests as you code, run as you build. No separate testing phase.
- **Iterative generate:** `/mission generate` is callable unlimited times during planning. Replaces ghost nodes.

---

## Workstream A: Foundation Modules (new shared infrastructure)

| ID | Task | New File | Depends On | Effort |
|----|------|----------|------------|--------|
| A1 | CEO translator — raw signals → human text. Pattern library + task→component lookup chain | `jb_ceo_translator.py` | Nothing | Medium |
| A2 | Labels module — mission phase labels, service status labels, component display_status | `jb_labels.py` | Nothing | Small |
| A3 | Swarm view module — joins queue + components + signals + services into per-worker rows | `jb_swarm.py` | A1 | Medium |
| A4 | Signal reactor — maps signals through session→task→component, updates state, emits SSE events | `jb_signal_reactor.py` | Nothing | Medium |

## Workstream B: Data Model Changes

| ID | Task | File(s) | Effort |
|----|------|---------|--------|
| B1 | Add `mission_id` to service data model | `jb_services.py` | Small |
| B2 | Add `deployed` to valid mission statuses | `jb_missions.py` | Small |
| B3 | Add `description` field to company model | `jb_companies.py` | Small |
| B4 | Add `mission_id` as direct field on components | `jb_components.py` | Small |
| B5 | Add `progress` computed field to mission responses | `jb_missions.py` | Small |
| B6 | Add `last_activity` / `last_activity_at` to workspace, mission, service responses | `jb_api.py` | Small |
| B7 | Add `health` dot computation (green/yellow/red/gray) | `jb_api.py` | Small |
| B8 | Add `phase_label` / `status_label` to all mission + service responses | `jb_api.py` | Small |

## Workstream C: API Endpoints

| ID | Task | Endpoint | Effort |
|----|------|----------|--------|
| C1 | Fix session key bug (`:company:` vs `:channel:`) | `jb_api.py` | Tiny |
| C2 | Dashboard running services aggregate | `GET /api/dashboard/running` | Small |
| C3 | Dashboard building missions aggregate | `GET /api/dashboard/building` | Small |
| C4 | Dashboard recent activity (REST, human-readable) | `GET /api/dashboard/recent` | Medium |
| C5 | Dashboard heartbeat | `GET /api/dashboard/heartbeat` | Small |
| C6 | Dashboard swarm view | `GET /api/dashboard/swarm` | Medium |
| C7 | Mission-scoped swarm | `GET /api/missions/{id}/swarm` | Small |
| C8 | Deploy endpoint | `POST /api/missions/{id}/deploy` | Medium |
| C9 | Undeploy endpoint | `POST /api/services/{id}/undeploy` | Small |
| C10 | Start service endpoint | `POST /api/services/{id}/start` | Small |
| C11 | Mission progress endpoint | `GET /api/missions/{id}/progress` | Small |
| C12 | Mission-filtered graph | `GET /api/workspaces/{id}/graph?mission_id=X` | Small |
| C13 | Component PATCH endpoint | `PATCH /api/components/{id}` | Small |
| C14 | Workspace detail (categorized missions/agents) | `GET /api/workspaces/{id}/detail` | Medium |
| C15 | Workspace description CRUD | `PATCH /api/workspaces/{id}/description` | Small |
| C16 | Workspace-level tasks endpoint | `GET /api/workspaces/{id}/tasks` | Small |
| C17 | Global component list (library) | `GET /api/components` + `GET /api/components/library` | Small |
| C18 | Enrich workspace list response | Modify `GET /api/workspaces` | Medium |
| C19 | CEO/full query param on key endpoints | Modify agents, workspaces, missions | Medium |
| C20 | CEO-mode event stream transformation | Modify `GET /api/events/stream` | Medium |
| C21 | SSE mission_id filter | Modify `GET /api/events/stream` | Small |
| C22 | Service report endpoint | `POST /api/services/{id}/report` | Small |
| C23 | Usage endpoint de-stub | `GET /api/usage` | Medium |
| C24 | Mission cancel stops pending/running tasks | Modify cancel flow | Small |
| C25 | Enriched live services (last_run, uptime, health) | Modify `GET /api/services` | Medium |
| C26 | Per-task signal timeline | `GET /api/tasks/{id}/signals` | Small |
| C27 | Task file trees | `GET /api/tasks/{id}/files` | Small |
| C28 | Component code views | `GET /api/components/{id}/files` | Small |

## Workstream D: Graph Enrichment

| ID | Task | File(s) | Effort |
|----|------|---------|--------|
| D1 | Enrich `build_graph()` — real progress, active agents, edge labels, mission_id, description, contract, is_active, built_by | `jb_components.py` | Medium |
| D2 | Unify mock and real graph shapes (source/target vs from/to) | `jb_mock_data.py` | Small |
| D3 | Graph-specific SSE events from reactor | `jb_reactor.py` | Medium |

## Workstream E: Chat

| ID | Task | File(s) | Effort |
|----|------|----------|--------|
| E1 | Mission-scoped session keys | `jb_api.py` | Small |
| E2 | Global chat session | `jb_api.py` | Small |
| E3 | Global dashboard context generation | `jb_openclaw_bridge.py` | Medium |
| E4 | Inject component catalog into plan generation prompt | `jb_plan_generate.py` | Medium |
| E5 | Planning context enhancement (inject plan items into chat) | Plugin (JS) | Small |
| E6 | Plugin update for mission-scoped session keys | Plugin (JS) | Small |

## Workstream F: Pipeline & Deployment

| ID | Task | File(s) | Effort |
|----|------|---------|--------|
| F1 | `jb_pipeline.py` — topological sort, generate pipeline.py, config injection, contract validation | New file | Large |
| F2 | Component directory scaffolding (contract.py/main.py/test_main.py) | `jb_components.py` | Medium |
| F3 | Coding agent task prompts — prescriptive prompt with component contract spec | `jb_openclaw_bridge.py` | Medium | **P0 — This is the highest risk item. If agents don't produce conformant components, the pipeline runner can't compose them.** |
| F4 | "Try It" endpoint — generate + run once + return results | `POST /api/missions/{id}/try` | Medium |

## Workstream G: Iterative Generate

| ID | Task | File(s) | Effort |
|----|------|---------|--------|
| G1 | Make `generate` idempotent — clear previous draft, include previous graph in prompt | `jb_plan_generate.py` | Medium |
| G2 | Draft graph endpoint — `GET /api/missions/{id}/graph` returns draft before approval | `jb_api.py`, `jb_components.py` | Medium |
| G3 | Previous graph as context — inject current draft + new chat into worker prompt for refinement | `jb_plan_generate.py`, `jb_openclaw_bridge.py` | Medium |
| G4 | Graph diff markers — `changed: true/false` per component between iterations | `jb_plan_generate.py` | Small |
| G5 | Graph layout preservation across regenerations — match by name/type, preserve positions | `jb_api.py` | Small |

## Workstream H: Feedback & Developer Tools

| ID | Task | File(s) | Effort |
|----|------|---------|--------|
| H1 | Agent decision logging — agents log decisions with rationale, surfaced as system messages in mission chat | `jb_openclaw_bridge.py`, `jb_api.py` | Medium |
| H2 | Post-hoc iteration — user replies to decision in chat, answer included as context in next task re-dispatch | `jb_api.py`, `jb_orchestrator.py` | Medium |
| H3 | Edge animation events — `graph.edge.active` SSE events when pipeline components execute (gated on F1) | `jb_reactor.py` | Small |
| H4 | Graph layout persistence — `PATCH /api/missions/{id}/graph-layout` stores node positions | `jb_api.py` | Small |

---

## Deferred (v2+)

- Real process management (cron, daemon, health monitoring)
- Standalone app deployment / packaging
- Full pause-and-wait feedback loop (agent blocks until user answers)
- Cross-workspace component reuse mechanics (actual wiring, not just AI suggestion)
- Token/cost tracking per mission
- Auto-generated company descriptions via LLM
- Live execution stats on deployed nodes
- Pipeline hot-reload
- Real-time ghost nodes from free-form chat (superseded by iterative generate)

---

## Build Order (recommended)

**Phase 1 — Foundation (+ frontend structural changes):** A1, A2, A4, B1-B8, C1
**Phase 2 — Dashboard & Views (+ frontend Home, Company, My AI pages):** C2-C7, C14, C16-C18, C25, D1-D2
**Phase 3 — Graph & Generate (+ frontend graph renderer):** G1-G5, C12, C13, D3
**Phase 4 — Chat & Context (+ frontend chat improvements):** E1-E6
**Phase 5 — CEO Mode (+ frontend CEO-mode activity text):** C19, C20, C21, A3
**Phase 6 — Deployment (+ frontend deploy/undeploy controls):** F1-F4, C8-C10, C24
**Phase 7 — Feedback & Dev Tools (+ frontend Settings/Debug page):** H1-H4, C22, C23, C26-C28

---

## Frontend Tasks (webui/)

Frontend work lives in `webui/` and is built alongside each backend workstream. The existing UI is a developer-oriented control plane that needs to be transformed into the PRD's CEO-mode product.

### Structural Changes
- Replace "JBCP Control Plane" branding with "Salt Desktop" 
- Replace sidebar nav (Workspaces/Activity/Agents/Debug) with PRD structure (Home, Companies, My AI, Component Library, Settings)
- Add bottom status ticker (SSE-driven)
- Add persistent heartbeat indicator (top-right)

### Page Rewrites (aligned to backend workstreams)
| Page | Replaces | Backend Dependencies |
|------|----------|---------------------|
| Home (Living Dashboard) | workspaces.js | C2, C3, C4, C5, B5-B7 |
| Company View | workspace.js (partial) | C14, C15, C18 |
| Mission View (chat + graph) | workspace.js (partial) | G2, C12, E1, D1 |
| My AI (Swarm + Services) | agents.js | C6, C7, C25, A3 |
| Component Library | New | C17 |
| Settings / Debug | debug.js | C19, C23 |

### Component Graph Renderer
- Canvas or SVG-based graph renderer for component nodes + edges
- Node states: planned (gray), building (yellow/pulse), built (green), live (green/breathing)
- Edge labels from contracts
- Drag-to-reposition with layout persistence (H4)
- Edge animation when pipeline executes (H3, gated on F1)

### Chat Improvements
- Command palette (already exists, keep it)
- Typing indicator (already exists via signals, keep it)
- System messages for agent decisions (H1)
- CEO-mode activity text in sidebar (A1)
