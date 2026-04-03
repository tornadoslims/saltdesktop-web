# JBCP Event Stream Specification

## Overview

The frontend connects to the JBCP backend with exactly **two SSE connections**:

1. **Event Stream** (`GET /api/events/stream`) — ONE connection, always open. Receives ALL system events: state changes, agent activity, tool calls, keepalives. This drives every UI update outside of chat.
2. **Chat** (`POST /api/chat`) — ONE per message. Send a message, stream the agent's response, connection closes when done.

No Redis, no external dependencies. Events are in-memory (JBCP mutations) + file-tailed (agent signals from OpenClaw plugin). The API server merges both sources into one unified stream.

---

## Event Stream

### Connecting

```swift
// Swift EventSource (or any SSE client)
let url = URL(string: "http://localhost:8718/api/events/stream")!
let eventSource = EventSource(url: url)

eventSource.onMessage { event in
    let data = try JSONDecoder().decode(JBCPEvent.self, from: event.data)
    handleEvent(data)
}
```

```javascript
// JavaScript
const events = new EventSource('http://localhost:8718/api/events/stream');
events.onmessage = (e) => handleEvent(JSON.parse(e.data));
```

### Event Format

Every event is a JSON object with a `type` field:

```json
{
  "type": "mission.created",
  "timestamp": "2026-03-29T14:30:00Z",
  "workspace_id": "ws_123",
  ...event-specific fields
}
```

### Event Types

#### JBCP State Changes (instant, from command handler)

| Type | When | Key Fields | Frontend Action |
|------|------|-----------|-----------------|
| `mission.created` | `/mission new` | workspace_id, mission_id, goal | Add mission to sidebar |
| `mission.switched` | `/mission switch` | workspace_id, mission_id, goal | Update focused indicator |
| `mission.completed` | All tasks done | workspace_id, mission_id | Update status badge |
| `mission.failed` | Tasks exhausted | workspace_id, mission_id | Show error state |
| `plan.created` | `/mission new` | workspace_id, plan_id, title | Show planning banner |
| `plan.generated` | `/plan generate` | workspace_id, plan_id, item_count, component_count | Populate plan panel |
| `plan.approved` | `/plan approve` | workspace_id, plan_id, tasks_created, components_created | Show graph + tasks |
| `plan.cancelled` | `/plan cancel` | workspace_id, plan_id | Clear plan panel |

#### Agent Activity (from OpenClaw plugin signals, ~0.5s latency)

| Type | When | Key Fields | Frontend Action |
|------|------|-----------|-----------------|
| `agent.turn` | Agent completed a turn | agent_id, session_id, success, duration_ms | Update agent status |
| `agent.tool_call` | Agent calling a tool | agent_id, tool, params | Show in activity feed |
| `agent.tool_result` | Tool returned | agent_id, tool, ok, duration_ms | Update activity feed |
| `agent.session_start` | Session began | agent_id, session_id | Show agent active |
| `agent.session_end` | Session finished | agent_id, message_count, duration_ms | Show agent idle |
| `agent.subagent_spawned` | Subagent created | agent_id, child_session_key | Show in agent tree |
| `agent.subagent_ended` | Subagent finished | outcome, reason | Update agent tree |
| `message.received` | Inbound message | channel, conversation_id | (internal use) |

#### System

| Type | When | Key Fields | Frontend Action |
|------|------|-----------|-----------------|
| `system.health` | Every ~30s keepalive | workspaces, tasks_active, agents_active | Update status bar |

### Example Stream

```
data: {"type": "system.health", "timestamp": "...", "workspaces": 3, "tasks_active": 0}

data: {"type": "mission.created", "timestamp": "...", "workspace_id": "ws_123", "mission_id": "m_456", "goal": "Build email bot"}

data: {"type": "plan.created", "timestamp": "...", "workspace_id": "ws_123", "plan_id": "p_789", "title": "Build email bot"}

data: {"type": "agent.tool_call", "type": "agent.tool_call", "agent_id": "main", "tool": "read", "params": {"file": "/path/to/file.py"}}

data: {"type": "plan.approved", "timestamp": "...", "workspace_id": "ws_123", "tasks_created": 5, "components_created": 3}

data: {"type": "agent.turn", "agent_id": "jbcp-worker", "success": true, "duration_ms": 8500}

data: {"type": "system.health", "timestamp": "...", "workspaces": 3, "tasks_active": 2}
```

