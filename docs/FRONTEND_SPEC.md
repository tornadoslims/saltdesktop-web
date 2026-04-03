# JBCP Frontend Specification

## Overview

Build a web-based chat frontend that connects to an OpenClaw gateway and provides multi-channel workspaces (companies) with mission planning, task tracking, and full JBCP control plane integration.

Each "channel" in the frontend maps to a JBCP Company. Each company has its own chat session, missions, plans, and context injection — mirroring how Discord channels work with OpenClaw today.

---

## Architecture

```
Frontend (React/Next.js/whatever)
    ↓ WebSocket + REST
OpenClaw Gateway (localhost:18789)
    ↓
JBCP Plugin (jbcp-observer)
    ↓ reads/writes
JBCP Runtime (Python, JSON files)
    ↓
Dashboard (Textual TUI, reads same files)
```

The frontend does NOT talk to JBCP directly. It talks to OpenClaw's gateway, which routes messages to agents. The JBCP plugin handles company auto-creation, context injection, and command routing behind the scenes.

---

## Gateway Connection

### Authentication

```
Token auth: Pass OPENCLAW_GATEWAY_TOKEN in connect params
Default port: 18789
```

### Option A: OpenAI-Compatible REST (Simplest)

```http
POST http://localhost:18789/v1/chat/completions
Authorization: Bearer <token>
Content-Type: application/json

{
  "model": "openclaw/main",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": true
}
```

Streaming SSE response, identical to OpenAI format. Works with any ChatGPT-compatible client library.

**Limitation:** No session isolation per channel. All messages go to the same session.

### Option B: WebSocket Protocol (Full Features)

Connect to `ws://localhost:18789` with JSON frames.

**Handshake:**
```json
{
  "type": "req",
  "id": "connect-1",
  "method": "connect",
  "params": {
    "minProtocol": 3,
    "maxProtocol": 3,
    "client": {
      "id": "jbcp-frontend",
      "version": "1.0.0",
      "platform": "web",
      "mode": "webchat"
    },
    "role": "operator",
    "scopes": ["operator.read", "operator.write"],
    "auth": { "token": "GATEWAY_TOKEN" }
  }
}
```

**Send message to a specific channel/session:**
```json
{
  "type": "req",
  "id": "msg-1",
  "method": "chat.send",
  "params": {
    "message": "Build a trading bot",
    "agentId": "main",
    "sessionKey": "agent:main:jbcp-frontend:channel:my-company-id",
    "idempotencyKey": "unique-uuid-per-message"
  }
}
```

**Receive agent responses:**
```json
{
  "type": "event",
  "event": "chat.event",
  "payload": {
    "text": "I'll help you build that. Let's start with...",
    "sessionKey": "agent:main:jbcp-frontend:channel:my-company-id"
  }
}
```

**Session key format for channel isolation:**
```
agent:main:jbcp-frontend:channel:<COMPANY_ID>
```

Each company gets its own session key, giving isolated conversation history.

---

## Channel/Company Model

### How Discord Does It

Discord channel → OpenClaw session key `agent:main:discord:channel:<DISCORD_CHANNEL_ID>`

The JBCP plugin sees the session key, extracts the channel ID, looks up the company mapping, and injects company+mission context into the agent's prompt.

### How Your Frontend Should Do It

1. **Frontend creates/manages companies** by calling the JBCP Python CLI (via a thin API layer or direct exec)
2. **Each company has a session key** derived from the company ID
3. **Messages sent with that session key** get routed to the correct agent session
4. **The JBCP plugin** sees the session key, matches the company, and injects context

### Session Key Convention

The JBCP plugin currently parses session keys matching `:discord:(channel:\d+)$`. For a custom frontend, extend this pattern. The plugin should recognize:

```
:jbcp-frontend:(company:<COMPANY_UUID>)$
```

OR: register the frontend as a channel source in the company mapping table with source `"jbcp-frontend"` instead of `"discord"`.

---

## Frontend Views

### 1. Sidebar — Company/Channel List

```
┌─────────────────────┐
│ JBCP                │
│                     │
│ ● Trading Bot Dev   │  ← active, has running tasks
│ ○ API Integration   │  ← idle
│ ✎ New Project       │  ← in planning mode
│ ○ General           │  ← default
│                     │
│ [+ New Company]     │
└─────────────────────┘
```

- Show company name, status icon (active/idle/planning)
- Highlight if tasks are running (from JBCP signals)
- Show unread/activity indicators
- Click to switch — loads that company's chat session

### 2. Main Chat Area

Standard chat interface with agent. Messages flow through the gateway with the company's session key.

**Special rendering:**
- When agent outputs a plan (JSON code block from `/plan generate`), render it as an interactive plan card
- When agent mentions tasks, link to the task detail view
- Show "Planning Mode" banner when active

### 3. Right Panel — Company Context

```
┌─────────────────────────┐
│ Trading Bot Dev         │
│ Status: active          │
│                         │
│ ── Focused Mission ──   │
│ Build websocket feed    │
│ [switch mission]        │
│                         │
│ ── Plan ──              │
│ ✎ Drafting (4 items)   │
│ 1. [coding] Setup WS   │
│ 2. [coding] Parse data  │
│ 3. [coding] Store DB    │
│ 4. [research] Test feed │
│ [Approve] [Regenerate]  │
│                         │
│ ── Tasks ──             │
│ ○ pending: 2            │
│ ● running: 1            │
│ ✓ complete: 5           │
│                         │
│ ── Context ──           │
│ Company: 450 chars      │
│ Mission: 320 chars      │
│ [Edit Context]          │
└─────────────────────────┘
```

