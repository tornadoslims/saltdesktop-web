# PRD Analysis: Deployment Model + Pipeline Runner

**PRD Section:** Lines ~446-555 of APP_UX_PRD_FINAL_v0.1.md

---

## 1. Current Service System vs PRD

### What Exists (`jb_services.py`)
- Service CRUD with: name, type (scheduled/daemon/webhook/manual), status, schedule, port
- Lifecycle: `create_service()`, `start_service()`, `pause_service()`, `resume_service()`, `stop_service()`
- Run tracking: `record_run()` with start/end/status
- Port allocation: `allocate_port()` assigns from 9100-9199 range
- `list_runs()` returns run history

### What's Missing
- **`start_service()` is a no-op** — sets status flag, doesn't launch anything
- **No `mission_id` on services** — can't link service back to mission
- **No pipeline runner** — `jb_pipeline.py` does not exist
- **No "Try It" capability** — no way to run a pipeline once
- **No actual process management** — no cron scheduling, no daemon launching, no health checks

---

## 2. Existing Runner Examples vs PRD Component Interface

### PRD Specifies:
```
components/gmail_connector/
├── contract.py    # Dataclass: Config, Input, Output
├── main.py        # def run(config) -> Output
└── test_main.py   # Tests
```

### Existing Runners:
- `email_digest_runner.py` — monolithic script, imports from sibling modules (`email_digest_gmail.py`, etc.), uses hardcoded config
- `cryptodash_runner.py` — same pattern, monolithic

**Gap:** Existing runners do NOT follow the PRD's component interface. They're hand-written integration scripts, not auto-generated pipelines from the component graph. They prove the concept (import + call) but aren't structurally aligned.

---

## 3. What jb_pipeline.py Needs to Do

1. **Read component graph** for a mission — ordered by connection topology
2. **Generate `pipeline.py`** — imports each component's `run()` function, chains them per connections
3. **Inject config** — each component's `config_fields` from contract become constructor args
4. **Validate contracts** — output_type of source must match input_type of target
5. **Handle errors** — try/except per component with meaningful error messages
6. **Support "Try It"** — run generated pipeline once, capture output
7. **Support "Go Live"** — register as OpenClaw cron/daemon task

### Generated Pipeline Shape:
```python
# Auto-generated from component graph for mission {mission_id}
from components.gmail_connector.main import run as gmail_connector
from components.email_filter.main import run as email_filter
from components.telegram_sender.main import run as telegram_sender

def pipeline():
    emails = gmail_connector(gmail_config)
    filtered = email_filter(filter_config, emails)
    telegram_sender(telegram_config, filtered)

if __name__ == "__main__":
    pipeline()
```

---

## 4. "Try It" and "Go Live" Backend Requirements

### "Try It" (Run Once)
- `POST /api/missions/{id}/try` 
- Generates pipeline if not exists, runs it once in subprocess
- Returns: stdout, stderr, exit code, duration
- Streaming optional (SSE of output lines)

### "Go Live" (Deploy)
- `POST /api/missions/{id}/deploy`
- Creates service record linked to mission
- Sets up OpenClaw cron/daemon based on service type
- Mission status → `deployed`
- Returns service ID

### "Stop" (Undeploy)
- `POST /api/services/{id}/undeploy`
- Kills running process/removes cron
- Mission status → `complete` (ready to redeploy)

---

## 5. Concrete Coding Tasks

### v1 — Critical Path

| # | Task | Effort | Priority |
|---|------|--------|----------|
| 1 | **`jb_pipeline.py` — pipeline generator** — topological sort of components, generate pipeline.py from template | Medium-Large | P0 — blocks everything |
| 2 | **Component directory scaffolding** — ensure each component has contract.py/main.py/test_main.py after agent builds it | Medium | P0 |
| 3 | **Contract validation** — verify output→input type compatibility across connections | Small | P0 |
| 4 | **`POST /api/missions/{id}/try`** — generate + run once + return results | Medium | P1 |
| 5 | **`POST /api/missions/{id}/deploy`** — create service, link to mission, set status | Medium | P1 |
| 6 | **`POST /api/services/{id}/undeploy`** — stop + unlink | Small | P1 |
| 7 | **Mission → service linkage** — add `mission_id` to service model | Small | P1 |
| 8 | **Coding agent task prompts** — include component contract spec in task prompt so agents produce the right interface | Medium | P1 |

### v2

| # | Task | Notes |
|---|------|-------|
| 9 | Real cron scheduling via OpenClaw or launchd | Actual "always-on" |
| 10 | Daemon process management (start/stop/restart/health) | Real process lifecycle |
| 11 | Standalone app deployment (binary packaging) | PRD explicitly marks as v2 |
| 12 | Pipeline hot-reload (swap component without regenerating) | Optimization |

---

## 6. Key Risk: The Coding Agent Output Problem

The entire pipeline model assumes coding agents produce components with the exact interface: `contract.py` + `main.py` with `def run(config)`. Today, coding agents just write code however they want. The task prompt must be extremely prescriptive about the expected output structure, or the pipeline generator will fail.

This is the **highest risk item** in the deployment model. If agents don't reliably produce the right interface, nothing downstream works.
