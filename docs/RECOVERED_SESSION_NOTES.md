# Recovered Session Notes -- March 30, 2026

Extracted from conversation `8d204a82-245c-4eff-9dc4-50783f341cdf` (13MB, 2661 lines JSONL). This document captures product direction, UX decisions, object model changes, and architecture decisions made during that session.

---

## 1. Object Model: Plan-to-Mission Merge

The user questioned the entire Plan construct mid-session:

> "do we need plans under missions? couldnt each mission just be a plan and we could remove the entire plan construct all together? would that simplify things? how would that impact user experience and flexibility? i am asking bc i designed the entire thing and now i'm wondering why wouldnt i just create a bunch of missions versus a mission and then having a bunch of plan objects under it"

**Decision: Merge plans into missions.** The separate Plan entity was eliminated. Missions gained `items`, `components`, `connections` fields directly. Status flow became: `planning` -> `planned` -> `active` -> `complete/failed`.

- Deleted `jb_plans.py` and `test_plans.py` entirely
- Commands changed: `/plan generate` -> `/mission generate`, `/plan approve` -> `/mission approve`
- API endpoints: removed 4 plan endpoints, added 3 mission equivalents (net -1, from 38 to 37 routes)
- Default missions from company auto-creation set to `active` status (not `planning`, which was blocking users)

---

## 2. Discord Channel Gating with `company-` Prefix

The user wanted to protect existing Discord channels from JBCP processing while developing:

> "i dont want to lose all the context i have in my old discord channels, but since they have a bunch of content and were created before we deployed JBCP, what do you think about putting in a temporary rule in where only channels that are prefixed with company- will go through the entire JBCP system and all other channels will be ignored?"

**Decision: Single-point gate in the plugin.** A `shouldProcessChannel()` guard function checks for the `company-` prefix. Placed in one location (`ensureCompanyForChannel`). All 5 existing Discord companies were unmapped (data preserved, just no Discord link). Easy to remove later: delete constant + helper + one guard line.

The user confirmed this would NOT impact the frontend:

> "how does that impact the front end?"

Answer: Zero impact. Discord path (plugin) and frontend path (API) are completely separate pipelines.

---

## 3. Multi-Claude Coordination System

The user wanted to connect backend Claude, frontend Claude, and potentially a monitor Claude:

> "lets discuss how we can connect you to the claude code building the front end as efficiently as possible. i also would like to introduce a 3rd claude code that monitors everything thats going on and is able to send you or the front end claude code messages. we should have a central place to have a shared memory that can be referenced when needed, and all of our PRDs in a single place / able to be updated by any claude code. everything any claude code does should be written into a file dedicated to them but readable by all."

The user corrected over-engineering:

> "i think you are conflating the logic of JBCP with the much more simple thing i'm trying to do which is get you and this other claude to work together to finish the backend and frontend of JBCP"

**Decision: Simple file-based coordination in `claude_plan/`.** No monitor Claude for now. Structure:
```
claude_plan/
  MESSAGES.md           -- Messages between Claudes (replaced INTEGRATION_LOG.md)
  prds/                 -- Shared specs
  status/backend.md     -- Backend Claude status
  status/frontend.md    -- Frontend Claude status
  status/SHARED_CONTEXT.md
  locks/                -- File locking for concurrent edits
```

Important rule established: **Messages stay in Unread until the receiving Claude has IMPLEMENTED/ADDRESSED them, not just acknowledged them.** The user caught premature archiving:

> "why are both you and the front end archiving things that havent been addressed?"

---

## 4. Pivot from Native macOS App to Web UI

This was a major product direction decision. The user recognized the native app approach was failing:

> "this back and forth trying to build the backend and figure out the object structure and the user flow and everything while having another agent work on a native macos app isnt working. what do you think about us building a very simple (doesnt have to be pretty) lightweight web version of the product so we can iterate very fast/ ensure all the api endpoints and backend is working, focus getting the openclaw->jbcp->web front end working rock solid and then once we have that pinned down we can write a full spec for the native app developer"

**Decision: Build a web dashboard first, nail the API contracts, then spec the native app.**

> "it needs a little more than a single file i think if we want to have it be with real live data hitting all of our backend apis. it can be ugly but its gotta be fully functional with real data"

The web UI was built in `webui/` -- vanilla JS, no framework, no build step. Served by FastAPI at `http://localhost:8718/`. Pages: Workspaces, Workspace Detail (missions/tasks/components/graph/chat), Activity feed, Agents, Debug panel.

---

## 5. Real-Time Agent Status & Activity Signals

The user wanted live visibility into what agents are doing:

> "can we determine that its 'Claude Code' thinking vs 'long bash script' thinking vs 'web browser automation' thinking?"

A detailed mapping was designed:

