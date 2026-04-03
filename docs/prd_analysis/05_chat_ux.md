# PRD Analysis: Chat UX

**PRD Section:** Lines ~370-390 of APP_UX_PRD_FINAL_v0.1.md

---

## 1. Current Chat Implementation

### Chat Proxy (`jb_api.py`)
- `POST /api/chat` proxies to OpenClaw gateway via SSE streaming
- Session key format: `agent:main:jbcp-frontend:company:{workspace_id}`
- Accepts optional `mission_id` parameter (but currently IGNORED for session scoping)
- Command interception: messages starting with `/` are handled by `jb_commands.py` instead of proxied

### BUG FOUND: Session Key Inconsistency
- Chat proxy uses: `agent:main:jbcp-frontend:company:{id}` 
- `get_chat_history` uses: `agent:main:jbcp-frontend:channel:{id}`
- `clear_chat_history` uses: `agent:main:jbcp-frontend:channel:{id}`
- **History retrieval fetches from a different session than the proxy writes to!**

### Chat History
- `GET /api/workspaces/{id}/chat/history` reads from OpenClaw session store
- `DELETE /api/workspaces/{id}/chat/history` clears session

### Command Interception (`jb_commands.py`)
- Handles: `/mission`, `/status`, `/contextmem`, `/jbdebug`
- Returns JSON response that frontend displays as system message
- Commands bypass the AI entirely

---

## 2. PRD Requirements vs Current State

### Mission Chat (Planning + Building)
| Requirement | Current | Gap |
|-------------|---------|-----|
| Split view: chat + draft graph | Backend serves both — no gap | Frontend layout concern |
| Context scoped to mission + workspace | Plugin injects company + mission context | ✅ Working |
| AI as solution architect during planning | Plugin injects planning mode prompt | ✅ Working |
| Ghost nodes appearing during chat | ❌ Nothing exists | Need draft graph preview system |
| Chat during building phase | ✅ Chat always available | None |
| Chat after completion for iteration | ✅ Works | None |

### Global Dashboard Chat
| Requirement | Current | Gap |
|-------------|---------|-----|
| Cross-company view | No global session — each workspace has own session | Need global session key |
| AI knows everything via summary + tools | Context injection only for focused workspace | Need cross-workspace summary injection |
| "How's the Gmail Checker doing?" | AI would need CLI tool access to query services | Plugin needs global context path |

### Ghost Nodes (Draft Graph During Planning)
This is the most complex missing feature. The PRD says ghosted nodes appear on the graph as the user chats, evolving with the conversation.

**Implementation approach:**
1. After each chat turn during planning, trigger async analysis of conversation
2. Extract mentioned components/connections from conversation
3. Return a draft graph that updates alongside the chat
4. These are ephemeral — not stored in the component registry until plan generation

---

## 3. Concrete Coding Tasks

### v1

**Design change:** Ghost nodes replaced by iterative `/mission generate`. See `04_component_graph.md` for G1-G5 tasks.

| # | Task | File(s) | Effort |
|---|------|---------|--------|
| C1 | **Fix session key bug** — unify to `company:` prefix | `jb_api.py` | Tiny |
| C2 | **Mission-scoped session keys** — when mission_id provided, use `agent:main:jbcp-frontend:company:{wid}:mission:{mid}` | `jb_api.py` | Small |
| C5 | **Global chat session** — `POST /api/chat` with no workspace_id uses global session key with cross-workspace summary context | `jb_api.py` | Small |
| C6 | **Plugin update for new session key format** — plugin must recognize mission-scoped keys | Plugin (JS) | Small |
| C7 | **Global dashboard context** — plugin/bridge generates compact all-workspace summary for global chat | `jb_openclaw_bridge.py` | Medium |
| C8 | **Planning context enhancement** — inject current plan items/components into planning chat context | Plugin (JS) | Small |

### v2

| # | Task | Notes |
|---|------|-------|
| C3 | Draft graph preview endpoint — `POST /api/missions/{id}/draft-graph` accepts conversation text, returns ephemeral nodes/edges | Superseded by iterative generate. Only revisit if users want real-time ghost nodes beyond explicit generate. |
| C4 | Post-chat-turn preview trigger — after each planning chat message, async call to draft graph preview and push result via SSE | Superseded by iterative generate. Only revisit if users want real-time ghost nodes beyond explicit generate. |
| C9 | Global chat tools — AI can query/mutate any workspace via CLI during global chat | Requires tool registration |
| C10 | Auto-naming — mission name auto-derived from first few chat messages | LLM call + mission update |
| C11 | Full conversation history persistence beyond OpenClaw sessions | Backend-managed history |
| C12 | Draft graph diffing — highlight what changed since last turn | Requires graph diff algorithm |
| C13 | Cross-workspace component reuse suggestions in planning chat | Depends on component sharing |

---

## 4. Key Risks

1. **Draft graph quality** — extracting components from free-form conversation is an LLM task. Quality will vary. May need structured "thinking" prompt.
2. **Session isolation** — mission-scoped sessions mean switching missions loses context. Need clear UX for this.
3. **Global chat token limits** — summarizing all workspaces into context may exceed limits with many active workspaces.
