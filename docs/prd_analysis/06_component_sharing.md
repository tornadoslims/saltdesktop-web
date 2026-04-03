# PRD Analysis: Component Sharing + Component Library

**PRD Section:** Lines ~416-443 of APP_UX_PRD_FINAL_v0.1.md

---

## 1. Current State: How Components Are Scoped

Components are **strictly per-workspace**:
- `_normalize_component()` raises `ValueError` if `workspace_id` is missing
- `list_components(workspace_id)` filters by workspace; `None` returns all (internal only)
- `build_graph(workspace_id)` is workspace-scoped
- API: `GET /api/workspaces/{id}/components` only returns components for that workspace
- `GET /api/components/{id}` returns single component with no cross-workspace context
- **No global component listing endpoint**
- **No usage tracking** across workspaces
- Plan generation has **zero awareness** of components from other workspaces

**Bottom line:** Components are born, live, and die within a workspace. No sharing infrastructure exists.

---

## 2. What the PRD Wants

| Capability | Description |
|------------|-------------|
| Global sharing | Gmail Connector from Company A reusable in Company B |
| Component Library page | Browse all, grouped by type, showing usage/LOC/age |
| Automatic reuse in chat | AI detects existing components during planning |
| Cross-workspace visualization | Graph shows which missions use each component |

---

## 3. Recommended Data Model Approach

Keep `workspace_id` as `origin_workspace_id`. Add `workspace_refs: list[str]` for all workspaces using the component. `list_components(workspace_id)` returns components where `workspace_id in workspace_refs`.

**New fields needed:**
- `origin_workspace_id: str` — where it was first built
- `workspace_refs: list[str]` — all workspaces using it
- `shared: bool` — explicitly marked as shareable
- `usage_count: int` — missions/plans referencing it
- `tags: list[str]` — for library browsing
- `version: str` — for evolution tracking

---

## 4. New API Endpoints Needed

| Endpoint | Purpose |
|----------|---------|
| `GET /api/components` | All components globally, with `?type=&status=` filters |
| `GET /api/components/library` | Library view grouped by type, includes usage counts |
| `POST /api/components/{id}/reuse` | Add workspace_ref to existing component |
| `GET /api/components/{id}/usage` | Cross-ref: which workspaces/missions use it |

---

## 5. AI Reuse During Planning

Currently `jb_plan_generate.py` sends zero info about existing components. Fix:
1. Query all components with status in (built, passing, deployed)
2. Build compact summary (name, type, contract input/output, component_id)
3. Inject as "Available Components" in worker prompt
4. Worker references existing components with `reused: true`
5. Plan parser handles `reused: true` — calls `reuse_component()` instead of `create_component()`

Cap at ~20 components to avoid prompt bloat.

---

## 6. v1 vs v2 — Honest Assessment

### v1 (include — ~3-4 days)
- `GET /api/components` global list endpoint (trivial — `list_components(None)` almost works)
- `GET /api/components/library` grouped by type (low effort, high delight)
- Available components summary for prompt injection (core to "chat IS the interface")
- This is "awareness" — the AI knows about and suggests reuse

### v2 (defer — ~5-7 additional days)
- Actual cross-workspace reuse mechanics (workspace_refs, versioning)
- Cross-workspace graph visualization
- Parsing reused components and wiring them into new plans
- Hard problems: file locations across workspaces, version pinning, contract compatibility

### v1.5 Quick Win
Inject component summary into planning prompt so AI *suggests* reuse without actually wiring it. User sees intent; mechanics come in v2.

---

## 7. Key Risks

- **Component files live in workspace directories** — reuse means code is in another workspace's dir. Copy? Symlink? (v2 problem)
- **Prompt bloat** — 50+ components overwhelm planning prompt. Cap at 20 with compact format.
- **Contract compatibility** — reuse assumes types are compatible. Plan generator should validate.
- **Stale components** — filter library to built/passing/deployed only.
