# Next Session Pickup Guide

Last updated: 2026-03-31

## CRITICAL: Read the PRD First

The product is called **Salt Desktop** -- a CEO's AI command center. "Notion meets N8N." The user describes what they want, AI plans and builds it, and the user watches the swarm work in real time.

**PRD location:**
- FROZEN: `~/Projects/santiago-salt-desktop/claude_plan/prds/APP_UX_PRD_FINAL_v0.1.md`
- Working draft: `~/Projects/santiago-salt-desktop/claude_plan/prds/APP_UX_PRD.md`

Read the frozen PRD before doing anything. It defines:
- 7 UX experiences (chat, graph interaction, "Build It", error states, navigation, creating things, "Go Live")
- 4 systems (real-time streaming, context injection, agent autonomy, multi-mission routing)
- Mission→Agent lifecycle (missions are the build process, agents are the deployed result)
- Component summary chain (invisible Layer 2 for status reporting through the graph)
- "The Swarm" (anonymous workers by role: Coder/Researcher/Analyst/Writer building in parallel)
- Living dashboard replaces portfolio kanban

## Current State

### Web UI v2 Rebuild
The web UI v2 (`webui-v2/`) is being rebuilt against the PRD. It is served by the JBCP API server at `http://localhost:8718/v2`.

There were 7 known bugs from the previous session (graph labels, mission scoping, build progress, activity panel, create mission 404, architecture preview duplication, chat messages). Check the current state of the code and browser to see what still needs work.

### API Gaps
The PRD gap analysis found the API is ~80% covered with 7 gaps to build:

1. **Gap 1: Component summary chain** -- summaries flow through graph connections for status reporting
2. **Gap 2: "Go Live" promotion** -- mission complete → service deployment with one click
3. **Gap 3: Real-time graph updates** -- SSE events that update component nodes as they're being built
4. **Gap 4: Agent roster** -- expose "The Swarm" workers with roles, not just raw agent state
5. **Gap 5: Mission chat history** -- scoped chat per mission (not just workspace-level)
6. **Gap 7: Component library** -- "trophy case" of reusable built components across workspaces

(Gap 6 -- feedback loop -- was eliminated during PRD discussion)

### Mock Mode
```bash
curl -s -X POST http://localhost:8718/api/mock/enable
```
Mock data in `runtime/jb_mock_data.py`. 2 workspaces, 6 missions, 12 tasks, 15 components, 2 services, 2 agents, 38 signals.

### Reference Screenshots
Saved at `docs/reference-screenshots/` -- use these for visual reference when building UI.

## Running the System

```bash
cd ~/.openclaw/workspace && source .venv/bin/activate

# API server
python -m runtime.jb_api

# Enable mock mode
curl -s -X POST http://localhost:8718/api/mock/enable

# Tests
python -m pytest tests/ -q

# Browser tools
# MCP Puppeteer config is at .mcp.json in workspace root (NOT ~/.claude/.mcp.json)
# Restart Claude Code after changing .mcp.json
```

## Product Vision

Salt Desktop is the CEO's AI command center. The user is the CEO of their own AI company. They describe what they want built, Santiago (the AI) plans it, dispatches workers ("the swarm"), and the user watches it get built in real time through a living graph.

Key metaphors:
- **Missions** = the build process (planning → building → complete)
- **Agents/Services** = the deployed result (what missions produce)
- **Component Graph** = the executable architecture (like N8N but AI-generated)
- **The Swarm** = anonymous workers by role, building in parallel
- **Living Dashboard** = replaces static portfolio kanban with real-time status

## Coordination

Frontend Claude works on the Swift macOS app at `~/Projects/santiago-salt-desktop/`.
- Check messages: `~/Projects/santiago-salt-desktop/claude_plan/MESSAGES.md`
- Check frontend status: `~/Projects/santiago-salt-desktop/claude_plan/status/frontend.md`
- Update backend status: `~/Projects/santiago-salt-desktop/claude_plan/status/backend.md`

## User Preferences

- **Don't ask, just do.** Execute without asking for confirmation.
- **Delegate ALL coding to subagents.** Keep main conversation responsive.
- **The user is visual.** Show, don't describe. Use Puppeteer to verify UI changes.
- **Update docs after milestones.**
