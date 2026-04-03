# runtime/jb_labels.py

**Path:** `runtime/jb_labels.py`
**Purpose:** Single source of truth for all user-facing label translations. The frontend consumes these via the API.

## Label Dictionaries

### `MISSION_PHASE_LABELS`
| Internal | Display |
|----------|---------|
| planning | Planning |
| planned | Ready to Build |
| active | Building |
| complete | Ready to Deploy |
| deployed | Running |
| failed | Failed |
| cancelled | Cancelled |

### `SERVICE_STATUS_LABELS`
running -> Healthy, paused -> Paused, stopped -> Stopped, error -> Problem

### `COMPONENT_DISPLAY_STATUS`
planned -> Planned, building -> Building, built -> Built, testing -> Testing, passing -> Built (collapsed for CEO mode), failing -> Problem, deployed -> Live

### `WORKER_ROLE_LABELS`
coding -> Coder (hammer icon), research -> Researcher (magnifier), document -> Writer (pencil), analysis -> Analyst (chart)

### `COMPONENT_TYPE_ICONS`
connector -> plug, processor -> gear, ai -> brain, output -> arrow-right, scheduler -> clock, storage -> database, config -> sliders

## Functions

- `mission_label(status) -> str`: Returns human-friendly mission phase label
- `service_label(status) -> str`: Returns human-friendly service status
- `component_label(status) -> str`: Returns human-friendly component status
- `worker_role(task_type) -> dict`: Returns `{label, icon}` for a task type
- `component_icon(comp_type) -> str`: Returns icon name for a component type
