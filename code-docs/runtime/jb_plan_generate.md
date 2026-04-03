# runtime/jb_plan_generate.py

**Path:** `runtime/jb_plan_generate.py` (719 lines)
**Purpose:** Mission plan generation. Reads chat history, calls LLM directly to generate structured components/connections/tasks, saves to mission. Supports idempotent regeneration with diff tracking.

## Main Entry Point

### `generate_mission_plan(mission_id, session_key=None) -> dict`
Full plan generation flow:

1. Validates mission exists and is in "planning" state
2. **Idempotent regeneration (G1)**: If items/components already exist, stores them as `_previous_draft` and clears the current draft
3. Fetches chat history from SQLite
4. Builds prompt via `build_generation_prompt()` (includes component catalog, previous architecture, new messages since last generation)
5. Calls LLM via `call_worker()` -> `_call_llm_direct()`
6. Parses structured JSON response via `parse_items_from_response()`
7. Normalizes task items
8. Saves items, components, connections, `_last_generated_at` to mission
9. **Computes graph diff (G4)**: Compares current vs previous, stores `_last_diff`
10. Builds display text with markdown formatting and diff markers

Returns: `{ok, mission_id, item_count, items, components, connections, diff, display}`

### `generate_preview(mission_id) -> dict`
Lightweight preview for the live draft graph during planning. Only returns component names + types and connections (no tasks, no full contracts). Requires at least 2 chat messages. Uses a compact prompt template.

## Prompt Building

### `build_generation_prompt(mission_goal, chat_history, existing_items, mission=None) -> str`
Assembles the LLM prompt with sections:
1. "You are a project planner" instructions
2. Component catalog for reuse awareness (E4)
3. Previous architecture context for regeneration (G3)
4. Messages since last generation
5. Conversation context (last 30 messages)
6. JSON response format specification (components, connections, tasks)
7. Rules: 2-8 components, clear contracts, 3-10 tasks, valid types

## LLM Calling

### `_call_llm_direct(prompt, system="") -> dict`
Calls the configured LLM provider directly. Reads provider/model from runtime settings or env vars. Supports both Anthropic and OpenAI paths. Returns `{ok: True, text: "..."}` or `{ok: False, error: "..."}`.

Default models: `claude-sonnet-4-20250514` (Anthropic), `gpt-4o` (OpenAI)

### `call_worker(prompt) -> dict`
Alias for `_call_llm_direct()`.

## Response Parsing

### `parse_items_from_response(text) -> dict`
Extracts components, connections, and tasks from LLM response text. Handles:
- Markdown code fences (strips them)
- Structured JSON with `components`/`connections`/`tasks` keys
- Nested JSON objects
- Flat JSON arrays
- Fallback to `items` key

Returns: `{components: [], connections: [], tasks: []}`

## Regeneration Support (G1-G4)

### `_store_previous_draft(mission) -> dict | None`
Saves current items/components/connections as `_previous_draft` for diffing.

### `_clear_draft(mission_id)`
Clears items, components, connections on the mission to prepare for regeneration.

### `_build_previous_graph_context(mission) -> str`
Builds prompt section describing the previous architecture for context when regenerating.

### `_get_messages_since(chat_history, since_timestamp) -> str`
Filters chat messages to only those after the last generation timestamp.

### `compute_graph_diff(mission) -> list[dict]`
Compares current components to `_previous_draft` by (name, type) key. Returns list of `{name, type, change}` where change is "added", "removed", "modified", or "unchanged".

## Component Catalog (E4)

### `_build_component_catalog() -> str`
Builds compact summary of all built/passing/deployed components across all workspaces. Capped at 20 components. Enables the LLM to suggest reusing existing components.