| Signal | Source | Display |
|--------|--------|---------|
| `llm_input` | -- | "Santiago is thinking on claude-opus-4-6..." |
| `tool_start` + `exec` | bash | "Running pytest" / "Running npm build" |
| `tool_start` + `write` | claude-code | "Writing email_parser.py" |
| `tool_start` + `edit` | claude-code | "Editing config.json" |
| `tool_start` + `web_search` | web | "Searching: gmail api oauth" |
| `tool_start` + `browser` | browser | "Browsing: https://..." |
| `llm_output` | -- | clears indicator |

Plugin hooks capture: `llm_input` (model, provider, prompt size), `llm_output` (model, token usage, text preview), enhanced `tool_start` (source label, human-readable description), enhanced `tool_end` (result preview, char count).

---

## 6. Signal Delivery: File Tailing vs HTTP Push

The user identified latency in the file-tailing approach:

> "instead of tailing files could we write an openclaw plugin that connected to literally every available openclaw hook and then as soon as one fired streamed it out to our own messaging bus like redis? would that speed things up or are the file writes happening at about the same time the internal openclaw hook fires?"

**Decision: HTTP push in addition to file writes.** Plugin POSTs signals to `POST /api/signals/push` (fire-and-forget, non-blocking). API pushes to in-memory event bus instantly. Latency dropped from 0-500ms (file polling) to <50ms (localhost HTTP). File write preserved as archive/fallback.

The user confirmed this worked:

> "this works well!"

---

## 7. Chat UX: Streaming & Status Indicators

Key UX requirement: the user does NOT want dead silence while waiting for a response.

> "the issue is that claude code can go away for 5 minutes at a time"

> "i send a message and just wait with no feedback until the response streams in"

> "no - we had an entire mapping of what the agent was going to be doing designed above. we need to implement that and make it work."

The user wants the REAL signal-based status (what the agent is actually doing), not generic rotating messages. When tool calls happen during chat, the status should update in real-time: "Santiago is searching: BTC price" -> "Santiago is writing: report.md" -> "Santiago is running tests" etc.

Status should persist even while content is streaming -- shown as a status bar alongside the streaming response, not replaced by it.

---

## 8. Discord Command UX

> "also the discord commands are hard to use. i want to just be able to type /mission new and then have it ask me the mission name. discord pops up an input box. i want to just type /mission and have it suggest new or whatever else is the second command and then have it ask me what it needs to know."

**Decision: Not implementing Discord native slash commands (too complex). Instead:**
- Frontend will get its own command palette UI
- Discord keeps text-based commands but with better error handling
- Empty `/mission new` now responds with a friendly prompt asking for the goal
- `/mission` with no subcommand shows a helpful menu

---

## 9. Debug/Observability Features

The user wants deep visibility into the system:

> "i want a debug mode in the web ui where when on somewhere below the activity panel i can see the entire prompt sent into the chat engine. it should be a tree structure where the context type (primary->company) etc."

**Built:** `GET /api/workspaces/{id}/prompt-debug` returns the full prompt injection tree: each section with char counts, previews, planning mode state, blocked tools. Frontend spec written for the debug prompt inspector panel.

**Built:** `GET /api/commands` returns all available commands, subcommands, descriptions, and workflow steps. Designed for frontend command palette autocomplete.

---

## 10. Living Documentation

> "how can we update claude.md to create two document files that are always auto-updated. one should be an update by update real time log of everything we do that is updated by a spawned sub agent, the other should be a complete doc on the whole system that is always kept up to date"

**Decision: CLAUDE.md workflow instructions (not hooks).**
- `docs/ACTIVITY_LOG.md` -- append-only timestamped log after each significant action
- `docs/SYSTEM_SPEC.md` -- complete system spec, regenerated by background agent after major architecture changes

---

## 11. End-of-Session State

By end of session:
- **358 tests passing** (started at 373, fluctuated as tests were added/removed/rewritten)
- **44 API routes** (started at 36)
- **Web UI** fully built in `webui/` with 5 pages, all hitting real API endpoints
- **Signal push system** working with <50ms latency
- **Chat bubbles** working with real-time typing indicators (though signal-to-UI mapping still had bugs being debugged at session end)
- **Plan entity deleted** -- missions are the single organizing concept
- **Plugin fixes**: token parsing, channel resolver, planning mode tool blocking (including `subagents`), `jbdebug` command rename

### Unresolved at Session End
- Chat typing indicator was showing generic messages instead of real signal-based status (the handler was wired up and signals were flowing, but a `cb is not a function` error in the event listener was breaking the chain)
- The indicator disappeared when content started streaming (needed to coexist as a status bar)
- Long-running agent tasks showed no progress between tool calls (5-minute LLM thinking gaps)
- Puppeteer MCP server discussed but not set up for automated browser testing

---

## Key User Preferences (Behavioral)

> "yes and stop asking" -- Execute tasks without asking for confirmation.

> "run them in a background agent so we can keep chatting" -- Delegate work to background agents, keep the main conversation responsive.

> "it can be ugly but its gotta be fully functional with real data" -- Function over form. Real data, real APIs, working end-to-end.

> "no - we had an entire mapping of what the agent was doing designed above. we need to implement that and make it work." -- When a design is agreed on, implement it fully. Don't fall back to shortcuts.