### 4. Task Board View (Optional)

Kanban-style view of tasks across all missions:

```
| Pending    | Running    | Complete   | Failed    |
| ○ Task A   | ● Task C   | ✓ Task E   | ✗ Task G  |
| ○ Task B   | ● Task D   | ✓ Task F   |           |
```

Click a task to see full detail: goal, session ID, agent response, duration, errors.

---

## Data Sources

The frontend needs to read JBCP state. Two options:

### Option A: Read JSON Files Directly (Simple)

JBCP stores everything in `~/.openclaw/workspace/data/`:

```
data/jb_companies.json       — companies
data/jb_company_mappings.json — channel→company mappings
data/jb_missions.json        — missions
data/jb_plans.json           — plans
data/jb_queue.json           — tasks
data/signals/jbcp_signals.jsonl — real-time agent signals
logs/jbcp_events.jsonl       — JBCP events
```

Frontend polls these files (or watches with fs.watch) and renders state.

### Option B: Thin API Layer (Better)

Build a small HTTP API that wraps the Python CLI:

```
GET  /api/companies              → python -m runtime.jb_cli company list
GET  /api/companies/:id/missions → python -m runtime.jb_cli mission list --company-id :id
POST /api/companies/:id/missions → python -m runtime.jb_cli mission new --company-id :id --goal "..."
GET  /api/plans?company_id=:id   → python -m runtime.jb_cli plan status --company-id :id
POST /api/plans/:id/set-items    → python -m runtime.jb_cli plan set-items --plan-id :id --items-json "..."
POST /api/plans/:id/approve      → python -m runtime.jb_cli plan approve --plan-id :id
GET  /api/tasks                  → list from jb_queue.json
GET  /api/signals?limit=100      → tail from jbcp_signals.jsonl
GET  /api/context/:company_id    → python -m runtime.jb_cli contextmem --company-id :id
```

This keeps the Python runtime as single source of truth.

### Real-Time Updates

For live updates (signals, task status changes):

1. **Poll** — fetch `/api/signals` and `/api/tasks` every 2-3 seconds
2. **SSE stream** — build a small endpoint that tails `jbcp_signals.jsonl` and streams new lines
3. **WebSocket** — subscribe to gateway events for agent activity

---

## Commands

The frontend should support the same commands as Discord, either through a command palette or by sending them as messages:

| Command | What it does |
|---------|-------------|
| `/mission new <goal>` | Create mission + enter planning mode |
| `/mission list` | List all missions in this company |
| `/mission switch <name>` | Change focused mission |
| `/mission` | Show current mission status |
| `/plan generate` | Agent creates structured plan from conversation |
| `/plan approve` | Convert plan items to tasks |
| `/plan cancel` | Cancel active plan |
| `/plan` | Show current plan |
| `/contextmem` | Show what context is injected |

Commands are sent as regular messages through `chat.send`. The JBCP plugin intercepts them before the agent sees them (except `/plan generate` which the agent handles).

---

## Context Injection Integration

When the frontend sends a message with a company's session key, the JBCP plugin's `before_prompt_build` hook:

1. Parses the company ID from the session key
2. Reads company_context.md and mission_context.md
3. Appends them to the agent's system prompt via `appendSystemContext`

**The frontend does NOT need to handle context injection.** It happens transparently at the gateway level. The frontend just sends messages with the right session key.

For the plugin to recognize frontend session keys, update the session key parsing in the plugin:

```javascript
// Current: only matches Discord
const channelMatch = sk.match(/:discord:(channel:\d+)$/);

// Updated: matches any channel source
const channelMatch = sk.match(/:(discord|jbcp-frontend):(channel:\S+)$/);
```

And create company mappings with source `"jbcp-frontend"`:
```
python -m runtime.jb_cli company get-or-create \
  --source jbcp-frontend \
  --external-id "channel:<company-uuid>" \
  --name "My Company"
```

---

## Planning Mode UX

When a company is in planning mode (has a drafting plan):

1. **Show banner** at top of chat: "Planning Mode — chatting about: Build a trading bot"
2. **Show plan panel** in sidebar with current items (may be empty)
3. **Generate button** sends `/plan generate` as a message
4. **Agent responds** with structured plan AND calls the CLI to save items
5. **Plan panel updates** showing the generated items
6. **Approve button** sends `/plan approve`, which creates tasks
7. **Planning mode ends**, tasks appear in task board

The key insight: `/plan generate` is not a command that returns a static response. It triggers the agent to think, review the conversation, and produce a plan. The agent uses the `exec` tool to call `python -m runtime.jb_cli plan set-items` to persist the plan items.

---

## Tech Stack Recommendation

- **Framework:** Next.js or SvelteKit (SSR + API routes in one project)
- **WebSocket client:** native WebSocket or socket.io-client
- **State:** Zustand or Jotai (lightweight, good for real-time updates)
- **UI:** Tailwind + shadcn/ui or similar
- **Chat rendering:** Markdown renderer with code block support
- **API layer:** Next.js API routes wrapping `child_process.execSync` to call JBCP CLI

---

## Minimum Viable Version

1. Sidebar with company list (read from `jb_companies.json`)
2. Chat area connected to gateway via WebSocket with per-company session keys
3. Right panel showing focused mission + plan status
4. `/mission new`, `/plan generate`, `/plan approve` working through chat
5. Poll task status every 3 seconds

That gives you the core Discord-like experience with JBCP integration. Task board, context editing, and signal streaming are enhancements.
