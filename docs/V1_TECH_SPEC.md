# Salt Desktop v1 — Technical Specification

**Status:** Final Draft
**Date:** 2026-03-31
**Source:** APP_UX_PRD_FINAL_v0.1.md + codebase analysis (docs/prd_analysis/01-09)
**Audience:** Coding agents building the v1 backend + web UI

---

## Decisions

- **Platform:** Web app (vanilla HTML/CSS/JS in `webui/`). Updating the existing web UI served by FastAPI at localhost:8718.
- **OpenClaw dependency:** Accepted as-is. Fix issues as they surface.
- **Component interface:** Hard contract. Coding agents MUST produce `contract.py` / `main.py` / `test_main.py`. Task prompts are prescriptive (like ComfyUI/N8N/Salt.ai node specs).
- **Frontend:** Built alongside backend in `webui/`. Each workstream includes frontend.
- **Testing:** Continuous. Write tests as you code, run `python -m pytest tests/ -q` as you build.
- **Iterative generate:** `/mission generate` callable unlimited times during planning. Replaces ghost nodes concept.
- **No separate v2 planning during v1 build.** Deferred items are listed at the end. Don't build them.

---

## Architecture Overview

```
webui/ (vanilla HTML/CSS/JS)
  ↓ REST + SSE
FastAPI (runtime/jb_api.py, port 8718)
  ↓ imports
Runtime Modules (runtime/jb_*.py)
  ↓ reads/writes
JSON Data (data/*.json)
  ↓
OpenClaw Gateway (10.0.0.137:18789)
  ↓
jbcp-worker agents (coding/research/etc)
```

**New modules to create:**
| Module | Purpose | Estimated Lines |
|--------|---------|-----------------|
| `runtime/jb_ceo_translator.py` | Raw signals → human-readable text | ~150 |
| `runtime/jb_labels.py` | Status/phase label translation maps | ~50 |
| `runtime/jb_swarm.py` | Swarm view: joins queue + components + signals into worker rows | ~150 |
| `runtime/jb_signal_reactor.py` | Signal → task → component state updates + SSE events | ~200 |
| `runtime/jb_pipeline.py` | Generate executable pipeline.py from component graph | ~400 |

**Existing modules to modify:**
| Module | Changes |
|--------|---------|
| `jb_services.py` | Add `mission_id` field |
| `jb_missions.py` | Add `deployed` status, progress computation |
| `jb_companies.py` | Add `description` field |
| `jb_components.py` | Add `mission_id` field, enrich `build_graph()`, add `display_status` |
| `jb_api.py` | ~25 new/modified endpoints, CEO/full query param, dashboard routes |
| `jb_plan_generate.py` | Iterative generate, previous graph as context, component catalog injection |
| `jb_openclaw_bridge.py` | Prescriptive task prompts with component contract spec, global context |
| `jb_mock_data.py` | Unify graph shape (source/target) |
| `jb_event_bus.py` | Support structured graph/swarm events from reactor |

---

## Workstream A: Foundation Modules

### A1: CEO Translator (`runtime/jb_ceo_translator.py`)

**Purpose:** Translates raw signal events into human-readable CEO-mode text. Used by dashboard, swarm, sidebar, event stream.

**Interface:**
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class CeoActivity:
    text: str                    # "Writing the email parsing logic"
    category: str                # "building" | "testing" | "thinking" | "reading" | "error"
    component_name: Optional[str]  # "Email Parser" or None
    icon: str                    # "hammer" | "magnifier" | "brain" | "check" | "warning"

def translate_signal(signal: dict, task_lookup: dict = None, component_lookup: dict = None) -> CeoActivity:
    """Translate a raw signal into CEO-friendly activity text."""

def translate_task_status(task: dict, component: dict = None) -> CeoActivity:
    """Translate a task status change into CEO-friendly text."""