---

## Chat Stream

### Sending a Message

```
POST /api/chat
Content-Type: application/json

{
  "workspace_id": "ws_123",
  "message": "Build me an email bot",
  "history": []
}
```

### Response (SSE)

**For regular messages** (proxied to agent):
```
data: {"content": "I'll help you", "model": "openclaw/main"}
data: {"content": " build that.", "model": "openclaw/main"}
data: {"done": true, "model": "openclaw/main"}
data: [DONE]
```

**For commands** (intercepted by backend):
```
data: {"content": "**Mission created: Build email bot**\nYou are now in planning mode...", "command": true, "command_type": "mission.new"}
data: {"done": true}
data: [DONE]
```

Commands are intercepted BEFORE reaching the agent. The response has `"command": true` so the frontend knows it's not agent output.

When a command is processed, the event stream ALSO receives the corresponding event (e.g., `mission.created`). The frontend should use the event stream to update the UI, not the chat response.

---

## Frontend Integration Pattern

```swift
class JBCPClient {
    private var eventSource: EventSource?

    func connect() {
        // One event stream connection — stays open forever
        eventSource = EventSource(url: "http://localhost:8718/api/events/stream")
        eventSource?.onMessage { [weak self] event in
            self?.handleEvent(event)
        }
    }

    func sendChat(workspaceId: String, message: String) async -> AsyncStream<ChatChunk> {
        // Per-message SSE — opens, streams, closes
        let request = ChatRequest(workspace_id: workspaceId, message: message)
        return streamSSE(url: "http://localhost:8718/api/chat", body: request)
    }

    private func handleEvent(_ event: JBCPEvent) {
        switch event.type {
        case "mission.created":
            store.addMission(event.workspaceId, event.missionId, event.goal)
        case "plan.approved":
            store.refreshTasks(event.workspaceId)
            store.refreshGraph(event.workspaceId)
        case "agent.tool_call":
            store.addActivityItem(event)
        case "system.health":
            store.updateHealth(event)
        default:
            break
        }
    }
}
```

### When to Re-fetch vs Update In Place

| Event | Action |
|-------|--------|
| `mission.created/switched` | Re-fetch `GET /api/workspaces/:id/missions` |
| `plan.generated/approved` | Re-fetch `GET /api/missions/:id/plan` and `GET /api/workspaces/:id/graph` |
| `task.completed/failed` | Update task in place from event data, or re-fetch task list |
| `component.status_changed` | Update graph node in place |
| `agent.tool_call/result` | Append to activity feed (no re-fetch) |
| `system.health` | Update status bar counters in place |

---

## Architecture

```
┌──────────────────────────────────────┐
│  Swift App                           │
│                                      │
│  EventSource ←── GET /events/stream  │  (one connection, always open)
│  Chat SSE   ←── POST /api/chat       │  (per message)
│  REST polls ←── GET /api/*           │  (on-demand, driven by events)
└───────────────┬──────────────────────┘
                │
                ▼
┌──────────────────────────────────────┐
│  JBCP API Server (port 8718)         │
│                                      │
│  In-memory event bus (asyncio.Queue) │ ← JBCP mutations
│  Signal file tailer                  │ ← Agent activity from OpenClaw
│  Chat proxy to OpenClaw              │ ← Forwards to gateway
└───────────────┬──────────────────────┘
                │
                ▼
┌──────────────────────────────────────┐
│  OpenClaw Gateway (port 18789)       │
│  + jbcp-observer plugin              │
│    writes signals to JSONL file      │
└──────────────────────────────────────┘
```

No Redis. No external dependencies. Three processes, two SSE streams, REST for on-demand data.
