# runtime/jb_api.py

**Path:** `runtime/jb_api.py` (2,762 lines)
**Purpose:** FastAPI backend server on port 8718. Wraps all JBCP runtime modules. Planning chat uses direct Anthropic/OpenAI SDK calls. Building uses Claude Code CLI.

## Configuration

| Constant | Value | Meaning |
|----------|-------|---------|
| `VERSION` | `"0.4.0"` | API version |
| `PORT` | `8718` | Server port |
| `SECRETS_PATH` | `~/.missionos/credentials/secrets.json` | API keys location |
| `_mock_mode` | `False` | Global flag for mock data mode |
| `_planning_settings` | dict | Mutable runtime settings for LLM provider/model |

## API Key Reading

### `_read_openai_key() -> str | None`
Reads from env vars `SALT_OPENAI_API_KEY` or `OPENAI_API_KEY`, falling back to `secrets.json`.

### `_read_anthropic_key() -> str | None`
Reads from env var `ANTHROPIC_API_KEY`, falling back to `secrets.json`.

## Pydantic Request Models

- `CreateWorkspaceRequest`: `prompt: str | None`, `name: str | None`
- `PatchWorkspaceRequest`: `name: str | None`, `description: str | None`
- `CreateMissionRequest`: `goal: str`, `name: str | None`
- `ChatRequest`: `workspace_id: str`, `mission_id: str | None`, `message: str`, `history: list | None`
- `PatchMemoryRequest`: `content: str`
- `PromoteWorkspaceRequest`: `name`, `description`, `type`, `schedule`, `entry_point`, `has_frontend`
- `PlanningModelRequest`: `provider: str | None`, `model: str | None`

## Endpoints (~40 total)

### TIER 1 -- Direct Data Reads

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | System health: uptime, workspace/mission/task counts, event bus status |
| GET | `/api/workspaces` | List all workspaces with computed stage, health, activity metrics |
| POST | `/api/workspaces` | Create workspace; optionally creates initial mission from prompt |
| PATCH | `/api/workspaces/{id}` | Update workspace name/description |
| GET | `/api/workspaces/{id}/missions` | List missions for a workspace |
| POST | `/api/workspaces/{id}/missions` | Create a new mission in planning state |
| GET | `/api/missions/{id}/tasks` | List tasks for a mission |
| POST | `/api/missions/{id}/generate` | Generate plan (components + tasks) via LLM |
| POST | `/api/missions/{id}/generate-preview` | Lightweight preview for draft graph |
| POST | `/api/missions/{id}/approve` | Approve plan, create components, enqueue tasks |
| POST | `/api/missions/{id}/build` | Dispatch build tasks via Claude Code CLI |
| POST | `/api/missions/{id}/cancel` | Cancel mission and fail its active tasks |
| GET | `/api/commands` | List available slash commands |
| GET | `/api/workspaces/{id}/prompt-debug` | Show full prompt injection tree |
| GET | `/api/agents` | List agents (stub) |
| GET | `/api/missions/{id}/context` | Mission context summary |
| POST | `/api/tasks/{id}/retry` | Retry a failed task |
| GET | `/api/workspaces/{id}/memory` | Read company + mission context files |
| PATCH | `/api/workspaces/{id}/memory` | Write company context file |

### TIER 2 -- Chat (Direct LLM)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Streaming chat. Intercepts slash commands first, then proxies to LLM |
| GET | `/api/workspaces/{id}/chat/history` | Fetch conversation history from SQLite |
| DELETE | `/api/workspaces/{id}/chat/history` | Clear chat history |

### TIER 3 -- SSE Event Stream

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/events/stream` | Unified SSE stream with keepalive, CEO translation, mock signals |
| POST | `/api/signals/push` | Accept HTTP-pushed signals |

### TIER 4 -- Components, Services, Settings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/workspaces/{id}/components` | List components for a workspace |
| GET | `/api/workspaces/{id}/graph` | Component graph (nodes + edges) |
| GET | `/api/settings` | System settings (paths, version, model) |
| GET | `/api/settings/planning-model` | Current planning LLM settings |
| POST | `/api/settings/planning-model` | Update planning LLM provider/model |
| GET | `/api/live` | List running/starting services |
| GET | `/api/usage` | Aggregate token usage from signal data |
| POST | `/api/workspaces/{id}/promote` | Create a service from a workspace |
| GET | `/api/components` | Global component list with type/status filters |
| GET | `/api/components/library` | Components grouped by type |
| GET | `/api/components/{id}` | Single component detail |
| GET | `/api/services` | List services |
| GET | `/api/services/{id}` | Single service detail |
| POST | `/api/services/{id}/pause` | Pause a running service |
| POST | `/api/services/{id}/resume` | Resume a paused service |
| POST | `/api/services/{id}/stop` | Stop a service |
| POST | `/api/services/{id}/undeploy` | Stop service and revert mission to complete |
| POST | `/api/services/{id}/report` | Accept a run report |
| GET | `/api/services/{id}/runs` | List run history |
| GET | `/api/connections` | List all connector services with connection status |
| GET | `/api/mock/status` | Check mock mode |
| POST | `/api/mock/enable` / `/api/mock/disable` | Toggle mock mode |
| GET | `/api/reference` | Self-documenting API reference |

## Chat System -- Detailed Flow

### `_stream_planning_chat(req, mission)` (async generator)

1. Reads the planning provider and model from runtime settings
2. Builds system context via `_build_chat_context()` which includes: Santiago identity, company context file, mission context file, planning mode instructions, connected services, existing components
3. Loads chat history from SQLite (last 30 messages)
4. Saves user message to SQLite
5. For OpenAI: calls `client.chat.completions.create(stream=True)` with system message
6. For Anthropic: calls `client.messages.stream()` with system parameter
7. Streams SSE chunks in OpenAI-compatible format
8. Saves full assistant response to SQLite
9. Sends `[DONE]` sentinel

### `_build_chat_context(workspace_id, mission_id)` (1000+ chars)

Assembles system prompt sections:
1. Base identity ("You are Santiago...")
2. Company context from disk
3. Mission context with components and context file
4. Planning mode instructions (if mission is in planning state)
5. Connected services list
6. Existing built components

## Helper Functions

### `_compute_health(workspace_id) -> str`
Returns dot color: green (services running or all complete), yellow (building), red (failed), gray (idle).

### `_compute_stage(company, missions, tasks) -> str`
Derives workspace stage: "production", "planning", "building", "ready", "failed", "idle".

### `_company_to_workspace(company) -> dict`
Transforms internal company dict to workspace API response with computed fields (stage, health, activity metrics, session_key).

### `_relative_time(iso_timestamp) -> str`
Converts ISO timestamp to "5 minutes ago" style string.