```

**Translation rules:**
| Signal Pattern | CEO Text | Category |
|---------------|----------|----------|
| `tool_start` + label contains "write" or "edit" | "Writing {component_name}" | building |
| `tool_start` + label contains "pytest" or "test" | "Running tests" | testing |
| `tool_start` + label contains "read" | "Reviewing code" | reading |
| `tool_start` + source="web" or "http" | "Researching" | reading |
| `llm_input` | "Thinking..." | thinking |
| `tool_end` + error | "Hit an issue, retrying" | error |
| `subagent_spawned` | "Starting a new worker" | building |
| Task complete | "Finished building {component_name}" | building |
| Task failed | "{component_name} needs attention" | error |
| Fallback | "Working on {component_name}" or "AI is active" | building |

**Lookup chain:** signal.session_id → task (via openclaw_session_id) → component (via component_id on task) → component name.

**Tests:** `tests/test_ceo_translator.py` — test each translation rule, test fallback, test with missing lookups.

---

### A2: Labels Module (`runtime/jb_labels.py`)

**Purpose:** Single source of truth for all user-facing label translations.

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

COMPONENT_DISPLAY_STATUS = {
    "planned": "Planned",
    "building": "Building",
    "built": "Built",
    "testing": "Testing",
    "passing": "Built",      # collapse to "Built" for CEO mode
    "failing": "Problem",
    "deployed": "Live",
}

WORKER_ROLE_LABELS = {
    "coding": {"label": "Coder", "icon": "hammer"},
    "research": {"label": "Researcher", "icon": "magnifier"},
    "document": {"label": "Writer", "icon": "pencil"},
    "analysis": {"label": "Analyst", "icon": "chart"},
}

COMPONENT_TYPE_ICONS = {
    "connector": "plug",
    "processor": "gear",
    "ai": "brain",
    "output": "arrow-right",
    "scheduler": "clock",
    "storage": "database",
    "config": "sliders",
}

def mission_label(status: str) -> str: ...
def service_label(status: str) -> str: ...
def component_label(status: str) -> str: ...
def worker_role(task_type: str) -> dict: ...
```

**Tests:** `tests/test_labels.py` — test all mappings, test unknown values return sensible defaults.

---

### A3: Swarm Module (`runtime/jb_swarm.py`)

**Purpose:** Read-only view layer that joins running tasks + components + signals into per-worker rows grouped by mission.

**Interface:**
```python
def get_swarm(mission_id: str = None) -> dict:
    """
    Returns:
    {
      "building": [
        {
          "mission_id": "...",
          "mission_name": "Slack Analyzer",
          "workers": [
            {
              "task_id": "...",
              "role": "Coder",
              "role_icon": "hammer",
              "component_name": "Gmail Connector",
              "component_id": "...",
              "status": "running",     # running | queued | complete | failed
              "activity": "writing auth logic",
              "lines_of_code": 145,    # null if not complete
              "duration_s": 120,       # null if not started
            }
          ],
          "progress": {"completed": 3, "total": 5, "percent": 60}
        }
      ],
      "running": [
        {
          "service_id": "...",
          "name": "Gmail Checker",
          "status": "healthy",
          "schedule_label": "every 15 minutes",
          "run_count": 142,
          "last_run_ago": "8 minutes ago",
        }
      ]
    }
    """
```

**Data sources:** `jb_queue.py` (running/pending tasks), `jb_components.py` (component names), `jb_signals.py` (latest signals per session), `jb_services.py` (running services), `jb_ceo_translator.py` (activity text).

**Tests:** `tests/test_swarm.py`

---

### A4: Signal Reactor (`runtime/jb_signal_reactor.py`)

**Purpose:** Processes incoming signals, updates component state, and emits structured SSE events.

