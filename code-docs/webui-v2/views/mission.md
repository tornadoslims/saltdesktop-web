# webui-v2/views/mission.js

**Path:** `webui-v2/views/mission.js` (687 lines)
**Purpose:** Phase-adaptive mission view. Renders different layouts depending on the mission phase: Planning, Building, Complete, or Live.

## Lifecycle Bar

All phases show a horizontal lifecycle progress indicator: PLANNING -> SPEC'D -> BUILDING -> LIVE. The current phase is highlighted with an active dot. Phase-appropriate action buttons appear:
- Spec'd phase: "Build It" button
- Complete phase: "Deploy as Agent" button

## Phase: Planning (`_renderPlanning`)

50/50 split layout:
- **Left pane**: Chat interface with message history, input field, and send button
- **Right pane**: Component graph canvas with draft preview

Chat sends messages to `POST /api/chat` as SSE stream. Messages are rendered as user/assistant bubbles.

After sufficient conversation, a "Lock It In" button appears over the graph. Clicking it calls `POST /api/missions/{id}/generate` to create the plan, then transitions to the spec'd phase.

Draft graph preview is fetched from `POST /api/missions/{id}/generate-preview`.

## Phase: Building (`_renderBuilding`)

Shows the component graph with active build progress. Components show building/built status with progress percentages.

## Phase: Complete (`_renderComplete`)

Shows the final component graph. All components shown as built. "Deploy as Agent" action available.

## Phase: Live (`_renderLive`)

Shows the running service with health status, schedule, run history, and last run summary.

## API Calls Made

- `POST /api/chat` (SSE streaming)
- `GET /api/workspaces/{id}/chat/history?mission_id={id}`
- `POST /api/missions/{id}/generate`
- `POST /api/missions/{id}/generate-preview`
- `POST /api/missions/{id}/approve`
- `POST /api/missions/{id}/build`
- `POST /api/workspaces/{id}/promote`

## Graph Integration

Uses `GraphRenderer.init()` to render the component graph on a canvas element. Supports zoom, pan, and auto-layout.
