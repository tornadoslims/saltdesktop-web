# runtime/jb_ceo_translator.py

**Path:** `runtime/jb_ceo_translator.py`
**Purpose:** CEO-mode translator. Converts raw signal events and task status changes into human-readable activity text. The CEO does not care about tool names or session IDs -- they want "what is the AI doing right now?" in plain English.

## Classes

### `CeoActivity` (dataclass)
- `text: str` -- "Writing the email parsing logic"
- `category: str` -- "building" | "testing" | "thinking" | "reading" | "error"
- `component_name: str | None` -- "Email Parser" or None
- `icon: str` -- "hammer" | "magnifier" | "brain" | "check" | "warning"

## Functions

### `translate_signal(signal, task_lookup=None, component_lookup=None) -> CeoActivity`
Translates a raw signal into CEO-friendly activity. Translation rules (evaluated in order):

| Signal | Condition | Text | Category |
|--------|-----------|------|----------|
| tool_start | source=web/http | "Researching" | reading |
| tool_start | label contains write/edit | "Writing {component}" | building |
| tool_start | label contains pytest/test | "Running tests" | testing |
| tool_start | label contains read | "Reviewing code" | reading |
| llm_input | any | "Thinking..." | thinking |
| tool_end | has error | "Hit an issue, retrying" | error |
| subagent_spawned | any | "Starting a new worker" | building |
| fallback | has component | "Working on {component}" | building |
| fallback | no component | "AI is active" | building |

Component name is resolved via chain: `signal.session_id -> task_lookup -> task.component_id -> component_lookup -> component.name`

### `translate_task_status(task, component=None) -> CeoActivity`
Translates task status changes:
- complete -> "Finished building {component}" (check icon)
- failed -> "{component} needs attention" (warning icon)
- running/dispatched -> "Started building {component}" (hammer icon)
- pending -> "{component} queued" (clock icon)