**Interface:**
```python
def process_signal(signal: dict) -> list[dict]:
    """
    Given a raw signal, update component state and return structured events to publish.
    
    Returns list of events like:
    [
      {"type": "graph.node.status", "component_id": "...", "status": "building", "display_status": "Building"},
      {"type": "swarm.worker.progress", "task_id": "...", "activity": "writing auth logic"},
    ]
    """

def get_session_task_mapping() -> dict[str, str]:
    """Returns session_id -> task_id mapping from current running tasks."""

def get_task_component_mapping() -> dict[str, str]:
    """Returns task_id -> component_id mapping."""
```

**Signal → component chain:**
1. Signal has `session_id`
2. Look up task with matching `openclaw_session_id` in queue
3. Task has `component_id`
4. Update component status based on signal type (tool_start → "building", task complete → "built")
5. Emit structured event for SSE

**Integration:** Called from the SSE event stream handler when new signals arrive. Also callable from orchestrator after task status changes.

**Tests:** `tests/test_signal_reactor.py`

---

## Workstream B: Data Model Changes

All changes are small additions to existing modules. No new files.

### B1: Service `mission_id` (`jb_services.py`)

Add `mission_id` to `_normalize_service()`. Optional field (existing services won't have it). Add to `create_service()` params.

### B2: Mission `deployed` status (`jb_missions.py`)

Add `"deployed"` to `VALID_MISSION_STATUSES`. Add `mark_deployed(mission_id)` and `mark_undeployed(mission_id)` (returns to `complete`).

### B3: Company `description` (`jb_companies.py`)

Add `description` field to company data model. Default `None`. Add `update_company_description(company_id, description)`.

### B4: Component `mission_id` (`jb_components.py`)

Add `mission_id` as direct field on components in `_normalize_component()`. Optional. Currently derivable only through task linkage (fragile).

### B5: Mission `progress` computation (`jb_missions.py`)

```python
def compute_mission_progress(mission_id: str) -> dict:
    """Returns {"completed": N, "total": N, "percent": float}"""
    # Count tasks by status for this mission
```

### B6: `last_activity` on responses (`jb_api.py`)

Add `last_activity` (human text) and `last_activity_at` (ISO timestamp) to workspace, mission, and service list responses. Derived from most recent signal or event for that entity.

### B7: Health dot computation (`jb_api.py`)

```python
def _compute_health(workspace_id: str) -> str:
    """Returns 'green' | 'yellow' | 'red' | 'gray'"""
    # green: all done or service running
    # yellow: tasks in progress
    # red: any failed
    # gray: idle
```

Add `health` field to workspace and mission responses.

### B8: Phase/status labels on responses (`jb_api.py`)

Add `phase_label` (from `jb_labels.py`) to all mission responses. Add `status_label` to all service responses. These are always included — not gated by CEO/dev mode.

**Tests for all B items:** Add to existing test files (`test_services.py`, `test_missions.py`, `test_companies.py`, `test_components.py`). Plus new assertions in `tests/test_api_flow.py`.

---

## Workstream C: API Endpoints

### C1: Fix session key bug

**File:** `jb_api.py`
**Bug:** Chat proxy uses `agent:main:jbcp-frontend:company:{id}`, but `get_chat_history` and `clear_chat_history` use `agent:main:jbcp-frontend:channel:{id}`. Unify to `company:`.

### C2-C5: Dashboard Endpoints

All new endpoints under `/api/dashboard/`:

```python
@app.get("/api/dashboard/running")
# Returns: all services with status=running across all workspaces
# Each: {service_id, name, workspace_name, status, health, schedule_label, run_count, last_run_ago}

@app.get("/api/dashboard/building")  
# Returns: all missions with status=active across all workspaces
# Each: {mission_id, name, workspace_name, progress: {completed, total, percent}, current_activity}

@app.get("/api/dashboard/recent")
# Params: ?since=ISO_TIMESTAMP&limit=20
# Returns: recent events formatted via CEO translator
# Each: {text, timestamp, category, icon, workspace_name, mission_name}

@app.get("/api/dashboard/heartbeat")
# Returns: {active_workers: N, running_services: N, latest_events: [...top 5]}
```

### C6-C7: Swarm Endpoints

```python
@app.get("/api/dashboard/swarm")
# Returns: full swarm view from jb_swarm.get_swarm()

@app.get("/api/missions/{mission_id}/swarm")
# Returns: mission-scoped swarm from jb_swarm.get_swarm(mission_id)
```

### C8-C10: Deploy/Undeploy/Start

```python
@app.post("/api/missions/{mission_id}/deploy")
# Body: {service_type: "scheduled"|"daemon"|"webhook"|"manual", schedule: "*/15 * * * *" (optional)}
# Creates service linked to mission, sets mission status to deployed
# Returns: {service_id, name, status}

@app.post("/api/services/{service_id}/undeploy")
# Stops service, sets mission status back to complete
# Returns: {mission_id, status: "complete"}

@app.post("/api/services/{service_id}/start")
# Starts/restarts the service
# Returns: {service_id, status: "running"}
```

### C11-C13: Mission/Graph/Component

```python
@app.get("/api/missions/{mission_id}/progress")
# Returns: {completed: N, total: N, percent: float, components: [{name, status, display_status}]}

@app.get("/api/workspaces/{workspace_id}/graph")
# NEW PARAM: ?mission_id=X filters to components belonging to that mission
# Returns: enriched graph from build_graph() with real progress, agents, edge labels

@app.patch("/api/components/{component_id}")
# Body: partial component update (status, lines_of_code, etc.)
# Returns: updated component
```

### C14-C18: Workspace Enrichment

```python
@app.get("/api/workspaces/{workspace_id}/detail")
# Returns: {
#   id, name, description,
#   agents: [{name, status, health, last_run_ago}],       # deployed services
#   missions: [{name, status, phase_label, progress}],     # non-complete
#   completed: [{name, completed_at}],                     # done but not deployed
#   last_activity, last_activity_at
# }

@app.patch("/api/workspaces/{workspace_id}/description")
# Body: {description: "string"}

@app.get("/api/workspaces/{workspace_id}/tasks")
# Returns: all tasks across all missions in workspace. ?status=running filter.

@app.get("/api/workspaces")
# ENRICHED response: add description, running_agents count, active_missions count,
# completed_missions_count, last_activity, last_activity_at, health, phase_label on missions
```

### C19-C21: CEO Mode + Event Stream

```python
@app.get("/api/agents")
# NEW PARAM: ?detail=ceo|full (default: ceo)
# CEO mode: [{status, activity, workspace_name}] — hide model, tokens, sessions
# Full mode: existing response (backward compatible)

@app.get("/api/events/stream")
# NEW PARAMS: ?detail=ceo|full (default: ceo), ?mission_id=X
# CEO mode: signals passed through CEO translator, only user-relevant events emitted
# mission_id: filter events to specific mission
```

### C22-C28: Remaining Endpoints

```python
@app.post("/api/services/{service_id}/report")
# Body: {summary: "checked 47 emails, sent 3 alerts", metrics: {}}
# Stores on service record for dashboard display

@app.get("/api/usage")
# DE-STUB: aggregate token counts from llm_output signals by model/agent/workspace

@app.post("/api/missions/{mission_id}/cancel")  # MODIFY existing
# Now also cancels all pending/running tasks for the mission

@app.get("/api/services")
# ENRICHED: add last_run_ago, health, human-friendly schedule_label

@app.get("/api/tasks/{task_id}/signals")
# Filter signals by task's openclaw_session_id. CEO-translated by default.

@app.get("/api/tasks/{task_id}/files")
# Aggregate file paths from tool_start signals (write/edit operations)

@app.get("/api/components/{component_id}/files")
# List files in component directory, read contents with path safety validation
```

---

## Workstream D: Graph Enrichment

### D1: Enrich `build_graph()` (`jb_components.py`)

Current `build_graph()` returns placeholder data. Enrich:

**Node additions:**
- `mission_id` — direct field from component
- `description` — from component record
- `contract` — summary of input_type/output_type/config_fields
- `is_active` — boolean, true if any linked task is running
- `active_agent` — agent name + model from running task's session
- `built_by` — agent that completed the task (from task result)
- `progress_percent` — real value: completed_tasks / total_tasks * 100
- `display_status` — mapped from A2 labels (planned/building/built/live)

**Edge changes:**
- Normalize keys to `source` / `target` (not `from` / `to`)
- Auto-derive `label` from source component's `output_type` when label is null
- Add `display_label` for human-friendly edge text

### D2: Unify mock/real graph shapes (`jb_mock_data.py`)

Make mock graph return same enriched structure as real graph.

### D3: Graph SSE events (`jb_signal_reactor.py`)

Reactor emits structured events when component state changes:
- `graph.node.status` — component status changed
- `graph.node.progress` — progress updated  
- `graph.node.agent` — active agent changed
- `graph.edge.active` — data flowing through edge (gated on F1)

---

## Workstream E: Chat

### E1: Mission-scoped session keys (`jb_api.py`)

When `mission_id` is provided to `POST /api/chat`, use session key:
`agent:main:jbcp-frontend:company:{wid}:mission:{mid}`

### E2: Global chat session (`jb_api.py`)

When no `workspace_id` provided to `POST /api/chat`, use global session key:
`agent:main:jbcp-frontend:global`

Context injected via E3.

### E3: Global dashboard context (`jb_openclaw_bridge.py`)

```python
def build_global_summary() -> str:
    """Compact summary of all workspaces for global chat context injection.
    
    Returns something like:
    'You manage 3 companies. Work Automation Co has 2 running agents and 1 mission building.
     Trading Co has 1 running agent. Personal Projects has 1 mission in planning.'
    """
```

### E4: Component catalog in plan generation (`jb_plan_generate.py`)

When generating a plan, inject existing components into the worker prompt:

```python
def _build_component_catalog() -> str:
    """Build compact summary of all built/deployed components for reuse awareness.
    
    Returns:
    'Available components (reuse if applicable):
     - Gmail Connector (connector): input=None, output=email_list, config=[credentials_path, max_results]
     - Email Filter (processor): input=email_list, output=email_list, config=[filter_rules]
     ...'
    """
```

Cap at 20 components. Filter to status in (built, passing, deployed).

### E5: Planning context enhancement (Plugin JS)

Plugin injects current plan items/components into planning chat context so the AI knows what's been generated so far.

### E6: Plugin mission-scoped session keys (Plugin JS)

Plugin recognizes and handles the new `company:{wid}:mission:{mid}` session key format.

---

## Workstream F: Pipeline & Deployment

### F1: Pipeline Generator (`runtime/jb_pipeline.py`)

**This is the largest single task.** Generates executable `pipeline.py` from a mission's component graph.

```python
def generate_pipeline(mission_id: str) -> str:
    """Generate pipeline.py content from mission's component graph.
    
    1. Read components and connections for this mission
    2. Topological sort based on connections (data flow order)
    3. Validate contracts: source.output_type must match target.input_type
    4. Generate Python code that imports each component's run() and chains them
    
    Returns: Python source code as string
    """

def write_pipeline(mission_id: str, output_dir: Path) -> Path:
    """Generate and write pipeline.py to disk. Returns path."""

def run_pipeline(mission_id: str) -> dict:
    """Generate pipeline, run in subprocess, return results.
    Returns: {exit_code: int, stdout: str, stderr: str, duration_ms: int}
    """
```

**Generated code shape:**
```python
#!/usr/bin/env python3
"""Auto-generated pipeline for mission: {mission_name}"""
import sys
from pathlib import Path

# Add component directories to path
sys.path.insert(0, str(Path(__file__).parent))

from components.gmail_connector.main import run as gmail_connector
from components.email_filter.main import run as email_filter  
from components.telegram_sender.main import run as telegram_sender

def pipeline():
    # Stage 1: Gmail Connector
    result_gmail = gmail_connector(config={
        "credentials_path": ".credentials/gmail.json",
        "max_results": 50,
    })
    
    # Stage 2: Email Filter  
    result_filter = email_filter(
        config={"filter_rules": ["from:boss"]},
        input_data=result_gmail,
    )
    
    # Stage 3: Telegram Sender
    result_telegram = telegram_sender(
        config={"bot_token": "...", "chat_id": "..."},
        input_data=result_filter,
    )
    
    return result_telegram

if __name__ == "__main__":
    result = pipeline()
    print(f"Pipeline complete: {result}")
```

**Contract validation:**
- For each connection: source component's `output_type` must match target component's `input_type`
- If mismatch, raise `ContractValidationError` with details
- If no connections, components run in item order

### F2: Component Directory Scaffolding

After coding agents complete a component, verify the directory structure:
```
data/companies/{workspace_id}/components/{component_name}/
├── contract.py    # Dataclass definitions
├── main.py        # def run(config, input_data=None) -> output
└── test_main.py   # Tests
```

```python
def validate_component_directory(workspace_id: str, component_id: str) -> dict:
    """Check component has required files. Returns {valid: bool, missing: [str], errors: [str]}"""

def scaffold_component_directory(workspace_id: str, component_id: str) -> Path:
    """Create directory structure with template files if missing."""
```

### F3: Prescriptive Task Prompts (`jb_openclaw_bridge.py`) — **P0 HIGHEST RISK**

**This is the highest risk item. If agents don't produce conformant components, the pipeline runner can't compose them.**

When dispatching a coding task, the prompt MUST include the exact component contract specification:

```python
def _build_component_task_prompt(task: dict, component: dict) -> str:
    """Build prescriptive prompt that constrains agent output to match the component interface.
    
    The prompt must specify:
    1. Exact directory to create files in
    2. contract.py with exact dataclass definitions (Config, Input, Output)
    3. main.py with exact function signature: def run(config: Config, input_data: Input = None) -> Output
    4. test_main.py with at least one test
    5. What input_data shape to expect (from upstream component's output_type)
    6. What output shape to produce (for downstream component's input_type)
    """
```

**Example task prompt:**
```
You are building the "Email Filter" component for the "Gmail Checker" mission.

## Component Specification

**Directory:** data/companies/{workspace_id}/components/email_filter/

**You MUST create exactly these files:**

### contract.py
```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class Config:
    filter_rules: List[str] = field(default_factory=list)

@dataclass  
class Input:
    emails: List[dict]  # Each dict has: sender, subject, body, date

@dataclass
class Output:
    filtered_emails: List[dict]  # Same shape as input, but filtered
    filter_count: int
```

### main.py
```python
from .contract import Config, Input, Output

def run(config: Config, input_data: Input = None) -> Output:
    # Your implementation here
    # MUST return an Output instance
    ...
```

### test_main.py
```python
from .contract import Config, Input
from .main import run

def test_basic_filter():
    config = Config(filter_rules=["from:boss@company.com"])
    input_data = Input(emails=[...test data...])
    result = run(config, input_data)
    assert isinstance(result.filtered_emails, list)
```

## Context
- This component receives input from: Gmail Connector (output type: email_list)
- This component sends output to: Telegram Sender (input type: email_list)
- The filter_rules config specifies which emails to keep
```

### F4: "Try It" Endpoint

```python
@app.post("/api/missions/{mission_id}/try")
async def try_mission(mission_id: str):
    """Generate pipeline and run once. Returns results."""
    # 1. Validate all components are built
    # 2. Generate pipeline via jb_pipeline.generate_pipeline()
    # 3. Run in subprocess with timeout (60s default)
    # 4. Return {exit_code, stdout, stderr, duration_ms}
```

---

## Workstream G: Iterative Generate

### G1: Make generate idempotent (`jb_plan_generate.py`)

When `/mission generate` is called on a mission that already has items/components/connections:
1. Store the previous draft (for diff in G4)
2. Clear existing draft items/components/connections on the mission object
3. Include the previous graph in the prompt (G3) so the AI refines rather than starts fresh
4. Regenerate with full conversation history

### G2: Draft graph endpoint

```python
@app.get("/api/missions/{mission_id}/graph")
async def get_mission_graph(mission_id: str):
    """Returns the mission's draft component graph.
    
    Before approval: returns components/connections from mission.items (draft state)
    After approval: returns components/connections from the component registry (committed state)
    
    Response shape matches build_graph() output for consistent frontend rendering.
    """
```

### G3: Previous graph as context (`jb_plan_generate.py`)

When regenerating, inject into the worker prompt:
```
## Previous Architecture (refine this based on user feedback below)
Components: [list of component names, types, contracts]
Connections: [list of data flows]

## User Feedback Since Last Generation
[chat messages since the last /mission generate]

## Instructions
Update the architecture based on the user's feedback. Keep what works, change what they asked about. You can add, remove, or modify components.
```

### G4: Graph diff markers

After regeneration, compare new components to previous draft:
- Components with matching name+type: `changed: false`
- Components with matching name but different type/contract: `changed: true`
- New components: `new: true`
- Removed components: included in response as `removed: true`

### G5: Layout preservation across regenerations

`PATCH /api/missions/{mission_id}/graph-layout` stores `{node_id: {x, y}}`.

When regenerating, if a component name/type matches a previous one, the frontend reuses its stored position. New components get auto-placed. This is mostly a frontend concern — backend just stores and returns positions.

---

## Workstream H: Feedback & Developer Tools

### H1: Agent Decision Logging

Modify task prompts to instruct agents to log key decisions:
```
When you make a significant design decision, output a line:
DECISION: [what you decided] — [why]

Example:
DECISION: Using async/await for Gmail API calls — the API supports batching and we need to handle rate limits
```

Parse `DECISION:` lines from task results, store on the task record, surface as system messages in mission chat.

### H2: Post-hoc Iteration

When user replies to a decision/question in mission chat:
1. Identify which component/task the reply relates to
2. Include the user's reply as additional context in the next task dispatch for that component
3. If the component is already built, create a new task to modify it

### H3: Edge Animation Events (Gated on F1)

When pipeline runner executes each component:
```python
emit_event("graph.edge.active", {
    "source_component_id": "...",
    "target_component_id": "...",
    "data_preview": "47 emails",
})
```

**Do not build until F1 (pipeline runner) is complete and working.**

### H4: Graph Layout Persistence

```python
@app.patch("/api/missions/{mission_id}/graph-layout")
# Body: {"positions": {"component_id": {"x": 100, "y": 200}, ...}}
# Stores on mission record

@app.get("/api/missions/{mission_id}/graph-layout")
# Returns: {"positions": {...}} or {}
```

---

## Frontend (webui/)

### Structural Changes

1. **Rebrand:** "JBCP Control Plane" → "Salt Desktop"
2. **Sidebar:** Replace Workspaces/Activity/Agents/Debug with:
   - Home (living dashboard)
   - Companies (sidebar tree with agents + missions per company)
   - My AI (swarm + services)
   - Component Library
   - Settings (debug toggle, connection status)
3. **Bottom ticker:** SSE-driven scrolling event text
4. **Heartbeat indicator:** Top-right, shows active worker count

### Pages

| Page | File | Backend Dependencies |
|------|------|---------------------|
| Home | `pages/home.js` (new) | C2, C3, C4, C5 |
| Company View | `pages/company.js` (new) | C14, C15, C18 |
| Mission View | `pages/mission.js` (rewrite of workspace.js) | G2, C12, E1, D1 |
| My AI | `pages/myai.js` (new) | C6, C7, C25 |
| Component Library | `pages/library.js` (new) | C17 |
| Settings | `pages/settings.js` (rewrite of debug.js) | C19, C23 |

### Component Graph Renderer

Create `components/graph.js`:
- Canvas or SVG-based renderer
- Node states: planned (gray border), building (yellow glow + pulse), built (green), live (green + subtle breathing)
- Edge labels from component contracts
- Drag-to-reposition nodes, positions saved via H4
- Click node for detail slideout
- Color coding per PRD: gray → yellow → green → blue (testing) → green (live)

### Chat Component

Update existing chat in `pages/mission.js`:
- Split view: chat left, graph right
- Command palette (already exists, keep)
- Typing indicator (already exists, keep)
- System messages for agent decisions (H1) rendered differently from user/AI messages
- "Generate" button triggers `/mission generate`, updates graph on right
- "Build It" button triggers `/mission approve`

---

## Build Order

**Phase 1 — Foundation + Frontend Structure**
- A1, A2, A4 (new modules)
- B1-B8 (data model changes)
- C1 (bug fix)
- Frontend: rebrand, new sidebar, new page structure, bottom ticker, heartbeat

**Phase 2 — Dashboard & Views + Frontend Pages**
- C2-C7 (dashboard endpoints)
- C14-C18 (workspace enrichment)
- C25 (enriched services)
- A3 (swarm module)
- D1-D2 (graph enrichment)
- Frontend: Home page, Company View, My AI page

**Phase 3 — Graph & Iterative Generate + Frontend Graph Renderer**
- G1-G5 (iterative generate)
- C12, C13 (mission graph filter, component PATCH)
- D3 (graph SSE events)
- Frontend: graph renderer component, Mission View with split chat+graph

**Phase 4 — Chat & Context**
- E1-E6 (session keys, global chat, component catalog, plugin updates)
- Frontend: chat improvements, global dashboard chat

**Phase 5 — CEO Mode**
- C19-C21 (CEO query param, CEO event stream, SSE filter)
- Frontend: CEO/dev mode toggle in Settings

**Phase 6 — Pipeline & Deployment**
- F1-F4 (pipeline generator, scaffolding, task prompts, "Try It")
- C8-C10, C24 (deploy, undeploy, start, cancel)
- Frontend: "Try It" button, "Go Live" flow, deploy/undeploy controls

**Phase 7 — Feedback & Dev Tools**
- H1-H4 (decision logging, post-hoc iteration, edge animation, layout persistence)
- C22, C23, C26-C28 (service reports, usage, signal timeline, file trees, code views)
- Frontend: developer mode panels, signal timeline, file tree, code viewer

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
- Native macOS app (builds against this same API when ready)

---

## Testing Strategy

- Write tests alongside code — every new function gets a test
- Run `python -m pytest tests/ -q` after each module completion
- New test files for new modules: `test_ceo_translator.py`, `test_labels.py`, `test_swarm.py`, `test_signal_reactor.py`, `test_pipeline.py`
- Extend existing test files for modifications: `test_services.py`, `test_missions.py`, `test_companies.py`, `test_components.py`, `test_api_flow.py`
- Target: maintain >90% pass rate during development, 100% before declaring a phase complete

---

## Acceptance Criteria

The v1 is shippable when:

1. A user can create a company, create a mission, chat about what they want to build
2. They can run `/mission generate` multiple times, watching the graph evolve
3. They can click "Build It" and watch workers appear in the swarm, components light up on the graph
4. They can see agent decisions in the chat
5. They can click "Try It" to run the built system once
6. They can click "Go Live" to deploy as a service
7. The home dashboard shows running services, active builds, and recent activity
8. Everything uses CEO-mode language — no agent names, PIDs, session IDs, or technical jargon in the default view
9. Developer mode toggle reveals full technical detail
10. The whole thing runs at localhost:8718 and feels alive
