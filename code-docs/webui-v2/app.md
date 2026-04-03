# webui-v2/app.js

**Path:** `webui-v2/app.js` (1,094 lines)
**Purpose:** Core application module containing the API client, global state management, hash-based router, sidebar rendering, status bar/ticker, SSE event stream connection, and canvas-based graph renderer.

## Key Objects

### `API`
HTTP client wrapping `fetch()`.
- `get(path)`: GET request, returns parsed JSON
- `post(path, data)`: POST with JSON body
- `stream(path)`: Returns an `EventSource` for SSE

### `State`
Global application state, single source of truth.

**Data stores:**
- `workspaces: []` -- all workspaces
- `missions: {}` -- workspace_id -> [missions]
- `services: []` -- all services
- `components: {}` -- workspace_id -> [components]
- `graphs: {}` -- workspace_id -> {nodes, edges}
- `chatHistory: {}` -- cache key -> {messages, total}
- `health: null` -- system health

**Key methods:**
- `loadAll()`: Parallel-fetches workspaces, services, agents, health; then loads missions, components, and graphs for each workspace
- `loadChatHistory(workspaceId, missionId)`: Fetches chat history from API
- `getMission(missionId)`: Searches all workspaces for a mission
- `getMissionPhase(mission)`: Computes phase from component statuses: planning, building, complete, live

**Change notification:** `onChange(fn)` / `_notify(key)` pattern for reactive updates

### `Router`
Hash-based SPA router.
- `register(name, view)`: Register a view for a route
- `go(route)`: Navigate by setting `location.hash`
- `_onRoute()`: Parses hash, destroys previous view, renders new view
- Routes: `dashboard`, `company/{id}`, `mission/{id}`, `library`, `connectors`, `settings`
- `myai` route redirects to `dashboard`

### `Sidebar`
Renders the left navigation panel.
- Lists workspaces with expandable sections
- Shows missions grouped under each workspace with phase dots (running, building, planning, complete)
- "New Agent" and "New Company" buttons with modal dialog
- Highlights active route

### `Ticker`
Bottom status bar event feed.
- `addEvent(evt)`: Adds event with icon and text, max 20 items
- Duplicates items for seamless scrolling animation

### `SSE`
Server-Sent Events connection for live updates.
- Connects to `/api/events/stream?detail=ceo`
- Dispatches meaningful signal events to Ticker
- Updates status bar summary from `system.health` events
- Forwards events to current view's `onEvent()` handler

### `GraphRenderer`
Canvas-based N8N-style component graph.
- `init(canvas, nodes, edges, options)`: Sets up canvas with nodes and edges
- Auto-layouts nodes using topological sort and level-based positioning
- Renders: rounded rect nodes with type icons, status badges, progress bars, connection lines with labels
- Supports zoom (mouse wheel), pan (drag), and hover tooltips
- Planning mode renders lightweight preview nodes

### `SaltApp`
App initialization.
- `init()`: Loads all state, initializes sidebar, router, ticker, SSE connection
- Registers all views
- Sets up auto-refresh on tab visibility change

## API Calls Made

- `GET /api/workspaces`
- `GET /api/services`
- `GET /api/agents`
- `GET /api/health`
- `GET /api/workspaces/{id}/missions`
- `GET /api/workspaces/{id}/components`
- `GET /api/workspaces/{id}/graph`
- `GET /api/workspaces/{id}/chat/history`
- `POST /api/workspaces` (create company)
- `POST /api/workspaces/{id}/missions` (create agent)
- `GET /api/events/stream?detail=ceo` (SSE)
