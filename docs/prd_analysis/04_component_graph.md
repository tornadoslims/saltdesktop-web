# PRD Analysis: Component Graph (The N8N Moment)

**PRD Section:** Lines ~312-368 of APP_UX_PRD_FINAL_v0.1.md

---

## 1. What `build_graph()` Currently Returns vs PRD Needs

### Current Output (`jb_components.py`)
Nodes: `id`, `type`, `label`, `status`, `metadata` (lines_of_code, files count, assigned_agents=None, build_progress_percent from static map, test_status)
Edges: `from`, `to`, `type`, `label`

### PRD Requires Per Node
- Icon (derivable from type — no backend change)
- Name ✅ (label field)
- Activity indicator — ❌ `is_active` boolean needed
- Type badge ✅ (type field)
- Status badge ✅ (status field)
- Lines of code ✅ (in metadata, but often 0)
- Progress bar with REAL percentage — ❌ static map, not task-based
- Active agent + model name — ❌ `assigned_agents` always None
- Edge labels from contracts — ⚠️ label field exists but often null

### Key Gaps

| Field | Current | Needed |
|-------|---------|--------|
| `is_active` | Not present | Boolean from running task signals |
| Progress % | Static status map (building=25%) | `completed_tasks / total_tasks * 100` |
| Active agent | `assigned_agents: None` always | Join: task → session → agent state |
| Edge labels | Often null | Auto-derive from contract `output_type` |
| `mission_id` | Not on component or node | Needed for frontend grouping |
| `description` | On component, not in graph | Include in node |
| Contract summary | On component, not in graph | Needed for edge derivation |
| `built_by` | Set by reactor on write/edit signals | Not included in graph output |

### Mock vs Real Shape Mismatch
- Mock uses `source`/`target` on edges; real uses `from`/`to`
- Mock has `mission_id` on nodes; real does not
- Must unify to single shape

---

## 2. Concrete Coding Tasks

### v1 (MVP)

| # | Task | File(s) | Effort |
|---|------|---------|--------|
| 1 | **Enrich `build_graph()`** — compute real progress from tasks, look up active agents, add mission_id/description/contract/built_by/is_active to nodes, auto-derive edge labels, normalize edge keys to source/target | `jb_components.py` ~80 lines | Medium |
| 2 | **Unify mock and real graph shapes** | `jb_mock_data.py` ~40 lines | Small |
| 3 | **Add `PATCH /api/components/{id}`** — mutation endpoint for component updates | `jb_api.py` ~30 lines | Small |
| 4 | **Add `mission_id` as direct field on components** — currently only derivable through task linkage (fragile) | `jb_components.py` | Small |
| 5 | **Graph-specific SSE events** — `graph.node.status`, `graph.node.progress`, `graph.node.agent` published by reactor on component changes | `jb_reactor.py`, `jb_event_bus.py` ~40 lines | Medium |
| 6 | **Status mapping** — add `display_status` field mapping 7 backend statuses to PRD's 4 (planned/building/built/live) | `jb_components.py` | Small |
| 7 | **Tests** — enriched graph, progress computation, edge label derivation | `tests/test_components.py` ~100 lines | Medium |

### Iterative Generate (G1-G5)

These tasks replace the ghost nodes feature (C3/C4 in chat UX). User explicitly triggers graph updates via `/mission generate` instead of automatic per-turn extraction.

| # | Task | File(s) | Effort |
|---|------|---------|--------|
| G1 | **Make `generate` idempotent** — clear previous draft items/components/connections before regenerating. Include previous graph in prompt so AI refines rather than starts fresh. | `jb_plan_generate.py` | Medium |
| G2 | **Draft graph endpoint** — `GET /api/missions/{id}/graph` returns mission's draft components/connections before they exist in component registry. Distinct from workspace graph. | `jb_api.py`, `jb_components.py` | Medium |
| G3 | **Previous graph as context** — when regenerating, inject current draft graph + user chat since last generate into worker prompt. "Here's what you had. Here's what the user said. Refine." | `jb_plan_generate.py`, `jb_openclaw_bridge.py` | Medium |
| G4 | **Graph diff markers** — response from generate includes `changed: true/false` per component so frontend highlights what changed. | `jb_plan_generate.py` | Small |
| G5 | **Graph layout preservation across regenerations** — matching component name/type preserves position. New ones auto-place. Removed ones disappear. | `jb_api.py` | Small |

### v2

| # | Task | Notes |
|---|------|-------|
| 8 | Live execution stats on deployed nodes (run count, error rate) | Depends on pipeline runner |
| 9 | Edge animation data — `graph.edge.active` events for data flow visualization | Depends on pipeline runner |
| 10 | Component detail expansion endpoint — full file list, contract schemas, task history, logs | Inspector panel feature |
| 11 | Graph layout persistence — store user-arranged node positions per workspace | Frontend-driven, backend stores positions |

---

## 3. Key Risks

1. **Progress granularity** — task-count is coarse (3 tasks = 0/33/66/100%). Could augment with signal heuristics. Recommend task-count for v1.
2. **Edge label quality** — contract `output_type` gives technical names ("email_list"). PRD shows friendly names ("parsed emails"). Plan generation should produce `display_label` on connections.
3. **Event bus scope** — reactor running outside API server process can't publish to in-memory bus. Solution: reactor writes events to JSONL, SSE tails both signal and event files.
4. **Real-time graph updates** — need reactor to publish structured events after each component update, not just raw signals.
